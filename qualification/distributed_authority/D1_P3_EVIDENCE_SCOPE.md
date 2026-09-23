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

The campaign did **not** physically power down or physically sever every individual authority/transport path.

In particular, Authority C and the campaign coordinator execute on the same laptop failure domain. The campaign exercised C as an isolated authority process and exercised A+B progress while C was quarantined, but it did not demonstrate continued A+B coordination after complete laptop power/network loss.

Therefore the qualified physical claim is deliberately narrower than:

> survives any single physical node outage.

Physical power-loss, cable-cut, and transport-path fault tolerance remain separate qualification targets.

This note narrows interpretation only. It does not alter the recorded gate observations in `physical-quorum-qualification.json`.
