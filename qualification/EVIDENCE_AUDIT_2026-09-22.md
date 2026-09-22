# Repository-Wide Evidence-Substrate Audit

**Policy:** `qualification/EVIDENCE_POLICY.md`  
**Physical enforcement campaign head:** `ed9a229f6e05adc7192f67086c3041f4aa8cfd33`  
**Audit date:** 2026-09-22

## Rule

A capability may only PASS when the mechanism/substrate named by the claim was actually exercised.

Portable and simulated runs remain valuable, but their evidence level is part of the claim.

## Audit coverage

This audit reviewed:

- canonical repository acceptance;
- standalone/reference acceptance;
- timing-independence qualification;
- proposer/TFWR integration tests;
- external-effects tests;
- ESP32/CPU/GPU/NPU qualification;
- external proposer and NPU adaptation harnesses;
- checked-in qualification reports and documentation.

## Findings and dispositions

### 1. ESP32 adaptive router — corrected

Previously, several gates could overstate the substrate actually exercised.

Corrected:

- mock authority can no longer satisfy physical authority gates;
- NPU requests cannot silently execute on OpenVINO CPU;
- GPU requests cannot silently execute without CUDA;
- physical mode must be explicitly requested;
- G1 forces an offline-target proposal through the actual authority boundary;
- G3 counts attested execution backends, not requested logical targets;
- G4/G12 use measured hardware shadow-oracle execution, not a hand-written proxy;
- G5 independently recomputes every scheduler SHA-256 evidence-chain link.

Fresh physical requalification at `ed9a229...` passed all G0–G12 gates under the stricter semantics.

### 2. TFWR integration fallback — corrected

`integrations/tfwr/adapter.py` previously delegated to the reference heuristic when no external client was attached while retaining TFWR/NPU-like telemetry labels.

Corrected behavior:

- attached external client: may emit TFWR/device-target metadata supplied by the actual external path;
- no external client: emits `REFERENCE_HEURISTIC`, `PORTABLE_REFERENCE`, `hardware_executed=false`, and records the intended target as a substitution.

Portable adapter tests now claim interface compatibility only.

### 3. U14 simulated edge proposer — corrected

A simulated edge-policy proposer was named and described as an NPU proposer.

It is now explicitly a simulated/portable proposer used to test the `BaseProposer` seam. It does not constitute NPU evidence.

Historical learned-NPU benchmark numbers remain historical evidence from their original campaign, not outputs of the portable unit test.

### 4. Repository-native canonical acceptance — classified PORTABLE

`qualification/uow_system_acceptance.py` and `qualification/uow_system_acceptance_repo.py` execute the real repository implementation, but:

- GPU/NPU resource slots are logical capacity tokens;
- external effects use `MockExternalClient`;
- timing-independence uses synthetic local clocks and host API interdiction.

Their reports are therefore explicitly **PORTABLE**.

They qualify software architecture and repository behavior. They do not qualify physical accelerators, live third-party services, or arbitrary distributed physical clocks.

The section formerly labeled `EXTERNAL WORLD` is now labeled `EXTERNAL-EFFECT PROTOCOL (MOCK SERVICE)`.

### 5. Standalone canonical acceptance — classified SIMULATED

`qualification/canonical_acceptance.py` contains its own reference implementation and simulated external service.

Its report is now explicitly **SIMULATED** and claims only that the standalone acceptance scenario is coherent and executable. It does not qualify the repository implementation or physical substrates.

### 6. Timing-independence campaign — valid PORTABLE claim

`qualification/timing_independence.py` tests a software architectural invariant:

- independently owned local timing domains;
- causal/dependency ordering independent of timing metadata;
- no canonical orchestration dependency on common host wall-clock APIs.

It already excludes arbitrary distributed physical-clock synchronization from its claim.

No physical-clock qualification is inferred.

### 7. External-effects unit tests — valid software tests

`tests/test_effects.py` uses `MockExternalClient` to qualify deterministic effect/saga protocol logic.

These tests do not claim a live external service. No core behavior change was required.

### 8. Historical checked-in reports

Reports committed before this policy may contain undifferentiated `[PASS]` lines.

Those lines retain their historical meaning at the commit where they were generated, but must be interpreted according to the substrate actually exercised.

After this policy:

- a report must state its evidence level;
- a physical claim requires physical evidence context;
- a historical portable/simulated PASS cannot be promoted into a physical PASS by wording alone.

## Result

The live qualification code now follows this hierarchy:

```text
SIMULATED
  reference implementations, mocks, synthetic devices
       |
       | may validate logic
       v
PORTABLE
  actual repository/runtime on available host substrate
       |
       | may qualify software architecture
       v
PHYSICAL
  actual named device/transport/failure boundary
       |
       | may qualify physical claims
       v
CLAIM PASS
```

A higher-level claim cannot be satisfied by lower-level evidence unless the claim itself only requires that lower level.

## New development requirement

All new qualification gates must declare:

1. the claim;
2. required evidence level;
3. required actual components;
4. substitutions/fallbacks, if any;
5. observed result;
6. qualification result.

If a fallback occurs, the report must preserve the fallback as evidence rather than relabel it as the requested substrate.
