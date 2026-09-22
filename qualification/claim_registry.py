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
}


def get_claim(claim_id: str) -> ClaimSpec:
    return CLAIMS[claim_id]
