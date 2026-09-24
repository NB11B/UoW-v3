from __future__ import annotations

import inspect

import uow
from uow.composition import AdaptiveGraphProposer, CompositionRuntimeState, GraphAdaptationObservation
from uow.composition.adaptation import (
    CompositionRuntimeState as SemanticCompositionRuntimeState,
    GraphAdaptationObservation as SemanticGraphAdaptationObservation,
)
from uow.realizations.adaptation.graph_policy import AdaptiveGraphProposer as ImplAdaptiveGraphProposer


def test_s4_graph_policy_split_preserves_public_identity():
    assert AdaptiveGraphProposer is ImplAdaptiveGraphProposer
    assert uow.AdaptiveGraphProposer is ImplAdaptiveGraphProposer
    assert CompositionRuntimeState is SemanticCompositionRuntimeState
    assert GraphAdaptationObservation is SemanticGraphAdaptationObservation


def test_s4_historical_policy_module_is_only_compatibility_surface():
    import uow.composition.policy as shim

    source = inspect.getsource(shim)
    assert "class AdaptiveGraphProposer" not in source
    assert "class CompositionRuntimeState" not in source
    assert "class GraphAdaptationObservation" not in source
    assert "realizations.adaptation.graph_policy" in source
    assert "from .adaptation import" in source


def test_s4_graph_substitution_certifier_remains_semantic():
    import uow.composition.substitution as substitution

    source = inspect.getsource(substitution)
    assert "class CompositionCertifier" in source
    assert "class GraphReplacementProposal" in source
    assert "class GraphReplacementCertificate" in source
