#!/bin/bash
# HashLatch Server Setup Script
# Run this after fresh clone or server restore
# Usage: bash SETUP.sh

echo "=== HashLatch Server Setup ==="

# 1. Install crontab
crontab - << 'CRON'
@reboot sleep 30 && /home/dstrychalski/PoWH/src/hashlatchd -server -rpcuser=hashlatch -rpcpassword=test123 -rpcport=8766 -rpcallowip=127.0.0.1 -txindex=1 -addressindex=1 -bypassdownload=1 -listen=1 -port=18767 -rpcworkqueue=512 -rpcthreads=16 -daemon
@reboot sleep 60 && cd /home/dstrychalski/kawpow-stratum && /home/dstrychalski/.nvm/versions/node/v16.20.2/bin/node server.js >> /home/dstrychalski/stratum.log 2>&1
@reboot sleep 55 && python3 /home/dstrychalski/hashlatch_api.py >> /home/dstrychalski/api.log 2>&1
@reboot sleep 55 && python3 /home/dstrychalski/admin_panel.py >> /home/dstrychalski/admin.log 2>&1
@reboot sleep 65 && /home/dstrychalski/cloudflared tunnel run 1938441e-4962-4b98-b9ee-648897774bc3 >> /home/dstrychalski/tunnel.log 2>&1
* * * * * ss -tlnp | grep -q ':8766 ' || (/home/dstrychalski/PoWH/src/hashlatchd -server -rpcuser=hashlatch -rpcpassword=test123 -rpcport=8766 -rpcallowip=127.0.0.1 -txindex=1 -addressindex=1 -bypassdownload=1 -listen=1 -port=18767 -rpcworkqueue=512 -rpcthreads=16 -daemon)
* * * * * ss -tlnp | grep -q ':3052 ' || (cd /home/dstrychalski/kawpow-stratum && /home/dstrychalski/.nvm/versions/node/v16.20.2/bin/node server.js >> /home/dstrychalski/stratum.log 2>&1 &)
* * * * * ss -tlnp | grep -q ':5000 ' || (python3 /home/dstrychalski/hashlatch_api.py >> /home/dstrychalski/api.log 2>&1 &)
* * * * * ss -tlnp | grep -q ':5001 ' || (python3 /home/dstrychalski/admin_panel.py >> /home/dstrychalski/admin.log 2>&1 &)
* * * * * pgrep -f cloudflared || (nohup /home/dstrychalski/cloudflared tunnel run 1938441e-4962-4b98-b9ee-648897774bc3 >> /home/dstrychalski/tunnel.log 2>&1 &)
0 3 * * * cp -r /home/dstrychalski/.powh/blocks /home/dstrychalski/.powh_daily_backup && echo "Backup done $(date)" >> /home/dstrychalski/backup.log
CRON
echo "Crontab installed: $(crontab -l | wc -l) lines"

# 2. Install systemd service
sudo tee /etc/systemd/system/hashlatch.service << 'EOF'
[Unit]
Description=HashLatch Node
After=network.target
StartLimitIntervalSec=0

[Service]
Type=simple
User=dstrychalski
WorkingDirectory=/home/dstrychalski/PoWH
ExecStart=/home/dstrychalski/PoWH/src/hashlatchd \
  -server \
  -rpcuser=hashlatch -rpcpassword=test123 \
  -rpcport=8766 -rpcallowip=127.0.0.1 \
  -txindex=1 -addressindex=1 -bypassdownload=1 \
  -listen=1 -port=18767 \
  -rpcworkqueue=512 -rpcthreads=16
Restart=always
RestartSec=15
TimeoutStartSec=300
TimeoutStopSec=60

[Install]
WantedBy=multi-user.target
EOF
sudo systemctl daemon-reload
sudo systemctl enable hashlatch
echo "Systemd service installed"

# 3. Start everything
python3 /home/dstrychalski/hashlatch_api.py >> /home/dstrychalski/api.log 2>&1 &
python3 /home/dstrychalski/admin_panel.py >> /home/dstrychalski/admin.log 2>&1 &
/home/dstrychalski/cloudflared tunnel run 1938441e-4962-4b98-b9ee-648897774bc3 >> /home/dstrychalski/tunnel.log 2>&1 &

echo "=== Setup complete ==="
echo "Start node: sudo systemctl start hashlatch"
echo "Start stratum: cd ~/kawpow-stratum && nohup node server.js > ~/stratum.log 2>&1 &"
