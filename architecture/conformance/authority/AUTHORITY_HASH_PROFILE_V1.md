# UoW Heterogeneous Authority Hash Profile v1

Status: R5 boundary-specific canonicalization profile.

This profile documents the authority identity format already implemented by:
- the x86 Python authority service;
- ESP32-S3 authority firmware;
- Arduino UNO Q STM32 authority firmware.

It is not the universal canonical representation for all UoW objects.

## Scope

The profile applies to the heterogeneous physical authority boundary used for:
- authority state identity;
- proposal identity;
- deterministic certificate identity;
- evidence-record identity;
- AuthorityVote identity;
- QuorumCertificate identity.

## Canonical strings

### State

```text
r0=<u64>;r1=<u64>;pc=<u32>;sequence=<u64>;halted=<0|1>
```

### Proposal

```text
pre=<pre_state_hash>;post=<post_state_hash>;pc=<selected_pc>;halted=<0|1>
```

### Certificate

```text
proposal=<proposal_hash>;valid=<0|1>;reason=<reason_code>
```

### Evidence

```text
step=<n>;pre=<pre>;post=<post>;proposal=<proposal>;certificate=<certificate>;prev=<previous_root>
```

## Vote canonical JSON

Fields in canonical order:

```text
accepted
certificate_hash
evidence_step
node_id
pre_evidence_root
pre_state_hash
proposal_hash
proposed_state_hash
rejection_reason
ruleset_version
```

Encoding:
- compact UTF-8 JSON;
- booleans are JSON booleans;
- absent rejection reason is JSON null;
- no whitespace.

## Quorum-certificate canonical JSON

Fields in canonical order:

```text
certificate_hash
committed_state_hash
evidence_step
expected_evidence_root
pre_evidence_root
pre_state_hash
proposal_hash
proposed_state_hash
ruleset_version
threshold
uow_id
vote_hashes
voters
```

Arrays preserve supplied order. Qualification code sorts/selects voter identity before QC formation where required.

## Identity function

All objects in this profile use:

[
Identity(x)=SHA256(CanonicalBytes(x))
]

with lowercase hexadecimal digest rendering.

## R5 interpretation

For this profile, exact canonical-string equality is an L4 property and exact SHA-256 equality is an L5 property.

This does not imply that native Python WorldState, generic A2 objects, or every future UoW object must adopt this representation.

Profile boundaries must be explicit.
