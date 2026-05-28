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

# Check if T-Rex is already installed and working
if [ -f "$TREX_DIR/t-rex" ] && "$TREX_DIR/t-rex" --version &>/dev/null; then
    echo "T-Rex already installed."
elif [ -f "./t-rex" ] && "./t-rex" --version &>/dev/null; then
    TREX_DIR="."
    echo "T-Rex found in current directory."
else
    echo "T-Rex not found or corrupted. Downloading..."
    mkdir -p "$TREX_DIR"
    
    # Download with retry and verification
    MAX_RETRIES=3
    RETRY=0
    SUCCESS=0
    
    while [ $RETRY -lt $MAX_RETRIES ]; do
        echo "Download attempt $((RETRY+1))/$MAX_RETRIES..."
        curl -L --retry 3 --retry-delay 5 --connect-timeout 30             "https://github.com/trexminer/T-Rex/releases/download/${TREX_VERSION}/t-rex-${TREX_VERSION}-linux.tar.gz"             -o /tmp/t-rex.tar.gz
        
        # Verify download
        if [ -f /tmp/t-rex.tar.gz ] && [ $(stat -c%s /tmp/t-rex.tar.gz) -gt 1000000 ]; then
            echo "Download OK, extracting..."
            tar -xzf /tmp/t-rex.tar.gz -C "$TREX_DIR" && SUCCESS=1 && break
        fi
        
        echo "Download failed or file too small, retrying..."
        rm -f /tmp/t-rex.tar.gz
        RETRY=$((RETRY+1))
        sleep 5
    done
    
    rm -f /tmp/t-rex.tar.gz
    
    if [ $SUCCESS -eq 0 ]; then
        echo "ERROR: Failed to download T-Rex after $MAX_RETRIES attempts."
        echo "Try manually: https://github.com/trexminer/T-Rex/releases/tag/v${TREX_VERSION}"
        exit 1
    fi
    
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
