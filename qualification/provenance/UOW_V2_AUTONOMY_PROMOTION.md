# UoW-v2 Autonomy Production Promotion Provenance

## Baseline Lineage

- **Source qualified commit:** `c559d6c1c962b436fa9c05c68de42f29afa4ad6f`
- **Architecture baseline:** `004104ba3fba7e855bf42580d467e7d24f6e5dab`
- **Freeze digest:** `8bc28b79646a72aff2f389d007592169a859b69c8904ca723ff3dffa9f01d35d`
- **Frozen evaluator tag:** `e1c-gate0-evaluator`
- **Integration strategy:** Qualified-reference to condensed production transplant (PR #54 preserved as research history)

## Operational Parameters

- **Canonical Authority Stack:** `WorldState`, `canonical_json`, `UoW`, `ApplicationSpine`, `CommitSequencer`, `EvidenceLedger` reused without replacement.
- **Production Autonomy Package:** `src/uow/autonomy/`
- **Authority Boundary Invariant:** `Autonomy decides/proposes work; existing UoW machinery governs work.` The controller executes work items exclusively through `ExecutionPort` -> `ApplicationSpine` -> `PROPOSE -> CERTIFY -> COMMIT`. Direct mutation of authoritative state is rejected.

## Status

- **Differential conformance:** IN_PROGRESS
- **Authority-boundary test:** PENDING
- **Production promotion commit:** PENDING
