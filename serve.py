#!/usr/bin/env python3
"""
serve.py — static file server for the portfolio site.
Automatically rebuilds live-data.js (Goodreads + Letterboxd) on each page
load, at most once every CACHE_MINS minutes so the APIs aren't hammered.

Usage: python3 serve.py
Then open: http://localhost:3000
"""

import time
import threading
import http.server
import socketserver
import build_live

PORT       = 3000
CACHE_MINS = 5

_lock       = threading.Lock()
_last_built = 0.0


def maybe_rebuild():
    global _last_built
    with _lock:
        if time.time() - _last_built < CACHE_MINS * 60:
            return
        print("[live] refreshing data from Goodreads + Letterboxd…")
        try:
            build_live.build()
            _last_built = time.time()
        except Exception as e:
            print(f"[live] rebuild failed: {e}")


class Handler(http.server.SimpleHTTPRequestHandler):
    def do_GET(self):
        if self.path.split("?")[0] in ("/", "/index.html", "/live-data.js"):
            maybe_rebuild()
        super().do_GET()

    def log_message(self, fmt, *args):
        print(f"  {fmt % args}")


socketserver.TCPServer.allow_reuse_address = True
with socketserver.TCPServer(("", PORT), Handler) as httpd:
    print(f"Serving at http://localhost:{PORT}")
    print(f"Live data auto-refreshes every {CACHE_MINS} min on page load.")
    print("Press Ctrl+C to stop.\n")
    httpd.serve_forever()
