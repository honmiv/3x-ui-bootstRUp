#!/usr/bin/env python3
"""HTTP proxy: GET /<SECRET_SUB_PATH>/<client_name> returns the subscription
content fetched from the node's subscription URL.

The client name is looked up in subs.yml (two lists: proxy and freedom).
  - proxy   -> RUSSIAN_SUB_URL  (Russian node)
  - freedom -> FOREIGN_SUB_URL  (non-Russian node)

Env vars:
  DATABASE_FILE   path to subs.yml (default: subs.yml)
  FORCE_FILE      path to force-subs.yml overrides (default: force-subs.yml)
  SECRET_SUB_PATH path prefix from the domain root (default: subs)
  RUSSIAN_SUB_URL subscription URL of the Russian node
  FOREIGN_SUB_URL subscription URL of the non-Russian node
  HOST            listen address (default: 0.0.0.0)
  PORT            listen port (default: 8080)
"""

import logging
import os
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import unquote

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("sub-server")

DATABASE_FILE = os.environ.get("DATABASE_FILE", "subs.yml")
FORCE_FILE = os.environ.get("FORCE_FILE", "force-subs.yml")
SECRET_SUB_PATH = os.environ.get("SECRET_SUB_PATH", "subs").strip("/")
RUSSIAN_SUB_URL = os.environ.get("RUSSIAN_SUB_URL", "")
FOREIGN_SUB_URL = os.environ.get("FOREIGN_SUB_URL", "")
HOST = os.environ.get("HOST", "0.0.0.0")
PORT = int(os.environ.get("PORT", "8080"))


def load_subs(path):
    subs = {"proxy": [], "freedom": []}
    section = None
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if line.endswith(":"):
                section = line[:-1].strip()
                if section not in subs:
                    section = None
                continue
            if section and line.startswith("-"):
                name = line[1:].strip()
                if name:
                    subs[section].append(name)
    return subs


def load_force_subs(path):
    force = {}
    if not os.path.exists(path):
        return force
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if ":" not in line:
                continue
            key, _, value = line.partition(":")
            key = key.strip()
            value = value.strip()
            if key and value:
                force[key] = value
    return force


def fetch_subscription(url):
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    req = urllib.request.Request(url, headers={"User-Agent": "sub-server/1.0"})
    with urllib.request.urlopen(req, timeout=15) as resp:
        return resp.read()


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        path = unquote(self.path.split("?", 1)[0]).strip("/")
        parts = path.split("/")
        if len(parts) == 1 and parts[0] == SECRET_SUB_PATH:
            self._list_subscriptions()
            return
        if len(parts) != 2 or parts[0] != SECRET_SUB_PATH:
            log.warning("404 unknown path: %s", self.path)
            self.send_error(404)
            return
        client = parts[1]
        if client in FORCE_SUBS:
            body = FORCE_SUBS[client].encode("utf-8")
            log.info("200 %s (force) -> %d bytes", client, len(body))
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if client in SUBS["proxy"]:
            base_url = RUSSIAN_SUB_URL
            group = "proxy"
        elif client in SUBS["freedom"]:
            base_url = FOREIGN_SUB_URL
            group = "freedom"
        else:
            log.warning("404 unknown client: %s", client)
            self.send_error(404)
            return
        if not base_url:
            log.error("502 no subscription URL configured for group '%s' (client %s)", group, client)
            self.send_error(502)
            return
        url = f"{base_url.rstrip('/')}/{client}"
        try:
            body = fetch_subscription(url)
        except urllib.error.HTTPError as e:
            log.error("502 fetch failed for %s (%s): HTTP %s %s (url=%s)", client, group, e.code, e.reason, url)
            self.send_error(502)
            return
        except urllib.error.URLError as e:
            log.error("502 fetch failed for %s (%s): %s (url=%s)", client, group, e.reason, url)
            self.send_error(502)
            return
        except Exception as e:
            log.error("502 fetch failed for %s (%s): %r (url=%s)", client, group, e, url)
            self.send_error(502)
            return
        log.info("200 %s (%s) <- %s (%d bytes)", client, group, url, len(body))
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _list_subscriptions(self):
        lines = []
        for client in SUBS["proxy"]:
            if RUSSIAN_SUB_URL:
                lines.append(f"{RUSSIAN_SUB_URL}/{client}")
        for client in SUBS["freedom"]:
            if FOREIGN_SUB_URL:
                lines.append(f"{FOREIGN_SUB_URL}/{client}")
        body = ("\n".join(lines) + "\n").encode("utf-8")
        log.info("200 subscription list (%d urls)", len(lines))
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):
        log.info("request: %s", format % args)


def main():
    global SUBS, FORCE_SUBS
    SUBS = load_subs(DATABASE_FILE)
    FORCE_SUBS = load_force_subs(FORCE_FILE)
    log.info("listening on %s:%s, path prefix /%s, db %s", HOST, PORT, SECRET_SUB_PATH, DATABASE_FILE)
    log.info("RUSSIAN_SUB_URL=%s", RUSSIAN_SUB_URL or "(not set)")
    log.info("FOREIGN_SUB_URL=%s", FOREIGN_SUB_URL or "(not set)")
    log.info("proxy clients: %s", ", ".join(SUBS["proxy"]) or "(none)")
    log.info("freedom clients: %s", ", ".join(SUBS["freedom"]) or "(none)")
    log.info("force overrides: %s", ", ".join(FORCE_SUBS) or "(none)")
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
