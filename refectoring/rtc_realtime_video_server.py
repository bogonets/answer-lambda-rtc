# -*- coding: utf-8 -*-

import os
import sys
import ssl
import json
import string
import random
import asyncio

import multiprocessing as mp
from queue import Empty

import numpy as np

from aiortc import RTCPeerConnection, RTCSessionDescription, VideoStreamTrack
from aiohttp import web
import aiohttp_cors
import av


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


def create_video_frame(image, frame_format):
    return av.video.VideoFrame.from_ndarray(image, format=frame_format)


class VideoImageTrack(VideoStreamTrack):
    """
    """

    def __init__(self, queue: mp.Queue, frame_format='bgr24'):
        super().__init__()  # don't forget this!
        self.queue = queue
        self.frame_format = frame_format
        self.last_frame = create_video_frame(EMPTY_IMAGE, frame_format)

    async def recv(self):
        pts, time_base = await self.next_timestamp()

        try:
            frame = create_video_frame(self.queue.get_nowait(), self.frame_format)
            frame.pts = pts
            frame.time_base = time_base
            self.last_frame = frame
        except:
            frame = self.last_frame

        print_out(f'rtc.realtime_video.VideoImageTrack.recv() frame: {frame}')
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
        self.rtc_queue = rtc_queue
        self.rtc_password = rtc_password

        self.host = host
        self.port = port
        self.verbose = verbose

        if cert_file and key_file:
            self.ssl_context = ssl.SSLContext()
            self.ssl_context.load_cert_chain(cert_file, key_file)
        else:
            self.ssl_context = None

        self.peer_connections = set()

        self.app = web.Application()
        self.app.on_shutdown.append(self.on_shutdown)
        self.app.on_cleanup.append(self.on_cleanup)
        self.app.router.add_get(INDEX_HTML_PATH, self.on_index_html)
        self.app.router.add_get(CLIENT_JS_PATH, self.on_client_js)
        self.app.router.add_post(OFFER_PATH, self.on_offer)
        self.app.router.add_post(EXIT_SIGNAL_PATH, self.on_exit_signal)

        self.empty_response = web.Response(content_type='text/html', text='')
        self.index_html_response = web.Response(content_type='text/html', text=INDEX_HTML_CONTENT)
        self.client_js_response = web.Response(content_type='application/javascript', text=CLIENT_JS_CONTENT)

        self.cors = aiohttp_cors.setup(self.app, defaults={
            '*': aiohttp_cors.ResourceOptions(
                allow_credentials=True,
                expose_headers='*',
                allow_headers='*',
            )
        })
        for route in list(self.app.router.routes()):
            self.cors.add(route)

        print_out(f'rtc.realtime_video.RealTimeVideoServer.__init__(host={host},port={port},verbose={verbose})')

    async def on_shutdown(self, app):
        # close peer connections
        coros = [pc.close() for pc in self.peer_connections]
        await asyncio.gather(*coros)
        self.peer_connections.clear()

    async def on_cleanup(self, app):
        pass

    async def on_exit_process_background(self):
        await self.app.shutdown()
        await self.app.cleanup()
        raise web.GracefulExit()

    async def on_exit_signal(self, request):
        print_out(f'on_exit_signal(request={request})')
        data = await request.post()
        password = data[PASSWORD_PARAM_KEY]

        if self.rtc_password == password:
            asyncio.create_task(self.on_exit_process_background())

        return self.empty_response

    async def on_index_html(self, request):
        print_out(f'on_index_html(request={request})')
        return self.index_html_response

    async def on_client_js(self, request):
        print_out(f'on_client_js(request={request})')
        return self.client_js_response

    async def on_offer(self, request):
        params = await request.json()
        offer = RTCSessionDescription(sdp=params['sdp'], type=params['type'])

        pc = RTCPeerConnection()
        self.peer_connections.add(pc)

        @pc.on('iceconnectionstatechange')
        async def on_iceconnectionstatechange():
            print_out(f'ICE connection state is {pc.iceConnectionState}')
            if pc.iceConnectionState == 'failed':
                await pc.close()
                self.peer_connections.discard(pc)
            if pc.iceConnectionState == 'closed':
                await pc.close()
                self.peer_connections.discard(pc)

        await pc.setRemoteDescription(offer)

        for t in pc.getTransceivers():
            if t.kind == 'video':
                pc.addTrack(VideoImageTrack(self.rtc_queue))
            elif t.kind == 'audio':
                pass

        answer = await pc.createAnswer()
        await pc.setLocalDescription(answer)

        return web.Response(
            content_type='application/json',
            text=json.dumps(
                {
                    'sdp': pc.localDescription.sdp,
                    'type': pc.localDescription.type
                }
            ),
        )

    def run(self):
        web.run_app(self.app,
                    host=self.host,
                    port=self.port,
                    print=print_null,
                    ssl_context=self.ssl_context,
                    handle_signals=False)


def on_runner(rtc_queue, rtc_process, host, port):
    print_out('rtc.realtime_video.on_runner BEGIN.')
    RealTimeVideoServer(rtc_queue, rtc_process, host, port).run()
    print_out('rtc.realtime_video.on_runner END.')


if __name__ == '__main__':
    pass
