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
        "block_reward": 50,
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
    # Get received
    received, _ = rpc(["getreceivedbyaddress", address, "0"])
    # Get unspent
    utxos, _ = rpc(["listunspent", "0", "9999999", json.dumps([address])])
    balance = sum(u.get("amount", 0) for u in (utxos or []))
    # Get transactions
    txs_raw, _ = rpc(["listtransactions", "*", "100", "0", "true"])
    addr_txs = []
    if txs_raw:
        for t in txs_raw:
            if t.get("address") == address:
                addr_txs.append({
                    "txid": t.get("txid"),
                    "amount": t.get("amount"),
                    "type": t.get("category"),
                    "time": t.get("time"),
                    "confirmations": t.get("confirmations"),
                })
    return jsonify({
        "address": address,
        "balance": balance,
        "received": received or 0,
        "transactions": addr_txs[:50],
    })

@app.route('/api/richlist')
def richlist():
    """Build richlist from listreceivedbyaddress"""
    data, err = rpc(["listreceivedbyaddress", "0", "true"])
    if not data:
        return jsonify({"addresses": [], "total": 0})
    
    balances = []
    for entry in data:
        addr = entry.get("address", "")
        bal = entry.get("amount", 0)
        if addr and bal > 0:
            balances.append({"address": addr, "balance": bal})
    
    balances.sort(key=lambda x: x["balance"], reverse=True)
    top100 = balances[:100]
    
    total_supply = sum(b["balance"] for b in balances)
    for b in top100:
        b["percent"] = round(b["balance"] / total_supply * 100, 4) if total_supply > 0 else 0
    
    return jsonify({"addresses": top100, "total": len(top100), "supply": total_supply})

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
