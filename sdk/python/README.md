# UoW Python Client SDK

Typed Python client for the Unit-of-Work (UoW) Capability Platform.

## Installation

```bash
pip install .
```

## Quick Start

```python
from uow import UoWClient, ClientWorkRequest

# Connect to local or remote UoW node
client = UoWClient(node_id="client_worker_01")

# Submit typed work request
req = ClientWorkRequest(
    capability_id="industrial.cutoff",
    payload={"pressure": 195.0},
)
response = client.submit_work(req)

print(f"Work ID: {response.work_id}")
print(f"Status: {response.disposition}")
print(f"Action: {response.action}")
print(f"Latency: {response.total_latency_ms:.2f} ms")
```
