@echo off
echo ========================================
echo   HashLatch (HLC) - KawPow Miner
echo ========================================
echo.

set POOL=34.185.173.154
set PORT=3052
set ALGO=kawpow

if not exist "t-rex.exe" (
    echo T-Rex not found. Downloading...
    curl -L https://github.com/trexminer/T-Rex/releases/download/0.26.8/t-rex-0.26.8-win.zip -o t-rex.zip
    tar -xf t-rex.zip
    del t-rex.zip
    echo Download complete.
)

set /p WALLET="Enter your HLC address (starts with c): "

if "%WALLET%"=="" (
    echo ERROR: No address provided.
    pause
    exit /b 1
)

echo.
echo Starting T-Rex miner...
echo Address: %WALLET%
echo Pool:    %POOL%:%PORT%
echo.

t-rex.exe -a %ALGO% -o stratum+tcp://%POOL%:%PORT% -u %WALLET%.rig1 -p x

pause
