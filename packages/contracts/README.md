# contracts

Contratos Solidity (Foundry) para la capa de incentivos: `UsageLedger` (liquidación por lotes vía Merkle root en USDC sobre Base), y más adelante `StakeManager`/`SlashingModule`. Ver [`docs/roadmap.md`](../../docs/roadmap.md#fase-2--contrato-de-liquidación).

**Pendiente — Fase 2/3.** Setup cuando llegue el momento:

```bash
curl -L https://foundry.paradigm.xyz | bash && foundryup
cd packages/contracts && forge init --no-commit
forge install OpenZeppelin/openzeppelin-contracts
```
