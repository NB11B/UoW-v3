# R6 Reduction Eligibility Audit

## Purpose

R6 asks which current structures may be consolidated **without reducing the reconstructed capability set**.

Reconstruction is not deletion authority.

## Eligibility classes

- **K0 — RETAIN_AXIOMATIC:** semantic primitive or trusted boundary.
- **K1 — RETAIN_REALIZATION:** distinct implementation, baseline, substrate, or evidence-bearing realization.
- **K2 — CONSOLIDATE_INTERFACE_ONLY:** common ontology/interface is justified; implementation collapse is not.
- **K3 — SHADOW_REFACTOR_ELIGIBLE:** reconstruction evidence supports a common implementation/control-flow prototype beside production code.
- **K4 — DELETE_ELIGIBLE:** no unique capability, negative control, API role, realization property, or evidence role remains.

At R6 entry there are **zero K4 candidates**.

## Candidate matrix

| Construct/family | Eligibility | Evidence / disposition |
|---|---|---|
| Authoritative state / semantic contract / proposal / conformance / authorization / transition / evidence | K0 | Reconstructs the full portable experiment chain |
| Proposal != authority boundary | K0 | U14, U15, distributed authority, A2 |
| External effect boundary | K0 | Q1 proves external invocation != internal commit |
| TransitionContract vs IntentContract | K0/K1 | R4 reconstructs both but does not prove they are one contract type |
| Typed requirement/capability matching | K2 | Resource, actor, authority, OCC, timing, evidence, failure predicates fit one typed ontology; specialized predicates remain necessary |
| Repeated proposal/certify/commit control flow across orchestration/resources/proposer/effects | K3 | U11-U15/Q1 reconstruct through one minimal authority application spine |
| A2 graph/rebinding/delegation/history/QC application paths | K3 | R3/R4 application-closure results |
| Runtime -> qualification dependency in QuorumCommitSequencer | K3 HIGH PRIORITY | Caused real circular import during reconstruction; shadow authority protocol works without qualification dependency |
| canonical_json helper duplication | K2 | Identity primitive is common; byte profiles are boundary-specific |
| compute_hash/calculate_hash boilerplate | K2 | Common identity ontology justified; payload fields remain type-specific |
| to_dict/from_dict boilerplate | K2 | Versioned schema generation may reduce code after artifact round-trip proof |
| DeterministicSequencer / WALSequencer / QuorumCommitSequencer | K1 + K2 interface | Distinct durability/authority realizations must remain |
| EvidenceLedger / WAL / AuthoritativeHistory / TopologyLineage | K1 + K2 interface | Common lineage semantics; different ordering/durability/distribution properties |
| A2.6 wire/host/WAL mechanisms | K1 | Retained transport/durability realization, not axiom |
| Random proposer / FIFO / B0 / B1 / adversarial controls | K1/P2 | Scientific baselines and falsification instruments |
| U14-B graph synthesis | K1 | Unique goal -> candidate graph capability reconstructed from archive |
| archived U12 concurrent_engine | K1 | Actual threaded execution realization remains useful |
| semantic_matrix_prior | K1 | Optional ontology-informed concurrency optimization |
| bounded backend | P2/P3 | Falsification boundary for extensible-memory universality |
| embedded C++ / ESP32 / UNO Q / physical authority code | K1/P3 | Cross-language + physical evidence |
| proposer/learned.py compatibility aliases | K1 compatibility | Public/package/test consumers still exist |
| flat top-level `uow` re-export surface | R7 organization candidate | API organization does not imply semantic level |

## First R6 refactor prototypes

### R6-A — Common authority application spine

Prototype a common internal control flow for:

[
Candidate
ightarrow Conformance
ightarrow Authorization
ightarrow Transition
ightarrow Evidence
]

while retaining domain-specific:
- proposal formation;
- validators;
- authorization profiles;
- pre/post hooks;
- external-effect boundary.

Target duplicated paths:
- orchestration runtime;
- resource-aware runtime;
- proposer engine;
- effect bookkeeping transitions;
- A2 accepted meta-mutations.

### R6-B — Authority protocol decoupling

Prototype a semantic authority-provider interface independent of qualification packaging.

Required operations:
- evaluate candidate / issue vote;
- verify vote;
- aggregate threshold authorization;
- verify authorization;
- apply authorized transition through the common spine.

Qualification and physical implementations become realizations of the interface.

### R6-C — Identity/schema consolidation

Do not centralize bytes globally.

Instead:
- centralize semantic schema/version/profile metadata;
- retain boundary-specific canonicalization profiles;
- generate serialization helpers only where round-trip and historical-artifact compatibility are proven.

## Explicit non-candidates

R6 must not:
- remove B0/B1 or negative controls;
- collapse WAL/quorum/memory commit implementations;
- replace physical evidence with portable tests;
- merge TransitionContract and IntentContract by naming alone;
- convert external effects into ordinary internal state mutation;
- impose the heterogeneous-authority hash profile globally.

## R6 exit criterion

R6 is complete when each K3 candidate has a shadow refactor prototype demonstrating:
1. reconstructed experiment parity;
2. no loss of negative controls;
3. no evidence-level downgrade;
4. no public API break;
5. a measurable reduction in duplicated implementation/control flow.

Only then may R7 reorganize repository structure around the validated architecture.
