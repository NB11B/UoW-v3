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
