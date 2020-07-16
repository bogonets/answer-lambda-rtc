# -*- coding: utf-8 -*-

import sys
import time

from multiprocessing import Process, Queue
from queue import Full, Empty

import rtc_realtime_video_server as vs


LOGGING_PREFIX = '[rtc.realtime_video] '
DEFAULT_MAX_QUEUE_SIZE = 4
DEFAULT_EXIT_TIMEOUT_SECONDS = 4.0


def print_out(message):
    sys.stdout.write(LOGGING_PREFIX + message)
    sys.stdout.flush()


def print_error(message):
    sys.stderr.write(LOGGING_PREFIX + message)
    sys.stderr.flush()


class RealTimeVideo:
    """
    """

    def __init__(self):
        self.host = '0.0.0.0'
        self.port = 8888
        self.ices = ['stun:stun.l.google.com:19302']
        self.max_queue_size = DEFAULT_MAX_QUEUE_SIZE
        self.exit_timeout_seconds = DEFAULT_EXIT_TIMEOUT_SECONDS
        self.fps = vs.DEFAULT_VIDEO_FPS
        self.frame_format = vs.DEFAULT_FRAME_FORMAT
        self.verbose = False

        self.exit_password = vs.generate_exit_password()
        self.process: Process = None
        self.queue: Queue = None

    def on_set(self, key, val):
        if key == 'host':
            self.host = val
        elif key == 'port':
            self.port = int(val)
        elif key == 'ices':
            self.ices = list(map(lambda x: x, str(val).split(',')))
        elif key == 'max_queue_size':
            self.max_queue_size = int(val)
        elif key == 'exit_timeout_seconds':
            self.exit_timeout_seconds = float(val) if float(val) >= 0.0 else 0.0
        elif key == 'fps':
            self.fps = int(val)
        elif key == 'frame_format':
            self.frame_format = val
        elif key == 'verbose':
            self.verbose = bool(val)

    def on_get(self, key):
        if key == 'host':
            return self.host
        elif key == 'port':
            return self.port
        elif key == 'ices':
            return ','.join(list(map(lambda x: str(x), self.ices)))
        elif key == 'max_queue_size':
            return self.max_queue_size
        elif key == 'exit_timeout_seconds':
            return self.exit_timeout_seconds
        elif key == 'fps':
            return self.fps
        elif key == 'frame_format':
            return self.frame_format
        elif key == 'verbose':
            return self.verbose

    def _put_nowait(self, data):
        try:
            self.queue.put_nowait(data)
            return True
        except Full:
            return False

    def _get_nowait(self):
        try:
            self.queue.get_nowait()
        except Empty:
            pass

    def push(self, data):
        if self._put_nowait(data):
            return True
        self._get_nowait()
        return self._put_nowait(data)

    def on_init(self):
        self.queue = Queue(self.max_queue_size)
        self.process = Process(target=vs.start_app,
                               args=(self.queue, self.exit_password, self.exit_timeout_seconds,
                                     self.ices, self.host, self.port,
                                     self.fps, self.frame_format,
                                     None, None, self.verbose))
        self.process.start()
        print_out(f'RealTimeVideo.on_init() Server process PID: {self.process.pid}')
        return self.process.is_alive()

    def on_valid(self):
        return self.process.is_alive()

    def on_run(self, image):
        self.push(image)

    def on_destroy(self):
        assert self.queue is not None
        assert self.process is not None

        timeout = self.exit_timeout_seconds
        print_out(f'RealTimeVideo.on_destroy(timeout={timeout}s)')

        if self.process.is_alive():
            request_begin = time.time()
            request_result = vs.request_exit(self.host, self.port, self.exit_password, timeout)
            request_end = time.time()

            timeout = timeout - (request_end - request_begin)
            timeout = timeout if timeout >= 0.0 else 0.0

            if not request_result:
                print_error(f'Exit request failure.')

        print_out(f'Join({timeout}s) the RTC process.')
        self.process.join(timeout=timeout)

        if self.process.is_alive():
            print_error('Send a KILL signal to the server process.')
            self.process.kill()

        # A negative value -N indicates that the child was terminated by signal N.
        print_out(f'The exit code of RTC process is {self.process.exitcode}.')

        self.queue.close()
        self.queue.cancel_join_thread()
        self.queue = None

        self.process.close()
        self.process = None

        print_out(f'RealTimeVideo.on_destroy() Done.')


MAIN_HANDLER = RealTimeVideo()


def on_set(key, val):
    MAIN_HANDLER.on_set(key, val)


def on_get(key):
    return MAIN_HANDLER.on_get(key)


def on_init():
    return MAIN_HANDLER.on_init()


def on_valid():
    return MAIN_HANDLER.on_valid()


def on_run(image):
    return MAIN_HANDLER.on_run(image)


def on_destroy():
    return MAIN_HANDLER.on_destroy()


if __name__ == '__main__':
    pass
