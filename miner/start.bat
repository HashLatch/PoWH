@echo off
echo === HashLatch GPU Miner ===
set /p addr="Enter your HLC address: "
echo Starting miner for address: %addr%
srbminer.exe --algorithm kawpow --pool 92.5.32.114:18767 --wallet %addr% --password x
pause
