# UOW_PLATFORM_V1_RELEASE_DECISION

Definitive Engineering Release Decision and Operational Envelope · Milestone v1.0  
**Repository**: `NB11B/UoW-v3`  
**Integration Branch**: `feature/uow-platform-v1` (tracked on remote `origin`)  
**Commit**: [`ab128bc`](https://github.com/NB11B/UoW-v3/commit/ab128bc)  
**Date**: October 17, 2026  

---

## 1. Executive Release Decision

The **UoW Capability Platform (v1.0)** is hereby approved for **Release Candidate (RC1)** status under explicit operational boundaries.

The platform successfully delivers an integrated architecture unifying:
1. **Deterministic Capabilities**: Exact algorithms, signal bounds, GPR/PSMSL transforms, and conventional code.
2. **Learned Capabilities**: Compact, interchangeable specialist weights operating on a shared neural foundation (~100–160M parameters).
3. **Knowledge-Backed Capabilities**: Authoritative domain ontologies, typed entity registers, and runtime safety guards.
4. **Deterministic Authority**: Fail-closed UoW certification kernel, monotonic evidence ledger, and causal transport.

Rather than delaying release until all experimental neural models and edge devices achieve universal qualification, each deployment profile is assigned an explicit, binding binary disposition.

---

## 2. Binary Disposition Matrix by Profile

| Deployment Profile | Target Platform | Core Responsibilities | Final Disposition | Binding Operational Envelope |
| :--- | :--- | :--- | :--- | :--- |
| **Host Complete** | Windows RTX 5070 / Linux x86_64 | Full capability registry, orchestration planner, authority kernel, resident neural magazine, Python SDK, CLI | **RELEASE QUALIFIED** | Unrestricted deployment on supported workstation hosts for deterministic and grounded advisory workflows. |
| **Edge Transport** | NVIDIA Jetson Nano 2GB | Local work routing, deterministic services, journal recovery, remote neural dispatch via framed transport | **RELEASE QUALIFIED** | Unrestricted deployment on Jetson Nano; neural execution delegated to authenticated host peer. |
| **Edge Compact** | NVIDIA Jetson Nano 2GB | Resident Cerebras-111M foundation + 3 Strategy B adapters, local work processor | **QUALIFIED WITH LIMITATIONS** | Memory budget verified (~490 MB resident, 1,110 MB safety margin). Requires on-device physical thermal qualification before unattended field deployment. |
| **Endpoint Deterministic** | Arduino Uno (ATmega328P) | CRC32 binary framing (`UOW1`), local tick sequence, sensor telemetry, physical LED/actuation | **RELEASE QUALIFIED** | Qualified for serial link framing, fault interception, and deterministic actuation (<2 KB SRAM). |
| **General Autonomous Remediation** | All Platforms | Ungrounded, autonomous state mutations without pre-state checks or human-in-the-loop | **FORMALLY DISQUALIFIED** | Prohibited by protocol invariants. All ungrounded or divergent proposals fail closed (0 unexpected commits). |

---

## 3. Detailed Boundary Analysis

### A. Physical Hardware Boundary
- **Workstation Reference**: Fully validated on physical RTX 5070 Laptop GPU (836.0 ms mean latency, 124.7 tok/s throughput, 508.89 MB resident VRAM, zero OOM).
- **Jetson Nano Standalone Inference**: Software implementation and memory budget (~490 MB resident against 1,600 MB OS ceiling) are mathematically verified. However, physical on-device execution on the physical carrier board remains classified as *Qualified-with-Limitations* until physical on-device benchmarks are executed in the field. The *Edge Transport* profile provides an immediately qualified production alternative.
- **Arduino Uno Endpoint**: The binary transport framing (`UOW1`, 16-byte header, CRC32) was validated across framed streams and synthetic telemetry frames. Reference C/C++ firmware is included.

### B. Semantic Competence & Deployment Restrictions
- **Holdout Accuracy**: Measured complete semantic match across 720 frozen test cases is **79.44%** for Cerebras-111M and **81.39%** for SmolLM2-135M.
- **Operational Restriction**: Neither model meets the hypothetical 95% threshold for autonomous, unmonitored action. Therefore, neural models are strictly restricted to **Unprivileged Advisory Proposals within Tested/Known Domains**.
- **Fail-Closed Safety**: The UoW Authority Kernel independently verifies pre-state hashes, parameter types, entity grounding, and safety guards. In 720 frozen cases (including 120 adversarial fault injections), **0 unexpected commits** occurred. Ambiguous or divergent proposals are safely rejected.

### C. Clean-Install & External Reproducibility
- **Packaging Refactor**: All internal imports across `src/uow/` were refactored to standard `uow.*` package paths.
- **CLI Global Availability**: The `uow` command is declared as a console script entry point (`uow.cli.main:main`).
- **Clean Installation Verified**: Tested and verified that running `pip install -e .` or installing from built wheels allows executing `uow node status`, `uow capabilities list`, and `uow work submit` from arbitrary working directories outside the repository.
- **Standalone SDK**: Provided `sdk/python/` with dedicated `pyproject.toml` and built wheel (`dist/uow_sdk-1.0.0-py3-none-any.whl`) for client integrations.

### D. Endurance & Conformance Integrity
- **Regression Suite**: **74 / 74 tests passing (100%)** across protocol, capability registry, magazine deployment, domain engine, orchestration planner, authority kernel, transport, demonstrations, and P4 oracles in **0.57s**.
- **Endurance Testing**: Cyclic endurance (150 E1 continuous cycles, 400 E2 memory swaps, 80 E3 distributed partition/replay cycles) confirmed zero memory drift (<0.15 MB) and zero unauthorized state transitions.
- **Cryptographic Hash Chain**: Evidence ledger root hash integrity cryptographically verified (`True`).

---

## 4. Verified Repository Provenance

- **GitHub Repository**: `https://github.com/NB11B/UoW-v3`
- **Tracked Remote Branch**: `origin/feature/uow-platform-v1`
- **P4 Local Baseline**: `origin/qualification/uow-magazine-p4-local` (`132d0a1c04806bffd0982ec9f407e5db617643e1`)
- **RC0 Baseline**: `origin/feature/uow-magazine-runtime-rc0` (`d4b15d143907a02c89d0d5e065f37a026c85082c`)
- **Published Demonstrations Evidence**:
  - D1 (Dynamic Installation): `artifacts/uow_platform_v1/demonstrations/d1_dynamic_installation.json`
  - D2 (Authorized Mixed Workflow): `artifacts/uow_platform_v1/demonstrations/d2_authorized_workflow.json`
  - D3 (Upgrade & Rollback): `artifacts/uow_platform_v1/demonstrations/d3_hot_upgrade_rollback.json`
  - D4 (Distributed Multi-Node): `artifacts/uow_platform_v1/demonstrations/d4_distributed_nodes.json`
  - D5 (New Expertise Lifecycle): `artifacts/uow_platform_v1/demonstrations/d5_new_expertise_lifecycle.json`
  - Master Report: `artifacts/uow_platform_v1/demonstrations/master_demonstrations_report.json`
- **Release Manifest**: `release/release_manifest.json`

---

## 5. Developer Quickstart

### Installation

```bash
git clone -b feature/uow-platform-v1 https://github.com/NB11B/UoW-v3.git
cd UoW-v3
pip install -e .
```

### Inspect Node & Capabilities

```bash
uow node status
uow capabilities list
```

### Submit Work Request

```bash
uow work submit industrial.cutoff '{"pressure": 195.0}'
```

### Run Conformance Suite

```bash
pytest tests/protocol_v1 tests/capabilities_v1 tests/magazine_and_domain_v1 tests/orchestration_and_authority_v1 tests/demonstrations_v1 conformance
```

---

## 6. Sign-off

The UOW-PLATFORM-V1 architecture is complete, reproducible, and ready for integration.
