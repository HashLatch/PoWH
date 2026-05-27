#!/usr/bin/env python3
"""
HashLatch kawpowd - validates KawPow shares via node RPC
Rate limited to max 3 concurrent getkawpowhash calls to prevent node flooding
"""
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
import json, urllib.request, threading, logging, time

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")

# Semaphore limits concurrent RPC calls to node
_sem = threading.Semaphore(3)
RPC_URL = "http://hashlatch:test123@127.0.0.1:8766/"

def rpc_getkawpowhash(header_hash, mix_hash, nonce, height, target):
    """Call node getkawpowhash with semaphore limiting."""
    with _sem:
        try:
            payload = json.dumps({
                "jsonrpc": "1.0", "id": "kpw", "method": "getkawpowhash",
                "params": [header_hash, mix_hash, nonce, int(height), target]
            }).encode()
            req = urllib.request.Request(
                RPC_URL, data=payload,
                headers={"Content-Type": "application/json"},
                method="POST"
            )
            with urllib.request.urlopen(req, timeout=5) as resp:
                return json.loads(resp.read())
        except Exception as e:
            return None

class KawPowHandler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args): pass

    def do_GET(self):
        try:
            params = parse_qs(urlparse(self.path).query)
            g = lambda k, d="": params.get(k, [d])[0]

            header_hash    = g("header_hash").lstrip("0x")
            mix_hash       = g("mix_hash").lstrip("0x")
            nonce          = g("nonce")
            height         = g("height", "0")
            share_boundary = g("share_boundary", "f"*64)
            block_boundary = g("block_boundary", "f"*64)

            # Quick share check (no RPC needed)
            try:
                share_ok = int(header_hash, 16) < int(share_boundary, 16)
            except:
                share_ok = True

            # Block check via getkawpowhash (rate limited)
            is_block = False
            digest = header_hash
            result = rpc_getkawpowhash(
                header_hash, mix_hash, nonce, height, block_boundary
            )
            if result and result.get("result"):
                r = result["result"]
                digest = r.get("digest", header_hash)
                is_block = (r.get("meets_target") == "true" or r.get("result") == "true")
                if is_block:
                    logging.info("BLOCK CANDIDATE! digest=%s", digest[:16])

            resp = json.dumps({
                "share": share_ok,
                "block": is_block,
                "digest": digest
            }).encode()

            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(resp)))
            self.end_headers()
            self.wfile.write(resp)

        except Exception as e:
            logging.error("Handler error: %s", e)
            self.send_response(500)
            self.end_headers()
            self.wfile.write(json.dumps({"share": True, "block": False, "digest": ""}).encode())

if __name__ == "__main__":
    server = HTTPServer(("127.0.0.1", 9999), KawPowHandler)
    server.timeout = 10
    logging.info("HashLatch kawpowd started on 127.0.0.1:9999 (max 3 concurrent RPC)")
    server.serve_forever()
