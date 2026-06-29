#!/usr/bin/env python3
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import base64
import os


BASE = Path(os.environ.get("SUBSCRIPTION_DIR", "/opt/vps-subscription"))
PORT = int(os.environ.get("SUBSCRIPTION_PORT", "28703"))


def read_text_file(name, default=""):
    path = BASE / name
    if not path.exists():
        return default
    return path.read_text(encoding="utf-8").strip()


def read_aliases():
    aliases = set()
    for line in read_text_file("aliases.txt").splitlines():
        alias = line.strip().strip("/")
        if alias:
            aliases.add(alias)
    return aliases


def read_sub():
    return (BASE / "sub.txt").read_bytes()


TOKEN = read_text_file("token")
ALIASES = read_aliases()
BASE64_ALIASES = {a + "-base64" for a in ALIASES if not a.endswith("-base64")}
BASE64_ALIASES.update({a for a in ALIASES if a.endswith("-base64")})


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def send_body(self, body, content_type):
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(body)
        self.close_connection = True

    def do_GET(self):
        path = self.path.split("?", 1)[0].strip("/")
        plain_paths = {TOKEN, TOKEN + ".txt"} | {a for a in ALIASES if not a.endswith("-base64")}
        b64_paths = {TOKEN + "-base64", TOKEN + ".b64"} | BASE64_ALIASES

        if path in plain_paths:
            self.send_body(read_sub(), "text/plain; charset=utf-8")
        elif path in b64_paths:
            self.send_body(base64.b64encode(read_sub()), "text/plain; charset=utf-8")
        else:
            body = b"Not found\n"
            self.send_response(404)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Connection", "close")
            self.end_headers()
            self.wfile.write(body)
            self.close_connection = True

    def log_message(self, fmt, *args):
        return


if __name__ == "__main__":
    ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
