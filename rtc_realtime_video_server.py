# -*- coding: utf-8 -*-

import os
import sys
import string
import random
import ssl
import numpy as np

import importlib
from queue import Empty

from aiohttp import web
from aiortc import RTCPeerConnection, RTCSessionDescription, VideoStreamTrack
from pygments.lexer import inherit

ROOT_DIR = os.path.dirname(__file__)
INDEX_HTML_CONTENT = open(os.path.join(ROOT_DIR, 'index.html'), 'r').read()
CLIENT_JS_CONTENT = open(os.path.join(ROOT_DIR, 'client.js'), 'r').read()
INDEX_HTML_PATH = '/'
CLIENT_JS_PATH = '/client.js'
CONFIG_PATH = '/config'
OFFER_PATH = '/offer'
EXIT_SIGNAL_PATH = '/__exit_signal__'
PASSWORD_PARAM_KEY = '@password'
PASSWORD_LENGTH = 256
EMPTY_IMAGE = np.zeros((300, 300, 3), dtype=np.uint8)
DEFAULT_FRAME_FORMAT = 'bgr24'
LOGGING_PREFIX = '[rtc.realtime_video.server] '


def print_out(message):
    sys.stdout.write(LOGGING_PREFIX + message)
    sys.stdout.flush()


def print_error(message):
    sys.stderr.write(LOGGING_PREFIX + message)
    sys.stderr.flush()


def print_null(*args):
    pass


def generate_exit_password():
    return ''.join(random.choices(string.ascii_letters + string.digits, k=PASSWORD_LENGTH))


def is_stun(text: str):
    return text.find('turn:') == 0


def is_turn(text: str):
    return text.find('stun:') == 0


def ice_to_dict(ice: str):
    """
    ``turn:admin:1234@localhost:3478`` -> ``{ urls: ['turn:localhost:3478'], username: 'admin', credential: '1234'}``
    """

    at_index = ice.find('@')
    if at_index == -1:
        return {'urls': [ice]}

    if is_stun(ice):
        schema = 'stun:'
    elif is_turn(ice):
        schema = 'turn:'
    else:
        return None

    username, credential = ice[5:at_index].split(':')
    address = ice[at_index+1]
    return {'urls': [schema+address], 'username': username, 'credential': credential}


def get_rtc_configuration_dict(ices: list):
    result = {
        'sdpSemantics': 'unified-plan',
        'iceTransportPolicy': 'all',
        'iceCandidatePoolSize': 0
    }

    ice_servers = list(filter(lambda x: x, [ice_to_dict(i) for i in ices]))
    if ice_servers:
        result['iceServers'] = ice_servers
    else:
        result['iceServers'] = [
            {'urls': ['stun:stun.l.google.com:19302']}
        ]

    return result


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


import aiohttp_cors
from aiortc import RTCPeerConnection, RTCSessionDescription
from multiprocessing import Queue
import asyncio
import logging
import json


class RealTimeVideoServer:
    """
    """

    def __init__(self,
                 mp_queue,
                 exit_password: str,
                 ices: list,
                 host: str,
                 port: int,
                 cert_file=None,
                 key_file=None,
                 verbose=False):
        self.mp_queue = mp_queue
        self.exit_password = exit_password
        self.ices = ices
        self.host = host
        self.port = port
        self.cert_file = cert_file
        self.key_file = key_file
        self.verbose = verbose

        if self.verbose:
            logging.basicConfig(level=logging.DEBUG)

        if self.cert_file and self.key_file:
            self.ssl_context = ssl.SSLContext()
            self.ssl_context.load_cert_chain(self.cert_file, self.key_file)
        else:
            self.ssl_context = None

        self.rtc_config_json = json.dumps(get_rtc_configuration_dict(self.ices))

        self.app = web.Application()
        self.app.on_shutdown.append(self.on_shutdown)
        self.app.on_cleanup.append(self.on_cleanup)
        self.app.router.add_get(INDEX_HTML_PATH, self.on_index_html)
        self.app.router.add_get(CLIENT_JS_PATH, self.on_client_js)
        self.app.router.add_get(CONFIG_PATH, self.on_config)
        self.app.router.add_post(OFFER_PATH, self.on_offer)
        self.app.router.add_post(EXIT_SIGNAL_PATH, self.on_exit_signal)

        self.cors = aiohttp_cors.setup(self.app, defaults={
            '*': aiohttp_cors.ResourceOptions(
                allow_credentials=True,
                expose_headers='*',
                allow_headers='*',
            )
        })
        for route in list(self.app.router.routes()):
            self.cors.add(route)

        self.peer_connections = set()

        print_out(f'RealTimeVideoServer() OK.')

    async def on_exit_process_background(self):
        await self.app.shutdown()
        await self.app.cleanup()
        raise web.GracefulExit()

    async def on_exit_signal(self, request):
        print_out(f'RealTimeVideoServer.on_exit_signal(remote={request.remote})')
        data = await request.post()
        password = data[PASSWORD_PARAM_KEY]
        if self.exit_password == password:
            asyncio.create_task(self.on_exit_process_background())
            return web.Response()
        else:
            return web.Response(status=400)

    async def on_index_html(self, request):
        print_out(f'RealTimeVideoServer.on_index_html(remote={request.remote})')
        return web.Response(content_type='text/html', text=INDEX_HTML_CONTENT)

    async def on_client_js(self, request):
        print_out(f'RealTimeVideoServer.on_client_js(remote={request.remote})')
        return web.Response(content_type='application/javascript', text=CLIENT_JS_CONTENT)

    async def on_config(self, request):
        print_out(f'RealTimeVideoServer.on_config(remote={request.remote})')
        return web.Response(content_type='application/json', text=self.rtc_config_json)

    async def on_offer(self, request):
        print_out(f'RealTimeVideoServer.on_offer(remote={request.remote})')

        params = await request.json()
        offer = RTCSessionDescription(sdp=params['sdp'], type=params['type'])

        pc = RTCPeerConnection()
        self.peer_connections.add(pc)

        @pc.on('iceconnectionstatechange')
        async def on_ice_connection_state_change():
            print_out(f'on_ice_connection_state_change({pc.iceConnectionState})')
            if pc.iceConnectionState == 'failed':
                await pc.close()
                self.peer_connections.discard(pc)

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
                pc.addTrack(VideoImageTrack(self.mp_queue))
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

    async def on_shutdown(self, app):
        # close peer connections
        coros = [pc.close() for pc in self.peer_connections]
        await asyncio.gather(*coros)
        self.peer_connections.clear()

    async def on_cleanup(self, app):
        pass

    def run(self):
        web.run_app(self.app,
                    host=self.host,
                    port=self.port,
                    print=print_null,
                    ssl_context=self.ssl_context,
                    handle_signals=False)


def start_app(mp_queue,
              exit_password: str,
              ices: list,
              host: str,
              port: int,
              cert_file=None,
              key_file=None,
              verbose=False):
    print_out(f'start_app(host={host},port={port},cert={cert_file},key={key_file},verbose={verbose}) BEGIN')
    try:
        server = RealTimeVideoServer(mp_queue, exit_password, ices, host, port, cert_file, key_file, verbose)
        server.run()
    except web.GracefulExit:
        print_out(f'RealTimeVideoServer Graceful Exit')
    except Exception as e:
        print_error(f'RealTimeVideoServer Exception: {e}')
    finally:
        print_out(f'start_app() END')


if __name__ == '__main__':
    pass
