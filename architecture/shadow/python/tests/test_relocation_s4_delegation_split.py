from __future__ import annotations

import inspect

import uow
from uow.composition import (
    AuthorityScope,
    DelegationCertificate,
    DistributedDelegationNode,
    validate_delegation,
)
from uow.realizations.authority.delegation import DistributedDelegationNode as ImplDistributedDelegationNode


def test_s4_delegation_split_preserves_public_identity():
    assert DistributedDelegationNode is ImplDistributedDelegationNode
    assert uow.DistributedDelegationNode is ImplDistributedDelegationNode


def test_s4_delegation_semantics_remain_canonical():
    import uow.composition.delegation as semantic

    source = inspect.getsource(semantic)
    assert "class AuthorityScope" in source
    assert "class DelegationCertificate" in source
    assert "def validate_delegation" in source
    assert "class DistributedDelegationNode" not in source
    assert "realizations.authority.delegation" in source
    assert AuthorityScope is semantic.AuthorityScope
    assert DelegationCertificate is semantic.DelegationCertificate
    assert validate_delegation is semantic.validate_delegation


def test_s4_delegation_realization_uses_distributed_fabric_implementation_directly():
    import uow.realizations.authority.delegation as implementation

    source = inspect.getsource(implementation)
    assert "implementations.distributed.fabric" in source
    assert "composition.fabric import DistributedActorFabric" not in source
