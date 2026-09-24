# R4 Validation Record

## Reconstructed and passing

- U1-U10 — runs 23/24.
- U11 — runs 25/26.
- U12 — runs 27/28.
- U13 — runs 29/30.
- U14 — runs 31/32.
- U14-B — runs 33/34.
- Q1 — runs 37/38.
- U15.1-U15.4 portable — runs 39/41/42.

## Distributed authority portable reconstruction now under test

The reconstruction keeps attestation formation explicit:

independent replica evaluation
-> AuthorityVote
-> threshold QuorumCertificate
-> QC verification
-> minimal shadow quorum authorization
-> shadow AuthorizedTransition
-> independent evidence chain

The canonical AuthorityNode.apply_quorum_certificate path is excluded.

Preserved negative controls:
- only one reachable authority cannot commit;
- conflicting proposals from one pre-state cannot both obtain quorum;
- divergent replica is quarantined rather than overwritten;
- duplicate QC delivery is idempotent;
- ruleset mismatch cannot silently participate.

Self-healing is reconstructed as verified replay of QC journal entries only from a recognized prefix. A non-prefix state is quarantined.
