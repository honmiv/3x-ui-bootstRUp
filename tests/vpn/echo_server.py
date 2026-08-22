#!/usr/bin/env python3
"""
Lightweight Echo HTTP Server for VPN E2E Testing.
Returns incoming client socket IP, headers, and requested path as JSON.
Used to verify actual egress node in Docker network.
"""

import json
import logging
from http.server import BaseHTTPRequestHandler, HTTPServer
import sys

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] [echo-server] %(message)s",
    datefmt="%H:%M:%S",
)


class EchoHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        client_ip = self.client_address[0]
        logging.info("Received GET %s from %s", self.path, client_ip)
        
        response_data = {
            "client_ip": client_ip,
            "path": self.path,
            "host": self.headers.get("Host", ""),
            "headers": {k: v for k, v in self.headers.items()},
        }

        body = json.dumps(response_data, indent=2).encode("utf-8")
        
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):
        # Delegate to standard logger
        pass


def main():
    port = 80
    server_address = ("0.0.0.0", port)
    httpd = HTTPServer(server_address, EchoHandler)
    logging.info("Echo server listening on port %d...", port)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    httpd.server_close()
    logging.info("Echo server stopped.")


if __name__ == "__main__":
    main()
