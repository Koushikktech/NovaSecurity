"""Bounded capture for trusted runner commands; child application code stays in Docker."""

import os
import selectors
import subprocess
import time


def bounded_capture(command, timeout, environment, limit=2_000_000):
    started = time.monotonic()
    process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, env=environment)
    output = bytearray()
    selector = selectors.DefaultSelector()
    try:
        selector.register(process.stdout, selectors.EVENT_READ)
        while True:
            remaining = timeout - (time.monotonic() - started)
            if remaining <= 0:
                raise subprocess.TimeoutExpired(command, timeout)
            if not selector.select(min(remaining, 0.25)):
                continue
            chunk = os.read(process.stdout.fileno(), 65536)
            if not chunk:
                break
            if len(output) + len(chunk) > limit:
                raise ValueError("Verification output exceeded its 2 MB capture limit")
            output.extend(chunk)
        process.wait(timeout=max(0.001, timeout - (time.monotonic() - started)))
        return subprocess.CompletedProcess(command, process.returncode, output.decode("utf-8", errors="replace"))
    finally:
        selector.close()
        if process.poll() is None:
            process.kill()
            process.wait(timeout=5)
        process.stdout.close()
