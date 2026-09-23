# Conformance Profiles — Draft

Different boundaries need different notions of same implementation.

## L0 — Behavioral semantic conformance

Equivalent valid input yields semantically equivalent result.

Exec_A(U,S) equivalent-to Exec_B(U,S).

## L1 — Rejection conformance

Invalid inputs violate the same semantic invariants and are rejected.

Exact error strings need not match unless externally specified.

## L2 — Evidence semantic conformance

Both implementations produce evidence containing equivalent authority-relevant bindings and causal information.

## L3 — Wire-schema conformance

Serialized messages/artifacts are mutually decodable under a shared schema.

## L4 — Canonical-byte conformance

The canonical byte sequence for the same semantic object is identical.

## L5 — Canonical-hash conformance

Authority-bearing object identities are bit-for-bit equal.

## Example requirements

### Local scheduling policy

May only require L0/L1.

### Python -> external NPU proposer

Likely requires L0/L1 plus a defined proposal adapter contract; L5 may not be necessary if the authority layer rebinds the proposal canonically.

### Heterogeneous authority quorum

Likely requires L3-L5 for vote/QC fields that participate in cross-device authorization.

### Historical qualification artifact

Must retain the profile under which it was qualified. New canonicalization does not silently rewrite old evidence.

## Profile declaration

Every future cross-language interface SHOULD declare the minimum conformance level for each object family.

This prevents unnecessary global byte-level constraints while ensuring strong interoperability where authority demands it.
