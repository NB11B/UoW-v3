# UoW Software Candidate Freeze

Status: **v4 physically qualified and release-closeout complete**.

Final software/qualification candidate:

`archive/uow-reduction-software-candidate-v4@9d95c11f4b09c34769e1f3a1e6d7b915291d43c8`

V4 incorporates the physically tested qualification/build surface, including USB CDC configuration, serial framing/reliability fixes, transaction-specific response matching, write flushing, retry handling, and the final F0 input manifest. Runtime/API semantics remain unchanged from the policy-integrated v3 candidate.

## Final qualification

The complete F0-F8 campaign ran with live flashing enabled and produced:

- `passed: true`
- `physical_claims_promotable: true`
- F0 source attestation: 18/18 pinned inputs
- F1 physical authority/quorum: PASS
- F2 heterogeneous execution: 13/13 gates PASS
- F2 evidence continuity: 2,400/2,400 cryptographic links verified
- F3-F6 NPU adaptive/hot-swap/drift/quorum: PASS
- F7 A3 frozen oracle: PASS
- F8 candidate shadow: 279/279 PASS
- F8 post-A3 P1-P5 policy suite: 44/44 PASS
- mandatory P1-P5 invariants: 13/13 PASS

Final campaign evidence is preserved under:

`qualification/artifacts/final-physical/20260924T203451Z/`

and summarized at:

`qualification/artifacts/final-physical-campaign-summary.json`

## Candidate lineage

- v1: `archive/uow-reduction-software-candidate@f842d62c7d18355886e2c9fdc25e9cc5db17987b` — pre-policy historical evidence.
- v2: `archive/uow-reduction-software-candidate-v2@728988f93a1ec0f634f450dc4d187fbd5e0e95c9` — policy-integrated candidate.
- v3: `archive/uow-reduction-software-candidate-v3@3e28e4bba1023810aada953e25d3e3c46a58f113` — self-consistent packaging candidate.
- v4: `archive/uow-reduction-software-candidate-v4@9d95c11f4b09c34769e1f3a1e6d7b915291d43c8` — final physically qualified candidate.

## Release state

No further architectural work or qualification repair is required by the completed campaign. Subsequent changes should begin from v4 as a new development cycle rather than mutating the closed evidence chain.
