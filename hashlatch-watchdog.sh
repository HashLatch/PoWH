#!/bin/bash
# HashLatch Watchdog — checks services every run, restarts any that died.
# Intended to be called by a systemd timer or cron every 1-2 minutes.
HOME_DIR="/home/dstrychalski"
export NVM_DIR="$HOME_DIR/.nvm"
source "$NVM_DIR/nvm.sh" 2>/dev/null
nvm use 16 2>/dev/null
LOG="$HOME_DIR/watchdog.log"

check_proc() {
    # $1 = pattern, $2 = friendly name, $3 = start command
    if ! pgrep -f "$1" > /dev/null 2>&1; then
        echo "$(date) - $2 DOWN, restarting" >> $LOG
        eval "$3"
    fi
}

# Node is managed by systemd (Restart=always), so we only watch aux services.
check_proc "node server.js" "stratum" \
    "cd $HOME_DIR/kawpow-stratum && nohup node server.js > $HOME_DIR/stratum.log 2>&1 &"
check_proc "hashlatch_api.py" "api" \
    "nohup python3 $HOME_DIR/hashlatch_api.py > $HOME_DIR/api.log 2>&1 &"
check_proc "admin_panel.py" "admin" \
    "nohup python3 $HOME_DIR/admin_panel.py > $HOME_DIR/admin.log 2>&1 &"
check_proc "hlc_explorer.py" "explorer" \
    "nohup python3 $HOME_DIR/PoWH/hlc_explorer.py > $HOME_DIR/explorer.log 2>&1 &"
check_proc "cloudflared tunnel" "tunnel" \
    "nohup $HOME_DIR/cloudflared tunnel run 1938441e-4962-4b98-b9ee-648897774bc3 > $HOME_DIR/tunnel.log 2>&1 &"
