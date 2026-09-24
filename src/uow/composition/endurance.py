"""Compatibility shim for the historical A2.8 endurance path."""

from ..implementations.composition.endurance import (
    AntiThrashingHysteresis,
    ContinuousPerturbationTrace,
    EnduranceAdaptiveRuntime,
    EnvironmentalState,
    FixedBaselineRuntime,
    LineageEdge,
    ObservationPoisoningEngine,
    RuleBasedRuntime,
    RuntimeObjectiveFunction,
    TopologyLineage,
)

__all__ = [
    "AntiThrashingHysteresis",
    "ContinuousPerturbationTrace",
    "EnduranceAdaptiveRuntime",
    "EnvironmentalState",
    "FixedBaselineRuntime",
    "LineageEdge",
    "ObservationPoisoningEngine",
    "RuleBasedRuntime",
    "RuntimeObjectiveFunction",
    "TopologyLineage",
]
