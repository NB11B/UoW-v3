# Frozen Reference Oracles for Reduction

The reduction/reorganization program is not judged only against `main@f4dc767`.

It must also preserve the qualified architectural behaviors established by later frozen research branches.

The governing rule is:

[
\boxed{
\text{implementation may change}
\quad\land\quad
\text{qualified architectural invariants must remain reconstructable}
}
]

## Oracle O1 — A2 portable adaptive-composition baseline

- Repository: `NB11B/UoW`
- Baseline: `main@f4dc767322233cd3bd9afc6c1b7af45a3987111d`
- Scope: U1-U15 portable, distributed authority portable, A2.0-A2.8, Q1.
- Reduction status: reconstructed through R4.

## Oracle O2 — A3 adaptive compute efficiency

- Branch: `qualification/a3-adaptive-compute-efficiency`
- Qualification tag: `a3-qualification-complete`
- Qualified long-soak anchor: `05c8094ac5c8572f7da6d00e781ce673754c5c59`
- Synthesis: `A3_FINAL_SYNTHESIS.md`
- Status: sealed experimental reference.

A3 adds acceptance requirements that are not implied merely by A2 correctness:

1. Computational architecture/placement is itself a measurable efficiency variable.
2. The efficient realization is a graph, not simply a device assignment.
3. Heterogeneous composition may outperform every monolithic device realization.
4. Discovery produces candidates only; it has zero promotion authority.
5. Prospective qualification gates policy promotion.
6. Qualified policy lookup is the normal steady-state execution path.
7. Learning/exploration may become exceptional while policy reuse dominates.
8. Power/capacity constraints participate in valid placement.
9. Semantic equivalence and hard correctness gates remain invariant under placement changes.
10. Physical energy/latency qualification remains separate from modeled/portable evidence.
11. Policy residency, promotion, invalidation, and thrash are measurable lifecycle properties.
12. Long-duration soak/endurance evidence remains part of the claim.

A3 physical/device artifacts remain retained evidence. Portable reconstruction must not replace them.

## Oracle O3 — Post-A3 Policy-Aware UoW Orchestrator P1–P5

This is the final qualified architecture layer built after A3 on September 23, 2026. It is a downstream extension of A3, not merely another name for A3.

- Branch: `architecture/policy-aware-uow-orchestrator`
- Tag: `policy-orchestrator-p5-qualified`
- Frozen commit: `aa886329298f87e8b006501d47dd89eb8f0d4a3b`
- Synthesis: `POLICY_ORCHESTRATOR_P1_P5_FINAL_SYNTHESIS.md`
- Status: qualified, feature-complete, frozen reference architecture.
- P1-P5 policy suite at closeout: 44 passed, 0 failed.
- Complete repository verification at closeout: 324 passed, 0 failed.
- No P6 is required for this series.

P1–P5 is downstream of A3 and contains the A3 experimental tree. Evidence inherited from A3 must not be double-counted as a separate independent physical campaign.

### Thirteen mandatory P1–P5 acceptance invariants

1. Canonical UoW -> requirement projection.
2. Deterministic world-state snapshot.
3. Execution realization graphs.
4. Qualified, immutable, versioned policy registry.
5. Discovery without authority.
6. Prospective qualification before promotion.
7. Deterministic policy reuse.
8. Live drift invalidation and safe replacement without corrupting in-flight work.
9. Transactional registry versioning with cryptographic lifecycle records.
10. Distributed policy authority distinct from compute capability.
11. Durable persistence and fail-closed crash recovery.
12. Zero duplicate external effects during recovery.
13. Full cryptographic provenance from distributed policy authority through recovery, lifecycle, policy decision, and execution certificate.

These are acceptance gates. Their current Python implementation is not itself canonical.

## Oracle O4 — A4 ontology adaptation frontier

Project hierarchy:

[
A0 \rightarrow A1 \rightarrow A2 \rightarrow A3 \rightarrow A4
]

A4 denotes **ontology adaptation**: the ability for the architecture's categories/types/semantic vocabulary to evolve under controlled evidence and authority rather than remaining permanently hard-coded.

Status: **CONCEPTUAL / UNQUALIFIED**.

There is currently no qualified `A4` branch in `NB11B/UoW`.

Therefore A4 has a different role from O1-O3:

- it is not evidence that an implementation already works;
- it must not be represented as a passed experiment;
- it is a forward-compatibility constraint on reduction and ontology design.

### A4 reduction constraint

The reduced architecture should not make ontology extension impossible by baking today's Python enums/classes into the universal protocol.

The future ontology must support versioned extension while preserving:
- deterministic meaning for a given ontology version;
- authority over ontology changes;
- migration lineage;
- compatibility/rejection rules;
- reconstruction of prior experiment semantics.

A4 qualification should occur only after the canonical ontology/protocol exists.

## Handoff rule

Every future consolidation/move must answer:

1. Which O1-O3 qualified invariant(s) does this code currently realize?
2. Does the target architecture preserve those invariants?
3. Is the code a unique realization/evidence artifact?
4. Does the change preserve A4 forward-compatibility without claiming A4 qualification?

No production deletion is allowed solely because a newer oracle includes an older branch's files.
