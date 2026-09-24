# Python Resource Runtime Implementation

Production implementation:

`src/uow/implementations/resources/runtime.py`

Historical compatibility remains at:

`uow.resources.runtime`

Resource requirement binding, capacity legality, leases, starvation accounting, and materialization certification remain domain-specific. Only the common proposal/certify/transaction/commit control flow is delegated to the production application spine.
