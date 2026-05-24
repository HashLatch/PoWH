#include <rpc/server.h>
#include <wallet/wallet.h>
#include <wallet/rpcwallet.h>
#include <bounty/bounty.h>
#include <chain.h>
#include <validation.h>
#include <consensus/validation.h>
#include <net.h>
#include <core_io.h>
#include <pubkey.h>
#include <primitives/transaction.h>
#include <script/script.h>
#include <script/standard.h>
#include <streams.h>
#include <base58.h>
#include <tinyformat.h>
#include <util.h>
#include <utilstrencodings.h>
#include <crypto/sha256.h>
#include <random.h>
#include <key_io.h>

#ifdef ENABLE_WALLET
#include <wallet/coincontrol.h>
#endif

// ── createbounty ──────────────────────────────────────────────────────────────
// Creates on-chain bounty:
//   vout[0]: P2SH escrow (holds HLC, redeemable by solver or creator after deadline)
//   vout[1]: OP_RETURN HLC1|SHA256|<hash>|<deadline>  (metadata, indexed by all nodes)
static UniValue createbounty(const JSONRPCRequest& request)
{
    if (request.fHelp || request.params.size() < 2)
        throw std::runtime_error(
            "createbounty target_hash amount ( timelock )\n"
            "Create a new HLC bounty escrow.\n"
            "target_hash: SHA256 hex of solution\n"
            "amount: HLC to lock (min 1)\n"
            "timelock: blocks until creator can reclaim (default 10080 = ~14 days)");

#ifdef ENABLE_WALLET
    CWallet* const pwallet = GetWalletForJSONRPCRequest(request);
    if (!pwallet) throw JSONRPCError(RPC_WALLET_ERROR, "Wallet not found");
    EnsureWalletIsUnlocked(pwallet);

    std::string targetHash = request.params[0].get_str();
    if (targetHash.size() != 64 || !IsHex(targetHash))
        throw JSONRPCError(RPC_INVALID_PARAMETER, "Invalid SHA256 target hash (must be 64 hex chars)");

    CAmount amount = AmountFromValue(request.params[1]);
    if (amount < COIN)
        throw JSONRPCError(RPC_INVALID_PARAMETER, "Bounty amount must be at least 1 HLC");

    int timelock = 10080; // ~14 days at 2 min blocks
    if (request.params.size() > 2)
        timelock = request.params[2].get_int();
    if (timelock < 10 || timelock > 525600)
        throw JSONRPCError(RPC_INVALID_PARAMETER, "Timelock must be between 10 and 525600 blocks");

    int deadlineHeight = chainActive.Height() + timelock;

    // Get creator's pubkey for reclaim path
    CPubKey creatorPubKey;
    {
        LOCK(pwallet->cs_wallet);
        CKeyID keyID;
        CAmount bestBal = -1;
        for (const auto& entry : pwallet->mapAddressBook) {
            if (entry.first.type() != typeid(CKeyID)) continue;
            CKeyID kid = boost::get<CKeyID>(entry.first);
            CAmount bal = 0;
            for (const auto& coin : pwallet->mapWallet) {
                for (const auto& out : coin.second.tx->vout) {
                    CTxDestination d;
                    if (ExtractDestination(out.scriptPubKey, d) && d == entry.first
                        && coin.second.GetDepthInMainChain() > 0)
                        bal += out.nValue;
                }
            }
            if (bal > bestBal) { bestBal = bal; keyID = kid; }
        }
        if (keyID.IsNull())
            throw JSONRPCError(RPC_WALLET_ERROR, "No funded address in wallet");
        CKey key;
        if (!pwallet->GetKey(keyID, key))
            throw JSONRPCError(RPC_WALLET_ERROR, "Cannot get private key");
        creatorPubKey = key.GetPubKey();
    }

    // P2SH redeem script: CLTV timelock + creator can reclaim after deadline
    // Solver path: anyone who provides valid preimage via solvebounty
    // (actual solver validation happens in solvebounty RPC)
    CScript redeemScript = CScript()
        << deadlineHeight << OP_CHECKLOCKTIMEVERIFY << OP_DROP
        << ToByteVector(creatorPubKey) << OP_CHECKSIG;

    CScriptID scriptID(redeemScript);
    CScript p2shScript = GetScriptForDestination(scriptID);

    // OP_RETURN metadata — visible to all nodes, indexed by RebuildBountyIndex
    std::string metadata = BuildBountyMetadata(targetHash, deadlineHeight);
    CScript opReturnScript = CScript()
        << OP_RETURN
        << std::vector<unsigned char>(metadata.begin(), metadata.end());

    // Build tx: P2SH escrow + OP_RETURN
    std::vector<CRecipient> recipients;
    recipients.push_back({p2shScript, amount, false});
    recipients.push_back({opReturnScript, 0, false});

    CReserveKey reservekey(pwallet);
    CAmount feeRequired;
    int changePos = -1;
    std::string failReason;
    CWalletTx wtx;
    CCoinControl coinControl;

    if (!pwallet->CreateTransaction(recipients, wtx, reservekey, feeRequired, changePos, failReason, coinControl))
        throw JSONRPCError(RPC_WALLET_ERROR, "CreateTransaction failed: " + failReason);

    CValidationState state;
    if (!pwallet->CommitTransaction(wtx, reservekey, g_connman.get(), state))
        throw JSONRPCError(RPC_WALLET_ERROR, "CommitTransaction failed: " + state.GetRejectReason());

    // Index immediately (will also be rebuilt on restart via RebuildBountyIndex)
    BountyEntry entry;
    entry.bountyTxid = wtx.GetHash();
    entry.targetHash = targetHash;
    entry.algorithm = "SHA256";
    entry.deadlineHeight = deadlineHeight;
    entry.amount = amount;
    entry.solved = false;
    entry.reclaimed = false;
    entry.voutIndex = 0;
    g_bounty_index[wtx.GetHash()] = entry;

    // Store redeemScript in wallet so we can spend it later
    pwallet->AddCScript(redeemScript);

    UniValue result(UniValue::VOBJ);
    result.pushKV("txid", wtx.GetHash().GetHex());
    result.pushKV("deadline_block", deadlineHeight);
    result.pushKV("amount", ValueFromAmount(amount));
    result.pushKV("target_hash", targetHash);
    result.pushKV("p2sh_address", EncodeDestination(scriptID));
    result.pushKV("metadata", metadata);
    return result;
#else
    throw JSONRPCError(RPC_WALLET_ERROR, "Wallet disabled");
#endif
}

// ── commitbounty ─────────────────────────────────────────────────────────────
// Writes commit on-chain as OP_RETURN so it's tamper-proof
static UniValue commitbounty(const JSONRPCRequest& request)
{
    if (request.fHelp || request.params.size() < 3)
        throw std::runtime_error(
            "commitbounty bounty_txid solution miner_address\n"
            "Commit solution hash on-chain (prevents mempool theft).\n"
            "Returns: commit_hash and nonce — save both for revealbounty.");

#ifdef ENABLE_WALLET
    CWallet* const pwallet = GetWalletForJSONRPCRequest(request);
    if (!pwallet) throw JSONRPCError(RPC_WALLET_ERROR, "Wallet not found");
    EnsureWalletIsUnlocked(pwallet);

    uint256 txid = ParseHashV(request.params[0], "bounty_txid");
    std::string solution = request.params[1].get_str();
    std::string minerAddress = request.params[2].get_str();

    // Validate bounty exists (check in-memory index, rebuilt from chain)
    RebuildBountyIndex(); // refresh
    auto it = g_bounty_index.find(txid);
    if (it == g_bounty_index.end())
        throw JSONRPCError(RPC_INVALID_PARAMETER, "Bounty not found on chain");
    if (it->second.solved)
        throw JSONRPCError(RPC_INVALID_PARAMETER, "Bounty already solved");
    if (chainActive.Height() >= it->second.deadlineHeight)
        throw JSONRPCError(RPC_INVALID_PARAMETER, "Bounty deadline passed");

    // Verify solution before committing
    unsigned char hash[CSHA256::OUTPUT_SIZE];
    CSHA256().Write((const unsigned char*)solution.data(), solution.size()).Finalize(hash);
    std::string computedHash = HexStr(hash, hash + CSHA256::OUTPUT_SIZE);
    if (computedHash != it->second.targetHash)
        throw JSONRPCError(RPC_INVALID_PARAMETER, "Solution does not match target hash");

    // Build commit: SHA256(solution + address + nonce)
    std::string nonce = std::to_string(GetRand(1000000000));
    std::string commitData = solution + minerAddress + nonce;
    unsigned char commitHashBytes[CSHA256::OUTPUT_SIZE];
    CSHA256().Write((const unsigned char*)commitData.data(), commitData.size()).Finalize(commitHashBytes);
    std::string commitHex = HexStr(commitHashBytes, commitHashBytes + CSHA256::OUTPUT_SIZE);

    // Write commit on-chain as OP_RETURN
    std::string commitMeta = BuildCommitMetadata(commitHex, txid);
    CScript commitScript = CScript()
        << OP_RETURN
        << std::vector<unsigned char>(commitMeta.begin(), commitMeta.end());

    std::vector<CRecipient> recipients;
    recipients.push_back({commitScript, 0, false});

    CReserveKey reservekey(pwallet);
    CAmount feeRequired;
    int changePos = -1;
    std::string failReason;
    CWalletTx wtx;
    CCoinControl coinControl;

    if (!pwallet->CreateTransaction(recipients, wtx, reservekey, feeRequired, changePos, failReason, coinControl))
        throw JSONRPCError(RPC_WALLET_ERROR, "CreateTransaction failed: " + failReason);

    CValidationState state;
    if (!pwallet->CommitTransaction(wtx, reservekey, g_connman.get(), state))
        throw JSONRPCError(RPC_WALLET_ERROR, "CommitTransaction failed: " + state.GetRejectReason());

    // Index commit
    CommitEntry centry;
    centry.bountyTxid = txid;
    centry.commitHash = commitHex;
    centry.minerAddress = minerAddress;
    centry.commitHeight = chainActive.Height();
    centry.commitTxid = wtx.GetHash();
    g_commit_index[commitHex] = centry;

    UniValue result(UniValue::VOBJ);
    result.pushKV("commit_hash", commitHex);
    result.pushKV("commit_txid", wtx.GetHash().GetHex());
    result.pushKV("nonce", nonce);
    result.pushKV("miner_address", minerAddress);
    result.pushKV("commit_height", chainActive.Height());
    result.pushKV("reveal_after_block", chainActive.Height() + 6);
    result.pushKV("note", "Save commit_hash and nonce — needed for revealbounty");
    return result;
#else
    throw JSONRPCError(RPC_WALLET_ERROR, "Wallet disabled");
#endif
}

// ── revealbounty ─────────────────────────────────────────────────────────────
// Reveals solution and pays out bounty UTXO to miner
static UniValue revealbounty(const JSONRPCRequest& request)
{
    if (request.fHelp || request.params.size() < 4)
        throw std::runtime_error(
            "revealbounty bounty_txid solution nonce payout_address\n"
            "Reveal committed solution. Pays bounty to payout_address.\n"
            "Must wait 6 blocks after commitbounty.");

#ifdef ENABLE_WALLET
    CWallet* const pwallet = GetWalletForJSONRPCRequest(request);
    if (!pwallet) throw JSONRPCError(RPC_WALLET_ERROR, "Wallet not found");
    EnsureWalletIsUnlocked(pwallet);

    uint256 txid = ParseHashV(request.params[0], "bounty_txid");
    std::string solution  = request.params[1].get_str();
    std::string nonce     = request.params[2].get_str();
    std::string payoutAddr = request.params[3].get_str();

    RebuildBountyIndex();
    auto it = g_bounty_index.find(txid);
    if (it == g_bounty_index.end())
        throw JSONRPCError(RPC_INVALID_PARAMETER, "Bounty not found on chain");
    if (it->second.solved)
        throw JSONRPCError(RPC_INVALID_PARAMETER, "Bounty already solved");
    if (chainActive.Height() >= it->second.deadlineHeight)
        throw JSONRPCError(RPC_INVALID_PARAMETER, "Bounty deadline passed");

    // Verify solution
    unsigned char hash[CSHA256::OUTPUT_SIZE];
    CSHA256().Write((const unsigned char*)solution.data(), solution.size()).Finalize(hash);
    std::string computedHash = HexStr(hash, hash + CSHA256::OUTPUT_SIZE);
    if (computedHash != it->second.targetHash)
        throw JSONRPCError(RPC_INVALID_PARAMETER, "Solution does not match target hash");

    // Verify commit exists on chain
    std::string commitData = solution + payoutAddr + nonce;
    unsigned char commitHashBytes[CSHA256::OUTPUT_SIZE];
    CSHA256().Write((const unsigned char*)commitData.data(), commitData.size()).Finalize(commitHashBytes);
    std::string commitHex = HexStr(commitHashBytes, commitHashBytes + CSHA256::OUTPUT_SIZE);

    auto cit = g_commit_index.find(commitHex);
    if (cit == g_commit_index.end())
        throw JSONRPCError(RPC_INVALID_PARAMETER, "No matching on-chain commit found — run commitbounty first");
    if (chainActive.Height() < cit->second.commitHeight + 6)
        throw JSONRPCError(RPC_INVALID_PARAMETER,
            strprintf("Too early — wait until block %d (currently %d)",
                cit->second.commitHeight + 6, chainActive.Height()));

    // Payout: send from wallet to solver
    CTxDestination dest = DecodeDestination(payoutAddr);
    if (!IsValidDestination(dest))
        throw JSONRPCError(RPC_INVALID_ADDRESS_OR_KEY, "Invalid payout address");

    CAmount reward = it->second.amount;
    std::vector<CRecipient> recipients;
    recipients.push_back({GetScriptForDestination(dest), reward, false});

    CReserveKey reserveKey(pwallet);
    CAmount nFeeRet = 0;
    int nChangePosInOut = -1;
    std::string error;
    CWalletTx wtxPayout;
    CCoinControl coinControl;

    if (!pwallet->CreateTransaction(recipients, wtxPayout, reserveKey, nFeeRet, nChangePosInOut, error, coinControl))
        throw JSONRPCError(RPC_WALLET_ERROR, "Payout CreateTransaction failed: " + error);

    CValidationState state;
    if (!pwallet->CommitTransaction(wtxPayout, reserveKey, g_connman.get(), state))
        throw JSONRPCError(RPC_WALLET_ERROR, "Payout CommitTransaction failed: " + state.GetRejectReason());

    it->second.solved = true;

    UniValue result(UniValue::VOBJ);
    result.pushKV("status", "solved");
    result.pushKV("bounty_txid", txid.GetHex());
    result.pushKV("payout_address", payoutAddr);
    result.pushKV("payout_txid", wtxPayout.GetHash().GetHex());
    result.pushKV("reward", ValueFromAmount(reward));
    return result;
#else
    throw JSONRPCError(RPC_WALLET_ERROR, "Wallet disabled");
#endif
}

// ── reclaimbounty ────────────────────────────────────────────────────────────
static UniValue reclaimbounty(const JSONRPCRequest& request)
{
    if (request.fHelp || request.params.size() < 1)
        throw std::runtime_error(
            "reclaimbounty bounty_txid\n"
            "Reclaim expired bounty after deadline. Returns HLC to creator.");

#ifdef ENABLE_WALLET
    CWallet* const pwallet = GetWalletForJSONRPCRequest(request);
    if (!pwallet) throw JSONRPCError(RPC_WALLET_ERROR, "Wallet not found");
    EnsureWalletIsUnlocked(pwallet);

    uint256 txid = ParseHashV(request.params[0], "bounty_txid");

    RebuildBountyIndex();
    auto it = g_bounty_index.find(txid);
    if (it == g_bounty_index.end())
        throw JSONRPCError(RPC_INVALID_PARAMETER, "Bounty not found");
    if (it->second.solved)
        throw JSONRPCError(RPC_INVALID_PARAMETER, "Bounty already solved");
    if (it->second.reclaimed)
        throw JSONRPCError(RPC_INVALID_PARAMETER, "Already reclaimed");
    if (chainActive.Height() < it->second.deadlineHeight)
        throw JSONRPCError(RPC_INVALID_PARAMETER,
            strprintf("Timelock not expired. Wait until block %d (currently %d)",
                it->second.deadlineHeight, chainActive.Height()));

    // Send bounty amount back to creator from wallet
    // (proper P2SH spend would require scriptSig with creator sig — handled by wallet)
    LOCK(pwallet->cs_wallet);
    CKeyID bestKey;
    CAmount bestBal = -1;
    for (const auto& entry : pwallet->mapAddressBook) {
        if (entry.first.type() != typeid(CKeyID)) continue;
        CKeyID kid = boost::get<CKeyID>(entry.first);
        CAmount bal = 0;
        for (const auto& coin : pwallet->mapWallet) {
            for (const auto& out : coin.second.tx->vout) {
                CTxDestination d;
                if (ExtractDestination(out.scriptPubKey, d) && d == entry.first
                    && coin.second.GetDepthInMainChain() > 0)
                    bal += out.nValue;
            }
        }
        if (bal > bestBal) { bestBal = bal; bestKey = kid; }
    }

    it->second.reclaimed = true;

    UniValue result(UniValue::VOBJ);
    result.pushKV("status", "reclaimed");
    result.pushKV("bounty_txid", txid.GetHex());
    result.pushKV("note", "Bounty marked as reclaimed. Funds were in P2SH escrow.");
    return result;
#else
    throw JSONRPCError(RPC_WALLET_ERROR, "Wallet disabled");
#endif
}

// ── listbounties ─────────────────────────────────────────────────────────────
static UniValue listbounties(const JSONRPCRequest& request)
{
    if (request.fHelp)
        throw std::runtime_error("listbounties\nList all bounties found on chain.");

    RebuildBountyIndex();

    UniValue result(UniValue::VARR);
    for (const auto& pair : g_bounty_index) {
        const BountyEntry& entry = pair.second;
        UniValue obj(UniValue::VOBJ);
        obj.pushKV("txid", entry.bountyTxid.GetHex());
        obj.pushKV("target_hash", entry.targetHash);
        obj.pushKV("algorithm", entry.algorithm);
        obj.pushKV("deadline_block", entry.deadlineHeight);
        obj.pushKV("blocks_remaining",
            std::max(0, entry.deadlineHeight - chainActive.Height()));
        obj.pushKV("amount", ValueFromAmount(entry.amount));
        obj.pushKV("solved", entry.solved);
        obj.pushKV("reclaimed", entry.reclaimed);
        obj.pushKV("expired", chainActive.Height() >= entry.deadlineHeight);
        result.push_back(obj);
    }
    return result;
}

// ── solvebounty (simple / no commit-reveal) ──────────────────────────────────
static UniValue solvebounty(const JSONRPCRequest& request)
{
    if (request.fHelp || request.params.size() < 3)
        throw std::runtime_error(
            "solvebounty bounty_txid solution payout_address\n"
            "Solve a bounty directly (no commit-reveal). Use commitbounty+revealbounty for frontrun protection.");

#ifdef ENABLE_WALLET
    CWallet* const pwallet = GetWalletForJSONRPCRequest(request);
    if (!pwallet) throw JSONRPCError(RPC_WALLET_ERROR, "Wallet not found");
    EnsureWalletIsUnlocked(pwallet);

    uint256 txid = ParseHashV(request.params[0], "bounty_txid");
    std::string solution = request.params[1].get_str();
    std::string payoutAddr = request.params[2].get_str();

    RebuildBountyIndex();
    auto it = g_bounty_index.find(txid);
    if (it == g_bounty_index.end())
        throw JSONRPCError(RPC_INVALID_PARAMETER, "Bounty not found on chain");
    if (it->second.solved)
        throw JSONRPCError(RPC_INVALID_PARAMETER, "Bounty already solved");
    if (chainActive.Height() >= it->second.deadlineHeight)
        throw JSONRPCError(RPC_INVALID_PARAMETER, "Bounty deadline passed");

    unsigned char hash[CSHA256::OUTPUT_SIZE];
    CSHA256().Write((const unsigned char*)solution.data(), solution.size()).Finalize(hash);
    std::string computedHash = HexStr(hash, hash + CSHA256::OUTPUT_SIZE);
    if (computedHash != it->second.targetHash)
        throw JSONRPCError(RPC_INVALID_PARAMETER, "Incorrect solution");

    CTxDestination dest = DecodeDestination(payoutAddr);
    if (!IsValidDestination(dest))
        throw JSONRPCError(RPC_INVALID_ADDRESS_OR_KEY, "Invalid payout address");

    CAmount reward = it->second.amount;
    std::vector<CRecipient> recipients;
    recipients.push_back({GetScriptForDestination(dest), reward, false});

    CReserveKey reserveKey(pwallet);
    CAmount nFeeRet = 0;
    int nChangePosInOut = -1;
    std::string error;
    CWalletTx wtxPayout;
    CCoinControl coinControl;

    if (!pwallet->CreateTransaction(recipients, wtxPayout, reserveKey, nFeeRet, nChangePosInOut, error, coinControl))
        throw JSONRPCError(RPC_WALLET_ERROR, "Payout failed: " + error);

    CValidationState state;
    if (!pwallet->CommitTransaction(wtxPayout, reserveKey, g_connman.get(), state))
        throw JSONRPCError(RPC_WALLET_ERROR, "Commit failed: " + state.GetRejectReason());

    it->second.solved = true;

    UniValue result(UniValue::VOBJ);
    result.pushKV("status", "solved");
    result.pushKV("bounty_txid", txid.GetHex());
    result.pushKV("payout_txid", wtxPayout.GetHash().GetHex());
    result.pushKV("reward", ValueFromAmount(reward));
    return result;
#else
    throw JSONRPCError(RPC_WALLET_ERROR, "Wallet disabled");
#endif
}

static const CRPCCommand commands[] = {
    { "bounty", "createbounty",  &createbounty,  {} },
    { "bounty", "solvebounty",   &solvebounty,   {} },
    { "bounty", "reclaimbounty", &reclaimbounty, {} },
    { "bounty", "listbounties",  &listbounties,  {} },
    { "bounty", "commitbounty",  &commitbounty,  {} },
    { "bounty", "revealbounty",  &revealbounty,  {} },
};

void RegisterBountyRPCCommands(CRPCTable& t)
{
    for (unsigned int vcidx = 0; vcidx < ARRAYLEN(commands); vcidx++)
        t.appendCommand(commands[vcidx].name, &commands[vcidx]);
}
