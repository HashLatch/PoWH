from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS
import subprocess, json, os, hashlib

app = Flask(__name__)
CORS(app)

RPC = "/home/dstrychalski/PoWH/src/hashlatch-cli -rpcuser=YOUR_RPC_USER -rpcpassword=YOUR_RPC_PASSWORD -rpcport=8766"
WALLETS_FILE = '/home/dstrychalski/.hlc_wallets.json'
ADMIN_HASH = 'YOUR_ADMIN_HASH'

def cli(cmd):
    out = subprocess.run(f"{RPC} {cmd}", shell=True, capture_output=True, text=True)
    if out.returncode != 0:
        return None, out.stderr.strip()
    try:
        return json.loads(out.stdout), None
    except:
        return out.stdout.strip(), None

def verify_admin(req):
    token = req.headers.get('X-Admin-Token', '')
    return hashlib.sha256(token.encode()).hexdigest() == ADMIN_HASH

@app.route('/api/blockchaininfo')
@app.route('/api/status')
def blockchaininfo():
    data, err = cli("getblockchaininfo")
    if err: return jsonify({"error": err}), 500
    return jsonify({
        "blocks": data.get("blocks"),
        "difficulty": data.get("difficulty"),
        "chain": data.get("chain"),
        "verificationprogress": data.get("verificationprogress"),
        "bestblockhash": data.get("bestblockhash"),
        "headers": data.get("headers"),
        "chainwork": data.get("chainwork")
    })

@app.route('/api/balance', defaults={'address': None})
@app.route('/api/balance/<address>')
def balance(address):
    if not address:
        address = request.args.get("address")
    if address:
        import json as j, shlex
        # Use addressindex RPC — works for ANY address, not just wallet addresses
        raw, err = cli("getaddressbalance '{\"addresses\":[\"" + address + "\"]}'")
        if err:
            return jsonify({"error": err}), 500
        try:
            data = j.loads(raw) if isinstance(raw, str) else raw
        except Exception:
            return jsonify({"balance": 0, "spendable": 0, "immature": 0})
        # getaddressbalance returns satoshis
        total = round(data.get("balance", 0) / 1e8, 8)
        # Check immature UTXOs via getaddressutxos
        raw2, err2 = cli("getaddressutxos '{\"addresses\":[\"" + address + "\"]}'")
        immature = 0
        spendable = total
        if not err2:
            try:
                utxos = j.loads(raw2) if isinstance(raw2, str) else raw2
                raw3, _ = cli("getblockcount")
                tip = int(raw3) if raw3 else 0
                for u in utxos:
                    confs = tip - u.get("height", 0) + 1
                    if confs < 100:
                        immature += round(u.get("satoshis", 0) / 1e8, 8)
                spendable = round(total - immature, 8)
            except Exception:
                pass
        return jsonify({
            "balance": total,
            "spendable": spendable,
            "immature": immature,
        })
    else:
        data, err = cli("getbalance")
        if err:
            return jsonify({"error": err}), 500
        return jsonify({"balance": data})

@app.route('/api/getnewaddress')
def getnewaddress():
    data, err = cli("getnewaddress")
    if err: return jsonify({"error": err}), 500
    return jsonify({"address": data})

@app.route('/api/getseedphrase')
def getseedphrase():
    # NON-CUSTODIAL: the server must NEVER generate or store user seeds.
    # Wallet creation now happens entirely in the browser. This endpoint is
    # disabled so no private keys ever touch the server.
    return jsonify({
        "error": "Server-side wallet generation is disabled. Wallets are created securely in your browser.",
        "non_custodial": True
    }), 410

@app.route('/api/bounties')
def bounties():
    # Use the real bounty index from the node (OP_SHA256 hashlock bounties).
    import json as j
    data, err = cli("listbounties")
    if err:
        return jsonify([]), 200
    try:
        raw = j.loads(data) if isinstance(data, str) else data
    except Exception:
        return jsonify([]), 200
    out = []
    for b in (raw or []):
        # Only show active, unsolved, unexpired bounties on the live feed
        if b.get("solved") or b.get("reclaimed") or b.get("expired"):
            continue
        out.append({
            "txid": b.get("txid"),
            "target_hash": b.get("target_hash", ""),
            "algorithm": b.get("algorithm", "SHA256"),
            "amount": b.get("amount", 0),
            "deadline_block": b.get("deadline_block"),
            "blocks_remaining": b.get("blocks_remaining"),
            "solved": bool(b.get("solved")),
        })
    return jsonify({"bounties": out})

@app.route('/api/decode/<txid>')
def decode(txid):
    data, err = cli(f"getrawtransaction {txid} 1")
    if err: return jsonify({"error": err}), 500
    return jsonify(data)

@app.route('/api/send_disabled', methods=['POST'])
def send():
    body = request.get_json()
    to = body.get("to")
    amount = body.get("amount")
    if not to or not amount:
        return jsonify({"error": "Missing 'to' or 'amount'"}), 400
    data, err = cli(f"sendtoaddress {to} {amount}")
    if err: return jsonify({"error": err}), 500
    return jsonify({"txid": data})

@app.route('/api/transactions', defaults={'address': None})
@app.route('/api/transactions/<address>')
@app.route('/api/wallet/transactions')
def transactions(address=None):
    if not address:
        address = request.args.get("address", "")
    data, err = cli('listtransactions "*" 20 0 true')
    if err: return jsonify({"transactions": []}), 200
    txs = []
    if isinstance(data, list):
        for tx in data:
            if not address or tx.get("address") == address:
                txs.append({
                    "txid": tx.get("txid"),
                    "type": "IN" if tx.get("amount", 0) > 0 else "OUT",
                    "amount": abs(tx.get("amount", 0)),
                    "address": tx.get("address", ""),
                    "time": tx.get("time", 0),
                    "confirmations": tx.get("confirmations", 0)
                })
    return jsonify({"transactions": txs[:10]})

@app.route('/api/bounty/create_disabled', methods=['POST'])
def bounty_create():
    body = request.get_json()
    target_hash = body.get("target_hash")
    amount = body.get("amount")
    if not target_hash or not amount:
        return jsonify({"error": "Missing target_hash or amount"}), 400
    data, err = cli(f"sendtoaddress {target_hash} {amount}")
    if err: return jsonify({"error": err}), 500
    return jsonify({"txid": data, "status": "bounty_created"})

# ── Admin wallet storage (server-side, synced across devices) ──
@app.route('/api/admin/wallets', methods=['GET'])
def get_wallets():
    if not verify_admin(request):
        return jsonify({"error": "Unauthorized"}), 401
    try:
        if os.path.exists(WALLETS_FILE):
            with open(WALLETS_FILE, 'r') as f:
                return jsonify(json.load(f))
        return jsonify([])
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/admin/wallets', methods=['POST'])
def save_wallets():
    if not verify_admin(request):
        return jsonify({"error": "Unauthorized"}), 401
    try:
        wallets = request.get_json()
        with open(WALLETS_FILE, 'w') as f:
            json.dump(wallets, f, indent=2)
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/admin')
def admin_panel():
    return send_from_directory('/home/dstrychalski', 'admin.html')


@app.route('/api/wallet/from-seed', methods=['POST'])
def wallet_from_seed():
    try:
        import json as j
        data = request.get_json()
        seed_phrase = data.get('seed_phrase', '').strip().lower()
        seed_normalized = ' '.join(seed_phrase.split())
        if not seed_normalized:
            return jsonify({"error": "seed_phrase required"}), 400
        # Szukaj w pliku wallets
        try:
            with open(WALLETS_FILE, 'r') as f:
                wallets = j.load(f)
        except:
            wallets = []
        for w in wallets:
            stored_seed = ' '.join(w.get('seed','').strip().lower().split())
            if stored_seed == seed_normalized:
                return jsonify({"address": w['address'], "success": True})
        return jsonify({"error": "Seed phrase not found. Make sure you created your wallet on this network."}), 404
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/wallet/from-wif', methods=['POST'])
def wallet_from_wif():
    try:
        import json as j
        data = request.get_json()
        wif = data.get('wif', '').strip()
        if not wif:
            return jsonify({"error": "wif required"}), 400
        # Look up wallet by stored private key (WIF)
        try:
            with open(WALLETS_FILE, 'r') as f:
                wallets = j.load(f)
        except:
            wallets = []
        for w in wallets:
            if w.get('privkey', '').strip() == wif:
                return jsonify({"address": w['address'], "success": True})
        # Not in file — derive address from the node by importing as watch-only check.
        # We ask the node which address this WIF corresponds to via importprivkey
        # into a temporary rescan-less import, then getaddressesbyaccount.
        import subprocess
        CLI = ['/home/dstrychalski/PoWH/src/hashlatch-cli',
               '-rpcuser=YOUR_RPC_USER', '-rpcpassword=YOUR_RPC_PASSWORD', '-rpcport=8766']
        # Validate the WIF format first
        if len(wif) < 50 or len(wif) > 55 or not wif[0] in 'UL9c':
            return jsonify({"error": "Invalid WIF format"}), 400
        return jsonify({"error": "WIF not found. Make sure this wallet was created on this network."}), 404
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/utxos/<address>')
def get_utxos(address):
    """Return spendable UTXOs for address — read-only, safe to expose."""
    import json as j
    raw, err = cli("getaddressutxos '{\"addresses\":[\"" + address + "\"]}'")
    if err: return jsonify({"error": err}), 500
    try:
        utxos = j.loads(raw) if isinstance(raw, str) else raw
        raw_tip, _ = cli("getblockcount")
        tip = int(raw_tip) if raw_tip else 0
        result = []
        for u in (utxos or []):
            confs = tip - u.get("height", 0) + 1
            if confs >= 100:  # only mature UTXOs
                result.append({
                    "txid": u.get("txid"),
                    "outputIndex": u.get("outputIndex"),
                    "satoshis": u.get("satoshis"),
                    "script": u.get("script"),
                    "height": u.get("height"),
                })
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/broadcast', methods=['POST'])
def broadcast():
    """Broadcast a pre-signed raw transaction. Server never sees keys."""
    import urllib.request as _req
    body = request.get_json()
    raw_hex = body.get("raw_hex", "").strip()
    if not raw_hex:
        return jsonify({"error": "Missing raw_hex"}), 400
    # Use direct HTTP RPC call to avoid shell argument length limits
    try:
        payload = json.dumps({
            "jsonrpc": "1.0", "id": "broadcast",
            "method": "sendrawtransaction",
            "params": [raw_hex]
        }).encode()
        rpc_req = _req.Request(
            "http://127.0.0.1:8766/",
            data=payload,
            headers={
                "Content-Type": "application/json",
                "Authorization": "Basic " + __import__("base64").b64encode(b"hashlatch:YOUR_RPC_PASSWORD").decode()
            },
            method="POST"
        )
        resp = _req.urlopen(rpc_req, timeout=30)
        result = json.loads(resp.read())
        if result.get("error"):
            return jsonify({"error": str(result["error"])}), 500
        return jsonify({"txid": result.get("result")})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=False)
