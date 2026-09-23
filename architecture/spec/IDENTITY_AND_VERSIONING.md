# Identity, Canonicalization, and Causal Versioning — Draft

## 1. Separate concepts

The current repository often uses hashes for several different roles. R2 separates them conceptually.

### Semantic identity

Deterministic identity of authority-relevant semantic content.

I_semantic(x) = Hash(Profile, CanonicalSemanticPayload(x)).

### Representation identity

Identity of a particular serialized artifact or implementation object.

This MAY differ from semantic identity where two encodings are semantically equivalent.

### Actor / issuer identity

Identity of the source responsible for an assertion, proposal, vote, or execution role.

### Causal coordinate

The context in which an authority-bearing object is valid.

Examples:
- state sequence;
- transaction versions;
- graph generation;
- model generation;
- history head;
- lease epoch.

These are typed coordinates, not one universal integer.

## 2. Canonicalization profile

Every authority-bearing object that requires deterministic identity MUST declare or inherit a canonicalization profile:

profile_id
schema_id
schema_version
canonicalization_algorithm
hash_algorithm

Current realizations include canonical JSON and embedded deterministic strings.

R2 does not declare either universally canonical.

## 3. Schema version vs causal version

Never conflate schema_version with sequence, epoch, generation, or history_head.

Schema version changes representation/meaning rules.

Causal version identifies position/state within an execution history.

## 4. Freshness law

An authority-bearing object is valid only for the causal context it names.

Valid(x,C_t) does not imply Valid(x,C_t+k), unless a contract explicitly defines persistence across those contexts.

## 5. Cross-language profiles

A boundary declares required conformance:
- semantic only;
- mutually decodable wire schema;
- canonical bytes;
- canonical hash.

Distributed authority messages are likely to require stronger profiles than local-only implementation objects.

## 6. Versioned migration rule

Changing canonicalization or authority-bearing schema is a semantic migration, not an ordinary refactor.

A migration MUST:
- preserve old artifact readability or explicitly version-break it;
- identify invalidated physical evidence;
- identify claims requiring requalification;
- provide cross-version rejection/upgrade rules.
