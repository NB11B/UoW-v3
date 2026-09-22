# Continuous Adaptation Canonicalization Review

**Compared:** `main` @ `d9f9750a3c2bfb0a9c46bb9b49ef00a8196b07e8`  
**Research branch:** `qualification/continuous-adaptation-v1`  
**Physically qualified research head:** `1f1f53f6c269f87bf23a9a8643766cb2927f0f0b`

## Executive review

The branch is architecturally well-contained.

Nearly all substantive implementation, hardware adapters, models, tests, and evidence live under:

```text
qualification/embedded/esp32_dual_core/
```

The canonical `src/uow` package and its public API are not modified by the continuous-adaptation work. Repository-wide changes are limited to CI workflow coverage and ignore rules.

This makes the branch suitable for preservation as a **qualification/research lineage** without silently redefining the canonical UoW runtime.

## What belongs in the repository

### A. Retain as qualification architecture

These mechanisms directly express or test demonstrated UoW architectural properties and should be retained in the qualification tree:

- ESP32 authority state and certify/commit/reject boundary;
- state-hash preconditions and OCC retry behavior;
- two-stage scheduling reservation/receipt protocol;
- bounded resource and device-online authority checks;
- hash-chained evidence root;
- external proposer protocol;
- reboot/persistence qualification;
- asynchronous worker-pool qualification;
- stochastic environment qualification;
- canary promotion/rollback qualification;
- distribution and endurance metrics.

These are qualification realizations of the architectural separation:

[
	ext{adaptive proposal / realization}
perp
	ext{authoritative state mutation}
]

They do not need to become dependencies of the canonical Python package.

### B. Retain as evidence and reproducibility assets

Retain:

- `HARDWARE_RESULTS.md`;
- `EXTERNAL_PROPOSER_TEST.md`;
- `ROUTER_CAMPAIGN_RESULTS.md`;
- `QUALIFICATION_SEAL.md`;
- `QUALIFICATION_MANIFEST.json`;
- compact JSON result artifacts;
- the full router campaign report;
- test suites and portable C++ qualification.

The full router report is large but still modest enough to preserve as a research artifact and provides useful per-job auditability.

### C. Retain as optional hardware-specific assets

These should remain explicitly optional and qualification-scoped:

- `intel_npu_adapter.py`;
- `adaptive_npu_experiment.py`;
- `workload_engine.py`;
- `routing_policy.py`;
- `minsky_npu.onnx`;
- NVIDIA/Intel-specific execution paths.

They demonstrate heterogeneous capability but are not required by the canonical UoW model.

## What should not be promoted into canonical core yet

Do not currently move the following into `src/uow` as general runtime guarantees:

- Intel NPU/OpenVINO-specific APIs;
- CUDA/PyTorch training loops;
- the benchmark vision model;
- stochastic environment generator;
- fixed router neural architecture;
- the serial command protocol as a universal UoW wire protocol;
- ESP32 NVS persistence as a general durability theorem;
- the current scheduling state structure as the only valid scheduler representation.

They are proven implementations for this campaign, not necessary definitions of UoW.

## Technical cleanup completed during seal

1. Scheduling evidence is documented as a **SHA-256 hash chain**, not a Merkle tree.
2. Gate `G1` is clarified so successful policy avoidance of an offline device is not confused with failure to test authority enforcement.
3. Physical evidence is pinned to the exact qualified research head.
4. A machine-readable blob manifest records source/test/result identities.
5. Portable CI coverage has been added for the adaptive host test suite.
6. ESP32 firmware CI is triggered on the continuous-adaptation branch.

## Integration dependency

The continuous-adaptation branch contains the complete unmerged ESP32 qualification lineage that was previously reviewed in PR #8.

Therefore there are two valid integration paths.

### Preferred: preserve review separation

1. complete review and merge of the foundational ESP32 qualification lineage;
2. update/rebase the continuous-adaptation branch onto the new `main`;
3. review the remaining continuous-adaptation delta;
4. merge that delta separately.

This preserves a clear distinction between:

```text
hardware authority qualification
        ↓
adaptive heterogeneous runtime qualification
```

### Alternative: one lineage merge

Merge the continuous-adaptation branch directly, which subsumes the foundational ESP32 qualification lineage.

This is mechanically simpler but produces a much larger single review and collapses the historical separation between the baseline hardware qualification and the later adaptation program.

## Current review conclusion

The research work is appropriately isolated and does not require changes to the canonical UoW public API.

The recommended repository treatment is:

[
oxed{
	ext{retain the entire lineage under qualification/}
quad+quad
	ext{do not promote hardware/model-specific code into core}
}
]

The branch is suitable for draft-PR review once portable CI is green.

No merge is authorized or implied by this review.
