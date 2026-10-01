# Protocol Specification: Economics Data Plane

## 1. Architectural Invariant

The Unit-of-Work v3 architecture enforces a strict boundary between economic data observation and pricing policy:

\[
\boxed{
\begin{aligned}
\text{Economic Observation} &= \text{Protocol (Data Plane)} \\
\text{Pricing Decision} &= \text{Replaceable Realization (Policy Plane)}
\end{aligned}
}
\]

The protocol standardizes the observation schema, units, and cryptographic bindings for economic measurements.
The protocol **never** dictates a pricing algorithm, market auction rule, or priority tariff.

---

## 2. Supported Economic Dimensions

The protocol schema carries eight distinct economic dimensions without loss of granularity:

1. **Compute Cost**: Floating-point resource usage debits (vCPU-hours, GPU-minutes, token counts, flop counts).
2. **Human Cost**: Review, approval, supervision, or physical human intervention overhead (labor-hours, approval tokens).
3. **Energy**: Instantaneous power (Watts), energy budget (Joules or Watt-hours), and carbon/thermal impact.
4. **Resource Cost**: Hardware lease expense, storage footprint, network egress volume.
5. **Latency / Delay Cost**: Opportunity cost or penalty function incurred per millisecond of scheduling delay.
6. **Failure / Recovery Cost**: Compensation liability, rollback expense, and re-execution penalty.
7. **Market Price**: Dynamic spot or forward price discovery from external exchanges or compute brokers.
8. **Capacity / Scarcity Observation**: Utilization fraction, reservation congestion, and regional scarcity indices.

---

## 3. Protocol Envelope Fields

Economic observations are encapsulated inside `CostObservation` and embedded within `ResourceRequirement`:

```json
{
  "observation_id": "obs-compute-0428",
  "resource_type": "COMPUTE",
  "metric_unit": "GPU_SECONDS",
  "observed_cost": 0.045,
  "spot_market_price": 0.040,
  "realization_overhead": 0.005,
  "metadata": {
    "accelerator": "NPU_INTEL_AI_BOOST",
    "power_watts": 12.4
  }
}
```

---

## 4. Separation from Realization Policy

- **Protocol Layer (`protocol/economics/`)**: Validates observation envelopes, bounds, and cryptographic non-repudiation.
- **Runtime Realization Layer (`uow.runtime.resources`)**: Implements specific scheduling heuristics:
  - `CostEnergySchedulingPolicy`: Selects hosts minimizing \(\alpha \cdot \text{Cost} + \beta \cdot \text{Energy}\).
  - `PriorityDeadlineSchedulingPolicy`: Minimizes deadline miss penalties.
  - Pluggable third-party optimizers (e.g. linear programming, auction clearing) plug in as interchangeable realizations.
