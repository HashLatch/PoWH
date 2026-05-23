var myCoin = {
    "name": "HashLatch",
    "symbol": "HLC",
    "algorithm": "kawpow",
    "peerMagic": "50574858",
    "peerMagicTestnet": "50574858"
};

var Stratum = require('./lib/index.js');
var pool = Stratum.createPool({
    "coin": myCoin,
    "address": "cUkzPSrC26NzCjaUc3AGxhziQpGuh6Ee1v",
    "rewardRecipients": {"cXgJpaAwQu7VZLkS6Berw3VTuLNLAMTH8d": 2},
    "kawpow_validator": "daemon",
    "blockRefreshInterval": 5000,
    "getNewBlockAfterFound": true,
    "jobRebroadcastTimeout": 55,
    "connectionTimeout": 1200,
    "tcpProxyProtocol": false,
    "banning": {
        "enabled": false
    },
    "ports": {
        "3052": {
            "diff": 0.001,
            "varDiff": {
                "minDiff": 0.0001,
                "maxDiff": 1,
                "targetTime": 15,
                "retargetTime": 60,
                "variancePercent": 30
            }
        }
    },
    "daemons": [
        {
            "host": "127.0.0.1",
            "port": 8766,
            "user": "hashlatch",
            "password": "test123"
        }
    ],
    "p2p": {
        "enabled": false
    }
}, function(ip, port, workerName, password, extraNonce1, version, callback) {
    callback({
        error: null,
        authorized: true,
        disconnect: false
    });
});

pool.on('share', function(isValidShare, isValidBlock, data) {
    if (isValidBlock) console.log('BLOCK FOUND! ' + JSON.stringify(data));
    else if (isValidShare) console.log('Share accepted from ' + data.worker);
    else console.log('Share rejected: ' + JSON.stringify(data));
});

pool.on('log', function(severity, logKey, logText) {
    console.log('[' + severity + '] [' + logKey + '] ' + logText);
});

pool.start();
console.log('HashLatch KawPow Stratum started on port 3052');
