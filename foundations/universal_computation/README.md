# Foundational Construction: Universal Computation

This directory houses the foundational construction demonstrating that the canonical Unit-of-Work (UoW) transition algebra is a universal computational substrate.

$$\boxed{\text{Universal Kernel} \subset \text{UoW Transition Algebra}}$$

$$\boxed{\text{Semantic Classification} \perp \text{Computational Semantics}}$$

---

## 1. Architectural Role

The Minsky two-counter construction is **architecturally essential evidence, but not a runtime dependency**.

Without this construction, the 64-cell work matrix might be misinterpreted as merely a workflow classification taxonomy:
```text
People → Processes
Rules → Data
Devices → Processes
...
```
and UoWs as simply tasks or jobs.

The Minsky construction proves that ordinary native UoW machinery—
$$U = (H, \Gamma, M, R, B, E, T)$$
with immutable state, guarded mutations, successor selection, and `PROPOSE -> CERTIFY -> COMMIT`—is computationally universal under standard extensible-memory semantics.

The computational power does **not** arise from special work categories or opcode tables. It emerges entirely from:
$$\boxed{\text{state} + \text{conditional transition} + \text{mutation} + \text{successor selection} + \text{iteration}}$$

The 64 Cartesian pairings $(C_{\text{src}}, C_{\text{tgt}})$ remain strictly semantic typing ("what kind of work is this?").

---

## 2. Orthogonality Theorem

The compiler (`uow_minsky_compiler.py`) maps arbitrary Minsky programs into ordinary UoWs:
- `INC(r, next_pc)` $\longrightarrow$ Guard `ALWAYS`, Mutation `ADD r 1`, Successor `next_pc`
- `DECJZ(r, zero_pc, nonzero_pc)` $\longrightarrow$
  - Route 0: Guard `EQ r 0`, NOOP, Successor `zero_pc`
  - Route 1: Guard `GT r 0`, Mutation `SUB r 1`, Successor `nonzero_pc`
- `HALT` $\longrightarrow$ Guard `ALWAYS`, Successor `HALT`

Crucially, **any of the 64 matrix cells can be assigned** to any instruction (either uniformly or varied dynamically per PC) without altering computational execution. Computational semantics are completely orthogonal to semantic classification.

---

## 3. The Bounded Negative Control (Gate U5)

Alongside the positive construction, `bounded_control.py` implements the architectural negative control:
- **Bounded State (8-bit)**: Enforcing $k$-bit modular arithmetic ($x \pmod{2^8}$) causes non-halting increment loops to return to their exact initial state configuration after $2^8 = 256$ steps, proving finite-state automaton behavior.
- **Extensible State**: Native unbounded integer attributes execute monotonically without repeating configurations, successfully scaling beyond $2^{1024} + 17$.

This establishes the precise falsification boundary:
$$\boxed{\text{finite controller} + \text{bounded state} \longrightarrow \text{finite-state system}}$$
$$\boxed{\text{finite controller} + \text{extensible memory} + \text{branch/mutation} \longrightarrow \text{universal computation}}$$

---

## 4. Empirical Qualification Metrics

The construction was empirically validated across:
1. **20,000 Randomized Single-Step Checks**: Zero divergence between native `PROPOSE -> CERTIFY -> COMMIT` transitions and the independent Minsky oracle.
2. **500 Terminating Program Comparisons**: Identical final register states and termination outcomes across random inputs.
3. **Cyclic Execution**: Verified stable execution to 100,000 steps without memory leaks or state corruption.
4. **State Magnitude**: Evaluated past $2^{1024} + 17$ without overflow or precision loss.
5. **Tamper Rejection**: Malicious proposed register mutations, invalid routes, corrupted state hashes, and illegal successors are deterministically rejected by the core certifier.
6. **Replay Determinism**: Re-executing identical programs against initial state produces bitwise identical evidence ledger root hashes.

---

## 5. Dependency Boundary

The dependency direction is strictly one-way:
$$\boxed{\text{foundations/universal\_computation} \longrightarrow \text{uses UoW core primitives}}$$
The core kernel `uow` **never** imports `foundations`. Minsky computation emerges from UoW; UoW does not embed a Minsky interpreter.
