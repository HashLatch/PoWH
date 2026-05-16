#!/usr/bin/env python3
"""
HashLatch Bridge v1.0.0 - Miner's assistant
Monitors bounties and automatically solves profitable ones using Hashcat.
"""

import subprocess
import json
import time
import os
import sys

VERSION = "1.0.0"
CLI = "./src/hashlatch-cli -regtest"
CONFIG_FILE = "bridge.conf"
MIN_CONFIRMATIONS = 6

def load_config():
    """Load miner configuration from bridge.conf"""
    default_config = {
        "min_profit_hlc": 1,
        "max_concurrent_jobs": 1,
        "hashcat_path": "hashcat",
        "hashcat_args": "-m 1400 -a 3",
        "poll_interval": 30
    }
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE) as f:
            for line in f:
                if '=' in line:
                    key, val = line.strip().split('=', 1)
                    default_config[key.strip()] = val.strip()
    return default_config

def run_cli(cmd):
    """Execute a hashLatch-cli command and return JSON result."""
    full_cmd = f"{CLI} {cmd}"
    result = subprocess.run(full_cmd, shell=True, capture_output=True, text=True)
    if result.returncode != 0:
        return None
    try:
        return json.loads(result.stdout)
    except:
        return None

def list_open_bounties():
    """Return list of open (unsolved) bounties."""
    bounties = run_cli("listbounties")
    if not bounties:
        return []
    return [b for b in bounties if b.get("solved") == 0 and b.get("reclaimed") == 0]

def solve_with_hashcat(bounty, config):
    """Attempt to crack the bounty using Hashcat."""
    target_hash = bounty["target_hash"]
    txid = bounty["txid"]
    
    # Build Hashcat command
    cmd = f"{config['hashcat_path']} {config['hashcat_args']} {target_hash} --potfile-disable --quiet -O"
    print(f"[Bridge] Running Hashcat for bounty {txid[:16]}...")
    
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    # Hashcat outputs: HASH:PLAINTEXT when cracked
    for line in result.stdout.split("\n"):
        if ":" in line:
            cracked_hash, plaintext = line.strip().split(":", 1)
            if cracked_hash == target_hash:
                return plaintext.strip()
    return None

def commit_solution(txid, solution, miner_address):
    """Commit the solution without revealing it."""
    result = run_cli(f'commitbounty {txid} "{solution}" {miner_address}')
    if result and "commit_hash" in result:
        print(f"[Bridge] Commit submitted: {result['commit_hash'][:16]}...")
        return result
    return None

def reveal_solution(txid, solution, nonce, payout_address):
    """Reveal the committed solution after waiting period."""
    result = run_cli(f'revealbounty {txid} "{solution}" {nonce} {payout_address}')
    if result and result.get("status") == "solved":
        print(f"[Bridge] Bounty {txid[:16]} SOLVED! Reward to {payout_address}")
        return True
    return False

def main():
    print(f"=== HashLatch Bridge v{VERSION} ===")
    config = load_config()
    miner_address = run_cli("getnewaddress")
    if not miner_address:
        print("[Bridge] ERROR: Cannot generate miner address. Is hashlatchd running?")
        sys.exit(1)
    miner_address = miner_address.strip()
    print(f"[Bridge] Miner address: {miner_address}")
    print(f"[Bridge] Polling every {config['poll_interval']}s...")
    
    while True:
        open_bounties = list_open_bounties()
        print(f"[Bridge] Found {len(open_bounties)} open bounties.")
        
        for bounty in open_bounties:
            txid = bounty["txid"]
            amount = bounty["amount"]
            
            # Simple profitability check
            if amount < float(config["min_profit_hlc"]):
                print(f"[Bridge] Skipping {txid[:16]}... (amount {amount} < min {config['min_profit_hlc']})")
                continue
            
            print(f"[Bridge] Attempting bounty {txid[:16]}... (reward: {amount} HLC)")
            solution = solve_with_hashcat(bounty, config)
            
            if solution:
                print(f"[Bridge] SOLUTION FOUND for {txid[:16]}: {solution}")
                commit = commit_solution(txid, solution, miner_address)
                if commit:
                    nonce = commit.get("nonce", "0")
                    wait_blocks = commit.get("wait_blocks", MIN_CONFIRMATIONS)
                    print(f"[Bridge] Waiting {wait_blocks} blocks before reveal...")
                    time.sleep(wait_blocks * 30)  # Rough estimate: 30s per block
                    if reveal_solution(txid, solution, nonce, miner_address):
                        print(f"[Bridge] Earned {amount} HLC!")
            else:
                print(f"[Bridge] No solution found for {txid[:16]}.")
        
        time.sleep(int(config["poll_interval"]))

if __name__ == "__main__":
    main()
