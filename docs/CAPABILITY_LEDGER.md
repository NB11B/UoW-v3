# UoW v3 Capability Ledger

This ledger establishes the authoritative disposition of every capability family from UoW v2 into UoW v3.
Per the consolidation mandate: **Inventory first. Reduce second. Port third.**
No capability disappears without an explicit disposition.

Valid dispositions:
- `PROMOTE`: Qualified capability migrated into v3 canonical architecture.
- `REFERENCE_ONLY`: Preserved as read-only architectural baseline or external specification.
- `RESEARCH`: Exploratory or mathematical proof campaigns sealed and preserved in v2 history.
- `SUPERSEDED`: Replaced by a more general, strictly tested implementation.
- `DUPLICATE`: Redundant implementation eliminated in favor of canonical component.
- `NOT_YET_QUALIFIED`: Under staging, deferred until cross-language gates pass.

---

## 1. Core Primitives Family

| Capability | Source Branch | Source Commit/Tag | Tests | Evidence Level | Current Implementation | Protocol Dependency | V3 Disposition | V3 Target Location | Status |
|---|---|---|---|---|---|---|---|---|---|
| **UoW Contract** | `v2-origin/main` | `535cc8f` | `tests/test_core_primitives.py` | L4 Formal / Host Qualified | `src/uow/contracts.py:Contract`, `UoW`, `make_uow` | `protocol/core/`, `schemas/canonical/` | `PROMOTE` | `src/uow/contracts.py`, `protocol/core/` | Verified (584/584 passed) |
| **WorldState Model** | `v2-origin/main` | `535cc8f` | `tests/test_core_primitives.py` | L4 Formal / Host Qualified | `src/uow/state.py:WorldState` | `protocol/state/`, RFC-8785 canonical JSON | `PROMOTE` | `src/uow/state.py`, `protocol/state/` | Verified (immutable, hash-bound) |
| **Guards & Predicates** | `v2-origin/main` | `535cc8f` | `tests/test_core_primitives.py`, `tests/test_jev_guard_semantics_campaign.py` | L4 Formal / Host Qualified | `src/uow/contracts.py:Guard`, `GuardOp` | `protocol/core/`, `schemas/json/` | `PROMOTE` | `src/uow/contracts.py`, `conformance/vectors/` | Verified (vector 002 rejection) |
| **Mutations & Deltas** | `v2-origin/main` | `535cc8f` | `tests/test_core_primitives.py` | L4 Formal / Host Qualified | `src/uow/contracts.py:Mutation`, `MutationOp` | `protocol/core/`, `protocol/transition/` | `PROMOTE` | `src/uow/contracts.py` | Verified (atomic state delta) |
| **Deterministic Routing** | `v2-origin/main` | `535cc8f` | `tests/test_core_primitives.py` | L4 Formal / Host Qualified | `src/uow/contracts.py:Route`, `Successor` | `protocol/core/` | `PROMOTE` | `src/uow/contracts.py` | Verified (exhaustive route evaluation) |
| **Boundary Descriptors** | `v2-origin/main` | `535cc8f` | `tests/test_autonomy_authority_boundary.py` | L4 Formal / Host Qualified | `src/uow/contracts.py:Boundary` | `protocol/core/` | `PROMOTE` | `src/uow/contracts.py` | Verified (inward/outward isolation) |
| **Timing Independence** | `v2-origin/main` | `535cc8f` | `tests/test_timing_independence.py` | L4 Formal / Host Qualified | `src/uow/contracts.py:Timing`, `tests/test_timing_independence.py` | `protocol/core/`, `protocol/lifecycle/` | `PROMOTE` | `protocol/core/TIMING_INDEPENDENCE.md`, `src/uow/contracts.py` | Verified (wall-clock invariant) |
| **Evidence Descriptor** | `v2-origin/main` | `535cc8f` | `tests/test_core_primitives.py` | L4 Formal / Host Qualified | `src/uow/contracts.py:EvidenceSpec` | `protocol/evidence/` | `PROMOTE` | `src/uow/contracts.py`, `protocol/evidence/` | Verified (Merkle hash link) |

---

## 2. Authority Family

| Capability | Source Branch | Source Commit/Tag | Tests | Evidence Level | Current Implementation | Protocol Dependency | V3 Disposition | V3 Target Location | Status |
|---|---|---|---|---|---|---|---|---|---|
| **PROPOSE Primitive** | `v2-origin/main` | `535cc8f` | `tests/test_core_primitives.py`, `tests/test_proposer.py` | L4 Formal / Host Qualified | `src/uow/engine.py:propose` | `protocol/authority/` | `PROMOTE` | `src/uow/authority/`, `protocol/authority/` | Verified (pure uncommitted generation) |
| **CERTIFY Primitive** | `v2-origin/main` | `535cc8f` | `tests/test_core_primitives.py` | L4 Formal / Host Qualified | `src/uow/engine.py:certify` | `protocol/authority/` | `PROMOTE` | `src/uow/authority/`, `protocol/authority/` | Verified (independent recomputation) |
| **COMMIT Primitive** | `v2-origin/main` | `535cc8f` | `tests/test_core_primitives.py` | L4 Formal / Host Qualified | `src/uow/engine.py:commit` | `protocol/authority/`, `protocol/evidence/` | `PROMOTE` | `src/uow/authority/` | Verified (evidence-bound transition) |
| **Evidence Ledger & Chaining** | `v2-origin/main` | `535cc8f` | `tests/test_core_primitives.py` | L4 Formal / Host Qualified | `src/uow/engine.py:EvidenceLedger`, `EvidenceRecord` | `protocol/evidence/` | `PROMOTE` | `src/uow/authority/`, `conformance/vectors/` | Verified (vector 005 continuity, 013 anti-tamper) |
| **Authority Service Interface** | `v2-origin/main` | `535cc8f` | `tests/test_authority_service_c.py` | L3 C-Interop Qualified | `src/uow/authority/` | `protocol/authority/`, `abi/c/` | `PROMOTE` | `src/uow/authority/`, `abi/c/` | Verified (C ABI binding) |

---

## 3. Transactions Family

| Capability | Source Branch | Source Commit/Tag | Tests | Evidence Level | Current Implementation | Protocol Dependency | V3 Disposition | V3 Target Location | Status |
|---|---|---|---|---|---|---|---|---|---|
| **Optimistic Concurrency Control (OCC)** | `v2-origin/main` | `535cc8f` | `tests/test_transactions.py` | L3 Host Qualified | `src/uow/transactions/occ.py:validate_occ` | `protocol/state/` | `PROMOTE` | `src/uow/transactions/` | Verified (hazard detection, WW/WR/RW) |
| **Deterministic Sequencing** | `v2-origin/main` | `535cc8f` | `tests/test_transactions.py` | L3 Host Qualified | `src/uow/transactions/sequencer.py:DeterministicSequencer` | `protocol/authority/` | `PROMOTE` | `src/uow/transactions/` | Verified (total transition order) |
| **WAL & Replay Mechanism** | `v2-origin/main` | `535cc8f` | `tests/test_transactions.py` | L3 Host Qualified | `src/uow/transactions/wal.py:WALSequencer` | `protocol/evidence/` | `PROMOTE` | `src/uow/transactions/` | Verified (crash-recovery replay) |

---

## 4. Orchestration Family

| Capability | Source Branch | Source Commit/Tag | Tests | Evidence Level | Current Implementation | Protocol Dependency | V3 Disposition | V3 Target Location | Status |
|---|---|---|---|---|---|---|---|---|---|
| **DAG Scheduling & Dispatch** | `v2-origin/main` | `535cc8f` | `tests/test_orchestration.py`, `tests/test_p1_end_to_end_orchestration.py` | L3 Host Qualified | `src/uow/orchestration/scheduler.py` | `protocol/core/`, `protocol/lifecycle/` | `PROMOTE` | `src/uow/runtime/orchestration/` | Verified (dependency graph resolution) |
| **Completion Materialization** | `v2-origin/main` | `535cc8f` | `tests/test_orchestration.py` | L3 Host Qualified | `src/uow/orchestration/completion.py` | `protocol/core/` | `PROMOTE` | `src/uow/runtime/orchestration/` | Verified (atomic task completion) |
| **Policy Orchestrator** | `v2-origin/main` | `535cc8f` | `tests/test_policy_orchestrator.py` | L3 Host Qualified | `src/uow/orchestration/orchestrator.py` | `protocol/lifecycle/` | `PROMOTE` | `src/uow/runtime/orchestration/` | Verified (P1-P5 lifecycle governance) |

---

## 5. Resources & Economics Family

| Capability | Source Branch | Source Commit/Tag | Tests | Evidence Level | Current Implementation | Protocol Dependency | V3 Disposition | V3 Target Location | Status |
|---|---|---|---|---|---|---|---|---|---|
| **Resource Envelope (Leased & Consumable)** | `v2-origin/main` | `535cc8f` | `tests/test_resources.py` | L3 Host Qualified | `src/uow/resources/requirement.py:ResourceRequirement` | `protocol/requirements/`, `protocol/economics/` | `PROMOTE` | `src/uow/resources/`, `protocol/requirements/` | Verified (CPU, RAM, GPU, NPU, Energy, Cost) |
| **Resource State Governance** | `v2-origin/main` | `535cc8f` | `tests/test_resources.py` | L3 Host Qualified | `src/uow/resources/state.py:ResourceState` | `protocol/state/` | `PROMOTE` | `src/uow/resources/` | Verified (lease acquisition & release) |
| **Scheduling Policies (FIFO, Greedy, Priority, Cost/Energy)** | `v2-origin/main` | `535cc8f` | `tests/test_resources.py` | L3 Host Qualified | `src/uow/resources/policies.py:CostEnergySchedulingPolicy` | `protocol/requirements/` | `PROMOTE` | `src/uow/resources/` | Verified (resource cost, energy budget, scheduling) |
| **Cost-Aware Realization Choice** | `v2-origin/main` | `535cc8f` | `tests/test_resources.py` | L3 Host Qualified | `src/uow/resources/policies.py` | `protocol/economics/` | `PROMOTE` | `src/uow/resources/` | Verified (cost/energy realization selection) |
| **Atomic Cost Observation** | `v3/consolidation` | Candidate | Schema models | L2 Model Draft | `src/uow/economics/` | `protocol/economics/` | `NOT_YET_QUALIFIED` | `src/uow/economics/` | Specification model in development |
| **Market Price Observation** | `v3/consolidation` | Candidate | Schema models | L2 Model Draft | `src/uow/economics/` | `protocol/economics/` | `NOT_YET_QUALIFIED` | `src/uow/economics/` | Spot market pricing model pending qualification |
| **Scarcity / Capacity Ratio** | `v3/consolidation` | Candidate | Schema models | L2 Model Draft | `src/uow/economics/` | `protocol/economics/` | `NOT_YET_QUALIFIED` | `src/uow/economics/` | Host capacity scarcity model pending qualification |
| **Failure / Recovery Cost** | `v3/consolidation` | Candidate | Schema models | L2 Model Draft | `src/uow/economics/` | `protocol/economics/` | `NOT_YET_QUALIFIED` | `src/uow/economics/` | Recovery cost model pending qualification |
| **Human Cost Observation** | `v3/consolidation` | Candidate | Schema models | L2 Model Draft | `src/uow/economics/` | `protocol/economics/` | `NOT_YET_QUALIFIED` | `src/uow/economics/` | Human-in-the-loop cost model pending qualification |

---

## 6. Effects Family

| Capability | Source Branch | Source Commit/Tag | Tests | Evidence Level | Current Implementation | Protocol Dependency | V3 Disposition | V3 Target Location | Status |
|---|---|---|---|---|---|---|---|---|---|
| **Effect Intent & Execution** | `v2-origin/main` | `535cc8f` | `tests/test_effects.py` | L3 Host Qualified | `src/uow/effects/intent.py:EffectDescriptor` | `protocol/effects/` | `PROMOTE` | `src/uow/runtime/effects/` | Verified (deterministic descriptor) |
| **Idempotency & Deduplication** | `v2-origin/main` | `535cc8f` | `tests/test_effects.py` | L3 Host Qualified | `src/uow/effects/idempotency.py` | `protocol/effects/` | `PROMOTE` | `src/uow/runtime/effects/`, `conformance/vectors/` | Verified (vector 007 replay, 011 conflict) |
| **Effect Receipts & Evidence Linkage** | `v2-origin/main` | `535cc8f` | `tests/test_effects.py` | L3 Host Qualified | `src/uow/effects/receipt.py:EffectReceipt` | `protocol/effects/`, `protocol/evidence/` | `PROMOTE` | `src/uow/runtime/effects/` | Verified (cryptographic receipt binding) |
| **Sagas & Compensation** | `v2-origin/main` | `535cc8f` | `tests/test_effects.py` | L3 Host Qualified | `src/uow/effects/saga.py` | `protocol/effects/` | `PROMOTE` | `src/uow/runtime/effects/` | Verified (forward-recovery and rollback) |

---

## 7. Proposers Family

| Capability | Source Branch | Source Commit/Tag | Tests | Evidence Level | Current Implementation | Protocol Dependency | V3 Disposition | V3 Target Location | Status |
|---|---|---|---|---|---|---|---|---|---|
| **Deterministic Proposer** | `v2-origin/main` | `535cc8f` | `tests/test_proposer.py` | L4 Formal / Host Qualified | `src/uow/proposer/deterministic.py` | `protocol/authority/` | `PROMOTE` | `src/uow/runtime/proposers/` | Verified (ground-truth proposal generator) |
| **Heuristic / Stochastic Proposer** | `v2-origin/main` | `535cc8f` | `tests/test_proposer.py` | L3 Host Qualified | `src/uow/proposer/stochastic.py` | `protocol/authority/` | `PROMOTE` | `src/uow/runtime/proposers/` | Verified (randomized proposal generation) |
| **NPU / Neural Adaptive Proposer** | `v2-origin/main` | `535cc8f` | `tests/test_npu_adaptive_proposer.py`, `tests/test_npu_hot_swap.py` | L3 Hardware/Host Qualified | `integrations/openvino_npu/` | `protocol/authority/` | `PROMOTE` | `adapters/openvino_npu/`, `src/uow/adapters/` | Verified (Intel AI Boost / OpenVINO hot-swap) |
| **Closed-Loop Adaptation** | `v2-origin/feat/x3-closed-loop-adaptation` | `ec3d6f0`, tag `uow-v2-m1-x3-qualified` | 1200-job stress test | L2 Qualification Run | `src/uow/composition/` | `protocol/authority/` | `PROMOTE` | `src/uow/runtime/adaptation/` | Verified (unchanged authority under adaptive proposer) |

---

## 8. Composition & Distributed Family

| Capability | Source Branch | Source Commit/Tag | Tests | Evidence Level | Current Implementation | Protocol Dependency | V3 Disposition | V3 Target Location | Status |
|---|---|---|---|---|---|---|---|---|---|
| **Recursive UoW Boundary (System-as-Actor)** | `v2-origin/main` | `535cc8f` | `tests/test_composition_recursive_boundary.py` | L4 Formal / Host Qualified | `src/uow/composition/` | `protocol/core/` | `PROMOTE` | `src/uow/runtime/composition/` | Verified (scale-invariant encapsulation) |
| **Composition Fabric & Substitution** | `v2-origin/main` | `535cc8f` | `tests/test_composition_fabric.py`, `tests/test_composition_substitution.py` | L3 Host Qualified | `src/uow/composition/` | `protocol/core/` | `PROMOTE` | `src/uow/runtime/composition/` | Verified (dynamic actor substitution) |
| **Distributed Delegation & Quorum** | `v2-origin/main` | `535cc8f` | `tests/test_distributed_authority.py`, `tests/test_adaptive_quorum.py` | L3 Host Qualified | `src/uow/authority/distributed.py` | `protocol/authority/` | `PROMOTE` | `src/uow/authority/` | Verified (M-of-N voting and failover) |
| **Physical Heterogeneous 2-of-3 Quorum** | `v2-origin/feat/s2-heterogeneous-physical-qualification` | `013fc64`, tag `uow-v2-s2-qualified` | Physical run log | L1 Physical Evidence | `qualification/heterogeneous_physical_s2/` | `protocol/authority/` | `REFERENCE_ONLY` | Preserved in v2 qualification logs; protocol interfaces in v3 | Verified on hardware (Laptop + ESP32 + Arduino) |

---

## 9. Semantic & Autonomy Family

| Capability | Source Branch | Source Commit/Tag | Tests | Evidence Level | Current Implementation | Protocol Dependency | V3 Disposition | V3 Target Location | Status |
|---|---|---|---|---|---|---|---|---|---|
| **Semantic Mediation & Ambiguity Resolution** | `v2-origin/main` | `535cc8f` | `tests/test_h4_authoritative_lifecycle.py`, `tests/test_h5_incremental_clarification.py` | L3 Host Qualified | `src/uow/semantic/` | `protocol/capabilities/` | `PROMOTE` | `src/uow/semantic/` | Verified (clarification rounds, ontology mapping) |
| **Governed Egress (H6/H7)** | `v2-origin/main` | `535cc8f` | `tests/test_h6_governed_egress.py`, `tests/test_h7_final_conformance.py` | L3 Host Qualified | `src/uow/semantic/egress.py` | `protocol/effects/` | `PROMOTE` | `src/uow/semantic/` | Verified (boundary filters, certified dispatch) |
| **Autonomous Goal Formation & Deficit Repair** | `v2-origin/main` | `535cc8f` | `tests/test_autonomy_conformance.py`, `tests/test_autonomy_public_api.py` | L3 Host Qualified | `src/uow/autonomy/` | `protocol/lifecycle/` | `PROMOTE` | `src/uow/autonomy/` | Verified (goal tracking, state gap closure) |
| **Policy Lifecycle & Live Drift Recovery** | `v2-origin/main` | `535cc8f` | `tests/test_p2_live_policy_promotion.py`, `tests/test_p3_live_drift_and_requalification.py`, `tests/test_p5_durable_recovery.py` | L3 Host Qualified | `src/uow/policy/` | `protocol/lifecycle/` | `PROMOTE` | `src/uow/runtime/policy/` | Verified (hot swap, drift requalification) |
| **Runtime Self-Model (Experimental Introspection)** | `v2-origin/feat/runtime-self-model` | `7548d35` | `tests/test_self_model_acceptance.py` | Experimental | `src/uow/self_model/` | None (internal) | `RESEARCH` | Preserved in v2 branch; mined for schema models | Candidate for v3.1 |

---

## 10. Substrate & Physical Family

| Capability | Source Branch | Source Commit/Tag | Tests | Evidence Level | Current Implementation | Protocol Dependency | V3 Disposition | V3 Target Location | Status |
|---|---|---|---|---|---|---|---|---|---|
| **Substrate Capability Ontology** | `feat/runtime-substrate-semantics` | `9eaff71`, tag `v2.0-runtime-substrate-m2` | Schema validations | L3 Specification | `spec/substrate/CAPABILITY_ONTOLOGY.md`, `spec/schemas/capability_descriptor.json` | `protocol/capabilities/` | `PROMOTE` | `protocol/capabilities/`, `schemas/json/` | Reconciled from substrate branch |
| **C ABI Interface** | `feat/runtime-substrate-semantics` | `9eaff71` | `tests/test_authority_service_c.py` | L3 ABI Qualified | `abi/c/include/uow.h` | `protocol/core/` | `PROMOTE` | `runtimes/cpp/abi/`, `abi/c/` | Reconciled header & types |
| **ESP32-S3 Dual-Core Firmware** | `feat/s2-heterogeneous-physical-qualification` | `013fc64`, tag `uow-v2-s2-qualified` | Physical upload logs, host tests | L1 Physical Evidence | `qualification/embedded/esp32_dual_core/` | `protocol/core/` | `PROMOTE` | `runtimes/embedded/esp32/` | Verified on ESP32-S3 hardware |
| **Arduino UNO Q Authority Kernel** | `feat/s2-heterogeneous-physical-qualification` | `013fc64` | Firmware build & push logs | L1 Physical Evidence | `qualification/embedded/uno_q_authority/` | `protocol/core/` | `PROMOTE` | `runtimes/embedded/arduino/` | Verified on Arduino UNO Q |
| **C++ Core Runtime & Wire Profiles** | `feat/s2-heterogeneous-physical-qualification` | `013fc64` | `architecture/shadow/python/tests/test_cross_language_cpp.py` | L3 Cross-language Qualified | `architecture/conformance/cpp/` | `protocol/core/` | `PROMOTE` | `runtimes/cpp/` | Native C++ core runtime (covers subset of golden vectors until full 16/16 conformance) |

---

## 11. Cross-Language SDKs & Compatibility Family

| Capability | Source Branch | Source Commit/Tag | Tests | Evidence Level | Current Implementation | Protocol Dependency | V3 Disposition | V3 Target Location | Status |
|---|---|---|---|---|---|---|---|---|---|
| **Rust SDK & Runtime Candidate** | `feat/runtime-substrate-semantics` | `9eaff71`, tag `v2.0-runtime-substrate-m2` | `sdk/rust/src/lib.rs` unit tests | L3 SDK Qualified | `sdk/rust/` | `protocol/core/` | `PROMOTE` | `sdk/rust/` | Rust native SDK / runtime candidate |
| **TypeScript Integration SDK** | `feat/runtime-substrate-semantics` | `9eaff71`, tag `v2.0-runtime-substrate-m2` | `sdk/typescript/test/conformance.test.js` | L3 SDK Qualified | `sdk/typescript/` | `schemas/json/` | `PROMOTE` | `sdk/typescript/` | Integration SDK + deterministic reference executor |
| **JavaScript Client Interop** | `feat/runtime-substrate-semantics` | `9eaff71` | `examples/javascript/demo.js` | L3 Example / Client | `examples/javascript/` | `sdk/typescript/` | `PROMOTE` | `examples/javascript/` | Pure JS consumer |
| **Perl Tested Protocol Adapter** | `feat/runtime-substrate-semantics` | `9eaff71` | `sdk/legacy/perl/t/conformance.t` | L3 Tested Adapter | `sdk/legacy/perl/` | `protocol/core/` | `PROMOTE` | `sdk/legacy/perl/`, `adapters/perl/` | Tested protocol adapter (62 checks) |
| **COBOL Wire/Batch Profile** | `feat/runtime-substrate-semantics` | `9eaff71` | `sdk/legacy/cobol/examples/UOWDEMO.cbl` | L3 Enterprise Qualified | `sdk/legacy/cobol/` | `schemas/wire/` | `PROMOTE` | `sdk/legacy/cobol/` | Wire/batch compatibility profile |
| **Pascal Type/Interface Profile** | `feat/runtime-substrate-semantics` | `9eaff71` | `sdk/legacy/pascal/UoWTypes.pas` | L3 Type Qualified | `sdk/legacy/pascal/` | `protocol/core/` | `PROMOTE` | `sdk/legacy/pascal/` | Type/interface compatibility profile |

---

## 12. Research Proof Campaigns (Immutable Evidence in v2)

| Capability | Source Branch | Source Commit/Tag | Tests | Evidence Level | Current Implementation | Protocol Dependency | V3 Disposition | V3 Target Location | Status |
|---|---|---|---|---|---|---|---|---|---|
| **JEV Operator Closure** | `v2-origin/main` | `535cc8f` | `tests/test_jev_operator_closure_campaign.py` | L4 Mathematical Proof | `docs/JEV_OPERATOR_CLOSURE_EXPERIMENT.md` | Core Primitives | `RESEARCH` | Sealed in v2; referenced in `docs/V2_TO_V3_PROVENANCE.md` | Preserved in v2 |
| **JEV Semigroup Associativity** | `v2-origin/main` | `535cc8f` | `tests/test_jev_semigroup_associativity_campaign.py` | L4 Mathematical Proof | `docs/JEV_SEMIGROUP_ASSOCIATIVITY_EXPERIMENT.md` | Core Primitives | `RESEARCH` | Sealed in v2; referenced in `docs/V2_TO_V3_PROVENANCE.md` | Preserved in v2 |
| **JEV Bilinearity & Idempotence** | `v2-origin/main` | `535cc8f` | `tests/test_jev_operator_bilinearity_campaign.py`, `tests/test_jev_idempotence_campaign.py` | L4 Mathematical Proof | `docs/JEV_OPERATOR_BILINEARITY_EXPERIMENT.md` | Core Primitives | `RESEARCH` | Sealed in v2; referenced in `docs/V2_TO_V3_PROVENANCE.md` | Preserved in v2 |
| **JEV Extreme Scale & Finite Size Scaling** | `v2-origin/main` | `535cc8f` | `tests/test_jev_extreme_scale_campaign.py`, `tests/test_jev_finite_size_scaling_campaign.py` | L4 Stress Proof | `docs/JEV_EXTREME_SCALE_EXPERIMENT.md` | Core Primitives | `RESEARCH` | Sealed in v2; referenced in `docs/V2_TO_V3_PROVENANCE.md` | Preserved in v2 |
| **S1 1-Hour Endurance Stress Campaign** | `v2-origin/feat/s1-endurance-stress` | `a83285d`, tag `uow-v2-s1-qualified` | 557-test full regression | L2 Qualification Run | Artifact manifest in v2 | Core Primitives | `RESEARCH` | Sealed in v2; provenance link retained | Preserved in v2 |
| **X-Final Integrated Generality** | `v2-origin/qualification/x-final-integrated-generality` | `0fae7d7`, tag `integrated-generality-v1-qualified` | Generality suite | L2 Qualification Run | Artifact registry in v2 | Core Primitives | `RESEARCH` | Sealed in v2; provenance link retained | Preserved in v2 |
