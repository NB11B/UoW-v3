# Source Module -> Semantic Concept -> Experiment Map

Baseline: `main@f4dc767322233cd3bd9afc6c1b7af45a3987111d`.

This map is descriptive. Preservation labels are research classifications, not refactor decisions.

| Module | Major symbols / functions | Primary semantic role | Experiment consumers | Preservation |
|---|---|---|---|---|
| `src/uow/ontology.py` | `WorkCategory`, `MatrixCell` | Semantic work ontology; classification orthogonal to computation | U1-U10, U11, U13, U14-B, Q1 | P0 |
| `src/uow/state.py` | `WorldState`, `canonical_json`, state hash, immutable updates | Canonical authoritative state + canonical representation | U1-U14, Q1, timing, U15 | P0 |
| `src/uow/contracts.py` | `UoW`, `Header`, `Contract`, `Route`, `Guard`, `Mutation`, `Successor` | Native work/transition contract algebra | U1-U14, Q1 | P0 |
| `src/uow/engine.py` | `Proposal`, `CertificateResult`, `EvidenceRecord`, `EvidenceLedger`, `propose`, `certify`, `commit`, `run` | Core proposal -> certification -> commit authority loop and evidence | U1-U14, Q1, U15 | P0 |
| `src/uow/transactions/descriptor.py` | `TransactionDescriptor`, `infer_footprint`, `create_transaction_descriptor` | Read/write/coupling footprint projection | U12-U14, Q1 | P0/P1 |
| `src/uow/transactions/occ.py` | `validate_occ`, `apply_transaction`, `HazardType` | Concurrency conformance / serializability predicate | U12-U14, Q1 | P0/P2 |
| `src/uow/transactions/sequencer.py` | `CommitSequencer`, `DeterministicSequencer`, `WALSequencer`, `verify_commit_bindings`, `recover` | Alternate authoritative commit/durability realizations | U12-U15, Q1 | P1 |
| `src/uow/orchestration/state.py` | `OrchestrationState`, queue/active/completed/dependencies, ready frontier | Typed orchestration projection over authoritative state | U11-U14 | P0/P1 |
| `src/uow/orchestration/materialization.py` | `UoWMaterializer`, `MaterializedUoW`, `bind_materialization`, `certify_materialization` | Higher-order decision -> ordinary UoW closure mechanism | U11-U14 | P0/P1 |
| `src/uow/orchestration/scheduler.py` | `SchedulerMaterializer`, `CompletionMaterializer`, `make_domain_task` | Self-hosted scheduling/completion realizations | U11-U14 | P1 |
| `src/uow/orchestration/runtime.py` | `execute_materialized`, `execute_domain_task`, `run_orchestration` | Composition of materialization, core certification, transaction commit | U11-U13 | P1 |
| `src/uow/resources/requirement.py` | `ResourceRequirement`, `ResourceBoundTask`, requirement binding | Resource requirement specialization of work requirements | U13-U15 | P0/P1 |
| `src/uow/resources/state.py` | `ResourceState`, `ResourceLease`, `can_accommodate`, lease lifecycle | Resource capability/state facet | U13-U15 | P0/P1 |
| `src/uow/resources/policies.py` | FIFO, GreedyCapacity, PriorityDeadline, CostEnergy | Alternative scheduling proposal realizations / baselines | U13-U15, A2.8 conceptual baseline relation | P1/P2 |
| `src/uow/resources/runtime.py` | resource-aware scheduler/completion materializers | Resource legality + orchestration closure composition | U13-U14 | P1 |
| `src/uow/effects/descriptor.py` | `EffectDescriptor`, `EffectReceipt`, idempotency key, compensation | External-effect contract/state and stable effect identity | Q1 | P0/P1 |
| `src/uow/effects/certification.py` | receipt authenticators, intent/receipt binding verification | External-effect conformance/attestation | Q1 | P0/P1 |
| `src/uow/effects/runner.py` | `EffectRunner`, `ExternalClientProtocol`, invoke/reconcile/commit intent/result | External realization boundary and crash reconciliation | Q1 | P1 |
| `src/uow/effects/saga.py` | `SagaCoordinator`, saga status/record/step, reverse compensation | Failure/compensation semantics for multi-effect work | Q1 | P1/P2 |
| `src/uow/proposer/base.py` | `BaseProposer`, `AdaptiveProposer` | Zero-authority candidate-generation protocol | U14-U15 | P0 |
| `src/uow/proposer/types.py` | `ModelProposal`, `ProposalCertificate`, `TelemetryRecord` | Proposal and conformance attestation envelopes | U14-U15 | P0/P1 |
| `src/uow/proposer/judge.py` | `certify_proposal` | Deterministic proposal conformance across freshness/deps/OCC/resources | U14-U15 | P0 |
| `src/uow/proposer/heuristic.py` | `HeuristicSchedulingProposer` | Deterministic/reference proposal realization | U14-U15 | P1/P2 |
| `src/uow/proposer/stochastic.py` | `RandomProposer` | Stochastic proposal realization / falsification baseline | U14 | P2 |
| `src/uow/proposer/adaptive.py` | `PortableAdaptiveProposer`, feedback/update/model identity | Portable online adaptation realization | U15 | P1/P2 |
| `src/uow/proposer/identity.py` | `ModelIdentity`, child lineage, artifact hash | Adaptive model identity / lineage | U15 | P0/P1 |
| `src/uow/proposer/observation.py` | `AdaptationObservation`, integrity validation | Certified feedback evidence for adaptation | U15 | P0/P1/P2 |
| `src/uow/proposer/fallback.py` | `DeterministicFallbackScheduler` | Liveness fallback realization independent of proposer | U14-U15 | P1/P2 |
| `src/uow/proposer/engine.py` | `ProposerOrchestrationEngine`, `run_dag` | Composition of proposer -> judge -> materialization -> commit -> feedback | U14-U15 | P1 |
| `src/uow/proposer/quorum_sequencer.py` | `QuorumCommitSequencer` | Distributed quorum commit realization | U15, distributed authority | P1; dependency inversion noted |
| `src/uow/proposer/learned.py` | compatibility aliases | Backward-compatible naming surface; no unique capability located in current file | U14 import compatibility | P4-CANDIDATE only after import/lineage proof |
| `src/uow/composition/contract.py` | `ParentContract`, O/D/A/E/T/R/F obligations | High-level semantic requirement/meta-contract | A2.0-A2.8 | P0/P1 |
| `src/uow/composition/graph.py` | `RealizationNode`, `RealizationGraph`, DAG/resource/cost methods | Logical realization topology | A2.0-A2.8 | P0/P1 |
| `src/uow/composition/projection.py` | `SemanticProjection`, `project_semantics`, equivalence/conformance | Realization -> parent-contract semantic conformance | A2.0-A2.8 | P0 |
| `src/uow/composition/boundary.py` | `BoundaryProjection`, `CompositionBoundaryCertificate`, scope contraction/verification | Recursive black-box conformance boundary; child-local semantics are hidden before parent projection | A2 recursive boundary | P0/P1 |
| `src/uow/composition/actor.py` | `ActorDescriptor`, `ActorRegistry`, `AuthorityClass` | Capability-bearing actor ontology | A2.2-A2.8 | P0/P1 |
| `src/uow/composition/binding.py` | `ActorBinding`, `validate_binding` | Logical realization -> qualified physical/logical actor binding | A2.2-A2.8 | P0/P1 |
| `src/uow/composition/substitution.py` | graph proposal/certificate, `CompositionCertifier` | Certified realization replacement meta-transition | A2.1-A2.8 | P1/P2 |
| `src/uow/composition/policy.py` | `AdaptiveGraphProposer`, runtime state, graph observation | Adaptive realization/binding proposal | A2.2-A2.8 | P1/P2 |
| `src/uow/composition/fabric.py` | `NetworkAgent`, `ActorLease`, `DistributedActorFabric` | Actor discovery, lease/liveness, discovery-vs-qualification | A2.3-A2.8 | P1/P2 |
| `src/uow/composition/delegation.py` | authority scopes, `DelegationCertificate`, `DistributedDelegationNode` | Recursive work delegation and authority attenuation | A2.4-A2.8 | P0/P1/P2 |
| `src/uow/composition/convergence.py` | `AuthoritativeHistory`, `HistoryEntry`, `MultiOrchestratorCluster` | Distributed authoritative lineage and partition convergence | A2.5-A2.8 | P0/P1/P2 |
| `src/uow/composition/wire.py` | `WireEnvelope`, signatures, `AdversarialChannel` | Transport realization / authenticated adversarial network harness | A2.6-A2.8 | P1/P2 |
| `src/uow/composition/host_node.py` | `DurableWAL`, `PhysicalHostNode`, crash/restart/catch-up | Independent process durability and physical-host realization | A2.6-A2.8 | P1/P2/P3 |
| `src/uow/composition/mutation.py` | mutation proposal/vote/QC, `QuorumMutationCoordinator` | Quorum-governed meta-runtime mutation | A2.7-A2.8 | P0/P1/P2 |
| `src/uow/composition/runtime.py` | `AdaptiveCompositionRuntime`, rebind, certify/replace, execute/fallback | Compatibility surface for active graph/binding runtime realization | A2.1-A2.8, recursive boundary | P1 |
| `src/uow/implementations/composition/actor_execution.py` | `ActorExecutor`, `ActorExecutionRegistry`, `CertifiedRuntimeActor` | Derived dispatch realization; exposes a boundary-certified child runtime as one actor without granting parent authority | A2 recursive boundary | P1 |
| `src/uow/composition/endurance.py` | B0/B1/A2 runtimes, objective, hysteresis, poisoning, lineage | Integrated adaptive endurance + scientific controls | A2.8 | P1/P2/P3 |
| `src/uow/semantic/schema.py` | `ExternalSignal`, `IngressContext`, `SemanticRequirement`, `SemanticBinding`, `CandidateSemanticBindings`, `SemanticClosureCertificate`, `IntentEnvelope`, `SemanticResult` | Immutable semantic mediation data contracts and envelopes | H0-H7 | P0 |
| `src/uow/semantic/context.py` | `SemanticContextProjector` | Minimal deterministic context projection ($C^{\min}$) from `WorldState` | H0-H7 | P0 |
| `src/uow/semantic/frontier.py` | `SemanticFrontierBuilder`, `DeterministicSemanticResolver` | Fixed-point deterministic closure ($Cl_D$) and residual prompt frontier ($F_P$); enforces $\beta_D = 0$ | H0-H7 | P0/P2 |
| `src/uow/semantic/closure.py` | `SemanticClosureEngine` | Frontier evaluation and closure oracle producing `YES`, `NO`, or `CLARIFY` | H0-H7 | P0/P2 |
| `src/uow/semantic/validation.py` | `DefaultSemanticAdmissibilityValidator` | Holdout admissibility interception and nonce generalization ($U_{\text{system}} = 0$) | H4, H7 | P0/P2 |
| `src/uow/semantic/compiler.py` | `SemanticCompilerRegistry`, `TransferUoWCompiler`, `PurgeUoWCompiler`, `derive_semantic_uow_id` | Deterministic lowering from qualified intent to canonical `make_uow` | H4, H7 | P1 |
| `src/uow/semantic/application.py` | `SemanticApplicationAdapter` | State-hash conformance check ($S_t \equiv S_{\text{cert}}$) and `ApplicationSpine` execution delegation | H4, H7 | P1 |
| `src/uow/semantic/clarification.py` | `ClarificationContext`, anti-drift and continuation errors | Ephemeral multi-turn clarification state with zero execution authority | H5, H7 | P1/P2 |
| `src/uow/semantic/harness.py` | `SemanticHarness` | Orchestration of interpretation, frontier construction, and clarification | H0-H7 | P1 |
| `src/uow/semantic/adapters/codec.py` | `SemanticPromptBuilder`, `SemanticOutputParser` | H3 native bidirectional prompt serialization and JSON candidate parsing | H3-H7 | P1 |
| `src/uow/semantic/adapters/manifest.py` | `SemanticModelManifest`, `verify_adapter_artifact` | Adapter cryptographic manifest validation and SHA-256 weight verification | H3-H7 | P0/P1 |
| `src/uow/semantic/adapters/huggingface.py` | `HuggingFaceSemanticTranslator`, `DefaultHuggingFaceBackend` | Lazy-loaded SmolLM2-135M / LoRA translation adapter | H3-H7 | P1 |
| `src/uow/semantic/projection.py` | `SemanticRecipientProjector` | Deterministic recipient projection ($I_B = \pi_B(I)$) and internal state isolation | H6, H7 | P0 |
| `src/uow/semantic/rendering.py` | `DeterministicEgressFormatter`, `DeterministicTemplateRenderer`, `ConfigurableRenderer` | Deterministic egress formatting and natural-language rendering | H6, H7 | P1 |
| `src/uow/semantic/roundtrip.py` | `SemanticRoundTripVerifier` | Bidirectional semantic round-trip certification across 10 dimensions ($\epsilon_{\text{drift}} = 0$) | H6, H7 | P2 |
| `src/uow/semantic/egress.py` | `GovernedEgressEngine` | Governed egress coordination, round-trip verification, and deterministic fallback | H6, H7 | P1 |

## Cross-module semantic clusters

### Canonical identity cluster
`state.py`, `engine.py`, proposer identity/types/observation, effects descriptors, composition contracts/graphs/bindings/history/mutation.

Research question: can representation boilerplate be reduced while preserving distinct semantic identities?

### Candidate/conformance/authority cluster
Core proposal/certification, proposer judge, OCC, resource legality, materialization certification, effect receipt verification, A2 projection/boundary/binding/delegation/QC.

Research question: are these specializations of one language-neutral conformance relation without flattening their semantics?

### Lineage cluster
EvidenceLedger, WALSequencer, DurableWAL, EffectReceipt, ModelIdentity/Observation, AuthoritativeHistory, TopologyLineage, delegation/QC artifacts.

Research question: can lineage share a common envelope/protocol while retaining typed payload semantics?

### Requirement/capability cluster
ResourceRequirement/ResourceState, DAG readiness, OCC footprints, ActorDescriptor/ActorBinding, ParentContract temporal/evidence/authority/resource obligations.

Research question: can these be represented as specializations of `Capabilities(R,S) |= Requirements(U)`?

## Notes

- This map does not assert that P4-CANDIDATE items should be removed.
- A module may carry multiple concepts; the table records the dominant semantic role.
- A later symbol-level machine-readable map should refine this document before R2.
