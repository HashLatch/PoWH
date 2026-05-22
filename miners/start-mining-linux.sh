#!/bin/bash
echo "========================================"
echo "  HashLatch (HLC) - KawPow Miner"
echo "========================================"
echo ""

POOL="34.185.173.154"
PORT="3052"
ALGO="kawpow"
TREX_VERSION="0.26.8"
TREX_DIR="$HOME/t-rex"

read -p "Enter your HLC address (starts with c): " WALLET

if [ -z "$WALLET" ]; then
    echo "ERROR: No address provided. Exiting."
    exit 1
fi

# Check if T-Rex is already installed
if [ -f "$TREX_DIR/t-rex" ]; then
    echo "T-Rex already installed. Skipping download."
elif [ -f "./t-rex" ]; then
    TREX_DIR="."
    echo "T-Rex found in current directory."
else
    echo "T-Rex not found. Downloading..."
    mkdir -p "$TREX_DIR"
    curl -L "https://github.com/trexminer/T-Rex/releases/download/${TREX_VERSION}/t-rex-${TREX_VERSION}-linux.tar.gz" \
        -o /tmp/t-rex.tar.gz
    tar -xzf /tmp/t-rex.tar.gz -C "$TREX_DIR"
    rm /tmp/t-rex.tar.gz
    chmod +x "$TREX_DIR/t-rex"
    echo "Download complete."
fi

echo ""
echo "Starting T-Rex miner..."
echo "Address: $WALLET"
echo "Pool:    $POOL:$PORT"
echo ""

"$TREX_DIR/t-rex" -a $ALGO \
    -o stratum+tcp://$POOL:$PORT \
    -u $WALLET.rig1 \
    -p x
