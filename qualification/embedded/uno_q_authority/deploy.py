#!/usr/bin/env python3
"""Build and flash the Arduino UNO Q authority sketch via ADB."""
import os
import shutil
import subprocess
import sys

ADB_CANDIDATES = [
    r"C:\Program Files (x86)\Android\android-sdk\platform-tools\adb.exe",
    os.path.expanduser(r"~\AppData\Local\Android\Sdk\platform-tools\adb.exe"),
    "adb",
]

def find_adb():
    for c in ADB_CANDIDATES:
        try:
            res = subprocess.run([c, "version"], capture_output=True, text=True)
            if res.returncode == 0:
                return c
        except Exception:
            continue
    raise FileNotFoundError("ADB executable not found.")

def main():
    adb = find_adb()
    device = "3093395174"
    sketch_dir = os.path.dirname(os.path.abspath(__file__))
    remote_dir = "/tmp/uno_q_authority"

    print(f"Creating remote directory {remote_dir}...")
    subprocess.run([adb, "-s", device, "shell", f"mkdir -p {remote_dir}"], check=True)

    files = ["uno_q_authority.ino", "uow_embedded.hpp", "uow_embedded.cpp"]
    for fname in files:
        local_path = os.path.join(sketch_dir, fname)
        remote_path = f"{remote_dir}/{fname}"
        print(f"Pushing {local_path} -> {remote_path}...")
        subprocess.run([adb, "-s", device, "push", local_path, remote_path], check=True)

    print("Compiling sketch on UNO Q (Zephyr Cortex-M33)...")
    cmd_compile = [
        adb, "-s", device, "shell",
        f"arduino-cli compile -b arduino:zephyr:unoq {remote_dir}"
    ]
    res = subprocess.run(cmd_compile, capture_output=True, text=True)
    print(res.stdout)
    if res.returncode != 0:
        print(res.stderr, file=sys.stderr)
        sys.exit(1)

    print("Uploading sketch to STM32 MCU...")
    cmd_upload = [
        adb, "-s", device, "shell",
        f"arduino-cli upload -b arduino:zephyr:unoq {remote_dir}"
    ]
    res = subprocess.run(cmd_upload, capture_output=True, text=True)
    print(res.stdout)
    if res.returncode != 0:
        print(res.stderr, file=sys.stderr)
        sys.exit(1)

    print("UNO Q authority sketch deployed successfully.")

if __name__ == "__main__":
    main()
