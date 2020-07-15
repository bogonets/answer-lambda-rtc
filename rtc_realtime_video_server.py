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


if __name__ == '__main__':
    pass
