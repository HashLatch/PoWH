#include <iostream>
#include "chainparams.h"

int main() {
    // Dla regtest
    CRegTestParams params;
    std::cout << "Regtest Genesis Hash: " << params.GenesisBlock().GetHash().GetHex() << std::endl;
    std::cout << "Regtest Merkle Root: " << params.GenesisBlock().hashMerkleRoot.GetHex() << std::endl;
    return 0;
}
