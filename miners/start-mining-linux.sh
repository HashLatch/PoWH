#!/bin/bash
read -p "Enter your HLC address: " WALLET
./gminer --algo kawpow --server 34.185.173.154 --port 3052 --user $WALLET.rig1 --pass x
