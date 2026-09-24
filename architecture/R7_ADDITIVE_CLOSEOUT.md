# R7 Additive Architecture Closeout

**Branch:** `research/uow-closure-architecture`  
**Control baseline:** `main@f4dc767322233cd3bd9afc6c1b7af45a3987111d`  
**Status:** **Qualified additive target architecture / frozen reduction reference**

## Executive result

The reduction campaign has reached the point where the repository architecture, preservation requirements, experiment reconstruction, cross-language conformance, and cutover gates are all explicit.

The result is not a smaller production tree yet.

It is the qualified answer to:

> What may be consolidated, what must remain distinct, and what must survive any future reorganization?

The recovered core application grammar is:

[
oxed{
Proposal
ightarrow
Conformance
ightarrow
Authorization
ightarrow
AuthorizedTransition
ightarrow
Evidence
}
]

with explicit preserved boundaries for:
- external physical effects;
- attestation/quorum formation;
- typed causal contexts such as OCC;
- cursor-owned versus detached control-plane work;
- physical evidence substrate;
- policy lifecycle and distributed policy authority.

## Phase closeout

- R0 — frozen control: COMPLETE.
- R1 — architecture/evidence mapping: COMPLETE.
- R2 — language-neutral semantic specification: COMPLETE INITIAL.
- R3 — shadow minimal implementation: COMPLETE INITIAL.
- R4 — portable experiment reconstruction: COMPLETE INITIAL.
- R5 — cross-language conformance: COMPLETE INITIAL.
- R6 — reduction eligibility: COMPLETE INITIAL.
- R7 — additive repository organization and cutover audit: COMPLETE INITIAL.

Latest dedicated closure workflow: runs 95/96 PASS.

## Experiment preservation

The target architecture has reconstruction coverage for:
- U1-U10;
- U11;
- U12;
- U13;
- U14;
- U14-B;
- Q1;
- U15 portable;
- distributed authority portable;
- A2.0-A2.8.

A2.8 retained the original comparative objective values:

[
B0=8299.78,quad B1=5934.51,quad A2=5907.99.
]

## Frozen external reference oracles

Reduction acceptance now also includes:

### A3 adaptive compute efficiency

Branch:
`qualification/a3-adaptive-compute-efficiency`

A3 remains sealed experimental evidence for:
- heterogeneous graph efficiency;
- policy reuse;
- discovery without authority;
- prospective promotion;
- energy/capacity behavior;
- physical/device characterization;
- long-duration endurance.

### Policy Orchestrator P1-P5

Branch:
`architecture/policy-aware-uow-orchestrator`

Frozen commit:
`aa886329298f87e8b006501d47dd89eb8f0d4a3b`

All 13 policy-orchestrator invariants are explicit R7 acceptance gates.

No P6 is required.

### A4 ontology adaptation

A4 is retained as a conceptual, **unqualified** forward-compatibility frontier.

It constrains ontology design but is not represented as a passed experiment.

## Reduction result

R6 found:

[
oxed{	ext{delete-eligible components}=0}
]

The validated consolidation targets are instead:

1. common authority-application spine;
2. qualification-independent authority-provider protocol;
3. typed conformance registry.

Realization diversity remains intentional.

## Target repository form

The qualified additive structure is:

```text
specification/
implementations/
realizations/
experiments/
qualification/
conformance/
```

The target now includes first-class semantic surfaces for both:
- policy;
- ontology.

This is necessary to preserve A3/P1-P5 while remaining compatible with a future A4 ontology program.

## Cross-language result

R5 established:

- L0 behavioral semantic conformance;
- L1 rejection-class conformance;
- L2 evidence-semantic conformance;
- L3 mutual Python/C++ wire schema;
- boundary-specific L4/L5 canonical/hash equality for heterogeneous physical authority.

No global canonical serialization is imposed.

## Public API and physical evidence

The current production Python package remains byte-identical at the frozen public-surface files recorded in `PUBLIC_API_BASELINE.yaml`.

Current R7 work has not changed the physical production mechanism, so it does not itself trigger new hardware runs.

Historical physical evidence remains scoped to its original qualified head.

Any later material change to firmware, wire/hash semantics, NPU/GPU routing, evidence verification, recovery, negative controls, measurement paths, or A3 device profiles must trigger the corresponding requalification.

## Cutover disposition

The result is:

[
oxed{	ext{staged cutover planning eligible}}
]

but:

[
oxed{	ext{production cutover not authorized or performed}}
]

No production file has been moved or deleted.

A future staged-cutover branch should begin from this closeout head and move one K3 path at a time behind compatibility shims, rerunning:
- the reconstructed experiment suite;
- A3/P1-P5 oracle gates;
- API compatibility;
- physical-impact analysis

after every move.

## Branch handoff

This branch should now be treated as the **frozen reduction and target-architecture reference**.

Further production relocation should occur on a new branch rather than continuing to accrete architecture work here.
