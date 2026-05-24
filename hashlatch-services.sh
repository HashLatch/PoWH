#!/bin/bash
# HashLatch — Start all services except node (managed by systemd)
HOME_DIR="/home/dstrychalski"
export NVM_DIR="$HOME_DIR/.nvm"
source "$NVM_DIR/nvm.sh"
nvm use 16

# Kill old
pkill -f "node server.js" 2>/dev/null || true
pkill -f hlc_explorer 2>/dev/null || true
pkill -f hashlatch_api 2>/dev/null || true
pkill -f admin_panel 2>/dev/null || true
pkill -f cloudflared 2>/dev/null || true
fuser -k 3001/tcp 2>/dev/null || true
sleep 3

# Start all
cd $HOME_DIR/kawpow-stratum && nohup node server.js > $HOME_DIR/stratum.log 2>&1 &
nohup python3 $HOME_DIR/hashlatch_api.py > $HOME_DIR/api.log 2>&1 &
nohup python3 $HOME_DIR/admin_panel.py > $HOME_DIR/admin.log 2>&1 &
nohup python3 $HOME_DIR/PoWH/hlc_explorer.py > $HOME_DIR/explorer.log 2>&1 &
nohup $HOME_DIR/cloudflared tunnel run 1938441e-4962-4b98-b9ee-648897774bc3 > $HOME_DIR/tunnel.log 2>&1 &

echo "All services started"
