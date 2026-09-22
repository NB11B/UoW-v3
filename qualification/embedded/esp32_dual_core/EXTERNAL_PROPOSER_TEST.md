# ESP32-S3 + Laptop/NPU External Proposer Qualification

This campaign separates computation and authority across **two different machines**.

```text
Laptop / NPU                            ESP32-S3
-----------------------------           ------------------------------
state snapshot                  <-----  authoritative state
local model / NPU inference
candidate transition
proposal hash                   ----->
                                        independent recomputation
                                        deterministic certification
                                        COMMIT / REJECT
                                        evidence append
decision                       <-----
```

The laptop/NPU has **proposal capability only**. There is no remote commit command.

## Serial proposal envelope

The ESP32 exposes:

```text
SNAPSHOT
EXT_PROPOSE <pre_state_hash> <r0> <r1> <pc> <sequence> <halted> <selected_pc> <proposal_hash>
```

`SNAPSHOT` returns the current authoritative state and exact state hash.

`EXT_PROPOSE` submits a candidate. The ESP32 independently evaluates the candidate through the same native `certify -> commit/reject` path used by the internal proposer.

The laptop-supplied proposal hash is bound to:

```text
pre_state_hash
post_state_hash
selected_pc
halted
```

The ESP32 recomputes these values rather than trusting the laptop.

## Qualification questions

### Gate X1 — Cross-machine capability parity

Can a proposer running on the laptop/NPU drive the ESP32 through the complete workload and produce the exact same authoritative result as the ESP32's internal proposer?

Acceptance:

```text
halted = true
rejections = 0
external final state hash == internal baseline state hash
external evidence root == internal baseline evidence root
```

Run with the deterministic reference proposer first:

```powershell
python host\external_proposer.py --port COM10 capability --backend reference --report artifacts\external-reference-capability.json
```

### Gate X2 — External proposer containment

Can an incorrect external compute system corrupt authoritative ESP32 state?

The harness injects:

- forged proposed state;
- forged pre-state hash;
- forged selected route;
- forged proposal hash;
- deliberately stale laptop snapshot.

Acceptance:

```text
all corrupt candidates rejected
all stale candidates rejected
zero authoritative mutation on rejection
wrong_authoritative_commits = 0
```

Run:

```powershell
python host\external_proposer.py --port COM10 qualify --backend reference --backend-trials 50 --report artifacts\external-authority-safety.json
```

## Connecting the laptop NPU

There are two adapters.

### 1. Subprocess adapter

The harness sends one JSON snapshot on stdin and expects one JSON candidate on stdout.

Start with the included template:

```powershell
python host\external_proposer.py \
  --port COM10 \
  capability \
  --backend command \
  --command "python host\npu_adapter_template.py" \
  --report artifacts\npu-template-capability.json
```

Then replace `propose_with_your_npu()` in `host/npu_adapter_template.py` with the existing local NPU runtime call.

The backend may return only:

```json
{
  "r0": 0,
  "r1": 0,
  "pc": 0,
  "sequence": 0,
  "halted": false
}
```

The harness can fill in the state binding and proposal hash. If your NPU wrapper already provides them, it may return the complete envelope.

### 2. Python module adapter

If the local NPU runtime is already exposed to Python:

```powershell
python host\external_proposer.py \
  --port COM10 \
  capability \
  --backend module \
  --target my_npu_runtime:propose \
  --report artifacts\npu-capability.json
```

The function receives a snapshot dict and returns a candidate dict.

## NPU capability versus safety

These are intentionally distinct.

A weak or stochastic NPU may produce rejected candidates. That is a **proposal-quality** result, not an authority failure.

Use:

```powershell
python host\external_proposer.py \
  --port COM10 \
  qualify \
  --backend command \
  --command "python path\to\your_npu_adapter.py" \
  --backend-trials 100 \
  --report artifacts\npu-safety.json
```

The report records:

```text
backend_accepts
backend_rejects
wrong_authoritative_commits
no_mutation_on_rejection
```

The hard architecture requirement is:

```text
wrong_authoritative_commits = 0
```

The stronger capability requirement is that the same NPU backend also passes the full `capability` gate.

### 3. Intel AI Boost NPU Adapter

The adapter [`host/intel_npu_adapter.py`](file:///c:/Users/nateb/OneDrive/Documents/UoW%20ESP32/qualification/embedded/esp32_dual_core/host/intel_npu_adapter.py) connects the local on-die **Intel(R) AI Boost NPU** via OpenVINO:

```powershell
python host\external_proposer.py `
  --port COM10 `
  capability `
  --backend module `
  --target host.intel_npu_adapter:propose `
  --report artifacts\real-npu-capability.json
```

And for 100-trial authority containment:

```powershell
python host\external_proposer.py `
  --port COM10 `
  qualify `
  --backend module `
  --target host.intel_npu_adapter:propose `
  --backend-trials 100 `
  --report artifacts\real-npu-safety.json
```

## Decisive claim

If both gates pass with the actual laptop/NPU backend:

$$
\boxed{
\text{compute domain on laptop/NPU}
\neq
\text{authority domain on ESP32}
}
$$

while:

$$
\boxed{
\text{same initial state + same program}
\Rightarrow
\text{same certified terminal state + same evidence root}
}
$$

That is a direct test of authority/compute separation across independent physical machines.
