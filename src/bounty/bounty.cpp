#include <sstream>
#include "bounty/bounty.h"
#include "script/script.h"
#include "utilstrencodings.h"
#include "chain.h"
#include "validation.h"
#include "txmempool.h"
#include "chainparams.h"

std::map<uint256, BountyEntry> g_bounty_index;
std::map<std::string, CommitEntry> g_commit_index;

bool IsBountyOpReturn(const CScript& script)
{
    if (script.size() < 6) return false;
    if (script[0] != OP_RETURN) return false;
    opcodetype opcode;
    std::vector<unsigned char> data;
    CScript::const_iterator pc = script.begin();
    if (!script.GetOp(pc, opcode)) return false;
    if (!script.GetOp(pc, opcode, data)) return false;
    if (data.size() < 12) return false;
    std::string s(data.begin(), data.begin() + 12);
    return s == BOUNTY_PREFIX;
}

bool IsCommitOpReturn(const CScript& script)
{
    if (script.size() < 5) return false;
    if (script[0] != OP_RETURN) return false;
    opcodetype opcode;
    std::vector<unsigned char> data;
    CScript::const_iterator pc = script.begin();
    if (!script.GetOp(pc, opcode)) return false;
    if (!script.GetOp(pc, opcode, data)) return false;
    if (data.size() < 12) return false;
    std::string s(data.begin(), data.begin() + 12);
    return s == COMMIT_PREFIX;
}

std::string BuildBountyMetadata(const std::string& targetHash, int deadlineHeight)
{
    return BOUNTY_PREFIX + targetHash + "|" + std::to_string(deadlineHeight);
}

std::string BuildCommitMetadata(const std::string& commitHash, const uint256& bountyTxid)
{
    return COMMIT_PREFIX + commitHash + "|" + bountyTxid.GetHex();
}

bool ParseBountyMetadata(const CScript& script, BountyEntry& entry)
{
    if (!IsBountyOpReturn(script)) return false;
    opcodetype opcode;
    std::vector<unsigned char> data;
    CScript::const_iterator pc = script.begin();
    if (!script.GetOp(pc, opcode)) return false;
    if (!script.GetOp(pc, opcode, data)) return false;
    std::string metadata(data.begin(), data.end());

    std::vector<std::string> parts;
    std::stringstream ss(metadata);
    std::string item;
    while (std::getline(ss, item, '|')) parts.push_back(item);

    if (parts.size() != 4) return false;
    if (parts[0] != "HLC1") return false;
    if (parts[1] != "SHA256") return false;
    if (parts[2].size() != 64 || !IsHex(parts[2])) return false;

    entry.algorithm = parts[1];
    entry.targetHash = parts[2];
    entry.deadlineHeight = atoi(parts[3].c_str());
    entry.solved = false;
    entry.reclaimed = false;
    return true;
}

bool ParseCommitMetadata(const CScript& script, CommitEntry& entry)
{
    if (!IsCommitOpReturn(script)) return false;
    opcodetype opcode;
    std::vector<unsigned char> data;
    CScript::const_iterator pc = script.begin();
    if (!script.GetOp(pc, opcode)) return false;
    if (!script.GetOp(pc, opcode, data)) return false;
    std::string metadata(data.begin(), data.end());

    std::vector<std::string> parts;
    std::stringstream ss(metadata);
    std::string item;
    while (std::getline(ss, item, '|')) parts.push_back(item);

    if (parts.size() != 4) return false;
    if (parts[0] != "HLC1") return false;
    if (parts[1] != "COMMIT") return false;
    if (parts[2].size() != 64 || !IsHex(parts[2])) return false;
    if (parts[3].size() != 64 || !IsHex(parts[3])) return false;

    entry.commitHash = parts[2];
    entry.bountyTxid.SetHex(parts[3]);
    return true;
}

void RebuildBountyIndex(int fromHeight)
{
    g_bounty_index.clear();
    g_commit_index.clear();

    if (!chainActive.Tip()) return;

    int height = std::max(0, fromHeight);
    CBlockIndex* pindex = chainActive[height];

    while (pindex) {
        CBlock block;
        if (!ReadBlockFromDisk(block, pindex, GetParams().GetConsensus())) {
            pindex = chainActive.Next(pindex);
            continue;
        }

        for (const auto& tx : block.vtx) {
            uint256 txid = tx->GetHash();
            bool hasBountyOutput = false;
            int bountyVout = -1;
            CAmount bountyAmount = 0;

            // Scan outputs for bounty OP_RETURN
            for (int i = 0; i < (int)tx->vout.size(); i++) {
                const CTxOut& out = tx->vout[i];
                BountyEntry entry;
                if (ParseBountyMetadata(out.scriptPubKey, entry)) {
                    entry.bountyTxid = txid;
                    // Find the hashlock output (OP_SHA256 <32> OP_EQUAL = 35 bytes)
                    for (int j = 0; j < (int)tx->vout.size(); j++) {
                        const CScript& spk = tx->vout[j].scriptPubKey;
                        if (j != i && spk.size() == 35 &&
                            spk[0] == OP_SHA256 && spk[1] == 0x20 &&
                            spk[34] == OP_EQUAL) {
                            bountyVout = j;
                            bountyAmount = tx->vout[j].nValue;
                            break;
                        }
                    }
                    entry.voutIndex = bountyVout;
                    entry.amount = bountyAmount;
                    g_bounty_index[txid] = entry;
                    hasBountyOutput = true;
                }

                // Check if this tx spends a bounty (solved/reclaimed)
                CommitEntry centry;
                if (ParseCommitMetadata(out.scriptPubKey, centry)) {
                    centry.commitTxid = txid;
                    centry.commitHeight = pindex->nHeight;
                    g_commit_index[centry.commitHash] = centry;
                }
            }

            // Check if inputs spend a known bounty UTXO (= solved)
            for (const auto& in : tx->vin) {
                auto it = g_bounty_index.find(in.prevout.hash);
                if (it != g_bounty_index.end() &&
                    in.prevout.n == (uint32_t)it->second.voutIndex) {
                    it->second.solved = true;
                }
            }
        }
        pindex = chainActive.Next(pindex);
    }
}
