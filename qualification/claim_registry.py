"""Declarative qualification claim registry.

This module is the executable counterpart of the architecture-level evidence
rules documented in the Hybrid Systems Architecture knowledgebase.

A claim is distinct from its test implementation. Each claim declares the
minimum evidence level and actual components required before an observation may
be promoted to a qualified PASS.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from qualification.evidence import EvidenceLevel


@dataclass(frozen=True)
class ClaimSpec:
    claim_id: str
    statement: str
    required_level: EvidenceLevel
    required_components: tuple[str, ...] = ()
    requires_negative_control: bool = False
    measurement_source: str = "direct"
    scope: str = "repository"


CLAIMS: Mapping[str, ClaimSpec] = {
    "U14.PROPOSER_ISOLATION": ClaimSpec(
        "U14.PROPOSER_ISOLATION",
        "A proposer cannot directly mutate authoritative state.",
        EvidenceLevel.PORTABLE,
        scope="canonical runtime",
    ),
    "U15.ADAPTIVE_CONTRACT": ClaimSpec(
        "U15.ADAPTIVE_CONTRACT",
        "Swapping or updating adaptive model parameters cannot change deterministic certification semantics or authority invariants.",
        EvidenceLevel.PORTABLE,
        scope="canonical runtime",
    ),
    "U15.FEEDBACK_INTEGRITY": ClaimSpec(
        "U15.FEEDBACK_INTEGRITY",
        "Learning observations are strictly derived from deterministic authority outcomes, prevent forged acceptances, detect stale feedback, and reconstruct exact training lineage.",
        EvidenceLevel.PORTABLE,
        requires_negative_control=True,
        scope="canonical runtime",
    ),
    "U15.PORTABLE_ADAPTATION": ClaimSpec(
        "U15.PORTABLE_ADAPTATION",
        "The closed-loop adaptive proposer converges under workload drift, reducing rejection rate R_reject(t+n) < R_reject(t) with strictly zero wrong authoritative commits.",
        EvidenceLevel.PORTABLE,
        requires_negative_control=True,
        scope="canonical runtime",
    ),
    "U15.ADAPTATION_CONTAINMENT": ClaimSpec(
        "U15.ADAPTATION_CONTAINMENT",
        "Catastrophic model degradation, corrupted labels, and proposer crashes reduce efficiency without compromising deterministic authority invariants or producing invalid state.",
        EvidenceLevel.PORTABLE,
        requires_negative_control=True,
        scope="canonical runtime",
    ),
    "U15.NPU_ADAPTIVE_PROPOSER.PORTABLE": ClaimSpec(
        "U15.NPU_ADAPTIVE_PROPOSER.PORTABLE",
        "The OpenVINO neural proposer adapter satisfies the canonical adaptive proposer contract with zero commit authority on portable backends.",
        EvidenceLevel.PORTABLE,
        scope="canonical proposer integration",
    ),
    "U15.NPU_ADAPTIVE_PROPOSER.PHYSICAL": ClaimSpec(
        "U15.NPU_ADAPTIVE_PROPOSER.PHYSICAL",
        "Physical Intel AI Boost NPU inference executes the canonical adaptive UoW scheduling proposer while deterministic authority remains fixed and wrong commits remain zero.",
        EvidenceLevel.PHYSICAL,
        ("authority", "npu"),
        requires_negative_control=True,
        scope="heterogeneous hardware qualification",
    ),
    "U15.NPU_HOT_SWAP.PORTABLE": ClaimSpec(
        "U15.NPU_HOT_SWAP.PORTABLE",
        "Live atomic model replacement updates active proposer without interrupting transaction flow, and corrupted staging models are rejected without rollback.",
        EvidenceLevel.PORTABLE,
        scope="canonical proposer lifecycle",
    ),
    "U15.NPU_HOT_SWAP.PHYSICAL": ClaimSpec(
        "U15.NPU_HOT_SWAP.PHYSICAL",
        "Physical Intel AI Boost NPU executes live atomic model generation hot swap with verified continuous DAG progress and zero wrong authoritative commits.",
        EvidenceLevel.PHYSICAL,
        ("authority", "npu"),
        requires_negative_control=True,
        scope="heterogeneous hardware qualification",
    ),
    "U15.CONTINUOUS_ADAPTATION_ENDURANCE.PORTABLE": ClaimSpec(
        "U15.CONTINUOUS_ADAPTATION_ENDURANCE.PORTABLE",
        "The adaptive proposer undergoes continuous adaptation across oscillating workload drift regimes without runtime reset while authoritative legality remains invariant.",
        EvidenceLevel.PORTABLE,
        scope="continuous adaptive endurance qualification",
    ),
    "U15.CONTINUOUS_ADAPTATION_ENDURANCE.PHYSICAL": ClaimSpec(
        "U15.CONTINUOUS_ADAPTATION_ENDURANCE.PHYSICAL",
        "Physical Intel AI Boost NPU undergoes repeated live multi-generation adaptation across continuous workload regimes, negative control injections, and regime reversals with zero wrong authoritative commits.",
        EvidenceLevel.PHYSICAL,
        ("authority", "npu"),
        requires_negative_control=True,
        scope="heterogeneous hardware qualification",
    ),
    "U15.ADAPTIVE_QUORUM_ORCHESTRATION.PORTABLE": ClaimSpec(
        "U15.ADAPTIVE_QUORUM_ORCHESTRATION.PORTABLE",
        "The adaptive proposer drives task execution under a distributed 2-of-3 quorum authority across independent replicas, tolerating single-node failure, isolating minority partitions, and incorporating quorum certificate feedback into policy adaptation.",
        EvidenceLevel.PORTABLE,
        scope="adaptive quorum orchestration qualification",
    ),
    "U15.ADAPTIVE_QUORUM_ORCHESTRATION.PHYSICAL": ClaimSpec(
        "U15.ADAPTIVE_QUORUM_ORCHESTRATION.PHYSICAL",
        "The physical Intel AI Boost NPU adaptive proposer drives live task execution under a heterogeneous physical 2-of-3 quorum across ESP32-S3, Arduino UNO Q STM32, and Laptop x86-64 CPU, verifying partition resilience, hot-swap under quorum, and zero wrong authoritative commits.",
        EvidenceLevel.PHYSICAL,
        ("authority_a_esp32", "authority_b_unoq_stm32", "authority_c_laptop_x86", "npu"),
        requires_negative_control=True,
        scope="heterogeneous hardware qualification",
    ),
    "A2.SEMANTIC_PROJECTION.PORTABLE": ClaimSpec(
        "A2.SEMANTIC_PROJECTION.PORTABLE",
        "Semantic projection Phi(G, U) deterministically establishes whether candidate realization graphs satisfy parent contract U (G |= U) and evaluates semantic equivalence G_a equiv_U G_b independent of graph topology.",
        EvidenceLevel.PORTABLE,
        scope="adaptive composition runtime qualification",
    ),
    "A2.GRAPH_SUBSTITUTION.PORTABLE": ClaimSpec(
        "A2.GRAPH_SUBSTITUTION.PORTABLE",
        "The adaptive composition runtime certifies candidate realization graph replacements against parent contract semantics prior to activation, guaranteeing semantic invariance Phi(G', U) = Phi(G, U) and falling back safely upon invalid proposals.",
        EvidenceLevel.PORTABLE,
        requires_negative_control=True,
        scope="adaptive composition runtime qualification",
    ),
    "A2.ACTOR_BINDING.PORTABLE": ClaimSpec(
        "A2.ACTOR_BINDING.PORTABLE",
        "Dynamic actor binding decouples logical realization graphs from physical actor execution, certifying capability matching and authority constraints prior to task dispatch.",
        EvidenceLevel.PORTABLE,
        requires_negative_control=True,
        scope="adaptive composition runtime qualification",
    ),
    "A2.ADAPTIVE_PROPOSER.PORTABLE": ClaimSpec(
        "A2.ADAPTIVE_PROPOSER.PORTABLE",
        "The adaptive composition proposer adapts its graph selection policy based on runtime state S_t and certified execution feedback, converging to optimal topology under environmental drift with strictly zero wrong substitutions.",
        EvidenceLevel.PORTABLE,
        requires_negative_control=True,
        scope="adaptive composition runtime qualification",
    ),
    "A2.ACTOR_FABRIC.PORTABLE": ClaimSpec(
        "A2.ACTOR_FABRIC.PORTABLE",
        "Distributed runtime agents dynamically announce, discover, qualify, and lease network actors under churning availability, maintaining valid leases and capability/authority matching with zero unauthorized bindings.",
        EvidenceLevel.PORTABLE,
        requires_negative_control=True,
        scope="adaptive composition runtime qualification",
    ),
    "A2.CHURN_RESILIENCE.PORTABLE": ClaimSpec(
        "A2.CHURN_RESILIENCE.PORTABLE",
        "The composition runtime adapts across network churn (node drop, saturation, latency spike, authority partition, reconnection) by separating actor rebinding from graph replacement, failing closed on authority loss and preserving parent semantics Phi(G, U) = Phi(U) with strictly zero wrong commits.",
        EvidenceLevel.PORTABLE,
        requires_negative_control=True,
        scope="adaptive composition runtime qualification",
    ),
    "A2.DELEGATION_ATTENUATION.PORTABLE": ClaimSpec(
        "A2.DELEGATION_ATTENUATION.PORTABLE",
        "Distributed nodes issue cryptographic DelegationCertificates with strict authority attenuation A(U_child) subset-of A(U_parent), preventing authority inflation, unauthorized delegation, and expired delegation under churning network state.",
        EvidenceLevel.PORTABLE,
        requires_negative_control=True,
        scope="adaptive composition runtime qualification",
    ),
    "A2.RECURSIVE_ORCHESTRATION.PORTABLE": ClaimSpec(
        "A2.RECURSIVE_ORCHESTRATION.PORTABLE",
        "Hierarchical multi-level UoW decomposition preserves parent semantic projection Phi(bigoplus U_i) = Phi(U) across delegate drop, safe retry, stale generation rejection, and recursive recovery with zero wrong commits.",
        EvidenceLevel.PORTABLE,
        requires_negative_control=True,
        scope="adaptive composition runtime qualification",
    ),
    "A2.RECURSIVE_BOUNDARY.PORTABLE": ClaimSpec(
        "A2.RECURSIVE_BOUNDARY.PORTABLE",
        "A boundary-certified child UoW runtime executes as an actor inside a parent runtime while child-local semantics remain scoped, child evidence is chained upward, equivalent child reconfiguration requires no parent recertification, and boundary drift, recursive cycles, authority loss, or output deficits fail closed.",
        EvidenceLevel.PORTABLE,
        requires_negative_control=True,
        scope="adaptive composition runtime qualification",
    ),
    "A2.MULTI_ORCHESTRATOR_CONCURRENCY.PORTABLE": ClaimSpec(
        "A2.MULTI_ORCHESTRATOR_CONCURRENCY.PORTABLE",
        "Multiple autonomous orchestrators concurrently propose realization graph mutations and sub-UoW delegations, deterministically resolving conflicts and merging commutative operations with strictly zero double commits.",
        EvidenceLevel.PORTABLE,
        requires_negative_control=True,
        scope="adaptive composition runtime qualification",
    ),
    "A2.PARTITION_CONVERGENCE.PORTABLE": ClaimSpec(
        "A2.PARTITION_CONVERGENCE.PORTABLE",
        "Under network partition into disjoint orchestrator clusters, minority partitions fail closed on authoritative commits while majority partitions proceed under quorum; upon partition healing, all nodes reconcile to a single authoritative history H* with zero semantic divergence.",
        EvidenceLevel.PORTABLE,
        requires_negative_control=True,
        scope="adaptive composition runtime qualification",
    ),
    "A2.PHYSICAL_NETWORK_FAULT.PORTABLE": ClaimSpec(
        "A2.PHYSICAL_NETWORK_FAULT.PORTABLE",
        "Physical multi-process nodes communicating over socket channels survive adversarial packet loss, duplication, reordering, asymmetric partitions, and clock skew with strictly zero double commits.",
        EvidenceLevel.PORTABLE,
        requires_negative_control=True,
        scope="adaptive composition runtime qualification",
    ),
    "A2.CRASH_RECOVERY_CONVERGENCE.PORTABLE": ClaimSpec(
        "A2.CRASH_RECOVERY_CONVERGENCE.PORTABLE",
        "Independent OS processes recover from crash-during-commit and crash-during-delegation via durable disk journals, catching up stale rejoined nodes with zero semantic divergence.",
        EvidenceLevel.PORTABLE,
        requires_negative_control=True,
        scope="adaptive composition runtime qualification",
    ),
    "A2.QUORUM_CERTIFIED_MUTATION.PORTABLE": ClaimSpec(
        "A2.QUORUM_CERTIFIED_MUTATION.PORTABLE",
        "Runtime execution topology (realization graph G and actor binding B) mutates if and only if certified by a cryptographic Quorum Certificate (QC) signed by a threshold of independent authority nodes, binding parent contract U, candidate G, candidate B, generation epoch, and history head, with zero uncertified substitutions.",
        EvidenceLevel.PORTABLE,
        requires_negative_control=True,
        scope="adaptive composition runtime qualification",
    ),
    "A2.HETEROGENEOUS_MUTATION_CONSENSUS.PORTABLE": ClaimSpec(
        "A2.HETEROGENEOUS_MUTATION_CONSENSUS.PORTABLE",
        "Distributed runtime nodes across an adversarial physical network substrate maintain strictly zero state divergence, zero stale generation mutations, and zero dropped in-flight tasks during live quorum-certified graph and binding transitions.",
        EvidenceLevel.PORTABLE,
        requires_negative_control=True,
        scope="adaptive composition runtime qualification",
    ),
    "A2.CONTINUOUS_TOPOLOGY_EVOLUTION.PORTABLE": ClaimSpec(
        "A2.CONTINUOUS_TOPOLOGY_EVOLUTION.PORTABLE",
        "The adaptive composition runtime continuously reorganizes realization graphs and actor bindings under overlapping environmental perturbations (load, latency, node drop, partition) over multi-epoch endurance execution with strictly zero wrong commits, zero uncertified mutations, zero double commits, zero lost tasks, and full partition reconciliation to H*.",
        EvidenceLevel.PORTABLE,
        requires_negative_control=True,
        scope="adaptive composition runtime qualification",
    ),
    "A2.ADAPTATION_QUALITY_AND_STABILITY.PORTABLE": ClaimSpec(
        "A2.ADAPTATION_QUALITY_AND_STABILITY.PORTABLE",
        "Under continuous environmental drift, the learned adaptive runtime achieves superior objective cost J_adaptive < J_static across identical perturbation traces, suppresses mutation thrashing via anti-thrashing hysteresis (R_mutation <= threshold), and maintains absolute semantic and authority integrity even under observation delay, reordering, and corruption.",
        EvidenceLevel.PORTABLE,
        requires_negative_control=True,
        scope="adaptive composition runtime qualification",
    ),
    "TIMING.LOCAL_INDEPENDENCE": ClaimSpec(
        "TIMING.LOCAL_INDEPENDENCE",
        "Canonical correctness does not require shared mutable execution clocks.",
        EvidenceLevel.PORTABLE,
        scope="canonical runtime",
    ),
    "ESP32.AUTHORITY": ClaimSpec(
        "ESP32.AUTHORITY",
        "The physical ESP32 authority rejects illegal scheduling transitions without mutation.",
        EvidenceLevel.PHYSICAL,
        ("authority",),
        requires_negative_control=True,
        scope="embedded qualification",
    ),
    "HETERO.EXECUTION": ClaimSpec(
        "HETERO.EXECUTION",
        "Work executes across the actual CPU, CUDA GPU, and OpenVINO NPU backends.",
        EvidenceLevel.PHYSICAL,
        ("authority", "cpu", "gpu", "npu"),
        scope="heterogeneous runtime",
    ),
    "HETERO.ADAPTATION": ClaimSpec(
        "HETERO.ADAPTATION",
        "The deployed routing policy adapts using actual GPU training and NPU inference while authority remains fixed.",
        EvidenceLevel.PHYSICAL,
        ("authority", "cpu", "gpu", "npu", "gpu_training", "npu_policy"),
        scope="heterogeneous runtime",
    ),
    "HETERO.PERFORMANCE": ClaimSpec(
        "HETERO.PERFORMANCE",
        "Routing performance is measured against actual alternate hardware execution.",
        EvidenceLevel.PHYSICAL,
        ("authority", "cpu", "gpu", "npu"),
        measurement_source="measured_actual_hardware",
        scope="heterogeneous runtime",
    ),
    "EVIDENCE.CHAIN": ClaimSpec(
        "EVIDENCE.CHAIN",
        "Every authoritative scheduler evidence link is independently recomputable.",
        EvidenceLevel.PHYSICAL,
        ("authority",),
        measurement_source="independent_recomputation",
        scope="embedded qualification",
    ),
    "DIST.AUTHORITY.AGREEMENT.PORTABLE": ClaimSpec(
        "DIST.AUTHORITY.AGREEMENT.PORTABLE",
        "Independent authority replicas deterministically agree on certification for the same state, proposal, and ruleset.",
        EvidenceLevel.PORTABLE,
        ("authority_a", "authority_b", "authority_c"),
        scope="distributed authority portable qualification",
    ),
    "DIST.AUTHORITY.QUORUM_SAFETY.PORTABLE": ClaimSpec(
        "DIST.AUTHORITY.QUORUM_SAFETY.PORTABLE",
        "A 2-of-3 quorum is required for authoritative progress and conflicting transitions cannot both obtain quorum from one pre-state.",
        EvidenceLevel.PORTABLE,
        ("authority_a", "authority_b", "authority_c"),
        requires_negative_control=True,
        scope="distributed authority portable qualification",
    ),
    "DIST.NETWORK.SELF_HEAL.PORTABLE": ClaimSpec(
        "DIST.NETWORK.SELF_HEAL.PORTABLE",
        "The portable network-fault model reroutes around failed links and catches up stale replicas only from verified quorum-certified history.",
        EvidenceLevel.PORTABLE,
        ("authority_a", "authority_b", "authority_c", "network_fabric", "self_healing_controller"),
        requires_negative_control=True,
        scope="distributed authority portable qualification",
    ),
    "DIST.AUTHORITY.DIVERGENCE_CONTAINMENT.PORTABLE": ClaimSpec(
        "DIST.AUTHORITY.DIVERGENCE_CONTAINMENT.PORTABLE",
        "A replica whose state/evidence is not a verified journal prefix is quarantined and is never silently overwritten.",
        EvidenceLevel.PORTABLE,
        ("authority_a", "authority_b", "authority_c", "self_healing_controller"),
        requires_negative_control=True,
        scope="distributed authority portable qualification",
    ),
    "DIST.AUTHORITY.PAIR_AGREEMENT.PHYSICAL": ClaimSpec(
        "DIST.AUTHORITY.PAIR_AGREEMENT.PHYSICAL",
        "Heterogeneous physical authorities (ESP32-S3 and Arduino UNO Q STM32) deterministically agree on state transitions, piecewise QC application, stale catch-up, and divergence quarantine across distinct physical authority/compute domains.",
        EvidenceLevel.PHYSICAL,
        ("authority_a_esp32", "authority_b_unoq_stm32"),
        requires_negative_control=True,
        scope="heterogeneous physical pair qualification",
    ),
    "DIST.AUTHORITY.QUORUM_2_OF_3.PHYSICAL": ClaimSpec(
        "DIST.AUTHORITY.QUORUM_2_OF_3.PHYSICAL",
        "A 2-of-3 quorum across three heterogeneous physical authority substrates (ESP32-S3 Xtensa, Arduino UNO Q STM32, and Laptop x86-64 CPU) authorizes progress for every tested 2-node/3-node voter combination, rejects insufficient quorum, and prevents conflicting commits from the same pre-state.",
        EvidenceLevel.PHYSICAL,
        ("authority_a_esp32", "authority_b_unoq_stm32", "authority_c_laptop_x86"),
        requires_negative_control=True,
        scope="heterogeneous physical quorum qualification",
    ),
}


def get_claim(claim_id: str) -> ClaimSpec:
    return CLAIMS[claim_id]
