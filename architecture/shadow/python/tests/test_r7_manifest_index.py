from pathlib import Path
import re


REPO = Path(__file__).resolve().parents[4]


def test_r7_manifest_index_covers_every_canonical_experiment_manifest():
    canonical = {
        p.as_posix().replace(REPO.as_posix() + "/", "")
        for p in (REPO / "architecture" / "experiments").glob("*.yaml")
        if p.name != "catalog.yaml"
    }
    text = (REPO / "experiments" / "manifests" / "index.yaml").read_text(encoding="utf-8")
    indexed = set(
        re.findall(r"^  [A-Z0-9_]+: (architecture/experiments/[^\n]+\.yaml)$", text, flags=re.MULTILINE)
    )

    assert indexed == canonical


def test_r7_manifest_index_targets_exist():
    text = (REPO / "experiments" / "manifests" / "index.yaml").read_text(encoding="utf-8")
    paths = re.findall(r"(?:^|: )(architecture/experiments/[^\n]+\.yaml|experiments/reference-oracles/[^\n]+\.yaml)", text, flags=re.MULTILINE)

    assert paths
    for rel in paths:
        assert (REPO / rel).exists(), rel


def test_r7_manifest_surface_keeps_a4_conceptual():
    text = (REPO / "experiments" / "manifests" / "index.yaml").read_text(encoding="utf-8")
    assert "A4_ONTOLOGY_ADAPTATION" in text
    assert "A4 remains conceptual and unqualified" in text
