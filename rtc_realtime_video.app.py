# -*- coding: utf-8 -*-

import sys
import time
import argparse
import psutil

from multiprocessing import Process, Queue
from queue import Full, Empty

import rtc_realtime_video_server as vs


LOGGING_PREFIX = '[rtc.realtime_video] '
LOGGING_SUFFIX = ''
DEFAULT_MAX_QUEUE_SIZE = 4
UNKNOWN_PID = 0


def print_out(message):
    sys.stdout.write(LOGGING_PREFIX + message + LOGGING_SUFFIX)
    sys.stdout.flush()


def print_error(message):
    sys.stderr.write(LOGGING_PREFIX + message + LOGGING_SUFFIX)
    sys.stderr.flush()


class CreateProcessError(Exception):
    pass


class RealTimeVideo:
    """
    """

    def __init__(self,
                 host=vs.DEFAULT_HOST,
                 port=vs.DEFAULT_PORT,
                 ices=vs.DEFAULT_ICES,
                 max_queue_size=DEFAULT_MAX_QUEUE_SIZE,
                 exit_timeout_seconds=vs.DEFAULT_EXIT_TIMEOUT_SECONDS,
                 fps=vs.DEFAULT_VIDEO_FPS,
                 frame_format=vs.DEFAULT_FRAME_FORMAT,
                 cert_file=None,
                 key_file=None,
                 verbose=False):
        self.host = host
        self.port = port
        self.ices = ices
        self.max_queue_size = max_queue_size
        self.exit_timeout_seconds = exit_timeout_seconds
        self.fps = fps
        self.frame_format = frame_format
        self.verbose = verbose
        self.cert_file = cert_file
        self.key_file = key_file

        self.exit_password = vs.generate_exit_password()

        self.process: Process = None
        self.queue: Queue = None
        self.pid = UNKNOWN_PID

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

    def _create_process_impl(self):
        assert self.queue is None
        assert self.process is None

        self.queue = Queue(self.max_queue_size)
        self.process = Process(target=vs.start_app,
                               args=(self.queue, self.exit_password, self.exit_timeout_seconds,
                                     self.ices, self.host, self.port,
                                     self.fps, self.frame_format,
                                     self.cert_file, self.key_file, self.verbose))
        self.process.start()
        if self.process.is_alive():
            self.pid = self.process.pid
            print_out(f'RealTimeVideo._create_process_impl() Server process PID: {self.pid}')
            return True
        else:
            print_error(f'RealTimeVideo._create_process_impl() Server process is not alive.')
            return False

    def _create_process(self):
        try:
            return self._create_process_impl()
        except Exception as e:
            print_error(f'RealTimeVideo._create_process() Exception: {e}')
            return False

    def _close_process_impl(self):
        if self.process is not None:
            timeout = self.exit_timeout_seconds
            if self.process.is_alive():
                request_begin = time.time()
                print_out(f'RealTimeVideo._close_process_impl() RequestExit(timeout={timeout}s)')
                request_result = vs.request_exit(self.host, self.port, self.exit_password, timeout)
                timeout = timeout - (time.time() - request_begin)
                timeout = timeout if timeout >= 0.0 else 0.0
                if not request_result:
                    print_error(f'RealTimeVideo._close_process_impl() Exit request failure.')

            print_out(f'RealTimeVideo._close_process_impl() Join(timeout={timeout}s) the RTC process.')
            self.process.join(timeout=timeout)

            if self.process.is_alive():
                print_error(f'RealTimeVideo._close_process_impl() Send a KILL signal to the server process.')
                self.process.kill()

        # A negative value -N indicates that the child was terminated by signal N.
        print_out(f'RealTimeVideo._close_process_impl() The exit code of RTC process is {self.process.exitcode}.')

        if self.queue is not None:
            self.queue.close()
            self.queue.cancel_join_thread()
            self.queue = None

        if self.process is not None:
            self.process.close()
            self.process = None

        if self.pid >= 1:
            if psutil.pid_exists(self.pid):
                print_out(f'Force kill PID: {self.pid}')
                psutil.Process(self.pid).kill()
            self.pid = UNKNOWN_PID

        assert self.queue is None
        assert self.process is None
        assert self.pid is UNKNOWN_PID
        print_out(f'RealTimeVideo._close_process_impl() Done.')

    def _close_process(self):
        try:
            self._close_process_impl()
        except Exception as e:
            print_error(f'RealTimeVideo._close_process() Exception: {e}')
        finally:
            self.queue = None
            self.process = None
            self.pid = UNKNOWN_PID

    def create_process(self):
        if self._create_process():
            return True
        self._close_process()
        return False

    def is_reopen(self):
        if self.process is None:
            return True
        if not self.process.is_alive():
            return True
        return False

    def reopen(self):
        self._close_process()
        if self._create_process():
            print_out(f'Recreated Server process PID: {self.pid}')
        else:
            raise CreateProcessError

    def on_init(self):
        return self.create_process()

    def on_valid(self):
        return self.pid != UNKNOWN_PID

    def on_run(self, image):
        if self.is_reopen():
            self.reopen()

        self.push(image)

    def on_destroy(self):
        self._close_process()


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


def main():
    parser = argparse.ArgumentParser(description='RealTimeVideo demo')
    parser.add_argument(
        '--cert-file',
        help='SSL certificate file (for HTTPS)')
    parser.add_argument(
        '--key-file',
        help='SSL key file (for HTTPS)')
    parser.add_argument(
        '--file',
        help='Read the media from a file and sent it.'),
    parser.add_argument(
        '--host',
        default=vs.DEFAULT_HOST,
        help=f'Host for HTTP server (default: {vs.DEFAULT_HOST})')
    parser.add_argument(
        '--port',
        type=int,
        default=vs.DEFAULT_PORT,
        help=f'Port for HTTP server (default: {vs.DEFAULT_PORT})')
    parser.add_argument(
        '--ices',
        default=vs.DEFAULT_ICES[0],
        help=f'ICE servers (default: {vs.DEFAULT_ICES[0]})')
    parser.add_argument(
        '--fps',
        type=int,
        default=vs.DEFAULT_VIDEO_FPS,
        help=f'WebRTC Video FPS (default: {vs.DEFAULT_VIDEO_FPS})')
    parser.add_argument(
        '--verbose',
        '-v',
        action='count')
    args = parser.parse_args()

    global LOGGING_SUFFIX
    LOGGING_SUFFIX = '\n'
    vs.LOGGING_SUFFIX = '\n'

    video = RealTimeVideo(host=args.host, port=args.port, ices=[args.ices], fps=args.fps, frame_format='bgr24',
                          cert_file=args.cert_file, key_file=args.key_file, verbose=bool(args.verbose))
    video.on_init()

    import cv2
    import time
    cap = cv2.VideoCapture(args.file)
    while cap.isOpened():
        ret, frame = cap.read()
        if not ret:
            break
        video.on_run(frame)
        time.sleep(1.0/args.fps)
    cap.release()
    video.on_destroy()


if __name__ == '__main__':
    main()
