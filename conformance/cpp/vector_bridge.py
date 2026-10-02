"""Semantic Conformance Bridge for Native C++ Runtime.

Invokes the native C++ conformance runner against canonical golden vectors.
The bridge does NOT execute mutations, evaluate guards, determine authority,
resolve idempotency, or calculate evidence. Those belong entirely to the native C++ kernel.
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any, Dict, Tuple

CPP_DIR = Path(__file__).resolve().parent.parent.parent / "runtimes" / "cpp"
DEFAULT_RUNNER_EXE = CPP_DIR / "conformance_runner.exe"


class CppVectorBridge:
    """Bridge for executing canonical test vectors through native C++."""

    def __init__(self, runner_exe: Path | str | None = None) -> None:
        self.runner_exe = Path(runner_exe) if runner_exe else DEFAULT_RUNNER_EXE
        if not self.runner_exe.exists():
            self._compile_runner()

    def _compile_runner(self) -> None:
        """Compile the native C++ conformance runner if binary is absent."""
        cmd = [
            r"C:\Strawberry\c\bin\g++.exe",
            "-std=c++17",
            "-I",
            str(CPP_DIR / "include"),
            str(CPP_DIR / "native_state.cpp"),
            str(CPP_DIR / "native_evidence.cpp"),
            str(CPP_DIR / "native_idempotency.cpp"),
            str(CPP_DIR / "native_protocol.cpp"),
            str(CPP_DIR / "conformance_runner.cpp"),
            "-o",
            str(self.runner_exe),
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True, check=True)

    def execute_vector(self, vector_file: Path | str) -> Dict[str, Any]:
        """Invoke C++ runner on a single canonical vector file and parse output."""
        cmd = [str(self.runner_exe), str(vector_file)]
        proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", check=False)
        if proc.returncode != 0:
            raise RuntimeError(f"C++ runner failed (code {proc.returncode}): {proc.stderr}")
        return json.loads(proc.stdout)

    def execute_all(self, vectors_dir: Path | str) -> Tuple[int, int, str]:
        """Invoke C++ runner in batch mode across all vectors."""
        cmd = [str(self.runner_exe), "--all", str(vectors_dir)]
        proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", check=False)
        output = proc.stdout.strip()
        lines = output.splitlines()

        passed = sum(1 for line in lines if "PASS" in line)
        failed = sum(1 for line in lines if "FAIL" in line or "ERROR" in line)
        total = passed + failed
        return passed, total, output
