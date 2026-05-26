#!/usr/bin/env python3
"""HashLatch Admin Panel - Full Control"""
from flask import Flask, jsonify, request, send_from_directory, Response
from flask_cors import CORS
import subprocess, os, json, psutil, time, signal
from datetime import datetime

app = Flask(__name__)
CORS(app)

ADMIN_PASSWORD_HASH = "5256b4864fb49ff968fe6e7b4a8939dbf1070dfbe0910ac9f6c78bb44b5e40ee"

def check_password(pw):
    import hashlib
    return hashlib.sha256(pw.encode()).hexdigest() == ADMIN_PASSWORD_HASH
NODE_DIR = "/home/dstrychalski/PoWH"
CLI = f"{NODE_DIR}/src/hashlatch-cli"
CLI_ARGS = ["-rpcuser=hashlatch", "-rpcpassword=test123", "-rpcport=8766"]
WALLETS_FILE = "/home/dstrychalski/.hlc_wallets.json"
DATA_DIR = "/home/dstrychalski/.powh"

def cli(cmd):
    import shlex, re
    # Reject any command with shell special characters
    if re.search(r'[;&|`$(){}\[\]<>!]', cmd):
        return "Error: invalid characters in command"
    parts = shlex.split(cmd)
    r = subprocess.run([CLI] + CLI_ARGS + parts, capture_output=True, text=True, timeout=10)
    return r.stdout.strip()

def is_node_running():
    for p in psutil.process_iter(['name', 'cmdline']):
        try:
            if 'hashlatchd' in ' '.join(p.info['cmdline'] or []):
                return True
        except: pass
    return False

def is_stratum_running():
    for p in psutil.process_iter(['name', 'cmdline']):
        try:
            if 'server.js' in ' '.join(p.info['cmdline'] or []):
                return True
        except: pass
    return False

def is_api_running():
    for p in psutil.process_iter(['cmdline']):
        try:
            if 'hashlatch_api.py' in ' '.join(p.info['cmdline'] or []):
                return True
        except: pass
    return False

def is_explorer_running():
    for p in psutil.process_iter(['cmdline']):
        try:
            if 'app.js' in ' '.join(p.info['cmdline'] or []) and 'explorer' in ' '.join(p.info['cmdline'] or []):
                return True
        except: pass
    return False

def is_tunnel_running():
    for p in psutil.process_iter(['cmdline']):
        try:
            if 'cloudflared' in ' '.join(p.info['cmdline'] or []):
                return True
        except: pass
    return False

def start_node():
    if is_node_running():
        return "Already running"
    subprocess.Popen([
        f"{NODE_DIR}/src/hashlatchd", "-daemon", "-server",
        "-rpcuser=hashlatch", "-rpcpassword=test123", "-rpcport=8766",
        "-rpcallowip=127.0.0.1", "-txindex=1", "-addressindex=1", "-bypassdownload=1",
        "-listen=1", "-port=18767", "-rpcworkqueue=64", "-rpcthreads=4"
    ])
    return "Node starting..."

def stop_node():
    subprocess.run(["pkill", "-f", "hashlatchd"], capture_output=True)
    return "Node stopped"

def start_stratum():
    if is_stratum_running():
        return "Already running"
    env = os.environ.copy()
    env['NVM_DIR'] = '/home/dstrychalski/.nvm'
    log = open("/home/dstrychalski/stratum.log", "a")
    subprocess.Popen(
        "source $NVM_DIR/nvm.sh && nvm use 16 && node server.js",
        shell=True, cwd="/home/dstrychalski/kawpow-stratum",
        stdout=log, stderr=log, env=env,
        executable="/bin/bash"
    )
    return "Stratum starting..."

def stop_stratum():
    subprocess.run(["pkill", "-f", "node server.js"], capture_output=True)
    return "Stratum stopped"

def start_api():
    if is_api_running():
        return "Already running"
    log = open("/home/dstrychalski/api.log", "a")
    subprocess.Popen(["python3", "/home/dstrychalski/hashlatch_api.py"], stdout=log, stderr=log)
    return "API starting..."

def stop_api():
    subprocess.run(["pkill", "-f", "hashlatch_api.py"], capture_output=True)
    return "API stopped"

def start_explorer():
    if is_explorer_running():
        return "Already running"
    env = os.environ.copy()
    env['NVM_DIR'] = '/home/dstrychalski/.nvm'
    log = open("/home/dstrychalski/explorer.log", "a")
    subprocess.Popen(
        "source $NVM_DIR/nvm.sh && nvm use 16 && node app.js",
        shell=True, cwd="/home/dstrychalski/explorer",
        stdout=log, stderr=log, env=env,
        executable="/bin/bash"
    )
    return "Explorer starting..."

def stop_explorer():
    subprocess.run(["pkill", "-f", "node app.js"], capture_output=True)
    return "Explorer stopped"

def start_tunnel():
    if is_tunnel_running():
        return "Already running"
    log = open("/home/dstrychalski/tunnel.log", "a")
    subprocess.Popen([
        "/home/dstrychalski/cloudflared", "tunnel", "run",
        "1938441e-4962-4b98-b9ee-648897774bc3"
    ], stdout=log, stderr=log)
    return "Tunnel starting..."

def stop_tunnel():
    subprocess.run(["pkill", "-f", "cloudflared"], capture_output=True)
    return "Tunnel stopped"

@app.route('/admin')
def admin():
    return send_from_directory('/home/dstrychalski', 'admin.html')

@app.route('/api/admin/auth', methods=['POST'])
def auth():
    data = request.get_json()
    if check_password(data.get('password','')):
        return jsonify({"ok": True})
    return jsonify({"ok": False}), 401

@app.route('/api/admin/status')
def status():
    # System metrics
    disk = psutil.disk_usage('/')
    mem = psutil.virtual_memory()
    cpu = psutil.cpu_percent(interval=1)
    
    # Node info
    node_info = {}
    if is_node_running():
        try:
            info = json.loads(cli("getblockchaininfo"))
            wallet = json.loads(cli("getwalletinfo"))
            net = json.loads(cli("getnetworkinfo"))
            node_info = {
                "blocks": info.get("blocks", 0),
                "chain": info.get("chain", ""),
                "difficulty": info.get("difficulty", 0),
                "connections": net.get("connections", 0),
                "balance": wallet.get("balance", 0),
                "immature_balance": wallet.get("immature_balance", 0),
            }
        except: pass

    return jsonify({
        "services": {
            "node": is_node_running(),
            "stratum": is_stratum_running(),
            "api": is_api_running(),
            "explorer": is_explorer_running(),
            "tunnel": is_tunnel_running(),
        },
        "system": {
            "cpu_percent": cpu,
            "ram_used_gb": round(mem.used / 1024**3, 2),
            "ram_total_gb": round(mem.total / 1024**3, 2),
            "ram_percent": mem.percent,
            "disk_used_gb": round(disk.used / 1024**3, 2),
            "disk_total_gb": round(disk.total / 1024**3, 2),
            "disk_percent": disk.percent,
        },
        "node": node_info,
        "time": datetime.now().isoformat(),
    })

@app.route('/api/admin/service/<name>/<action>', methods=['POST'])
def service_control(name, action):
    data = request.get_json() or {}
    if not check_password(data.get('password','')):
        return jsonify({"error": "Unauthorized"}), 401
    
    actions = {
        "node":     {"start": start_node,    "stop": stop_node},
        "stratum":  {"start": start_stratum, "stop": stop_stratum},
        "api":      {"start": start_api,     "stop": stop_api},
        "explorer": {"start": start_explorer,"stop": stop_explorer},
        "tunnel":   {"start": start_tunnel,  "stop": stop_tunnel},
    }
    
    if name not in actions or action not in ("start", "stop", "restart"):
        return jsonify({"error": "Invalid service or action"}), 400
    
    if action == "restart":
        actions[name]["stop"]()
        time.sleep(3)
        msg = actions[name]["start"]()
    else:
        msg = actions[name][action]()
    
    return jsonify({"ok": True, "message": msg})

@app.route('/api/admin/network-reset', methods=['POST'])
def network_reset():
    data = request.get_json() or {}
    if not check_password(data.get('password','')):
        return jsonify({"error": "Unauthorized"}), 401
    if not data.get('confirm'):
        return jsonify({"error": "Confirmation required"}), 400
    
    # Stop node
    stop_node()
    time.sleep(3)
    
    # Delete blockchain data
    import shutil
    for d in ['blocks', 'chainstate', 'indexes']:
        path = f"{DATA_DIR}/{d}"
        if os.path.exists(path):
            shutil.rmtree(path)
    
    for f in ['peers.dat', 'banlist.dat']:
        path = f"{DATA_DIR}/{f}"
        if os.path.exists(path):
            os.remove(path)
    
    # Clear wallets
    with open(WALLETS_FILE, 'w') as f:
        json.dump([], f)
    
    # Restart node
    time.sleep(2)
    start_node()
    
    return jsonify({"ok": True, "message": "Network reset complete. Node restarting..."})

@app.route('/api/admin/logs/<service>')
def get_logs(service):
    log_files = {
        "node": f"{DATA_DIR}/debug.log",
        "stratum": "/home/dstrychalski/stratum.log",
        "api": "/home/dstrychalski/api.log",
        "explorer": "/home/dstrychalski/explorer.log",
        "tunnel": "/home/dstrychalski/tunnel.log",
        "admin": "/home/dstrychalski/admin.log",
    }
    if service not in log_files:
        return jsonify({"error": "Invalid service"}), 400
    try:
        result = subprocess.run(['tail', '-100', log_files[service]], capture_output=True, text=True)
        return jsonify({"log": result.stdout})
    except:
        return jsonify({"log": "Log not available"})

@app.route('/api/admin/balance/<address>')
def get_balance(address):
    try:
        # Use the UTXO set (listunspent) for the true balance. listtransactions
        # double-counts historical coinbase and ignores spends, which inflated
        # the figure. UTXOs are the actual unspent coins on chain.
        r = subprocess.run([CLI] + CLI_ARGS + ['getaddressbalance',
            '{"addresses":["' + address + '"]}'],
            capture_output=True, text=True, timeout=15)
        data = json.loads(r.stdout.strip()) if r.returncode == 0 else {}
        r2 = subprocess.run([CLI] + CLI_ARGS + ['getaddressutxos',
            '{"addresses":["' + address + '"]}'],
            capture_output=True, text=True, timeout=15)
        utxos = json.loads(r2.stdout.strip()) if r2.returncode == 0 else []
        r3 = subprocess.run([CLI] + CLI_ARGS + ['getblockcount'],
            capture_output=True, text=True, timeout=15)
        tip = int(r3.stdout.strip()) if r3.returncode == 0 else 0
        total = round(data.get('balance', 0) / 1e8, 8)
        immature = round(sum(u.get('satoshis',0)/1e8 for u in utxos if tip - u.get('height',0) + 1 < 100), 8)
        return jsonify({"address": address,
                        "balance": round(total - immature, 8),
                        "immature": immature,
                        "total": total})
    except Exception as e:
        return jsonify({"error": str(e), "balance": 0, "immature": 0})


    try:
        with open(WALLETS_FILE, 'r') as f:
            return jsonify(json.load(f))
    except:
        return jsonify([])

@app.route('/api/admin/wallets', methods=['GET'])
def get_wallets():
    try:
        with open(WALLETS_FILE,'r') as f: return jsonify(json.load(f))
    except: return jsonify([])

@app.route('/api/admin/wallets', methods=['POST'])
def save_wallets():
    try:
        wallets = request.get_json()
        with open(WALLETS_FILE, 'w') as f:
            json.dump(wallets, f, indent=2)
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/admin/rpc', methods=['POST'])
def rpc_command():
    data = request.get_json() or {}
    if not check_password(data.get('password','')):
        return jsonify({"error": "Unauthorized"}), 401
    cmd = data.get('command', '').strip()
    if not cmd:
        return jsonify({"error": "No command"}), 400
    # Security: allow only safe commands
    allowed = ['getblockchaininfo','getblockcount','getwalletinfo','getnetworkinfo',
                'listreceivedbyaddress','getblock','gettransaction','getblockhash',
                'getmininginfo','getnewaddress','listbounties','getbalance']
    # Use exact first-word match to prevent injection
    first_word = cmd.strip().split()[0] if cmd.strip() else ''
    if first_word not in allowed:
        return jsonify({"error": "Command not allowed"}), 403
    result = cli(cmd)
    return jsonify({"result": result})

@app.route('/api/admin/miners')
def get_miners():
    import re, collections, time as time_mod
    _cache = get_miners.__dict__
    log_path = "/home/dstrychalski/stratum.log"
    if not os.path.exists(log_path):
        return jsonify({"miners": [], "total_workers": 0, "unique_addresses": 0, "unique_ips": 0, "network_hashrate": 0, "total_blocks_found": 0})
    try:
        with open(log_path, "rb") as f:
            try: f.seek(-6_000_000, 2)
            except OSError: f.seek(0)
            data = f.read().decode("latin-1", errors="ignore")

        auth_re   = re.compile(r'mining\.authorize.*?"params":\["([a-zA-Z0-9]+)\.([^"]*)"')
        submit_re = re.compile(r'mining\.submit.*?"params":\["([a-zA-Z0-9]+)\.([^"]*)"')
        accept_re = re.compile(r'Share accepted from ([a-zA-Z0-9]+)\.([^\s]+)')
        ip_re     = re.compile(r'"ip":"([^"]+)"')
        lines = data.splitlines()
        total_lines = len(lines)

        workers = collections.OrderedDict()
        for i, line in enumerate(lines):
            m = auth_re.search(line) or submit_re.search(line) or accept_re.search(line)
            if not m: continue
            addr, rig = m.group(1), m.group(2)
            key = f"{addr}.{rig}"
            ipm = ip_re.search(line)
            ip = ipm.group(1).replace("::ffff:", "") if ipm else None
            if key not in workers:
                workers[key] = {"address": addr, "rig": rig, "ip": ip, "shares": 0, "last_line": 0}
            if ip: workers[key]["ip"] = ip
            if "submit" in line or "Share accepted" in line:
                workers[key]["shares"] += 1
                workers[key]["last_line"] = i

        share_counts = collections.Counter()
        for m in submit_re.finditer(data): share_counts[f"{m.group(1)}.{m.group(2)}"] += 1
        for m in accept_re.finditer(data): share_counts[f"{m.group(1)}.{m.group(2)}"] += 1
        for key, info in workers.items():
            info["shares"] = share_counts.get(key, info["shares"])
            info["active"] = info["last_line"] > total_lines * 0.85

        # Blockchain scan with cache
        tip_r = subprocess.run([CLI]+CLI_ARGS+['getblockcount'], capture_output=True, text=True, timeout=10)
        tip = int(tip_r.stdout.strip()) if tip_r.returncode == 0 else 0
        cached_tip = _cache.get('blocks_tip', -1)
        blocks_per_addr = dict(_cache.get('blocks_data', {}))
        if tip != cached_tip:
            start = max(0, cached_tip + 1)
            for h in range(start, tip + 1):
                bh_r = subprocess.run([CLI]+CLI_ARGS+['getblockhash', str(h)], capture_output=True, text=True, timeout=5)
                if bh_r.returncode != 0: continue
                bl_r = subprocess.run([CLI]+CLI_ARGS+['getblock', bh_r.stdout.strip(), '2'], capture_output=True, text=True, timeout=15)
                if bl_r.returncode != 0: continue
                try:
                    bl = json.loads(bl_r.stdout.strip())
                    for vout in bl['tx'][0].get('vout', []):
                        for a in vout.get('scriptPubKey', {}).get('addresses', []):
                            if a != 'ce6KYfjYGUH5dzxXiBLfGEVArWgLRaLF3V':
                                blocks_per_addr[a] = blocks_per_addr.get(a, 0) + 1
                except: pass
            _cache['blocks_data'] = blocks_per_addr
            _cache['blocks_tip'] = tip

        # Group workers by address
        unique_addrs = list(set(w['address'] for w in workers.values()))
        addr_miners = {}
        for key, w in workers.items():
            addr = w['address']
            if addr not in addr_miners:
                addr_miners[addr] = {
                    'address': addr, 'rigs': [], 'ips': [],
                    'shares': 0, 'active': False,
                    'blocks_found': blocks_per_addr.get(addr, 0),
                    'balance': 0, 'spendable': 0, 'immature': 0,
                    'earned': round(blocks_per_addr.get(addr, 0) * 9.604, 4),
                }
            if w['rig'] and w['rig'] not in addr_miners[addr]['rigs']:
                addr_miners[addr]['rigs'].append(w['rig'])
            if w['ip'] and w['ip'] not in addr_miners[addr]['ips']:
                addr_miners[addr]['ips'].append(w['ip'])
            addr_miners[addr]['shares'] += w['shares']
            if w['active']: addr_miners[addr]['active'] = True

        # Balances
        for addr in unique_addrs:
            try:
                r = subprocess.run([CLI]+CLI_ARGS+['getaddressbalance', '{"addresses":["'+addr+'"]}'], capture_output=True, text=True, timeout=10)
                d = json.loads(r.stdout.strip()) if r.returncode == 0 else {}
                total = round(d.get('balance', 0) / 1e8, 8)
                r2 = subprocess.run([CLI]+CLI_ARGS+['getaddressutxos', '{"addresses":["'+addr+'"]}'], capture_output=True, text=True, timeout=10)
                utxos = json.loads(r2.stdout.strip()) if r2.returncode == 0 else []
                immature = round(sum(u.get('satoshis',0)/1e8 for u in utxos if tip - u.get('height',0) + 1 < 100), 8)
                addr_miners[addr]['balance'] = total
                addr_miners[addr]['spendable'] = round(total - immature, 8)
                addr_miners[addr]['immature'] = immature
            except: pass

        # Add blockchain miners not yet in log (historical)
        for addr, blk_count in blocks_per_addr.items():
            if addr not in addr_miners:
                addr_miners[addr] = {
                    'address': addr, 'rigs': [], 'ips': [],
                    'shares': 0, 'active': False,
                    'blocks_found': blk_count,
                    'balance': 0, 'spendable': 0, 'immature': 0,
                    'earned': round(blk_count * 9.604, 4),
                }
                unique_addrs.append(addr)

        # Balances for all addresses (including blockchain-only)
        for addr in unique_addrs:
            if addr_miners.get(addr, {}).get('balance', 0) != 0:
                continue
            try:
                r = subprocess.run([CLI]+CLI_ARGS+['getaddressbalance', '{"addresses":["'+addr+'"]}'], capture_output=True, text=True, timeout=10)
                d = json.loads(r.stdout.strip()) if r.returncode == 0 else {}
                total = round(d.get('balance', 0) / 1e8, 8)
                r2 = subprocess.run([CLI]+CLI_ARGS+['getaddressutxos', '{"addresses":["'+addr+'"]}'], capture_output=True, text=True, timeout=10)
                utxos = json.loads(r2.stdout.strip()) if r2.returncode == 0 else []
                immature = round(sum(u.get('satoshis',0)/1e8 for u in utxos if tip - u.get('height',0) + 1 < 100), 8)
                if addr in addr_miners:
                    addr_miners[addr]['balance'] = total
                    addr_miners[addr]['spendable'] = round(total - immature, 8)
                    addr_miners[addr]['immature'] = immature
            except: pass

        miner_list = sorted(addr_miners.values(), key=lambda x: x['blocks_found'], reverse=True)

        mi_r = subprocess.run([CLI]+CLI_ARGS+['getmininginfo'], capture_output=True, text=True, timeout=10)
        network_hashrate = 0
        if mi_r.returncode == 0:
            mi = json.loads(mi_r.stdout.strip())
            network_hashrate = mi.get('networkhashps', 0)

        return jsonify({
            "miners": miner_list,
            "total_workers": len(workers),
            "unique_addresses": len(miner_list),
            "unique_ips": len(set(ip for m in miner_list for ip in m['ips'] if ip)),
            "network_hashrate": network_hashrate,
            "total_blocks_found": sum(m['blocks_found'] for m in miner_list),
        })
    except Exception as e:
        return jsonify({"miners": [], "error": str(e), "total_workers":0, "unique_addresses":0, "unique_ips":0, "network_hashrate":0, "total_blocks_found":0})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5001, debug=False)
