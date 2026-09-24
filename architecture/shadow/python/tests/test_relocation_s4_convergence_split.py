from __future__ import annotations
import inspect
import uow

from uow.composition.convergence import (
    AuthoritativeHistory,
    HistoryEntry,
    HistoryEntryKind,
    MultiOrchestratorCluster,
)
from uow.composition.history import (
    AuthoritativeHistory as HistoryImpl,
    HistoryEntry as EntryImpl,
    HistoryEntryKind as KindImpl,
)
from uow.implementations.distributed import MultiOrchestratorCluster as ClusterImpl


def test_s4_convergence_semantics_and_cluster_imports_remain_compatible():
    assert AuthoritativeHistory is HistoryImpl is uow.AuthoritativeHistory
    assert HistoryEntry is EntryImpl is uow.HistoryEntry
    assert HistoryEntryKind is KindImpl is uow.HistoryEntryKind
    assert MultiOrchestratorCluster is ClusterImpl is uow.MultiOrchestratorCluster


def test_s4_historical_convergence_module_is_compatibility_surface():
    import uow.composition.convergence as shim

    source = inspect.getsource(shim)
    assert "class AuthoritativeHistory" not in source
    assert "class MultiOrchestratorCluster" not in source
    assert ".history import" in source
    assert "implementations.distributed.convergence" in source


def test_s4_internal_runtime_imports_history_semantics_directly():
    import uow.composition.mutation as mutation
    import uow.implementations.distributed.host_node as host_node
    import uow.implementations.composition.endurance as endurance

    assert "composition.history" in inspect.getsource(mutation)
    assert "composition.history" in inspect.getsource(host_node)
    assert "composition.history" in inspect.getsource(endurance)
