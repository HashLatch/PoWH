#!/bin/bash
# HashLatch — FULL NETWORK LAUNCH
# Resetuje siec do zera, importuje portfele, uruchamia wszystkie serwisy + watchdog.
# UWAGA: KASUJE BLOCKCHAIN. Uzyj TYLKO przy starcie nowej sieci.
set -e
HOME_DIR="/home/dstrychalski"
CLI="$HOME_DIR/PoWH/src/hashlatch-cli -rpcuser=hashlatch -rpcpassword=test123 -rpcport=8766"
DAEMON="$HOME_DIR/PoWH/src/hashlatchd"

# Safety confirmation — prevents accidental network wipe after launch
if [ "$1" != "--confirm" ]; then
    echo "############################################################"
    echo "#  UWAGA: To skasuje CALY blockchain i zresetuje siec!     #"
    echo "#  Wszystkie wykopane bloki i salda zostana usuniete.      #"
    echo "#                                                          #"
    echo "#  Uzyj tylko PRZED ogloszeniem, nigdy po starcie sieci.   #"
    echo "#                                                          #"
    echo "#  Aby potwierdzic: bash LAUNCH.sh --confirm               #"
    echo "############################################################"
    exit 1
fi

echo "=== 1/7 Zatrzymywanie wszystkiego ==="
sudo systemctl stop hashlatch-stratum hashlatch hashlatch-watchdog.timer 2>/dev/null || true
$CLI stop 2>/dev/null || true
sleep 5
pkill -9 -f hashlatchd 2>/dev/null || true
pkill -f "node server.js" 2>/dev/null || true
pkill -f hlc_explorer 2>/dev/null || true
pkill -f hashlatch_api 2>/dev/null || true
pkill -f admin_panel 2>/dev/null || true
pkill -f cloudflared 2>/dev/null || true
sleep 3

echo "=== 2/7 Reset blockchain do zera ==="
rm -rf $HOME_DIR/.powh/blocks $HOME_DIR/.powh/chainstate $HOME_DIR/.powh/indexes \
       $HOME_DIR/.powh/peers.dat $HOME_DIR/.powh/banlist.dat \
       $HOME_DIR/.powh/*.lock $HOME_DIR/.powh/*.pid

echo "=== 3/7 Start node (systemd) ==="
sudo systemctl start hashlatch
for i in $(seq 1 40); do
    if $CLI getblockchaininfo > /dev/null 2>&1; then echo "Node ready"; break; fi
    sleep 2
done

echo "=== 4/7 Import portfeli ==="
$CLI importprivkey UpcySTV658jy6uWV82Sx1rHG89hXyQSHZ7jMgxn3aDJ9EwKRVaSm "miner" false
$CLI importprivkey UvHWtS7dMbTV6THBZ43VzsooFQNkbSu5WsNGEae6tUyQHMj7LTsH "dev" false
$CLI importprivkey UuDE7TjnDo98fsc96qKPsN7PGZR8JXb4xuMxJjPZyPrywKAddnx6 "instance2" false

echo "=== 5/7 Reset pliku portfeli ==="
python3 -c "
import json,datetime
n=datetime.datetime.now().isoformat()
w=[{'address':'co8z5Qfgdo86XyEFeS2DnQEsUxQcKjnTFG','privkey':'UpcySTV658jy6uWV82Sx1rHG89hXyQSHZ7jMgxn3aDJ9EwKRVaSm','seed':'','label':'Miner wallet (98%)','created':n},
   {'address':'ce6KYfjYGUH5dzxXiBLfGEVArWgLRaLF3V','privkey':'UvHWtS7dMbTV6THBZ43VzsooFQNkbSu5WsNGEae6tUyQHMj7LTsH','seed':'','label':'Dev fee wallet (2%)','created':n},
   {'address':'cZ6AhXNM91T4EmeUDs4RPFUkVN8LYjnBeE','privkey':'UuDE7TjnDo98fsc96qKPsN7PGZR8JXb4xuMxJjPZyPrywKAddnx6','seed':'','label':'Instance2 wallet','created':n}]
open('$HOME_DIR/.hlc_wallets.json','w').write(json.dumps(w,indent=2))
print('Portfele zapisane')
"

echo "=== 6/7 Start serwisow ==="
sudo systemctl start hashlatch-stratum
sleep 5

echo "=== 7/7 Wlaczenie watchdog ==="
sudo systemctl start hashlatch-watchdog.timer

echo ""
echo "=========================================="
echo "  HashLatch URUCHOMIONY"
echo "  Blok: $($CLI getblockcount 2>/dev/null)"
echo "  Stratum: 34.185.173.154:3052"
echo "  Kop na: co8z5Qfgdo86XyEFeS2DnQEsUxQcKjnTFG"
echo "=========================================="
