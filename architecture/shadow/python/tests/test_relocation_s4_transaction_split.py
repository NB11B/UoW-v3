from __future__ import annotations

import inspect

import uow
from uow.realizations.commit import DeterministicSequencer as RealDeterministic
from uow.realizations.commit import WALSequencer as RealWAL
from uow.realizations.commit import QuorumCommitSequencer
from uow.transactions import (
    CommitSequencer,
    DeterministicSequencer,
    WALSequencer,
    verify_commit_bindings,
)
from uow.transactions.protocol import (
    CommitSequencer as ProtocolCommitSequencer,
    verify_commit_bindings as protocol_verify_commit_bindings,
)


def test_s4_transaction_protocol_and_realization_imports_are_identity_compatible():
    assert CommitSequencer is ProtocolCommitSequencer
    assert verify_commit_bindings is protocol_verify_commit_bindings
    assert DeterministicSequencer is RealDeterministic
    assert WALSequencer is RealWAL

    assert uow.DeterministicSequencer is RealDeterministic
    assert uow.WALSequencer is RealWAL


def test_s4_quorum_realization_depends_on_semantic_commit_protocol():
    assert issubclass(QuorumCommitSequencer, ProtocolCommitSequencer)

    import uow.realizations.commit.quorum as quorum
    source = inspect.getsource(quorum)
    assert "transactions.protocol import CommitSequencer" in source
    assert "transactions.sequencer import CommitSequencer" not in source


def test_s4_historical_transaction_sequencer_is_compatibility_surface():
    import uow.transactions.sequencer as shim

    source = inspect.getsource(shim)
    assert "class DeterministicSequencer" not in source
    assert "class WALSequencer" not in source
    assert "class CommitSequencer" not in source
    assert "transactions.protocol" not in source  # relative compatibility import
    assert "from .protocol import CommitSequencer" in source


def test_s4_commit_realization_modules_do_not_import_compatibility_sequencer():
    import uow.realizations.commit.deterministic as deterministic
    import uow.realizations.commit.wal as wal

    assert "transactions.sequencer" not in inspect.getsource(deterministic)
    assert "transactions.sequencer" not in inspect.getsource(wal)
    assert "transactions.protocol" in inspect.getsource(deterministic)
    assert "transactions.protocol" in inspect.getsource(wal)
