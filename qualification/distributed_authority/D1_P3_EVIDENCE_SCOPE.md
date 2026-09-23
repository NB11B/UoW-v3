# D1-P3 Physical Quorum Evidence Scope

**Raw physical campaign evidence head:** `93d87cd7eae078ef268c29f3689d2554db44d2c0`  
**Frozen evidence branch:** `archive/distributed-authority-d1-p3-physical-evidence-2026-09-23`

## Qualified physical claim

The D1-P3 campaign physically exercised three heterogeneous authority substrates:

- ESP32-S3 / COM10 (Xtensa LX7);
- Arduino UNO Q STM32U585 / COM5 (ARM Cortex-M33);
- laptop x86-64 CPU as an isolated authority service process.

The campaign physically demonstrated that a 2-of-3 quorum across these three authority substrates:

- produced identical deterministic certification for the tested transition;
- committed successfully for every tested voter set: {A,B}, {A,C}, {B,C}, and {A,B,C};
- rejected insufficient quorum without mutation;
- prevented a conflicting second quorum from the same pre-state through vote locking;
- recovered a stale replica by authorized rebuild/catch-up;
- quarantined a divergent authority and preserved majority progress using the two remaining authorities.

## Scope limitation

The three authorities occupy distinct physical authority/compute domains, but the current bench has a **shared upstream laptop power dependency**: the laptop powers the ESP32-S3 and Arduino UNO Q through their USB/serial connections while also hosting Authority C and the campaign coordinator.

D1-P3 is therefore complete for the claim it was designed to test: heterogeneous physical 2-of-3 authority quorum semantics. It does not claim continued operation after complete laptop power loss.

The campaign physically exercised authority omission/quarantine, quorum formation, insufficient-quorum rejection, non-equivocation, stale catch-up, and divergence containment while the bench remained powered.

Independent-power, cable-cut, and full host-power-loss resilience are distinct deployment/fault-tolerance questions, not prerequisites for the completed D1-P3 quorum qualification.

This note defines the final interpretation of the completed D1-P3 milestone. It does not alter the recorded gate observations in `physical-quorum-qualification.json`.
