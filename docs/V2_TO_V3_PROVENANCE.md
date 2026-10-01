# UoW v2 to v3 Provenance Record

This document records the exact cryptographic source commitments, qualification tags, test baseline results, and hardware evidence links for the transition from UoW v2 to UoW v3.

---

## 1. Frozen Baseline Metadata

| Field | Value |
|---|---|
| **V2 Source Repository** | `https://github.com/NB11B/UoW-v2.git` |
| **V2 Source Commit (HEAD of main)** | `535cc8fad3a34085afcb275caaeafdb8477a52c2` |
| **Baseline Test Execution** | `pytest -q` -> **562 passed, 81 warnings in 68.02s** |
| **Baseline Test Log** | `V2_BASELINE_TESTS.txt` |
| **Source Commit Record** | `V2_SOURCE_COMMIT.txt` |
| **Source Tags Record** | `V2_SOURCE_TAGS.txt` |
| **Source Branches Record** | `V2_SOURCE_BRANCHES.txt` |
| **V3 Working Branch** | `v3/consolidation` |

---

## 2. Source Capability Lineages & Worktree Audit Heads

Each major branch represents a demonstrated capability lineage. Side-by-side worktrees were established to inspect and extract assets without disturbing either `UoW-v2` or the `v3/consolidation` branch.

| Lineage / Capability Area | Source Remote Branch | HEAD Commit SHA | Associated Tag(s) | Primary Extracted Assets |
|---|---|---|---|---|
| **Canonical Production Kernel** | `v2-origin/main` | `535cc8fad3a34085afcb275caaeafdb8477a52c2` | `v2.0.0-qualified` | Core primitives, OCC transactions, DAG orchestration, resources, effects, proposers, policy, autonomy, 562 tests |
| **Polyglot Interop** | `v2-origin/feat/polyglot-interop` | `7881f5fe962d382b2f78ae9aa23893ecf2c9cacf` | `v2.0-polyglot-m1`, `v2.0-polyglot-m1.1` | Policy plane specifications, early cross-language interfaces |
| **Runtime Substrate Semantics** | `v2-origin/feat/runtime-substrate-semantics` | `9eaff7145e76221f148c89bbc7e2c967db53e566` | `v2.0-runtime-substrate-m2` | `abi/c/`, `sdk/rust/`, `sdk/typescript/`, `spec/protocol/`, `spec/schemas/`, `conformance/vectors/`, `examples/`, `legacy/` |
| **Runtime Self-Model** | `v2-origin/feat/runtime-self-model` | `7548d358902822d5f5f98de06624e5063f7883ac` | — | Experimental introspection models (classified `RESEARCH` for v3.1) |
| **S1 Endurance Stress** | `v2-origin/feat/s1-endurance-stress` | `a83285dbfee1cc1b5b1e5175b3b950ec856bc3d3` | `uow-v2-s1-qualified`, `mdss1-1h-qualified` | 1-hour endurance soak logs, 557-test verified qualification artifacts |
| **S2 Physical Qualification** | `v2-origin/feat/s2-heterogeneous-physical-qualification` | `013fc642b85267f7cc854ab9f3ea404ffd3eef64` | `uow-v2-s2-qualified` | ESP32-S3 dual-core firmware, Arduino UNO Q kernel, heterogeneous 2-of-3 quorum, physical upload logs |
| **X3 Closed-Loop Adaptation** | `v2-origin/feat/x3-closed-loop-adaptation` | `ec3d6f01b62b8e3f08dba7b49d5a4c4d2897fae8` | `uow-v2-m1-x3-qualified` | 1200-job stress test, GPU/NPU closed-loop adaptation against unchanged ESP32 authority |
| **Semantic Final Conformance** | `v2-origin/qualification/semantic-final-conformance` | `7d4d2145aa76375f0abcd28aededfbde01774381` | `semantic-harness-v1-qualified`, `semantic-ingress-h0-h5-qualified` | H0-H7 semantic egress/ingress roundtrip, clarification, adapter contracts |
| **Integrated Generality** | `v2-origin/qualification/x-final-integrated-generality` | `0fae7d746b139292ee8f2551a0fdc0da0ded9b8e` | `integrated-generality-v1-qualified` | Final evidence manifest, qualification registry, integrated generality across domains |

---

## 3. Physical Qualification Evidence References (Preserved in v2)

Physical hardware qualification artifacts represent massive empirical logs and firmware binaries. Per Step 13, physical evidence remains linked back to v2 rather than copying gigabytes of raw binary logs into v3:

1. **ESP32-S3 Dual-Core Hardware Qualification**:
   - Source Commit: `013fc642b85267f7cc854ab9f3ea404ffd3eef64` (`v2-origin/feat/s2-heterogeneous-physical-qualification`)
   - Flash & Upload Evidence: `qualification/artifacts/final-physical/20260924T203451Z/F0/f0_esp32_upload.log`
   - Execution Transcript: `qualification/artifacts/final-physical/20260924T203451Z/F1/esp32-transcript.jsonl`
   - Qualification Manifest: `qualification/embedded/esp32_dual_core/QUALIFICATION_MANIFEST.json`
   - Firmware Source: `runtimes/embedded/esp32/` (promoted for compilation and deployment)

2. **Arduino UNO Q Authority Kernel**:
   - Source Commit: `013fc642b85267f7cc854ab9f3ea404ffd3eef64`
   - Hardware Upload Evidence: `qualification/artifacts/final-physical/20260924T203451Z/F0/f0_unoq_push_uow_embedded_cpp.log`
   - Firmware Source: `runtimes/embedded/arduino/`

3. **Intel AI Boost NPU Proposer Integration**:
   - Source Commit: `ec3d6f01b62b8e3f08dba7b49d5a4c4d2897fae8` (`v2-origin/feat/x3-closed-loop-adaptation`)
   - ONNX Model & Adapter: `qualification/embedded/esp32_dual_core/host/minsky_npu.onnx`, `integrations/openvino_npu/`
   - Adapter Target: `adapters/openvino_npu/`

---

## 4. Formal Research Proof Campaigns (Sealed in v2)

The mathematical and algebraic campaigns that proved universality, semigroup properties, and scale invariance are permanently preserved in `v2-origin/main`:
- JEV Operator Closure Campaign: `test_jev_operator_closure_campaign.py`
- JEV Semigroup Associativity Campaign: `test_jev_semigroup_associativity_campaign.py`
- JEV Bilinearity Campaign: `test_jev_operator_bilinearity_campaign.py`
- JEV Idempotence Campaign: `test_jev_idempotence_campaign.py`
- JEV Extreme Scale Campaign: `test_jev_extreme_scale_campaign.py`
- JEV Finite Size Scaling Campaign: `test_jev_finite_size_scaling_campaign.py`
- Logistics Grammar Transfer Campaign: `test_logistics_grammar_transfer_campaign.py`
- Compliance Blind Derivation Campaign: `test_compliance_blind_derivation_campaign.py`

These proof campaigns demonstrated the algebraic foundation in v2; v3 builds upon this immutable foundation as an industrial, multi-language protocol and runtime.
