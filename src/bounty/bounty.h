#ifndef HASHLOCK_BOUNTY_H
#define HASHLOCK_BOUNTY_H

#include <amount.h>
#include <uint256.h>
#include <script/script.h>
#include <primitives/transaction.h>
#include <map>
#include <string>

// Prefix for bounty OP_RETURN metadata
static const std::string BOUNTY_PREFIX = "HLC1|SHA256|";
static const std::string COMMIT_PREFIX = "HLC1|COMMIT|";

struct BountyEntry {
    uint256 bountyTxid;
    std::string targetHash;   // SHA256 of solution
    std::string algorithm;
    int deadlineHeight;
    CAmount amount;
    bool solved;
    bool reclaimed;
    int voutIndex;            // which vout holds the P2SH escrow
};

struct CommitEntry {
    uint256 bountyTxid;
    std::string commitHash;   // SHA256(solution + address + nonce)
    std::string minerAddress;
    int commitHeight;
    uint256 commitTxid;       // on-chain commit tx
};

// In-memory index rebuilt from blockchain on startup
extern std::map<uint256, BountyEntry> g_bounty_index;
extern std::map<std::string, CommitEntry> g_commit_index;

// Parse/build metadata
std::string BuildBountyMetadata(const std::string& targetHash, int deadlineHeight);
std::string BuildCommitMetadata(const std::string& commitHash, const uint256& bountyTxid);
bool ParseBountyMetadata(const CScript& script, BountyEntry& entry);
bool ParseCommitMetadata(const CScript& script, CommitEntry& entry);
bool IsBountyOpReturn(const CScript& script);
bool IsCommitOpReturn(const CScript& script);

// Rebuild index by scanning blockchain
void RebuildBountyIndex(int fromHeight = 0);

#endif
