# UoW Software Candidate Freeze

Status: **policy-integrated v3 packaging candidate awaiting exact-seal qualification**.

The runtime/API content is unchanged from the policy-integrated v2 candidate. This v3 cut exists only to make the frozen repository package self-consistent for external review: candidate-local physical qualification files are neutral pre-seal templates rather than stale references to an earlier candidate.

Planned archive ref:

`archive/uow-reduction-software-candidate-v3`

The exact v3 commit is accepted only if it passes both **277/277** reduced shadow tests and **44/44** post-A3 P1-P5 policy tests.

## Runtime/API identity

The canonical package remains `uow` with the qualified post-A3 policy layer under `uow.policy`. V3 changes no runtime, authority, conformance, policy, persistence, recovery, or public API behavior.

## Historical candidates

- v1: `archive/uow-reduction-software-candidate@f842d62c7d18355886e2c9fdc25e9cc5db17987b` — immutable pre-policy evidence.
- v2: `archive/uow-reduction-software-candidate-v2@728988f93a1ec0f634f450dc4d187fbd5e0e95c9` — policy-integrated software candidate; superseded only for release-package metadata consistency.

## Candidate-local physical metadata

The frozen v3 tree deliberately uses `UNBOUND_PRESEAL` markers for the final physical target. A commit cannot self-embed its own final SHA. After exact-seal CI passes, post-freeze operator metadata binds the immutable v3 SHA and the harness is qualified separately.

## Next gate

Exact combined software qualification, creation of the v3 archive ref, then post-freeze physical-harness binding and local F0-F8 qualification.
