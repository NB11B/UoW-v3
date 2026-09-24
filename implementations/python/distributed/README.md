# Distributed Host/Durability Implementation

Production implementation:

`src/uow/implementations/distributed/host_node.py`

Historical compatibility path:

`uow.composition.host_node`

The implementation retains A2.6 WAL, crash/restart, catch-up, idempotency, wire verification, and QC-application behavior.
