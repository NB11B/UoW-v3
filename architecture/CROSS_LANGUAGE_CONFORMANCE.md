# Cross-Language Conformance Inventory

## Objective

Separate two different architectural claims:

### Semantic conformance

[
Exec_L(U,S)=Exec_{reference}(U,S)
]

An implementation in language/substrate `L` obeys the same transition and authority semantics.

### Canonical byte / wire conformance

[
CanonicalBytes_L(x)=CanonicalBytes_{reference}(x)
]

Implementations produce identical authority-bearing bytes/hashes for interoperable objects.

The repository currently provides meaningful evidence for semantic conformance between Python and embedded C++, but it does not yet define one universal byte representation for every object.

## Existing Python primitives

Canonical Python core:
- `WorldState`
- `Proposal`
- `CertificateResult`
- `EvidenceRecord`
- `EvidenceLedger`
- `propose`
- `certify`
- `commit`

Python canonical representation is generally deterministic JSON using sorted keys and compact separators.

## Existing embedded C++ primitives

The ESP32/UNO Q implementation independently contains:
- `State`
- `Proposal`
- `Certificate`
- `EvidenceRecord`
- `EvidenceLedger`
- `propose`
- `certify`
- `commit`
- `execute_one`

It also enforces:
- state hash preconditions;
- independent recomputation;
- stale-state rejection;
- route/state/halt divergence rejection;
- proposal hash verification;
- append-only hash-chained evidence.

This is strong evidence that the authority grammar is not Python-specific.

## Known byte-level mismatch

Python state identity is derived from canonical JSON.

Embedded C++ state identity currently uses explicit deterministic strings such as:

```text
r0=<...>;r1=<...>;pc=<...>;sequence=<...>;halted=<0|1>
```

Therefore:

[
SemanticConformance = plausible/demonstrated
]

does not imply:

[
CanonicalByteConformance = demonstrated
]

## Cross-language semantic vector candidates

| Vector | Python | C++ | Required comparison |
|---|---|---|---|
| INC transition | core UoW | embedded Program | same semantic next state |
| DECJZ zero branch | core UoW | embedded Program | same branch/result |
| DECJZ nonzero branch | core UoW | embedded Program | same decrement/result |
| HALT | core UoW | embedded Program | same halt semantics |
| stale pre-state | certifier | embedded certifier | both reject |
| tampered proposed state | certifier | embedded certifier | both reject |
| route divergence | certifier | embedded certifier | both reject |
| evidence-chain discontinuity | EvidenceLedger | embedded EvidenceLedger | both reject |
| replay | Python ledger | C++ ledger | same semantic history, byte equality only if canonical spec requires it |

## Objects requiring future language-neutral schemas

Priority 1:
- authoritative state;
- work contract;
- proposal;
- certificate/attestation envelope;
- evidence record;
- history entry.

Priority 2:
- resource requirement;
- actor descriptor;
- actor binding;
- delegation grant;
- quorum vote/QC;
- effect receipt;
- runtime mutation proposal.

## Interoperability levels

### L0 — behavioral
Same inputs produce semantically equivalent outputs.

### L1 — rejection
Same invalid inputs are rejected under equivalent reason classes/invariants.

### L2 — evidence semantic
Both implementations generate complete evidence with equivalent causal bindings.

### L3 — wire schema
Serialized objects are mutually readable.

### L4 — canonical bytes
Authority-bearing canonical byte sequence is identical.

### L5 — canonical hashes
All authority-bearing identity hashes match bit-for-bit.

Not every local realization requires L5. Distributed cross-language authority participants probably do.

## Research rule

Do not replace current Python or C++ canonicalization until experiments establish which interoperability level each boundary actually requires.
