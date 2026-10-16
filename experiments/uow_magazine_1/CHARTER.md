# UOW-MAGAZINE-1: Cross-Architecture Compact Models and Domain-Expertise Weight Magazines

**Campaign Status**: OPEN / ACTIVE RESEARCH  
**Branch**: `research/uow-magazine-1-cross-foundation`  
**Parent Reference Baseline**: UOW-GRAMMAR-1 (`af1f4ee`, unmerged and sealed)  
**Foundation Model Parameter Ceiling**: Strictly ~100–160 Million Parameters  
**Target Hardware**: Workstation NVIDIA RTX 5070 (12GB VRAM, CUDA 12.8)  

---

## 1. Architectural Objective

Establish whether ultra-compact foundation models (~100–160M parameters) can acquire, retain, switch, and compose specialized domain expertise through small, independently versioned weight sets (**Domain-Expertise Weight Magazines**), operating under deterministic Unit-of-Work (UoW) protocol authority:

$$\text{Domain Context } x \xrightarrow{\text{Magazine Select } \mathcal{M}(d, g)} (M_{0,\text{arch}} + \Delta W_{d, g}) \xrightarrow{\text{Typed Proposal}} \text{Deterministic UoW Authority } (\text{Certify} \to \text{Commit})$$

The foundation-model parameter count is strictly fixed. We test the scalability of specialized operational expertise and cross-architecture portability, not brute-force parameter scaling.

---

## 2. Seven-Model Cross-Architecture Foundation Roster

We evaluate seven diverse compact architectures within the ~100–160M parameter boundary:

| Model Identifier | Parameter Count | Architecture Family | Attention / Formulation | License | Role in Campaign |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `HuggingFaceTB/SmolLM2-135M-Instruct` | 135M | LLaMA / Decoder | RoPE, GQA, SwiGLU | Apache 2.0 | Established Reference Foundation |
| `EleutherAI/pythia-160m` | 160M | GPT-NeoX | RoPE, MHA, parallel attn/MLP | Apache 2.0 | Primary Interpretability Comparison |
| `EleutherAI/gpt-neo-125m` | 125M | GPT-Neo | Absolute Positional, Local/Global | MIT | Architectural Cross-Check |
| `cerebras-archive/Cerebras-GPT-111M` | 111M | GPT-2 Style Decoder | Learned Positional, MHA, GELU | Apache 2.0 | Architectural Cross-Check |
| `facebook/MobileLLM-125M` | 125M | MobileLLM Decoder | Deep-thin, SwiGLU, sharing | FAIR Research | Edge-Optimized Reference (Gated) |
| `state-spaces/mamba-130m-hf` | 130M | Selective SSM | Non-attention State Space | Apache 2.0 | Non-Attention Architecture Reference |
| `answerdotai/ModernBERT-base` | 149M | ModernBERT | Unpad, GeGLU, Rotary, Encoder | Apache 2.0 | Routing / Discriminative Reference |

---

## 3. Domain $\times$ Grammar Matrix ($3 \times 3 = 9$ Specializations)

The weight magazine organizes adapters across three operational domains and three functional grammars:

| Domain | Operational (`uow.operational.v1`) | Temporal (`uow.temporal.v1`) | Recovery (`uow.recovery.v1`) |
| :--- | :--- | :--- | :--- |
| **Industrial / OT** | SCADA telemetry, PLC valve actuation, emergency depressurization | Monotonic sequence locks, sensor heartbeat deadlines, interlock windows | Isolation containment, safe backout vents, failover to manual bypass |
| **Cybersecurity** | Firewall ACL rule injection, token revocation, endpoint quarantine | Rate-limiting sliding windows, token expiration TTLs, SIEM correlation | Session termination, circuit breaker trip, containment snapshot |
| **Logistics** | Freight route allocation, manifest dispatch, dock door assignment | Multi-leg transit windows, demurrage deadline tracking, ETA coordination | Alternate route rerouting, carrier penalty claim, warehouse overflow buffer |

Data Partition per Combination:
- 1,200 Synthetic Training Sequences
- 200 Development Sequences
- 200 Validation Sequences
- 300 Disjoint Frozen Holdout Sequences

---

## 4. Preregistered Research Gates (M0–M6)

### Gate M0 — Foundation Availability & Architectural Inspection
- Pin exact 40-character commit SHAs for all accessible candidate foundations.
- Perform sanity forward inference on target hardware (RTX 5070, CUDA 12.8).
- Document license types, parameter counts, context lengths, tokenizer vocabularies, and PEFT-targetable projection layers.
- Formally record gated status for `facebook/MobileLLM-125M`.

### Gate M1 — Domain-Grammar Weight Acquisition
- Train independent domain-grammar adapters ($r=8, \alpha=16$) on primary foundations. Base weights remain strictly frozen.
- Acceptance criteria: Every active domain-grammar adapter achieves $>80\%$ valid JSON and schema-compliant routing on its disjoint holdout, decisively outperforming frozen zero-shot foundations.

### Gate M2 — Magazine Capacity, Switch Latency, and Memory Footprint
- Implement `uow.magazine.v1` runtime manager supporting resident multi-adapter hosting.
- Sweep magazine capacity from 1 to 32 adapters:
  - Measure median switch latency using synchronized CUDA hardware timers (`torch.cuda.Event`). Target: $<5.0\text{ ms}$.
  - Measure peak VRAM allocation across resident states. Target: $<1.0\text{ GB}$ total footprint.
  - Verify zero cross-activation contamination across consecutive switches.

### Gate M3 — Cross-Architecture Portability and Expressivity
- Compare adapter expressivity and task accuracy across distinct model families (Llama/SmolLM2, GPT-NeoX/Pythia, GPT-Neo, Cerebras, Mamba, ModernBERT).
- Characterize inductive biases and architectural limitations across causal attention, state space, and encoder paradigms.

### Gate M4 — Mechanistic Interpretability Track
- Pythia-160M intermediate checkpoint analysis and SVD spectral energy concentration.
- Determine whether domain expertise concentrates in specific projection channels or layers across foundation families.

### Gate M5 — Deterministic UoW Multi-Domain Composition & Ledger Closure
- Execute end-to-end multi-domain composite transactions:
  - Industrial Alert $\to$ Temporal Windowing $\to$ Cybersecurity Quarantine $\to$ Logistics Reroute $\to$ Recovery Saga.
- Verify proposals pass deterministic UoW pre-state certification, commit to cryptographic `EvidenceLedger`, and reject state desyncs/replays with **zero unauthorized state commits**.

### Gate M6 — Cross-Foundation Qualification Scorecard & Engineering Synthesis
- Aggregate comprehensive metric scorecard across all tested foundations and magazines.
- Publish final findings in `artifacts/uow_magazine_1/qualification_report.md`.

---

## 5. Invariant Principles
1. **Parameter Ceiling**: Foundations strictly confined to ~100–160M parameters.
2. **Frozen Base Weights**: Pretrained base weights are never modified.
3. **Weight Privacy**: No raw checkpoint binaries (`.safetensors`, `.bin`) will be staged or pushed to Git.
4. **Deterministic Authority**: Neural adapters only produce typed proposals; execution authority resides exclusively in the deterministic UoW engine.
