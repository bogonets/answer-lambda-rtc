# -*- coding: utf-8 -*-

import os
import sys
import string
import random
import numpy as np

import importlib
from queue import Empty

from aiortc import RTCPeerConnection, RTCSessionDescription, VideoStreamTrack


ROOT_DIR = os.path.dirname(__file__)
INDEX_HTML_CONTENT = open(os.path.join(ROOT_DIR, 'index.html'), 'r').read()
CLIENT_JS_CONTENT = open(os.path.join(ROOT_DIR, 'client.js'), 'r').read()
INDEX_HTML_PATH = '/'
CLIENT_JS_PATH = '/client.js'
OFFER_PATH = '/offer'
EXIT_SIGNAL_PATH = '/__exit_signal__'
PASSWORD_PARAM_KEY = '@password'
PASSWORD_LENGTH = 256
EMPTY_IMAGE = np.zeros((300, 300, 3), dtype=np.uint8)
DEFAULT_FRAME_FORMAT = 'bgr24'


def print_out(message):
    sys.stdout.write(message)
    sys.stdout.flush()


def print_error(message):
    sys.stderr.write(message)
    sys.stderr.flush()


def print_null(*args):
    pass


def generate_exit_password():
    return ''.join(random.choices(string.ascii_letters + string.digits, k=PASSWORD_LENGTH))


class Singleton:
    __instance = None

    @classmethod
    def __get_instance(cls):
        return cls.__instance

    @classmethod
    def instance(cls, *args, **kwargs):
        cls.__instance = cls(*args, **kwargs)
        cls.instance = cls.__get_instance
        return cls.__instance


class FrameQueue(Singleton):

    def __init__(self, queue, frame_format=DEFAULT_FRAME_FORMAT):
        self.av = importlib.import_module('av')
        self.queue = queue
        self.frame_format = frame_format
        self.last_image = EMPTY_IMAGE
        self.last_frame = self.av.VideoFrame.from_ndarray(EMPTY_IMAGE, format=frame_format)

    def update(self, image):
        self.last_image = image
        self.last_frame = self.av.VideoFrame.from_ndarray(self.last_image, format=self.frame_format)

    def pop(self):
        try:
            self.update(self.queue.get_nowait())
        except:
            pass
        return self.last_frame


class VideoImageTrack(VideoStreamTrack):

    def __init__(self, queue, frame_format=DEFAULT_FRAME_FORMAT):
        super().__init__()  # don't forget this!
        self.queue = FrameQueue.instance(queue, frame_format)

    async def recv(self):
        pts, time_base = await self.next_timestamp()
        frame = self.queue.pop()
        frame.pts = pts
        frame.time_base = time_base
        return frame


class RealTimeVideoServer:
    """
    """

    def __init__(self,
                 rtc_queue,
                 rtc_password,
                 host: str,
                 port: int,
                 verbose=False,
                 cert_file=None,
                 key_file=None):
        pass


from aiohttp import web
import aiohttp_cors
from aiortc import RTCPeerConnection, RTCSessionDescription
from multiprocessing import Queue
import asyncio
import logging
import json
import ssl

app: web.Application
cors: aiohttp_cors.CorsConfig
consumer_queue: Queue
consumer_password = ''
peer_connections = set()

async def on_exit_process_background():
    global app
    await app.shutdown()
    await app.cleanup()
    raise web.GracefulExit()


async def on_exit_signal(request):
    data = await request.post()
    password = data[PASSWORD_PARAM_KEY]
    global consumer_password
    if consumer_password == password:
        asyncio.create_task(on_exit_process_background())
    return web.Response(content_type='text/html', text='')


async def on_index_html(request):
    return web.Response(content_type='text/html', text=INDEX_HTML_CONTENT)


async def on_client_js(request):
    return web.Response(content_type='application/javascript', text=CLIENT_JS_CONTENT)


async def on_offer(request):
    params = await request.json()
    offer = RTCSessionDescription(sdp=params['sdp'], type=params['type'])

    pc = RTCPeerConnection()
    peer_connections.add(pc)

    @pc.on('iceconnectionstatechange')
    async def on_iceconnectionstatechange():
        logging.info('ICE connection state is {}', pc.iceConnectionState)
        if pc.iceConnectionState == 'failed':
            await pc.close()
            peer_connections.discard(pc)

    # open media source
    # if args.play_from:
    #     player = MediaPlayer(args.play_from)
    # else:
    #     options = {'framerate': '30', 'video_size': '640x480'}
    #     if platform.system() == 'Darwin':
    #         player = MediaPlayer('default:none', format='avfoundation', options=options)
    #     else:
    #         player = MediaPlayer('/dev/video0', format='v4l2', options=options)

    await pc.setRemoteDescription(offer)
    for t in pc.getTransceivers():
        if t.kind == 'video':
            global consumer_queue
            pc.addTrack(VideoImageTrack(consumer_queue))
        elif t.kind == 'audio':
            pass

    answer = await pc.createAnswer()
    await pc.setLocalDescription(answer)

    return web.Response(
        content_type='application/json',
        text=json.dumps(
            {'sdp': pc.localDescription.sdp, 'type': pc.localDescription.type}
        ),
    )


async def on_shutdown(app):
    # close peer connections
    coros = [pc.close() for pc in peer_connections]
    await asyncio.gather(*coros)
    peer_connections.clear()


async def on_cleanup(app):
    pass


def start_app(http_host, http_port, ipc_queue, password, verbose=False, cert_file=None, key_file=None):
    if verbose:
        logging.basicConfig(level=logging.DEBUG)

    if cert_file and key_file:
        ssl_context = ssl.SSLContext()
        ssl_context.load_cert_chain(cert_file, key_file)
    else:
        ssl_context = None

    global consumer_queue
    consumer_queue = ipc_queue

    global consumer_password
    consumer_password = password

    logging.info('start_app(host={},port={},password={},verbose={})',
                 http_host, http_port, password, verbose)

    global app
    app = web.Application()
    app.on_shutdown.append(on_shutdown)
    app.on_cleanup.append(on_cleanup)
    app.router.add_get(INDEX_HTML_PATH, on_index_html)
    app.router.add_get(CLIENT_JS_PATH, on_client_js)
    app.router.add_post(OFFER_PATH, on_offer)
    app.router.add_post(EXIT_SIGNAL_PATH, on_exit_signal)

    global cors
    cors = aiohttp_cors.setup(app, defaults={
        '*': aiohttp_cors.ResourceOptions(
            allow_credentials=True,
            expose_headers='*',
            allow_headers='*',
        )
    })
    for route in list(app.router.routes()):
        cors.add(route)

    web.run_app(app,
                host=http_host,
                port=http_port,
                ssl_context=ssl_context,
                handle_signals=False)

if __name__ == '__main__':
    pass
