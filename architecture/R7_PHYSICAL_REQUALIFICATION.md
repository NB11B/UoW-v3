# R7 Physical Requalification Boundary

R7 is currently additive. Production runtime, firmware, qualification semantics, and public API remain unchanged.

Therefore no fresh physical run is required **for the current additive work itself**.

This does not transfer old physical PASS results to the new head. Historical artifacts remain evidence for the heads on which they were recorded.

Before production cutover, changed paths must be evaluated against `architecture/PHYSICAL_REQUALIFICATION_MAP.yaml`.

Fresh physical qualification is mandatory when a cutover materially changes the mechanism named by a physical claim, including:
- authority wire/hash semantics;
- firmware behavior;
- NPU/GPU/CPU backend or fallback behavior;
- evidence verification;
- negative-control injection;
- model hot swap;
- measured performance/energy path;
- hardware topology;
- A3 calibrated device/power/transfer models.

A pure organizational relocation that preserves production bytes and behavior does not itself create a new physical claim and does not rewrite historical evidence.

The policy-orchestrator P1-P5 branch is downstream of A3. Shared A3 physical artifacts are inherited reference evidence, not a second independent physical campaign.
