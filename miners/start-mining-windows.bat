@echo off
echo Downloading GMiner...
curl -L -o gminer.zip https://github.com/develsoftware/GMinerRelease/releases/download/3.44/gminer_3_44_windows64.zip
tar -xf gminer.zip
set /p WALLET="Enter your HLC address: "
miner.exe --algo kawpow --server 34.185.173.154 --port 3052 --user %WALLET%.rig1 --pass x
pause
