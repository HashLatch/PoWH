#!/bin/bash
# HashLatch — Start all auxiliary services (stratum, api, admin, explorer, tunnel)
HOME_DIR="/home/dstrychalski"
export NVM_DIR="$HOME_DIR/.nvm"
source "$NVM_DIR/nvm.sh" 2>/dev/null
nvm use 16 2>/dev/null

CLI="$HOME_DIR/PoWH/src/hashlatch-cli -rpcuser=hashlatch -rpcpassword=test123 -rpcport=8766"

# Wait for node RPC to be ready (up to 60s)
for i in $(seq 1 30); do
    if $CLI getblockchaininfo > /dev/null 2>&1; then
        echo "Node RPC ready after $((i*2))s"
        break
    fi
    sleep 2
done

# Kill any stale instances and free ports
pkill -f "node server.js" 2>/dev/null || true
pkill -f hlc_explorer 2>/dev/null || true
pkill -f hashlatch_api 2>/dev/null || true
pkill -f admin_panel 2>/dev/null || true
pkill -f cloudflared 2>/dev/null || true
for p in 3052 3001 5000 5001; do fuser -k ${p}/tcp 2>/dev/null || true; done
sleep 3

# Start all services
cd $HOME_DIR/kawpow-stratum && nohup node server.js > $HOME_DIR/stratum.log 2>&1 &
sleep 2
nohup python3 $HOME_DIR/hashlatch_api.py > $HOME_DIR/api.log 2>&1 &
nohup python3 $HOME_DIR/admin_panel.py > $HOME_DIR/admin.log 2>&1 &
nohup python3 $HOME_DIR/PoWH/hlc_explorer.py > $HOME_DIR/explorer.log 2>&1 &
nohup $HOME_DIR/cloudflared tunnel run 1938441e-4962-4b98-b9ee-648897774bc3 > $HOME_DIR/tunnel.log 2>&1 &

echo "All HashLatch services started at $(date)"
