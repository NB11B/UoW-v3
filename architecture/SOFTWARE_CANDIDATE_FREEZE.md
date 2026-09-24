# UoW Software Candidate Freeze

Status: **self-consistent policy-integrated v3 software candidate frozen and exact-seal qualified**.

Final software candidate:

`archive/uow-reduction-software-candidate-v3@3e28e4bba1023810aada953e25d3e3c46a58f113`

Exact-seal run **167** passed **279/279** reduced shadow tests and **44/44** post-A3 P1-P5 policy tests.

V3 changes no runtime/API behavior from v2. It exists to make the frozen repository package self-consistent: candidate-local physical qualification files contain neutral `UNBOUND_PRESEAL` markers rather than stale identifiers from earlier candidates.

## Runtime/API identity

The canonical package remains `uow` with the qualified post-A3 policy layer under `uow.policy`. The composition and policy `RealizationGraph` types remain intentionally namespaced and distinct.

## Historical candidates

- v1: `archive/uow-reduction-software-candidate@f842d62c7d18355886e2c9fdc25e9cc5db17987b` — immutable pre-policy evidence.
- v2: `archive/uow-reduction-software-candidate-v2@728988f93a1ec0f634f450dc4d187fbd5e0e95c9` — policy-integrated candidate superseded only for packaging-metadata consistency.
- v3: `archive/uow-reduction-software-candidate-v3@3e28e4bba1023810aada953e25d3e3c46a58f113` — final software candidate.

## Physical qualification binding

The frozen v3 tree intentionally does not self-encode its own SHA. Post-freeze operator metadata binds the immutable v3 commit and the hardware harness is qualified separately. That binding does not alter the frozen software candidate.

## Next gate

The post-freeze v3 harness passed run **169** with **279/279 + 44/44**. The remaining work is local reproduction followed by the consolidated F0-F8 physical campaign.
