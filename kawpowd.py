#!/usr/bin/env python3
"""
HashLatch KawPow validator - lightweight replacement for kawpowd
Accepts all shares, detects block candidates via simple hash comparison.
No node RPC calls - zero flooding risk.
"""
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
import json, logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")

class KawPowHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass  # suppress default access log

    def do_GET(self):
        try:
            params = parse_qs(urlparse(self.path).query)
            header_hash    = params.get("header_hash",    ["0"*64])[0].lstrip("0x")
            block_boundary = params.get("block_boundary", ["f"*64])[0].lstrip("0x")

            # Block candidate check: hash < block_boundary
            try:
                is_block = int(header_hash, 16) < int(block_boundary, 16)
            except Exception:
                is_block = False

            if is_block:
                logging.info("BLOCK CANDIDATE detected hash=%s", header_hash[:16])

            result = json.dumps({
                "share":  True,
                "block":  is_block,
                "digest": header_hash
            }).encode()

            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(result)))
            self.end_headers()
            self.wfile.write(result)
        except Exception as e:
            self.send_response(500)
            self.end_headers()
            self.wfile.write(json.dumps({"error": str(e)}).encode())

if __name__ == "__main__":
    server = HTTPServer(("127.0.0.1", 9999), KawPowHandler)
    logging.info("HashLatch kawpowd started on 127.0.0.1:9999")
    server.serve_forever()
