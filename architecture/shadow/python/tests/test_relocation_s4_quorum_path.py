from __future__ import annotations

import inspect

import uow
from uow.proposer import QuorumCommitError as ProposerError
from uow.proposer import QuorumCommitSequencer as ProposerSequencer
from uow.proposer.quorum_sequencer import QuorumCommitError as ShimError
from uow.proposer.quorum_sequencer import QuorumCommitSequencer as ShimSequencer
from uow.realizations.commit import QuorumCommitError as RealizationError
from uow.realizations.commit import QuorumCommitSequencer as RealizationSequencer


def test_s4_quorum_import_paths_are_identity_compatible():
    assert ProposerSequencer is RealizationSequencer
    assert ShimSequencer is RealizationSequencer
    assert uow.QuorumCommitSequencer is RealizationSequencer

    assert ProposerError is RealizationError
    assert ShimError is RealizationError
    assert uow.QuorumCommitError is RealizationError


def test_s4_historical_quorum_module_is_only_a_compatibility_shim():
    import uow.proposer.quorum_sequencer as shim

    source = inspect.getsource(shim)
    assert "class QuorumCommitSequencer" not in source
    assert "class QuorumCommitError" not in source
    assert "realizations.commit.quorum" in source


def test_s4_relocated_quorum_implementation_has_no_qualification_dependency():
    import uow.realizations.commit.quorum as implementation

    source = inspect.getsource(implementation)
    assert "qualification." not in source
    assert "QuorumAuthorityProvider" in source


def test_s4_repository_realization_surface_documents_python_implementation():
    from pathlib import Path

    repo = Path(__file__).resolve().parents[4]
    text = (repo / "realizations" / "commit" / "quorum" / "README.md").read_text(
        encoding="utf-8"
    )
    assert "src/uow/realizations/commit/quorum.py" in text
    assert "uow.proposer.quorum_sequencer" in text
