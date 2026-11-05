"""Read the host coretemp package sensor and submit an unverified observation."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from .service import Service, validate_observation

SENSOR_ID = "host-coretemp-package"


def sample_coretemp(hwmon_root: Path, epoch: int) -> dict:
    if type(epoch) is not int or epoch < 0:
        raise ValueError("EPOCH")
    for hwmon in sorted(Path(hwmon_root).glob("hwmon*")):
        try:
            if (hwmon / "name").read_text().strip() != "coretemp":
                continue
            for label in sorted(hwmon.glob("temp*_label")):
                if label.read_text().strip() != "Package id 0":
                    continue
                raw = (hwmon / label.name.replace("_label", "_input")).read_text().strip()
                if not raw.isascii() or not raw.isdigit() or len(raw) > 7:
                    raise ValueError("CORETEMP_READING")
                obs = {
                    "observation_id": f"{SENSOR_ID}-{epoch}",
                    "sensor_id": SENSOR_ID,
                    "sensor_type": "ENVIRONMENTAL_PROBE",
                    "causal_epoch": epoch,
                    "modality": "NUMERIC_GAUGE",
                    "reading": {"value": int(raw) / 1000, "unit": "C"},
                    "confidence": 0.5,
                }
                validate_observation(obs)
                return obs
        except OSError as exc:
            raise ValueError("CORETEMP_UNREADABLE") from exc
    raise ValueError("CORETEMP_UNAVAILABLE")


def ingest_coretemp(service: Service, hwmon_root: Path, token: str) -> dict:
    epoch = service.state.get("epoch." + SENSOR_ID, 0) + 1
    obs = sample_coretemp(hwmon_root, epoch)
    return service.handle({"request_id": obs["observation_id"], "token": token,
                           "kind": "observation.ingest", "payload": obs})


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, required=True)
    parser.add_argument("--policy", type=Path, required=True)
    parser.add_argument("--tokens", type=Path, required=True)
    parser.add_argument("--hwmon-root", type=Path, default=Path("/sys/class/hwmon"))
    args = parser.parse_args()
    if args.tokens.stat().st_mode & 0o077:
        parser.error("token file must have mode 0600")
    policy = json.loads(args.policy.read_text())
    tokens = json.loads(args.tokens.read_text())
    eligible = [token for token, principal in tokens.items()
                if "observation.ingest" in policy.get(principal, [])]
    if len(eligible) != 1:
        parser.error("exactly one observation.ingest token is required")
    service = Service(args.db, policy, tokens)
    try:
        print(json.dumps(ingest_coretemp(service, args.hwmon_root, eligible[0]), sort_keys=True))
    finally:
        service.close()


if __name__ == "__main__":
    main()
