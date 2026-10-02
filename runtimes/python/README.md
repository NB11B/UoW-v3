# Python Reference Runtime

The Python reference runtime for the Unit-of-Work (UoW) protocol is packaged and maintained directly from the top-level `src/uow/` source tree.

- **Source Code**: [`src/uow/`](../../src/uow/)
- **Minimal Root API**: `from uow import UoW, WorldState, execute`
- **Subsystem Namespaces**: `uow.authority`, `uow.runtime`, `uow.autonomy`, `uow.semantic`, `uow.economics`, `uow.protocol`, `uow.adapters`
- **Legacy Compatibility**: `from uow.compat.v2 import ...`
- **Packaging**: Governed by root `pyproject.toml`.
