from __future__ import annotations
import inspect
import uow
from uow.composition import EnduranceAdaptiveRuntime, RuntimeObjectiveFunction
from uow.composition.endurance import EnduranceAdaptiveRuntime as ShimRuntime
from uow.implementations.composition.endurance import EnduranceAdaptiveRuntime as ImplRuntime
from uow.implementations.composition.endurance import RuntimeObjectiveFunction as ImplObjective

def test_s4_endurance_import_paths_are_identity_compatible():
    assert EnduranceAdaptiveRuntime is ShimRuntime is ImplRuntime is uow.EnduranceAdaptiveRuntime
    assert RuntimeObjectiveFunction is ImplObjective is uow.RuntimeObjectiveFunction

def test_s4_historical_endurance_module_is_only_shim():
    import uow.composition.endurance as shim
    source = inspect.getsource(shim)
    assert "class EnduranceAdaptiveRuntime" not in source
    assert "implementations.composition.endurance" in source

def test_s4_relocated_endurance_uses_relocated_host_implementation():
    import uow.implementations.composition.endurance as implementation
    source = inspect.getsource(implementation)
    assert "implementations.distributed.host_node" in source
