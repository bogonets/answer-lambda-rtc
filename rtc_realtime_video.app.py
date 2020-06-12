# -*- coding: utf-8 -*-

import asyncio
import json
import logging
import os
import platform
import ssl

import http.client
import urllib.parse

from multiprocessing import Process, Queue
from queue import Full, Empty

import numpy as np

from av import VideoFrame
from aiohttp import web
import aiohttp_cors
from aiortc import RTCPeerConnection, RTCSessionDescription, VideoStreamTrack
from aiortc.contrib.media import MediaPlayer


ROOT_DIR = os.path.dirname(__file__)
INDEX_HTML_CONTENT = open(os.path.join(ROOT_DIR, 'index.html'), 'r').read()
CLIENT_JS_CONTENT = open(os.path.join(ROOT_DIR, 'client.js'), 'r').read()

host = '0.0.0.0'
port = 8888
max_queue_size = 4

app: web.Application
cors: aiohttp_cors.CorsConfig
rtc_process: Process
producer_queue: Queue
consumer_queue: Queue
producer_password = '0000'
consumer_password = '0000'
peer_connections = set()
empty_img = np.zeros((300, 300, 3), dtype=np.uint8)
last_frame = VideoFrame.from_ndarray(empty_img, format="bgr24")


class VideoImageTrack(VideoStreamTrack):
    """
    A video stream track that returns a rotating image.
    """

    def __init__(self, queue):
        super().__init__()  # don't forget this!
        self.queue = queue

    async def recv(self):
        pts, time_base = await self.next_timestamp()

        try:
            img = self.queue.get_nowait()
        except Empty:
            img = None

        global last_frame
        if img is not None:
            try:
                frame = VideoFrame.from_ndarray(img, format="bgr24")
            except:
                frame = last_frame
        else:
            frame = last_frame

        frame.pts = pts
        frame.time_base = time_base
        last_frame = frame

        return frame


async def on_exit_process_background():
    # global app
    # await app.shutdown()
    # await app.cleanup()
    raise web.GracefulExit()


async def on_exit_signal(request):
    data = await request.post()
    pwd = data['@pwd']
    asyncio.create_task(on_exit_process_background())
    return web.Response(content_type="text/html", text='')


async def on_index_html(request):
    return web.Response(content_type="text/html", text=INDEX_HTML_CONTENT)


async def on_client_js(request):
    return web.Response(content_type="application/javascript", text=CLIENT_JS_CONTENT)


async def on_offer(request):
    params = await request.json()
    offer = RTCSessionDescription(sdp=params["sdp"], type=params["type"])

    pc = RTCPeerConnection()
    peer_connections.add(pc)

    @pc.on("iceconnectionstatechange")
    async def on_iceconnectionstatechange():
        print("ICE connection state is %s" % pc.iceConnectionState)
        if pc.iceConnectionState == "failed":
            await pc.close()
            peer_connections.discard(pc)

    # open media source
    # if args.play_from:
    #     player = MediaPlayer(args.play_from)
    # else:
    #     options = {"framerate": "30", "video_size": "640x480"}
    #     if platform.system() == "Darwin":
    #         player = MediaPlayer("default:none", format="avfoundation", options=options)
    #     else:
    #         player = MediaPlayer("/dev/video0", format="v4l2", options=options)

    await pc.setRemoteDescription(offer)
    for t in pc.getTransceivers():
        if t.kind == "video":
            global consumer_queue
            pc.addTrack(VideoImageTrack(consumer_queue))
        elif t.kind == "audio":
            pass

    answer = await pc.createAnswer()
    await pc.setLocalDescription(answer)

    return web.Response(
        content_type="application/json",
        text=json.dumps(
            {"sdp": pc.localDescription.sdp, "type": pc.localDescription.type}
        ),
    )


async def on_shutdown(app):
    # close peer connections
    coros = [pc.close() for pc in peer_connections]
    await asyncio.gather(*coros)
    peer_connections.clear()


async def on_cleanup(app):
    pass


def start_app(http_host, http_port, ipc_queue, verbose=False, cert_file=None, key_file=None):
    if verbose:
        logging.basicConfig(level=logging.DEBUG)

    if cert_file and key_file:
        ssl_context = ssl.SSLContext()
        ssl_context.load_cert_chain(cert_file, key_file)
    else:
        ssl_context = None

    global consumer_queue
    consumer_queue = ipc_queue

    global app
    app = web.Application()
    app.on_shutdown.append(on_shutdown)
    app.on_cleanup.append(on_cleanup)
    app.router.add_get("/", on_index_html)
    app.router.add_get("/client.js", on_client_js)
    app.router.add_post("/offer", on_offer)
    app.router.add_post("/__exit_signal__", on_exit_signal)

    global cors
    cors = aiohttp_cors.setup(app, defaults={
        "*": aiohttp_cors.ResourceOptions(
            allow_credentials=True,
            expose_headers="*",
            allow_headers="*",
        )
    })
    for route in list(app.router.routes()):
        cors.add(route)

    web.run_app(app, host=http_host, port=http_port, ssl_context=ssl_context)


def on_set(key, val):
    if key == 'host':
        global host
        host = val
    elif key == 'port':
        global port
        port = int(val)
    elif key == 'max_queue_size':
        global max_queue_size
        max_queue_size = int(val)


def on_get(key):
    if key == 'host':
        return host
    elif key == 'port':
        return port
    elif key == 'max_queue_size':
        return max_queue_size


def on_init():
    global max_queue_size
    global producer_queue
    global rtc_process
    producer_queue = Queue(max_queue_size)
    rtc_process = Process(target=start_app, args=(host, port, producer_queue,))
    rtc_process.start()
    return rtc_process.is_alive()


def on_valid():
    return rtc_process.is_alive()


def on_run(image):
    global producer_queue
    try:
        producer_queue.put_nowait(image)
    except Full:
        producer_queue.get_nowait()
        try:
            producer_queue.put_nowait(image)
        except Full:
            pass


def on_destroy():
    params = urllib.parse.urlencode({'@pwd': '0000'})
    headers = {"Content-type": "application/x-www-form-urlencoded"}
    conn = http.client.HTTPConnection(f'{host}:{port}')
    conn.request("POST", "/__exit_signal__", params, headers)

    rtc_process.join()
    return True


if __name__ == '__main__':
    pass
