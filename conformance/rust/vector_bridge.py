"""Semantic Conformance Bridge for Native Rust Runtime.

Invokes the independent native Rust conformance runner against canonical golden vectors.
The bridge does NOT execute mutations, evaluate guards, determine authority,
resolve idempotency, or calculate evidence. Those belong entirely to the native Rust runtime.
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any, Dict, Tuple

RUST_RUNTIME_DIR = Path(__file__).resolve().parent.parent.parent / "runtimes" / "rust"
DEFAULT_RELEASE_EXE = RUST_RUNTIME_DIR / "target" / "release" / "conformance_runner.exe"
DEFAULT_DEBUG_EXE = RUST_RUNTIME_DIR / "target" / "debug" / "conformance_runner.exe"


class RustVectorBridge:
    """Bridge for executing canonical test vectors through native Rust runtime."""

    def __init__(self, runner_exe: Path | str | None = None) -> None:
        if runner_exe:
            self.runner_exe = Path(runner_exe)
        elif DEFAULT_RELEASE_EXE.exists():
            self.runner_exe = DEFAULT_RELEASE_EXE
        elif DEFAULT_DEBUG_EXE.exists():
            self.runner_exe = DEFAULT_DEBUG_EXE
        else:
            self._compile_runner()
            self.runner_exe = DEFAULT_RELEASE_EXE if DEFAULT_RELEASE_EXE.exists() else DEFAULT_DEBUG_EXE

    def _compile_runner(self) -> None:
        """Compile the native Rust conformance runner if binary is absent."""
        cmd = ["cargo", "build", "--release"]
        subprocess.run(cmd, cwd=str(RUST_RUNTIME_DIR), capture_output=True, text=True, check=True)

    def execute_vector(self, vector_file: Path | str) -> Dict[str, Any]:
        """Invoke Rust runner on a single canonical vector file and parse output."""
        cmd = [str(self.runner_exe), str(vector_file)]
        proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", check=False)
        if proc.returncode != 0:
            raise RuntimeError(f"Rust runner failed (code {proc.returncode}): {proc.stderr}")
        return json.loads(proc.stdout)

    def execute_all(self, vectors_dir: Path | str) -> Tuple[int, int, str]:
        """Invoke Rust runner in batch mode across all vectors."""
        cmd = [str(self.runner_exe), "--all", str(vectors_dir)]
        proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", check=False)
        output = proc.stdout.strip()
        lines = output.splitlines()

        passed = sum(1 for line in lines if "PASS" in line)
        failed = sum(1 for line in lines if "FAIL" in line or "ERROR" in line)
        total = passed + failed
        return passed, total, output
