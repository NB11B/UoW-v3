# UOW-CORE-WIRE/1

Status: R5 interoperability profile.

Purpose: provide a minimal mutually decodable wire schema for the core semantic objects already shown to be behaviorally conformant between Python and embedded C++.

This profile is **L3 wire-schema conformance only**.

It does not define:
- canonical authority bytes;
- canonical identity hashes;
- replacement serialization for existing Python or embedded C++ objects.

Therefore L3 conformance under this profile does not imply L4 or L5.

## Framing

One UTF-8 line:

```text
UOW1|<KIND>|key=value|key=value|...
```

Core v1 values are restricted to ASCII token values that do not contain `|` or `=`.

Decoders MUST reject:
- unknown protocol prefix;
- unknown object kind;
- missing required fields;
- malformed integer/boolean fields;
- duplicate keys.

Field order is not semantically significant for decoding.

## Kinds

### STATE

Required:
- r0: unsigned integer
- r1: unsigned integer
- pc: unsigned integer
- sequence: unsigned integer
- halted: 0 or 1

### PROPOSAL

Required:
- pre_state_hash: 64-char hex
- proposal_hash: 64-char hex
- r0: unsigned integer
- r1: unsigned integer
- pc: unsigned integer
- sequence: unsigned integer
- halted: 0 or 1
- selected_pc: unsigned integer
- proposal_halted: 0 or 1
- proposer_clock: unsigned integer

The embedded proposal's nested proposed State is flattened for transport.

### CERTIFICATE

Required:
- valid: 0 or 1
- reason: semantic rejection token
- certificate_hash: 64-char hex

Reason tokens are semantic labels, not language-specific enum ordinals.

### EVIDENCE

Required:
- step: unsigned integer
- pre_state_hash: 64-char hex
- post_state_hash: 64-char hex
- proposal_hash: 64-char hex
- certificate_hash: 64-char hex
- prev_record_hash: 64-char hex
- record_hash: 64-char hex

## Conformance requirement

L3 is satisfied when:
1. Python-generated messages are decoded by C++ with identical semantic field values.
2. C++-generated messages are decoded by Python with identical semantic field values.
3. field order differences do not alter decoded semantics.
4. malformed messages fail closed.

## Explicit non-claim

A deterministic encoder may use a stable field order for convenience. That stable wire rendering is not declared to be the canonical authority byte sequence and is not used to replace existing Python or C++ hash inputs.
