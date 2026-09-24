from __future__ import annotations

import inspect

import uow
from uow.proposer import PortableAdaptiveProposer
from uow.realizations.adaptation.portable import PortableAdaptiveProposer as ImplPortableAdaptiveProposer


def test_s4_portable_adaptive_proposer_imports_remain_identity_compatible():
    assert PortableAdaptiveProposer is ImplPortableAdaptiveProposer
    assert uow.PortableAdaptiveProposer is ImplPortableAdaptiveProposer


def test_s4_historical_portable_adaptive_module_is_only_compatibility_shim():
    import uow.proposer.adaptive as shim

    source = inspect.getsource(shim)
    assert "class PortableAdaptiveProposer" not in source
    assert "def observe_feedback(" not in source
    assert "def update(" not in source
    assert "realizations.adaptation.portable" in source


def test_s4_adaptive_realization_retains_semantic_lineage_dependencies():
    import uow.realizations.adaptation.portable as implementation

    source = inspect.getsource(implementation)
    assert "from ...proposer.identity import ModelIdentity" in source
    assert "from ...proposer.observation import AdaptationObservation" in source
    assert "from ...proposer.types import ModelProposal" in source
