# UoW-v2 Autonomy Production Promotion Provenance

## Baseline Lineage

- **Source qualified commit:** `c559d6c1c962b436fa9c05c68de42f29afa4ad6f`
- **Architecture baseline:** `004104ba3fba7e855bf42580d467e7d24f6e5dab`
- **Freeze digest:** `8bc28b79646a72aff2f389d007592169a859b69c8904ca723ff3dffa9f01d35d`
- **Frozen evaluator tag:** `e1c-gate0-evaluator`
- **Integration strategy:** Qualified-reference to condensed production transplant (PR #54 preserved as research history)
- **Production candidate commit:** `230a7d10b6aa514dd655d60acc07a665d9677951` (PR #55)
- **Production merge commit (`main`):** `7cfc56bbdbe5100a791a1971fcf09c4fa4cb6102`

## Operational Parameters

- **Canonical Authority Stack:** `WorldState`, `canonical_json`, `UoW`, `ApplicationSpine`, `CommitSequencer`, `EvidenceLedger` reused directly without shadow replacement.
- **Production Autonomy Package:** `src/uow/autonomy/`
- **Minimal Public Surface:** `AutonomousRuntime`, `AutonomyBudget`, `AutonomyRequest`, `AutonomyResult`, `CapabilitySpec`, `ExecutionPort`, `GoalSpec`, `TerminalDisposition`.
- **Frozen Seven-Letter Work Basis:** `O, E, K, C, F, D, S` certified at SHA-256 `5b6aad2b30a1225f7443327dbdbe7644b3977f964ea79135fc6e0c42f67a5b6f`.
- **Authority Boundary Invariant:** $\boxed{\text{Autonomy decides/proposes work; existing UoW machinery governs work.}}$
  The controller executes work items exclusively through `ExecutionPort` -> `ApplicationSpine` (`PROPOSE -> CERTIFY -> COMMIT`). Direct mutation of authoritative state or direct calls to `commit()` are strictly forbidden.

## Verification Status

- **Differential reference conformance:** PASS (12/12 test cases against frozen reference vectors at `tests/fixtures/autonomy_reference_c559d6c.json`, SHA-256 `941adef420a283d123aab1f40dabc54cea3030a4f19e2331581441fa371e59b7`)
- **Authority-boundary enforcement:** PASS (4/4 tests: Spine execution, unauthorized denial, self-grant rejection, certification isolation)
- **Public API namespace isolation:** PASS (4/4 tests: public surface import, zero research imports in fresh subprocess, clean root `uow` namespace, simulated smoke test)
- **Full regression test suite:** PASS (562 passed, 81 warnings, 0 failures)
- **Lint / Static analysis:** PASS (`ruff check src/uow/autonomy` clean, `compileall src/uow` clean, zero forbidden research imports in `src/uow`)
