#!/usr/bin/env python3
"""
HashLatch Bounty Extractor - MVP
Generates bounty creation commands from passwords, files, and seed phrases.
"""

import hashlib
import sys
import os

VERSION = "1.0.0"

def sha256(data: str) -> str:
    return hashlib.sha256(data.encode()).hexdigest()

def extract_from_password(password: str):
    target = sha256(password)
    masked = password[0] + '*' * (len(password) - 2) + password[-1] if len(password) > 1 else password
    print(f"""
=== HashLatch Bounty Creator v{VERSION} ===
Task Type: SHA256 password cracking
Password (masked): {masked}
Target Hash: {target}

To create this bounty, use:
./src/hashlatch-cli createbounty "{target}" <amount> <deadline_blocks>

Example (10 HLC, 100 blocks deadline):
./src/hashlatch-cli createbounty "{target}" 10 100
""")

def extract_from_file(filename: str):
    if not os.path.exists(filename):
        print(f"Error: File '{filename}' not found.")
        sys.exit(1)
    with open(filename, 'rb') as f:
        data = f.read()
    target = sha256(data.hex())
    print(f"""
=== HashLatch Bounty Creator v{VERSION} ===
Task Type: File hash recovery
File: {filename}
File size: {len(data)} bytes
Target Hash: {target}

To create this bounty, use:
./src/hashlatch-cli createbounty "{target}" <amount> <deadline_blocks>
""")

def print_usage():
    print(f"""HashLatch Bounty Extractor v{VERSION}

Usage:
  python3 hashlatch-extractor.py --password <your_password>
  python3 hashlatch-extractor.py --file <path_to_file>

Examples:
  python3 hashlatch-extractor.py --password "MySecret123"
  python3 hashlatch-extractor.py --file wallet.dat
""")

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print_usage()
        sys.exit(1)
    mode = sys.argv[1]
    value = sys.argv[2]
    if mode == "--password":
        extract_from_password(value)
    elif mode == "--file":
        extract_from_file(value)
    else:
        print_usage()
        sys.exit(1)
