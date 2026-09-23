# Candidate Axioms and Structural Laws

These are extracted from recurrence across code and persistence across experiments. They are candidates until falsification/reconstruction work is complete.

## A0 — Semantic invariance under valid realization

[
R_i \models U \Rightarrow \Phi(R_i,U)=\Phi(U)
]

Meaning is distinct from implementation.

## A1 — Authoritative state is distinct from speculation

There exists an authoritative state `S_t`. Proposals, observations, telemetry, model state, and candidate graphs are not authoritative merely by existing.

## A2 — Authority-bearing objects have deterministic canonical identity

[
I(x)=H(C(x))
]

The architectural requirement is deterministic canonical identity. JSON and SHA-256 are current realizations, not the axiom itself.

## A3 — Proposal does not confer authority

[
\operatorname{Propose}(x) \not\Rightarrow \operatorname{Authorize}(x)
]

This law persists across deterministic, stochastic, learned, NPU, graph, delegation, and runtime-mutation experiments.

## A4 — Independent conformance precedes authoritative mutation

A candidate must satisfy the requirements of the work and its current causal context before it can become authoritative.

[
R \models Q(U)
]

Current specializations include core certification, OCC validation, resource legality, actor binding, semantic projection, receipt verification, delegation validation, and quorum verification.

## A5 — Authoritative mutation requires authorization

[
P \rightarrow C \rightarrow A \rightarrow (S_t\rightarrow S_{t+1})
]

Certification alone is not equivalent to mutation authority.

## A6 — Authoritative mutation produces lineage

[
S_t\rightarrow S_{t+1} \Rightarrow E_t
]

Lineage includes evidence ledgers, WAL entries, receipts, model ancestry, topology lineage, delegation certificates, quorum certificates, and distributed history.

## A7 — Authority is causally scoped

An authorization is bound to the state/history/generation for which it was issued.

[
A(P,S_t) \not\Rightarrow A(P,S_{t+k})
]

Current realizations include state hashes, sequence numbers, epochs, generations, history heads, previous hashes, lease epochs, and parent hashes.

## Candidate structural laws

### S1 — Requirement / capability satisfaction

[
\operatorname{Capabilities}(R,S) \models \operatorname{Requirements}(U)
]

Resource capacity, actor capabilities, authority classes, dependency readiness, OCC compatibility, temporal bounds, and evidence requirements may be specializations of this relation.

### S2 — Fail closed when required authority is unavailable

[
\neg A_{required} \Rightarrow \neg \Delta S
]

### S3 — Retryable external/distributed work requires stable idempotent identity

Retry must not imply duplicate authoritative or external mutation.

### S4 — Delegation cannot create authority

[
A(U_{child}) \subseteq A(U_{parent})
]

### S5 — External effect is not internal commit

[
\Delta S \neq F_{external}
]

### S6 — Causal correctness is independent of one global mutable wall clock

Local timing may be observed, but causal order and authority must not depend on a shared execution timer.

## Promotion test

A candidate becomes axiomatic only after satisfying:

1. recurrence across independent subsystems;
2. experimental persistence across multiple campaigns;
3. architectural necessity;
4. language-neutral statement;
5. falsifiability;
6. measurable reduction value.
