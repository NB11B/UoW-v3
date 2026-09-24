# R5 Cross-Language Conformance Exit Record

Control baseline: `main@f4dc767322233cd3bd9afc6c1b7af45a3987111d`

Latest shadow runs: 67/68 PASS.

Latest shadow suite: **145 passed**.

## L0 — Behavioral semantic conformance

Python shadow reconstruction, compiled C++ embedded core, and the independent Minsky reference interpreter agree on:
- final machine state;
- halt behavior;
- causal step count;
- evidence-step count.

## L1 — Rejection conformance

Python and C++ reject the same semantic invariant classes for:
- stale pre-state;
- proposed-state divergence;
- route divergence.

Error-token spelling is not required to be identical when the semantic rejection class is equivalent.

## L2 — Evidence-semantic conformance

Python and C++ preserve equivalent evidence semantics:
- one evidence step per committed transition;
- deterministic replay;
- valid causal evidence chain.

Cross-language record-hash equality is not claimed at this level.

## L3 — Wire-schema conformance

`UOW-CORE-WIRE/1` provides mutual decoding for:
- State;
- Proposal;
- Certificate;
- Evidence.

Python-generated messages are decoded by compiled C++ and C++-generated messages are decoded by Python.

The decoder:
- ignores field ordering semantically;
- rejects bad prefix/kind;
- rejects missing/duplicate fields;
- rejects invalid integers, booleans, and hash fields.

This profile is transport interoperability, not canonical authority identity.

## L4/L5 — Boundary-specific canonical identity

The heterogeneous physical-authority protocol already defines an exact shared canonicalization profile for:
- authority state;
- proposal;
- deterministic certificate;
- evidence record;
- AuthorityVote;
- QuorumCertificate.

R5 verifies exact canonical-string equality and SHA-256 equality between:
- the R5 Python profile;
- a compiled C++ profile using the embedded SHA-256 implementation;
- the existing x86 authority-service hash functions.

The ESP32-S3 and UNO Q firmware source implements the same canonical vote/QC field ordering used by this profile.

### Scope restriction

This L4/L5 result is **boundary-specific**.

Generic Python `WorldState.state_hash` remains based on canonical JSON and is intentionally not equal to the physical-authority state hash profile.

Therefore:

[
L4/L5_{authority} 
otRightarrow L4/L5_{global}
]

## Physical evidence

R5 does not re-run physical devices.

Existing physical qualification remains the evidence that the authority profile has operated across ESP32-S3, STM32, and x86 authority domains.

The new R5 tests provide source/runtime cross-language conformance, not replacement physical evidence.

## R5 disposition

`R5_CROSS_LANGUAGE_CONFORMANCE = COMPLETE_INITIAL`.

The architecture now supports:
- language-neutral semantic contracts;
- language-specific implementations;
- explicit wire profiles;
- stronger canonical identity profiles only at boundaries that require them.

This is sufficient to enter R6 reduction eligibility without imposing one serialization/hash format on the whole repository.
