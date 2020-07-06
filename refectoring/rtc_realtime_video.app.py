# -*- coding: utf-8 -*-

import sys
import http.client
import urllib.parse
import multiprocessing as mp
from queue import Full

import rtc_realtime_video_server


DEFAULT_MAX_QUEUE_SIZE = 4
DEFAULT_EXIT_TIMEOUT_SECONDS = 4.0

host = '0.0.0.0'
port = 8888
max_queue_size = DEFAULT_MAX_QUEUE_SIZE
exit_timeout_seconds = DEFAULT_EXIT_TIMEOUT_SECONDS


def print_out(message):
    sys.stdout.write(message)
    sys.stdout.flush()


def print_error(message):
    sys.stderr.write(message)
    sys.stderr.flush()


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


rtc_password = ''
rtc_process: mp.Process
rtc_queue: mp.Queue


def run_process():
    global rtc_password
    rtc_password = rtc_realtime_video_server.generate_exit_password()

    global rtc_queue
    global max_queue_size
    queue_size = max_queue_size if max_queue_size > 0 else DEFAULT_MAX_QUEUE_SIZE
    rtc_queue = mp.Queue(queue_size)

    global rtc_process
    global host, port
    rtc_process = mp.Process(target=rtc_realtime_video_server.on_runner,
                             args=(rtc_queue, rtc_password, host, port,))
    rtc_process.start()

    print_out(f'rtc.realtime_video process PID is {rtc_process.pid}.')
    return rtc_process.is_alive()


def request_exit_process():
    global rtc_password
    params = urllib.parse.urlencode({rtc_realtime_video_server.PASSWORD_PARAM_KEY: rtc_password})
    headers = {'Content-type': 'application/x-www-form-urlencoded'}
    conn = http.client.HTTPConnection(f'{host}:{port}')
    conn.request('POST', rtc_realtime_video_server.EXIT_SIGNAL_PATH, params, headers)


def close_process():
    request_exit_process()

    global exit_timeout_seconds
    timeout = exit_timeout_seconds if exit_timeout_seconds > 0.0 else DEFAULT_EXIT_TIMEOUT_SECONDS

    global rtc_process
    print_out(f'rtc.realtime_video(pid={rtc_process.pid}) Join(timeout={timeout}s) ...')
    rtc_process.join(timeout=timeout)

    global rtc_queue
    rtc_queue.close()
    rtc_queue.cancel_join_thread()
    rtc_queue = None

    if rtc_process.is_alive():
        print_out(f'rtc.realtime_video(pid={rtc_process.pid}) Kill ...')
        rtc_process.kill()

    # A negative value -N indicates that the child was terminated by signal N.
    print_out(f'rtc.realtime_video(pid={rtc_process.pid}) Exit Code: {rtc_process.exitcode}')

    # A negative value -N indicates that the child was terminated by signal N.
    rtc_process.close()
    rtc_process = None


def push_data(data):
    global rtc_queue
    try:
        rtc_queue.put_nowait(data)
    except Full:
        rtc_queue.get_nowait()
        try:
            rtc_queue.put_nowait(data)
        except Full:
            pass


def on_init():
    return run_process()


def on_valid():
    global rtc_process
    return rtc_process.is_alive()


def on_run(image):
    push_data(image)


def on_destroy():
    close_process()


if __name__ == '__main__':
    pass
