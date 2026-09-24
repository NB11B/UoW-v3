# UoW Software Candidate Freeze

Status: **policy-integrated v2 software candidate frozen and exact-seal qualified**.

The final software candidate is:

`archive/uow-reduction-software-candidate-v2@728988f93a1ec0f634f450dc4d187fbd5e0e95c9`

Exact-seal run **158** passed **277/277** reduced shadow tests and **44/44** post-A3 P1-P5 policy tests.

The earlier `archive/uow-reduction-software-candidate@f842d62c7d18355886e2c9fdc25e9cc5db17987b` remains immutable as **pre-policy historical evidence only**. It is not the final release or physical-qualification target.

## Architectural closeout

The recovered architecture keeps semantic authority, conformance, transition, effect, evidence, transaction, resource, orchestration, graph, binding, history, delegation, mutation, and policy rules in canonical semantic packages. Stateful or substrate-specific machinery remains behind implementation/realization boundaries with historical compatibility imports preserved.

The post-A3 Policy-Aware UoW Orchestrator P1-P5 implementation is now part of the canonical package under `uow.policy`. Its frozen reference remains `policy-orchestrator-p5-qualified@aa886329298f87e8b006501d47dd89eb8f0d4a3b`.

The policy namespace is intentionally not flattened into the top-level facade because `uow.RealizationGraph` and `uow.policy.RealizationGraph` represent different qualified semantics.

## Freeze surfaces

The top-level `uow` package is a **200-symbol compatibility facade** for v2, including the `policy` namespace export. Exact symbols are pinned in `architecture/public_api_manifest.yaml`.

Wire, authority, mutation-QC, graph-substitution, quorum-commit, and cross-language conformance profiles are pinned by Git blob identity in `architecture/canonical_profiles_manifest.yaml`.

Physical source inputs are pinned in `qualification/final_physical_candidate_inputs.yaml`. Final flash/executable binaries are not stored as release binaries, so F0 must build/export them from the frozen source inputs and record cryptographic binary hashes before any physical claim is promoted.

## Preserved failure evidence

The reduction and finalization campaign intentionally retains failure evidence that exposed architectural or release-gate assumptions, including runs 139, 144, 149, 155, 159, and 160. Each was repaired without silently erasing the failed condition.

## Next gate

No further semantic software changes are planned. The next operation is local reproduction followed by the single consolidated physical confirmation campaign in `qualification/FINAL_PHYSICAL_CONFIRMATION_PLAN.md`, beginning with F0 candidate/binary attestation against the **v2** candidate.
