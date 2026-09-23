# Canonicalization Profile Draft

## Purpose

Separate semantic schema from byte-level identity rules.

A semantic object may be conformant at L0-L2 without sharing one byte representation. Cross-device authorization may require stronger L3-L5 profiles.

## Profile fields

A canonicalization profile should declare:

- profile_id
- semantic_schema_id
- semantic_schema_version
- encoding
- field inclusion rules
- field ordering rules
- numeric normalization rules
- string normalization rules
- collection ordering rules
- hash algorithm
- domain separation / object-kind tag
- backward compatibility policy

## Existing profiles observed

### PY-CANONICAL-JSON-v1

Observed in Python canonical runtime:
- JSON representation;
- sorted mapping keys;
- compact separators;
- UTF-8;
- non-finite floats rejected.

This is an implementation profile, not yet a universal standard.

### EMBEDDED-KV-v1

Observed in C++ embedded qualification:
- deterministic explicit key/value string construction;
- fixed field order;
- SHA-256.

Again, implementation profile only.

## Why one global profile may be undesirable

Different boundaries may need different guarantees.

Local semantic objects may require only deterministic local identity.

Cross-language quorum votes require mutually agreed authority-bearing bytes/hashes.

Historical physical evidence must remain verifiable under the profile used when it was recorded.

## R2 rule

Do not replace either existing canonicalization realization.

R3/R5 must first identify which object families require:
- semantic identity only;
- wire decodability;
- canonical byte identity;
- canonical hash identity.

## Migration requirement

If an existing authority-bearing object moves to a new canonical profile:
- assign a new profile/version;
- never reinterpret an old digest as if computed under the new profile;
- identify claims needing requalification;
- provide explicit cross-profile verification or migration behavior.
