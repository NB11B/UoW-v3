from __future__ import annotations

import inspect

import uow
from uow.proposer import RandomProposer
from uow.realizations.scheduling.stochastic import RandomProposer as ImplRandomProposer


def test_s4_stochastic_proposer_imports_remain_identity_compatible():
    assert RandomProposer is ImplRandomProposer
    assert uow.RandomProposer is ImplRandomProposer


def test_s4_historical_stochastic_proposer_module_is_only_compatibility_shim():
    import uow.proposer.stochastic as shim

    source = inspect.getsource(shim)
    assert "class RandomProposer" not in source
    assert "def propose(" not in source
    assert "realizations.scheduling.stochastic" in source
