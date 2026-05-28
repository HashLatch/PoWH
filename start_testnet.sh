#!/bin/bash

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo -e "${YELLOW}======================================================${NC}"
echo -e "${YELLOW}       URUCHAMIANIE PRODUKCYJNEGO TESTNETU PoWH       ${NC}"
echo -e "${YELLOW}======================================================${NC}"

# 1. Zabezpieczenie portów i czyszczenie zombie procesów
killall -9 hashlatchd 2>/dev/null
sleep 1

# 2. Nadpisywanie konfiguracji
mkdir -p ~/.powh
cat << 'CONF' > ~/.powh/powh.conf
rpcuser=YOUR_RPC_USER
rpcpassword=YOUR_RPC_PASSWORD
server=1
listen=1
rpcallowip=0.0.0.0/0
rpcbind=0.0.0.0
txindex=1
