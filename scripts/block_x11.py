#!/usr/bin/env python3
"""Bind to X11 ports 6000-6020, accept and immediately reject connections.
This tricks orted's X11 probe into finishing quickly instead of hanging."""
import socket
import threading
import time

def blocker(port):
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind(('127.0.0.1', port))
        s.listen(5)
    except OSError:
        return
    while True:
        try:
            c, addr = s.accept()
            # Send X11 "connection failed" response
            c.send(b'\x00\x00\x00\x00\x00\x00\x00\x00')
            c.close()
        except Exception:
            break

print("Binding X11 port blockers 6000-6020...", flush=True)
threads = []
for p in range(6000, 6021):
    t = threading.Thread(target=blocker, args=(p,), daemon=True)
    t.start()
    threads.append(t)

time.sleep(0.5)
print("READY - X11 ports 6000-6020 blocked", flush=True)

# Keep alive until killed
try:
    while True:
        time.sleep(60)
except KeyboardInterrupt:
    pass
