# Python External-Effect Runtime Implementation

Production implementation:

`src/uow/implementations/effects/runner.py`

Historical compatibility remains at:

`uow.effects.runner`

Internal effect intent/pending/result state transitions use the production application spine with `CursorPolicy.DETACHED`.

The external invocation boundary remains explicit and outside the spine:

`commit intent -> reconcile/invoke external service -> certify receipt -> commit result`

This preserves the Q1 invariant that internal commit is not the external physical effect.
