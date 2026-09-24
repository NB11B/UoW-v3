from __future__ import annotations
import inspect
import uow
from uow.composition import ActorLease, DistributedActorFabric, NetworkAgent
from uow.composition.fabric import DistributedActorFabric as ShimFabric
from uow.implementations.distributed import DistributedActorFabric as ImplFabric

def test_s4_fabric_import_paths_are_identity_compatible():
    assert DistributedActorFabric is ShimFabric is ImplFabric is uow.DistributedActorFabric
    assert ActorLease is uow.ActorLease
    assert NetworkAgent is uow.NetworkAgent

def test_s4_historical_fabric_module_is_only_shim():
    import uow.composition.fabric as shim
    source = inspect.getsource(shim)
    assert "class DistributedActorFabric" not in source
    assert "implementations.distributed.fabric" in source

def test_s4_relocated_fabric_has_no_qualification_dependency():
    import uow.implementations.distributed.fabric as implementation
    source = inspect.getsource(implementation)
    assert "from qualification" not in source
    assert "import qualification" not in source
    assert "Discover(A) != Qualify(A, U)" in source
