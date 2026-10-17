"""Split Integrity and Hash Verifier for Milestone P4 Frozen Corpus."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Dict


def verify_corpus_integrity(
    corpora_dir: Path = Path("experiments/uow_magazine_p4/corpora"),
) -> dict[str, Any]:
    manifest_file = corpora_dir / "frozen_manifest.json"
    if not manifest_file.exists():
        raise FileNotFoundError(f"Missing manifest: {manifest_file}")

    manifest = json.loads(manifest_file.read_text(encoding="utf-8"))
    corpus_file = Path(manifest["corpus_file"])

    if not corpus_file.exists():
        raise FileNotFoundError(f"Missing corpus file: {corpus_file}")

    raw_bytes = corpus_file.read_bytes()
    computed_sha = hashlib.sha256(raw_bytes).hexdigest()

    if computed_sha != manifest["sha256"]:
        raise ValueError(f"Corpus hash mismatch! Manifest: {manifest['sha256']}, Computed: {computed_sha}")

    cases = json.loads(raw_bytes.decode("utf-8"))
    if len(cases) != 720:
        raise ValueError(f"Expected 720 cases, got {len(cases)}")

    # Verify counts per category
    counts: dict[str, int] = {}
    for c in cases:
        cat = c["category"]
        counts[cat] = counts.get(cat, 0) + 1

    expected_splits = manifest["splits"]
    for split_key, expected_count in expected_splits.items():
        cat_name = split_key.replace("_cases", "")
        if counts.get(cat_name) != expected_count:
            raise ValueError(f"Split count mismatch for {cat_name}: expected {expected_count}, got {counts.get(cat_name)}")

    print(f"Corpus split integrity verified! 720/720 cases valid. SHA256={computed_sha[:16]}...")
    return {
        "verified": True,
        "total_cases": len(cases),
        "sha256": computed_sha,
        "counts": counts,
    }


if __name__ == "__main__":
    verify_corpus_integrity()
