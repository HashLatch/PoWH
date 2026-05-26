from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS
import subprocess, json, os, hashlib

app = Flask(__name__)
CORS(app)

RPC = "/home/dstrychalski/PoWH/src/hashlatch-cli -rpcuser=hashlatch -rpcpassword=test123 -rpcport=8766"
WALLETS_FILE = '/home/dstrychalski/.hlc_wallets.json'
ADMIN_HASH = '5256b4864fb49ff968fe6e7b4a8939dbf1070dfbe0910ac9f6c78bb44b5e40ee'

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
        data, err = cli(f"getreceivedbyaddress {address} 0")
    else:
        data, err = cli("getbalance")
    if err: return jsonify({"error": err}), 500
    return jsonify({"balance": data})

@app.route('/api/getnewaddress')
def getnewaddress():
    data, err = cli("getnewaddress")
    if err: return jsonify({"error": err}), 500
    return jsonify({"address": data})

@app.route('/api/getseedphrase')
def getseedphrase():
    addr, err = cli("getnewaddress")
    if err: return jsonify({"error": err}), 500
    from mnemonic import Mnemonic
    import datetime, json as j
    mnemo = Mnemonic("english")
    seed_phrase = mnemo.generate(128)
    # Save seed+address to wallets file so recovery works
    try:
        try:
            with open(WALLETS_FILE, 'r') as f: wallets = j.load(f)
        except: wallets = []
        wallets.append({"address": addr, "seed": seed_phrase, "created": datetime.datetime.now().isoformat()})
        with open(WALLETS_FILE, 'w') as f: j.dump(wallets, f, indent=2)
    except: pass
    return jsonify({"address": addr, "seed_phrase": seed_phrase})

@app.route('/api/bounties')
def bounties():
    data, err = cli("listunspent 0 9999999")
    if err: return jsonify([]), 200
    bounties_list = []
    if isinstance(data, list):
        for utxo in data:
            if utxo.get("amount", 0) > 0:
                bounties_list.append({
                    "txid": utxo.get("txid"),
                    "target_hash": utxo.get("address", ""),
                    "amount": utxo.get("amount"),
                    "deadline": "2026-12-31",
                    "solved": False
                })
    return jsonify(bounties_list)

@app.route('/api/decode/<txid>')
def decode(txid):
    data, err = cli(f"getrawtransaction {txid} 1")
    if err: return jsonify({"error": err}), 500
    return jsonify(data)

@app.route('/api/send', methods=['POST'])
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

@app.route('/api/bounty/create', methods=['POST'])
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

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=False)
