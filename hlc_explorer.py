#!/usr/bin/env python3
"""HashLatch Block Explorer — Custom lightweight explorer"""
from flask import Flask, jsonify, request, render_template_string
from flask_cors import CORS
import subprocess, json, time
from datetime import datetime
from collections import defaultdict

app = Flask(__name__)
CORS(app)

CLI = "/home/dstrychalski/PoWH/src/hashlatch-cli"
CLI_ARGS = ["-rpcuser=hashlatch", "-rpcpassword=test123", "-rpcport=8766"]

def rpc(cmd):
    try:
        r = subprocess.run([CLI] + CLI_ARGS + cmd, capture_output=True, text=True, timeout=15)
        if r.returncode != 0:
            return None, r.stderr.strip()
        return json.loads(r.stdout.strip()), None
    except Exception as e:
        return None, str(e)

def rpc_str(cmd):
    try:
        r = subprocess.run([CLI] + CLI_ARGS + cmd, capture_output=True, text=True, timeout=15)
        return r.stdout.strip(), None
    except Exception as e:
        return None, str(e)

import os

@app.route('/')
def index():
    html_path = os.path.join(os.path.dirname(__file__), 'explorer.html')
    with open(html_path, 'r') as f:
        return f.read()


@app.route('/api/info')
def info():
    chain, _ = rpc(["getblockchaininfo"])
    net, _ = rpc(["getnetworkinfo"])
    mining, _ = rpc(["getmininginfo"])
    wallet, _ = rpc(["getwalletinfo"])
    if not chain:
        return jsonify({"error": "Node unavailable"}), 503
    return jsonify({
        "blocks": chain.get("blocks", 0),
        "chain": chain.get("chain", ""),
        "difficulty": chain.get("difficulty", 0),
        "connections": net.get("connections", 0) if net else 0,
        "hashrate": mining.get("networkhashps", 0) if mining else 0,
        "supply": chain.get("blocks", 0) * 50,
        "max_supply": 21000000,
        "symbol": "HLC",
        "algorithm": "KawPow",
        "block_time": 120,
        "block_reward": 10,
    })

@app.route('/api/blocks')
def blocks():
    count = min(int(request.args.get('count', 20)), 100)
    offset = int(request.args.get('offset', 0))
    best, _ = rpc_str(["getblockcount"])
    if not best:
        return jsonify([])
    best = int(best)
    result = []
    for h in range(best - offset, max(best - offset - count, -1), -1):
        if h < 0:
            break
        bh, _ = rpc_str(["getblockhash", str(h)])
        if not bh:
            continue
        block, _ = rpc(["getblock", bh])
        if not block:
            continue
        result.append({
            "height": h,
            "hash": bh,
            "time": block.get("time", 0),
            "txcount": len(block.get("tx", [])),
            "size": block.get("size", 0),
            "difficulty": block.get("difficulty", 0),
            "miner": "",
        })
    return jsonify(result)

@app.route('/api/block/<identifier>')
def block(identifier):
    if len(identifier) < 10:
        bh, _ = rpc_str(["getblockhash", identifier])
        if not bh:
            return jsonify({"error": "Block not found"}), 404
    else:
        bh = identifier
    block, _ = rpc(["getblock", bh, "2"])
    if not block:
        return jsonify({"error": "Block not found"}), 404
    return jsonify(block)

@app.route('/api/tx/<txid>')
def tx(txid):
    tx, _ = rpc(["getrawtransaction", txid, "1"])
    if not tx:
        return jsonify({"error": "Transaction not found"}), 404
    return jsonify(tx)

@app.route('/api/address/<address>')
def address(address):
    bal_data, _ = rpc(["getaddressbalance", '{"addresses":["' + address + '"]}'])
    utxo_data, _ = rpc(["getaddressutxos", '{"addresses":["' + address + '"]}'])
    tip_str, _ = rpc_str(["getblockcount"])
    tip = int(tip_str) if tip_str else 0
    total = round((bal_data or {}).get("balance", 0) / 1e8, 8)
    received = round((bal_data or {}).get("received", 0) / 1e8, 8)
    immature = 0
    if utxo_data:
        for u in utxo_data:
            confs = tip - u.get("height", 0) + 1
            if confs < 100:
                immature += u.get("satoshis", 0) / 1e8
    immature = round(immature, 8)
    spendable = round(total - immature, 8)
    txids_data, _ = rpc(["getaddresstxids", '{"addresses":["' + address + '"]}'])
    addr_txs = []
    if txids_data:
        for txid in reversed(txids_data[-50:]):
            tx_data, _ = rpc(["getrawtransaction", txid, "1"])
            if tx_data:
                addr_txs.append({
                    "txid": txid,
                    "time": tx_data.get("time", 0),
                    "confirmations": tx_data.get("confirmations", 0),
                })
    return jsonify({
        "address": address,
        "balance": total,
        "spendable": spendable,
        "immature": immature,
        "received": received,
        "transactions": addr_txs,
    })

_richlist_cache = {"data": None, "tip": -1, "time": 0}

@app.route('/api/richlist')
def richlist():
    """Richlist with cache — rebuilds only when new block found"""
    import time as _time
    global _richlist_cache
    try:
        tip_str, _ = rpc_str(["getblockcount"])
        tip = int(tip_str) if tip_str else 0

        # Return cache if tip unchanged and cache < 60s old
        if (_richlist_cache["data"] is not None and
                _richlist_cache["tip"] == tip and
                _time.time() - _richlist_cache["time"] < 60):
            return jsonify(_richlist_cache["data"])

        # Only scan NEW blocks since last cache
        seen = set(_richlist_cache.get("seen", set()) if _richlist_cache["tip"] >= 0 else set())
        start = max(0, _richlist_cache["tip"] + 1) if _richlist_cache["tip"] >= 0 else 0

        for h in range(start, tip + 1):
            bh, _ = rpc_str(["getblockhash", str(h)])
            if not bh: continue
            bl, _ = rpc(["getblock", bh, "1"])
            if not bl: continue
            cbtxid = bl.get("tx", [None])[0]
            if not cbtxid: continue
            cbtx, _ = rpc(["getrawtransaction", cbtxid, "1"])
            if not cbtx: continue
            for vout in cbtx.get("vout", []):
                for addr in vout.get("scriptPubKey", {}).get("addresses", []):
                    seen.add(addr)

        # Get balances for all addresses
        balances = {}
        for addr in seen:
            raw, _ = rpc_str(["getaddressbalance", '{"addresses":["' + addr + '"]}'])
            if not raw: continue
            try:
                import json as _j
                bd = _j.loads(raw)
                bal = round(bd.get("balance", 0) / 1e8, 8)
                if bal > 0:
                    balances[addr] = bal
            except: pass

        if not balances:
            return jsonify({"addresses": [], "total": 0, "supply": 0})

        result = [{"address": a, "balance": b} for a, b in balances.items()]
        result.sort(key=lambda x: x["balance"], reverse=True)
        top100 = result[:100]
        total_supply = sum(x["balance"] for x in result)
        for b in top100:
            b["percent"] = round(b["balance"] / total_supply * 100, 4) if total_supply > 0 else 0

        response = {"addresses": top100, "total": len(top100), "supply": round(total_supply, 8)}
        _richlist_cache = {"data": response, "tip": tip, "time": _time.time(), "seen": seen}
        return jsonify(response)
    except Exception as e:
        return jsonify({"error": str(e), "addresses": [], "total": 0, "supply": 0})

@app.route('/api/search')
def search():
    q = request.args.get('q', '').strip()
    if not q:
        return jsonify({"error": "No query"}), 400
    
    # Try block height
    if q.isdigit():
        bh, _ = rpc_str(["getblockhash", q])
        if bh:
            return jsonify({"type": "block", "value": q, "hash": bh})
    
    # Try block hash (64 chars hex)
    if len(q) == 64:
        block, _ = rpc(["getblock", q])
        if block:
            return jsonify({"type": "block", "value": block.get("height"), "hash": q})
        tx, _ = rpc(["getrawtransaction", q, "1"])
        if tx:
            return jsonify({"type": "tx", "value": q})
    
    # Try address
    if q.startswith('c') and len(q) > 20:
        return jsonify({"type": "address", "value": q})
    
    return jsonify({"error": "Not found"}), 404

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=3001, debug=False)
