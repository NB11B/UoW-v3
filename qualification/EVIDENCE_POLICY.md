# Qualification Evidence Policy

This policy applies to **all qualification code in this repository**.

## Core rule

[
oxed{
	ext{A claim may only PASS when the mechanism named by the claim was actually exercised.}
}
]

Simulation, mocks, emulation, fallback devices, proxy metrics, and synthetic controls are useful for development and portable CI. They **cannot** satisfy a claim about a different substrate.

## Required result semantics

Every substrate-sensitive gate must distinguish:

- `observed_pass`: the tested logic behaved as expected;
- `qualified`: the run exercised the required evidence substrate/components;
- `passed`: `observed_pass AND qualified`.

A simulated or portable run may therefore produce:

```json
{
  "observed_pass": true,
  "qualified": false,
  "passed": false
}
```

That is a successful logic test, not physical qualification.

## Evidence levels

```text
SIMULATED
    mocks, in-process authority models, synthetic devices

PORTABLE
    real execution on the available host, but not the named physical topology

PHYSICAL
    the actual named hardware / transport / failure boundary was exercised
```

Evidence does not automatically upgrade because code is identical.

## No silent substitution

A component requested as one substrate must not silently execute on another substrate while retaining the original label.

Examples:

- OpenVINO `CPU` fallback is not Intel NPU evidence.
- CPU tensor execution is not CUDA GPU evidence.
- `MockAuthorityClient` is not ESP32 authority evidence.
- a synthetic outage flag is not a physical transport disconnect.
- a calculated latency proxy is not a measured hardware oracle.

Fallback is permitted only when it is explicitly recorded as a substitution and blocks any incompatible claim.

## Negative-control rule

If a gate claims that a boundary **rejects** a condition, the qualification must force that condition through the actual boundary.

Policy avoidance is not rejection evidence.

Example:

```text
policy does not propose offline GPU
!=
ESP32 rejected an offline-GPU proposal
```

Both are useful, but they are different claims.

## Measurement rule

If a gate claims measured performance, regret, latency, energy, concurrency, recovery, or evidence integrity:

- the measurement must come from the actual mechanism named;
- a proxy/surrogate must be labeled as such;
- proxy values cannot satisfy a physical measurement gate;
- evidence-chain integrity must be independently verified, not inferred from uniqueness or monotonic counters alone.

## Hardware attestation

Physical reports must record the actual components used. At minimum, hardware-specific campaigns must identify the authority and each accelerator required by the claim.

A physical heterogeneous CPU/GPU/NPU gate is blocked if any required target is unavailable or substituted.

## CI rule

Hosted CI is expected to exercise portable and simulated paths.

CI must verify:

- logic;
- serialization/protocol behavior;
- gate calculations;
- negative-control structure;
- substitution detection;
- firmware compilation;
- evidence-contract enforcement.

Hosted CI must not pretend to reproduce unavailable physical evidence.

## Historical evidence

Existing sealed physical artifacts remain valid for the code/head on which they were recorded.

When qualification semantics or wire protocols change materially, a new physical run is required before the new head can make the physical claim.

## Shared implementation

`qualification/evidence.py` provides the common evidence contract used by qualification harnesses.

New qualification code should use that contract rather than inventing independent pass/fail semantics.
