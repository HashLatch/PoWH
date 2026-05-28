#!/usr/bin/env python3
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
import json, urllib.request, threading, logging, base64

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
_sem = threading.Semaphore(3)

def rpc_getkawpowhash(header_hash, mix_hash, nonce, height, target):
    with _sem:
        try:
            payload = json.dumps({
                "jsonrpc": "1.0", "id": "kpw",
                "method": "getkawpowhash",
                "params": [header_hash, mix_hash, nonce, int(height), target]
            }).encode()
            creds = base64.b64encode(b"hashlatch:YOUR_RPC_PASSWORD").decode()
            req = urllib.request.Request(
                "http://127.0.0.1:8766/",
                data=payload,
                headers={
                    "Content-Type": "application/json",
                    "Authorization": "Basic " + creds
                },
                method="POST"
            )
            with urllib.request.urlopen(req, timeout=5) as resp:
                result = json.loads(resp.read())
                return result.get("result")
        except Exception as e:
            logging.warning("RPC error: %s", e)
            return None

class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args): pass

    def do_GET(self):
        try:
            params = parse_qs(urlparse(self.path).query)
            g = lambda k, d="": params.get(k, [d])[0]

            header_hash    = g("header_hash").lstrip("0x")
            mix_hash       = g("mix_hash").lstrip("0x")
            nonce          = g("nonce")
            height         = g("height", "1")
            block_boundary = g("block_boundary", "f"*64)

            is_block = False
            digest = header_hash

            r = rpc_getkawpowhash(header_hash, mix_hash, nonce, height, block_boundary)
            if r:
                digest = r.get("digest", header_hash)
                is_block = (r.get("meets_target") == "true")
                if is_block:
                    logging.info("*** BLOCK CANDIDATE! digest=%s height=%s", digest[:16], height)

            resp = json.dumps({"share": True, "block": is_block, "digest": digest}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(resp)))
            self.end_headers()
            self.wfile.write(resp)
        except Exception as e:
            logging.error("Handler error: %s", e)
            self.send_response(200)
            self.end_headers()
            self.wfile.write(json.dumps({"share": True, "block": False, "digest": ""}).encode())

if __name__ == "__main__":
    server = HTTPServer(("127.0.0.1", 9999), Handler)
    logging.info("kawpowd started on 127.0.0.1:9999")
    server.serve_forever()
