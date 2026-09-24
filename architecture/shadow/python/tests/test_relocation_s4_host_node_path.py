from __future__ import annotations

import inspect

import uow
from uow.composition import DurableWAL, PhysicalHostNode
from uow.composition.host_node import DurableWAL as ShimWAL
from uow.composition.host_node import PhysicalHostNode as ShimHost
from uow.implementations.distributed import DurableWAL as ImplWAL
from uow.implementations.distributed import PhysicalHostNode as ImplHost


def test_s4_host_node_import_paths_remain_identity_compatible():
    assert DurableWAL is ImplWAL is ShimWAL is uow.DurableWAL
    assert PhysicalHostNode is ImplHost is ShimHost is uow.PhysicalHostNode


def test_s4_historical_host_node_module_is_only_shim():
    import uow.composition.host_node as shim

    source = inspect.getsource(shim)
    assert "class DurableWAL" not in source
    assert "class PhysicalHostNode" not in source
    assert "implementations.distributed.host_node" in source


def test_s4_relocated_host_node_uses_relocated_network_realization():
    import uow.implementations.distributed.host_node as implementation

    source = inspect.getsource(implementation)
    assert "realizations.network.wire" in source
    assert "qualification." not in source
