# Continuous Adaptation Qualification Seal

**Research lineage:** `qualification/continuous-adaptation-v1`  
**Physically qualified research head:** `1f1f53f6c269f87bf23a9a8643766cb2927f0f0b`  
**Qualification date:** September 22, 2026  
**Manifest:** `QUALIFICATION_MANIFEST.json`

## Status

This document seals the completed three-step continuous-adaptation research campaign. The physically qualified code, tests, and result artifacts are pinned to the research-head commit above. Later commits on this branch may improve documentation, manifests, and CI coverage; they do not retroactively change the physical evidence unless a new hardware campaign is explicitly recorded.

The branch also contains the complete ESP32-S3 qualification lineage on which the continuous-adaptation work depends. It is therefore a self-contained research lineage, not a small patch against `main`.

## Hardware topology

```text
Host CPU
  - orchestration
  - telemetry
  - replay / retention buffers
  - fallback execution
          |
          +------ NVIDIA RTX 5070 Laptop GPU
          |         online gradient optimization
          |
          +------ Intel AI Boost NPU
          |         deployed routing-policy inference
          |
          +------ USB-Serial/JTAG
                    |
                    v
                ESP32-S3
                deterministic scheduling authority
                reservation / receipt certification
                state-hash OCC boundary
                SHA-256 hash-chained evidence root
```

The learned policy may change. The ESP32 authority rules do not learn from model weights and do not delegate commit authority to the CPU, GPU, or NPU.

## Sealed three-step campaign

### Step 1 — Adaptive robustness and operational memory

Qualified capabilities:

- stochastic semi-Markov regime changes with unannounced transitions;
- recurring regimes and reacquisition measurement;
- online GPU adaptation and NPU redeployment;
- retention-buffer replay;
- adversarial canary injection;
- transactional model rollback;
- fixed ESP32 authority throughout adaptation.

### Step 2 — Concurrent adaptive operation

Qualified capabilities:

- `K=6` asynchronous in-flight workers;
- concurrent CPU/GPU/NPU execution;
- thread-safe serial request/response multiplexing;
- naturally occurring stale-state proposals;
- OCC resnapshot/retry;
- 100% resolution of recorded `STALE_STATE_HASH` conflicts in the qualified runs;
- zero wrong authoritative commits.

### Step 3 — Multi-seed endurance and distribution stability

Two independent physical stochastic runs were recorded:

- Seed 42: 1,200 operations;
- Seed 101: 1,200 operations;
- total: 2,400 operations;
- concurrency: `K=6`;
- recorded OCC conflicts: 2,093;
- recorded successful OCC conflict resolutions: 2,093;
- wrong authoritative commits: 0.

The campaign evaluated gates `G0` through `G12`, including authority integrity, heterogeneous execution, canary safety, retention/reacquisition, OCC concurrency, and empirical latency/regret distribution bounds.

## Authority claim

Within the tested workload, hardware topology, concurrency level, stochastic environment generator, and qualification conditions:

[
oxed{
	ext{adaptive / stochastic proposal and routing}
;perp;
	ext{authoritative commit semantics}
}
]

The CPU/GPU/NPU side may:

- adapt;
- route differently across runs;
- produce stale proposals;
- deploy new model versions;
- fail canary validation;
- roll back;
- execute work concurrently.

The ESP32 remains responsible for deciding which reservations and receipts become authoritative.

The strongest recorded safety invariant is:

[
oxed{	ext{wrong authoritative commits}=0}
]

across the sealed physical campaigns.

## Evidence-chain terminology

The scheduling evidence root is a **sequential SHA-256 hash chain**:

```text
root_(n+1) = SHA256(root_n || authoritative event fields)
```

The experiment does not currently implement a Merkle tree. Historical result text using “Merkle” should be interpreted as referring to this hash-chained evidence root; current documentation uses the precise term.

## Gate G1 clarification

Earlier reports described `G1` as requiring a non-zero rejection count during a device-outage phase. That conflates two different properties.

The sealed interpretation is:

1. **policy competence:** an adapted policy may avoid proposing an offline device entirely; and
2. **authority enforcement:** an explicitly invalid/offline-target proposal must be rejected and must not mutate authority.

Therefore a stochastic endurance run may legitimately record zero outage-phase rejections if the policy never proposes the offline device. The authority property is not weakened by successful avoidance.

## Physical evidence versus automated CI

Physical claims require the recorded hardware campaigns and are not recreated by GitHub-hosted runners.

CI is intended to verify every portable part that does not require the attached physical devices:

- canonical repository tests and acceptance smoke;
- portable C++ authority qualification;
- host protocol tests;
- external proposer tests;
- router policy/mock-authority tests;
- stochastic environment tests;
- concurrency/OCC tests;
- endurance/distribution tests;
- both ESP32-S3 firmware core-mapping builds.

GPU/NPU/COM10 hardware identity and performance claims remain physical qualification results.

## Included evidence

Primary human-readable records:

- `HARDWARE_RESULTS.md`
- `EXTERNAL_PROPOSER_TEST.md`
- `ROUTER_CAMPAIGN_RESULTS.md`

Primary machine-readable records:

- `artifacts/*.json`
- `host/artifacts/router_campaign_report_seed_42.json`
- `host/artifacts/router_campaign_report_seed_101.json`
- `host/artifacts/multi_seed_report.json`

The full blob inventory and Git identities are recorded in `QUALIFICATION_MANIFEST.json`.

## Scope boundaries

This qualification does **not** establish:

- arbitrary distributed-system correctness;
- arbitrary workload generality;
- unlimited concurrency;
- unlimited-duration convergence or stability;
- network-partition tolerance;
- replicated or consensus-based authority;
- arbitrary ESP32 hardware-failure recovery;
- a formal proof of the scheduler implementation;
- general continual-learning convergence.

It establishes the tested architecture under the sealed conditions.

## Canonicalization decision

This branch is ready for repository review as a coherent research lineage. Before merging to `main`, review should distinguish:

1. **canonical architectural mechanisms** worth retaining;
2. **qualification harnesses and evidence** worth retaining as tests/research records;
3. **hardware-specific adapters/models** that may remain optional qualification assets;
4. any material that represents a new capability rather than the already demonstrated UoW architecture.

No merge is implied by this seal.
