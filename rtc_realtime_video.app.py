# -*- coding: utf-8 -*-

import asyncio
import json
import logging
import os
import sys
import platform
import ssl
import string
import random

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

import rtc_realtime_video_server


ROOT_DIR = os.path.dirname(__file__)
INDEX_HTML_CONTENT = open(os.path.join(ROOT_DIR, 'index.html'), 'r').read()
CLIENT_JS_CONTENT = open(os.path.join(ROOT_DIR, 'client.js'), 'r').read()
INDEX_HTML_PATH = '/'
CLIENT_JS_PATH = '/client.js'
OFFER_PATH = '/offer'
EXIT_SIGNAL_PATH = '/__exit_signal__'
PASSWORD_PARAM_KEY = '@password'
PASSWORD_LENGTH = 256
DEFAULT_MAX_QUEUE_SIZE = 4
DEFAULT_EXIT_TIMEOUT_SECONDS = 4.0

host = '0.0.0.0'
port = 8888
max_queue_size = DEFAULT_MAX_QUEUE_SIZE
exit_timeout_seconds = DEFAULT_EXIT_TIMEOUT_SECONDS

rtc_process: Process
producer_queue: Queue
producer_password = ''


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
    elif key == 'exit_timeout_seconds':
        global exit_timeout_seconds
        exit_timeout_seconds = float(val)


def on_get(key):
    if key == 'host':
        return host
    elif key == 'port':
        return port
    elif key == 'max_queue_size':
        return max_queue_size
    elif key == 'exit_timeout_seconds':
        return exit_timeout_seconds


def on_init():
    global producer_password
    producer_password = ''.join(random.choices(string.ascii_letters + string.digits, k=PASSWORD_LENGTH))

    global producer_queue
    global max_queue_size
    producer_queue = Queue(max_queue_size)

    global rtc_process
    rtc_process = Process(target=rtc_realtime_video_server.start_app, args=(host, port, producer_queue, producer_password,))
    rtc_process.start()

    sys.stderr.write(f'RTC process PID is {rtc_process.pid}.')
    sys.stderr.flush()

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
    global producer_password
    params = urllib.parse.urlencode({PASSWORD_PARAM_KEY: producer_password})
    headers = {'Content-type': 'application/x-www-form-urlencoded'}
    conn = http.client.HTTPConnection(f'{host}:{port}')
    conn.request('POST', EXIT_SIGNAL_PATH, params, headers)

    global exit_timeout_seconds
    timeout = exit_timeout_seconds if exit_timeout_seconds > 0.0 else DEFAULT_EXIT_TIMEOUT_SECONDS

    # logging.info('Join({}s) the RTC process.', timeout)
    sys.stderr.write(f'Join({timeout}s) the RTC process.')
    sys.stderr.flush()

    rtc_process.join(timeout=timeout)

    if rtc_process.is_alive():
        # logging.warning('Terminate the RTC process.')
        sys.stderr.write('Terminate the RTC process.')
        sys.stderr.flush()

        rtc_process.kill()

    # A negative value -N indicates that the child was terminated by signal N.
    # logging.info('The exit code of RTC process is {}.', rtc_process.exitcode)
    sys.stderr.write(f'The exit code of RTC process is {rtc_process.exitcode}.')
    sys.stderr.flush()

    rtc_process.close()

    sys.stderr.write('rtc_process closed.')
    sys.stderr.flush()

    global producer_queue
    producer_queue.close()
    producer_queue.join_thread()

    return True


if __name__ == '__main__':
    pass
