# UoW Software Candidate Freeze

Status: **policy-integrated v2 candidate pending exact combined qualification**.

This cutover ends the staged software/repository relocation campaign. The preseal package at `88b2802197c93d8a1a6e7bd52becad9c98e264c9` passed shadow run **147** with **271/271** tests. The exact seal commit `f842d62c7d18355886e2c9fdc25e9cc5db17987b` independently passed shadow run **148** with **271/271** tests and is preserved at `archive/uow-reduction-software-candidate`.

## Architectural closeout

The recovered architecture now keeps semantic authority, conformance, transition, effect, evidence, transaction, resource, orchestration, graph, binding, history, delegation, and mutation rules in canonical semantic packages. Stateful or substrate-specific machinery has been moved behind implementation/realization boundaries with historical compatibility imports preserved.

The reduction campaign found no remaining K3 code-reduction seam after the common application spine and authority-provider inversion. Later work was K1 relocation or semantic/realization splitting. In particular, graph substitution certification remains semantic; delegation authority rules remain semantic; mutation proposal/vote/QC/history rules remain semantic.

Two failed shadow attempts are intentionally retained as evidence. Run 139 exposed an eager-import cycle and led to a non-semantic package-initialization repair. Run 144 showed that the canonical history dependency in runtime-mutation semantics is architectural and must not be removed as an apparently unused import.

## Freeze surfaces

The top-level `uow` package remains a 199-symbol compatibility facade for this candidate. Its existence does not imply that every symbol is axiomatic. Exact symbols are pinned in `architecture/public_api_manifest.yaml`.

Wire, authority, mutation-QC, graph-substitution, quorum-commit, and cross-language conformance profiles are pinned by Git blob identity in `architecture/canonical_profiles_manifest.yaml`.

Physical confirmation inputs are pinned in `qualification/final_physical_candidate_inputs.yaml`. Final flash/executable binaries are not stored as release binaries in this tree, so F0 must build/export them from the frozen source inputs and record cryptographic binary hashes before any physical claim is promoted.

## Next gate

The exact freeze commit is preserved under `archive/uow-reduction-software-candidate`. No semantic changes follow this freeze. The next engineering operation is the single consolidated physical confirmation campaign described in `qualification/FINAL_PHYSICAL_CONFIRMATION_PLAN.md`, beginning with F0 candidate and binary attestation.


## Policy-integrated v2 candidate

The post-A3 P1-P5 implementation is now merged into the canonical package under `uow.policy`. Integration validation at `8b6893f3b4db4da161a27f89fd905feb7a794a87` passed **277/277** reduced shadow tests and **44/44** P1-P5 policy tests in run **156**.

The original `archive/uow-reduction-software-candidate@f842d62c7d18355886e2c9fdc25e9cc5db17987b` remains immutable as the pre-policy candidate. It is not the final physical target.

The new candidate will be frozen under `archive/uow-reduction-software-candidate-v2` only when the exact commit containing the v2 freeze manifest independently passes both required suites.
