# ESP32-S3 Dual-Core UoW Qualification

This is a **hardware falsification target** for the canonical UoW architecture. It is not a new runtime layer.

The experiment maps the hybrid authority boundary onto two physical execution contexts:

```text
ESP32-S3

Core P                          Core A
---------------------           -------------------------
immutable state snapshot        authoritative state owner
proposal generation             independent recomputation
local proposal clock            CERTIFY
fault injection                 COMMIT / REJECT
        |                               |
        +------ FreeRTOS queues --------+
```

The default PlatformIO environment pins proposer to Core 0 and authority/certifier to Core 1. A second environment reverses the assignment so core affinity itself can be falsified.

## Architectural invariant

The proposer never receives a pointer to authoritative state. It receives a copied snapshot over a FreeRTOS queue and returns a proposal over a second queue.

Only the authority task owns commit state:

```text
snapshot -> PROPOSE -> queue -> CERTIFY -> COMMIT / REJECT
```

Timing is observational:

```text
proposal_clock != authority_clock
```

but neither local clock is included in proposal/certificate/evidence authority hashes.

## Workload

The initial embedded program is the canonical two-counter transfer construction:

```text
while R0 > 0:
    R0 -= 1
    R1 += 1
halt
```

For initial `(R0=N, R1=M)`:

```text
R0 = 0
R1 = N + M
transitions = 2*N + 2
```

## Memory constraint

On-device evidence uses **root-only bounded-memory mode**. The ESP32 stores current evidence root, committed step count, and authoritative state. The laptop may retain the complete serial transcript.

## Host qualification

```bash
cmake -S host -B build
cmake --build build
./build/uow_embedded_tests
```

The host suite tests SHA-256, randomized reference parity, stale/tampered proposal rejection, independent/frozen logical clocks, exclusion of timing from authority hashes, bounded-memory evidence, threaded proposer/authority communication, and execution-context inversion.

## Build for ESP32-S3

```bash
pio run -e esp32s3_p0_a1
pio run -e esp32s3_p0_a1 -t upload
pio device monitor -b 115200
```

Inverted mapping:

```bash
pio run -e esp32s3_p1_a0
pio run -e esp32s3_p1_a0 -t upload
```

Run the same serial campaign under both images and require identical final state and evidence root.

## Serial protocol

```text
HELP
STATUS
RESET <r0> <r1>
STEP [NONE|TAMPER_STATE|TAMPER_PREHASH|TAMPER_ROUTE]
RUN <budget> [fault]
CLOCKS <proposal_stride> <authority_stride>
FREEZE <P|A> <0|1>
```

The firmware emits newline-delimited JSON.

## Laptop interrogation

Install pyserial:

```powershell
python -m pip install pyserial
```

For COM10:

```powershell
python host/serial_interrogate.py --port COM10 status
python host/serial_interrogate.py --port COM10 campaign
```

The campaign checks valid transfer parity, tamper rejection without mutation, stale/prehash rejection, route rejection, extreme clock asymmetry, and frozen proposal clock behavior.

A later two-board campaign can test independent oscillators and transport faults. This single-board campaign tests execution-domain isolation, timer independence, core-affinity independence, and deterministic authority under constrained hardware.


## Repeated hardware stress

After the baseline campaign passes, run repeated randomized trials from the laptop:

```powershell
python host\interrogator.py --port COM10 stress --trials 100 --seed 20260922 --report artifacts\stress-p0a1.json
```

For each trial the interrogator:

1. chooses a randomized initial `R0/R1` state;
2. executes it under one randomized proposal/authority clock pair;
3. injects a forged state proposal and verifies zero authority mutation;
4. reruns the same initial state under a second unrelated clock pair;
5. requires identical terminal state hash and cryptographic evidence root.

This directly tests the hardware invariant:

[
oxed{
	ext{same initial state + same UoW program}
Rightarrow
	ext{same certified state/evidence despite local clock variation}
}
]

The stress report is deterministic for a supplied host seed and records every initial state, both clock profiles, terminal state hash, evidence root, and pass/fail result.


## Transcript integrity

Every laptop-side transcript event is now hash-linked:

```text
event_hash_n = SHA256(index || host_monotonic || direction || payload || event_hash_(n-1))
```

This protects the **interrogation record**, not device authority. Host timestamps remain observational metadata.

Save a transcript during any serial run with `--transcript`, then verify it offline:

```powershell
python host\interrogator.py verify-transcript artifacts\p0a1.jsonl
```

The audit checks hash-chain integrity, host timestamp monotonicity, fatal/error event counts, command/event counts, and observational command-latency statistics.

## Fault matrix

Run every currently supported forged-proposal path from both zero and nonzero Minsky states:

```powershell
python host\interrogator.py --port COM10 fault-matrix --report artifacts\fault-matrix.json
```

Every rejection must preserve registers, sequence, state hash, and evidence root.

## Soak qualification

A soak run composes multiple seeded stress rounds:

```powershell
python host\interrogator.py \
  --port COM10 \
  --transcript artifacts\soak.jsonl \
  soak \
  --rounds 20 \
  --trials-per-round 25 \
  --seed 20260922 \
  --report artifacts\soak.json
```

That example executes 500 randomized paired clock/state trials plus a forged proposal in every trial. Each round stores its seed and transcript root so failures can be reproduced exactly.

The laptop interrogator is intentionally non-authoritative: it may command, observe, record, compare, and falsify, but only the ESP32 authority task can commit device state.
