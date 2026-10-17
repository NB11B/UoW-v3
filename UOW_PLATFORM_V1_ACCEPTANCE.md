# UOW_PLATFORM_V1_ACCEPTANCE

Complete Engineering Acceptance Specification · Milestone v1.0  
**Repository**: `NB11B/UoW-v3`  
**Integration Branch**: `feature/uow-platform-v1`  
**Published Release Revision**: [`424b668`](https://github.com/NB11B/UoW-v3/commit/424b668)  
**Date**: October 17, 2026  

---

## 1. Executive Acceptance Statement

This document defines the binding acceptance criteria for the **UoW Capability Platform (v1.0)**. 
Qualification is awarded only when an independent evaluator can execute all verification vectors, verify cryptographic state and ledger properties, install novel capabilities without runtime recompilation, and reproduce the recorded hardware envelopes.

---

## 2. Binding Qualification Gates

| Gate ID | Technical Area | Binding Acceptance Condition | Verification Method | Status |
| :--- | :--- | :--- | :--- | :--- |
| **G-01** | **Protocol Canonical Wire Contracts** | RFC 8785 deterministic JSON formatting; binary framing with CRC32; negative vectors (truncated, bit-flipped, invalid magic) fail closed. | `tests/protocol_v1/` | **QUALIFIED** |
| **G-02** | **Universal Capability Registry** | 100% detection of modified/mismatched artifact digests; immutable package storage; transactional activation, quarantine, and rollback. | `tests/capabilities_v1/` | **QUALIFIED** |
| **G-03** | **Multi-Strategy Magazine Engine** | Unified API across Resident Adapter, Paged Adapter, Fixed Export, Remote Peer, and Deterministic Substitute; zero cross-request adapter leakage. | `tests/magazine_and_domain_v1/` | **QUALIFIED** |
| **G-04** | **Authoritative Domain Engine** | Authoritative prompt compilation from domain specifications; 100% interception of hallucinated/fabricated entity identifiers outside domain registers. | `tests/magazine_and_domain_v1/` | **QUALIFIED** |
| **G-05** | **Expertise Toolchain** | Reproducible capability generation and validation CLI (`uow expertise`); explicit qualification recommendation before deployment. | `cli/main.py expertise` | **QUALIFIED** |
| **G-06** | **Deterministic-First Planner** | Automatic preference for exact algorithms over neural inference; comprehensive audit explanation detailing routing rationale, latency, and costs. | `tests/orchestration_and_authority_v1/` | **QUALIFIED** |
| **G-07** | **Authority Kernel & Ledger** | Zero field substitution into malformed proposals; zero unexpected commits on pre-state divergence; monotonic cryptographic hash chain verification. | `tests/orchestration_and_authority_v1/` | **QUALIFIED** |
| **G-08** | **Distributed Transport & Nodes** | Local sequence and causal vector clocks without shared global clocks; detection and rejection of replayed/duplicate events; partition tolerance. | `tests/orchestration_and_authority_v1/` | **QUALIFIED** |
| **G-09** | **Developer Product (SDK & CLI)** | Functional typed client (`sdk/python/uow/`), operator CLI (`uow node/work/diagnostics`), portable diagnostic bundle generation. | `tests/demonstrations_v1/` | **QUALIFIED** |
| **G-10** | **End-to-End Demonstrations** | 100% pass across Demonstrations D1 through D5 with recorded machine-readable evidence. | `demonstrations/platform_demonstrations.py` | **QUALIFIED** |

---

## 3. Product Demonstration Summary (D1 – D5)

1. **D1: Dynamic Capability Installation without Runtime Code Changes**  
   - Installed `domain.smart_grid.v1` ontology and `grid.feeder_trip.deterministic` capability into live registry.  
   - Successfully planned, executed, and committed work request without modifying core platform code.  
   - **Evidence**: `artifacts/uow_platform_v1/demonstrations/d1_dynamic_installation.json`.

2. **D2: Complete Authorized Mixed Deterministic/Neural Workflow**  
   - Sensor alarm ingress $\to$ neural grammar proposal $\to$ domain grounding validation $\to$ authority certification $\to$ evidence ledger commit.  
   - Verified ledger height advance and monotonic hash chain integrity (`True`).  
   - **Evidence**: `artifacts/uow_platform_v1/demonstrations/d2_authorized_workflow.json`.

3. **D3: Live Hot-Upgrade, Quarantine, and Rollback**  
   - Executed work on `process.optimizer` v1.0.0; upgraded to v1.1.0 live.  
   - Injected corrupt v1.2.0-bad candidate; quarantined and rolled back to v1.1.0 without downtime.  
   - **Evidence**: `artifacts/uow_platform_v1/demonstrations/d3_hot_upgrade_rollback.json`.

4. **D4: Multi-Node Distributed Execution across Host, Nano, and Uno**  
   - Framed telemetry stream from Uno serial endpoint received at Workstation; forwarded to Jetson Nano.  
   - Handled network partition and blocked replayed sequence frames.  
   - **Evidence**: `artifacts/uow_platform_v1/demonstrations/d4_distributed_nodes.json`.

5. **D5: New Domain Expertise Toolchain Lifecycle**  
   - Initialized `domain.robotics.v1` package, validated operations, verified grounding and intercepted fabricated entity IDs.  
   - Produced explicit deployment recommendation: `DEPLOY WITH AUTHORITATIVE CONTEXT`.  
   - **Evidence**: `artifacts/uow_platform_v1/demonstrations/d5_new_expertise_lifecycle.json`.

---

## 4. Hardware Deployment Profiles

| Deployment Profile | Target Platform | Neural Capability | Resident Memory Envelope | Final Disposition |
| :--- | :--- | :--- | :--- | :--- |
| **Host Complete** | Windows RTX 5070 / Linux x86_64 | Resident Magazine (Cerebras-111M / SmolLM2-135M) | ~508 MB VRAM / 2.3 GB Host RAM | **RELEASE QUALIFIED** |
| **Edge Transport** | NVIDIA Jetson Nano 2GB | Remote Neural Capability via Framed Transport | ~120 MB RAM | **RELEASE QUALIFIED** |
| **Edge Compact** | NVIDIA Jetson Nano 2GB | Resident Cerebras-111M (3 Strategy B adapters) | ~490 MB Resident (1,110 MB safety headroom) | **QUALIFIED WITH LIMITATIONS** (Requires on-device physical thermal/load qualification) |
| **Endpoint Deterministic** | Arduino Uno (ATmega328P) | None (CRC32 Framed Serial Packets & I/O) | <2 KB SRAM | **RELEASE QUALIFIED** |
| **General Autonomous Remediation** | All Platforms | Unguarded, autonomous model actuation without pre-state certification | N/A | **FORMALLY DISQUALIFIED** (All ungrounded proposals fail closed) |

---

## 5. Acceptance Invariant Certifications

- **Fail-Closed Boundary**: Neural models generate strictly unprivileged proposals. No proposal can bypass deterministic certification or substitute expected fields.
- **Ledger Monotonicity**: Every valid commit advances the cryptographic root hash chain; rejected transactions produce zero state changes.
- **Zero Global Clock Assumption**: Distributed nodes order events strictly via local sequences, vector clocks, and causal dependency lists.
