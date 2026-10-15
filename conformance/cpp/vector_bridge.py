"""Native C++ conformance bridge; selects platform compiler without bypassing native tests."""
from __future__ import annotations
import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any, Dict, Tuple

CPP_DIR = Path(__file__).resolve().parents[2] / "runtimes" / "cpp"

class CppVectorBridge:
    def __init__(self, runner_exe: Path | str | None = None) -> None:
        name = "conformance_runner.exe" if os.name == "nt" else "conformance_runner"
        self.runner_exe = Path(runner_exe) if runner_exe else CPP_DIR / name
        if not self.runner_exe.is_file():
            self._compile_runner()
        if not self.runner_exe.is_file():
            raise FileNotFoundError(self.runner_exe)

    def _compile_runner(self) -> None:
        compiler = os.environ.get("CXX") or shutil.which("g++") or shutil.which("clang++")
        if compiler is None:
            raise RuntimeError("No C++17 compiler found; set CXX or install g++/clang++")
        cmd = [
            compiler, "-std=c++17", "-I", str(CPP_DIR / "include"),
            *[str(CPP_DIR / f) for f in (
                "native_state.cpp", "native_evidence.cpp", "native_idempotency.cpp",
                "native_protocol.cpp", "conformance_runner.cpp"
            )],
            "-o", str(self.runner_exe)
        ]
        subprocess.run(cmd, capture_output=True, text=True, check=True)

    def execute_vector(self, vector_file: Path | str) -> Dict[str, Any]:
        proc = subprocess.run([str(self.runner_exe), str(vector_file)],
                              capture_output=True, text=True, encoding="utf-8")
        if proc.returncode:
            raise RuntimeError(f"C++ runner exited {proc.returncode}: {proc.stderr}")
        return json.loads(proc.stdout)

    def execute_all(self, vectors_dir: Path | str) -> Tuple[int, int, str]:
        proc = subprocess.run([str(self.runner_exe), "--all", str(vectors_dir)],
                              capture_output=True, text=True, encoding="utf-8")
        if proc.returncode:
            raise RuntimeError(f"C++ batch runner exited {proc.returncode}: {proc.stderr}")
        output = proc.stdout.strip()
        lines = output.splitlines()
        passed = sum("PASS" in line for line in lines)
        failed = sum("FAIL" in line or "ERROR" in line for line in lines)
        return passed, passed + failed, output
