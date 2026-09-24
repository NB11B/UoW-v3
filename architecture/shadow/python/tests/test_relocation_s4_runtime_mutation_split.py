from __future__ import annotations

import inspect

import uow
from uow.composition import (
    AuthorityMutationVote,
    QuorumMutationCoordinator,
    RuntimeMutationProposal,
    RuntimeMutationQC,
    assemble_mutation_qc,
    sign_mutation_vote,
    verify_mutation_qc,
    verify_mutation_vote,
)
from uow.realizations.authority.runtime_mutation import QuorumMutationCoordinator as ImplQuorumMutationCoordinator


def test_s4_runtime_mutation_split_preserves_public_identity():
    assert QuorumMutationCoordinator is ImplQuorumMutationCoordinator
    assert uow.QuorumMutationCoordinator is ImplQuorumMutationCoordinator


def test_s4_runtime_mutation_authority_semantics_remain_canonical():
    import uow.composition.mutation as semantic

    source = inspect.getsource(semantic)
    assert "class RuntimeMutationProposal" in source
    assert "class AuthorityMutationVote" in source
    assert "class RuntimeMutationQC" in source
    assert "def sign_mutation_vote" in source
    assert "def verify_mutation_vote" in source
    assert "def assemble_mutation_qc" in source
    assert "def verify_mutation_qc" in source
    assert "class QuorumMutationCoordinator" not in source
    assert "realizations.authority.runtime_mutation" in source

    assert RuntimeMutationProposal is semantic.RuntimeMutationProposal
    assert AuthorityMutationVote is semantic.AuthorityMutationVote
    assert RuntimeMutationQC is semantic.RuntimeMutationQC
    assert sign_mutation_vote is semantic.sign_mutation_vote
    assert verify_mutation_vote is semantic.verify_mutation_vote
    assert assemble_mutation_qc is semantic.assemble_mutation_qc
    assert verify_mutation_qc is semantic.verify_mutation_qc


def test_s4_runtime_mutation_realization_uses_relocated_dependencies_directly():
    import uow.realizations.authority.runtime_mutation as implementation

    source = inspect.getsource(implementation)
    assert "implementations.distributed.host_node" in source
    assert "composition.host_node import DurableWAL" not in source
    assert "composition.mutation import" in source
