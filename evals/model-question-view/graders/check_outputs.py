"""Deterministically check the public left-door view-eval outputs; never executes CAD."""

import hashlib
import json
from pathlib import Path
import sys


def check(outputs: Path, source: Path) -> dict:
    svg = outputs / "left-door-front.svg"
    manifest_path = outputs / "left-door-front.view.json"
    checks = []

    def record(text: str, passed: bool, evidence: str):
        checks.append({"text": text, "passed": bool(passed), "evidence": evidence})

    record("SVG exists and is nonempty", svg.is_file() and svg.stat().st_size > 0, str(svg))
    record(
        "View manifest exists and is nonempty",
        manifest_path.is_file() and manifest_path.stat().st_size > 0,
        str(manifest_path),
    )
    if not svg.is_file() or not manifest_path.is_file():
        return {"status": "failed", "expectations": checks}
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    source_hash = hashlib.sha256(source.read_bytes()).hexdigest()
    svg_bytes = svg.read_bytes()
    record(
        "Manifest binds the unchanged public source artifact",
        manifest["artifact_sha256"] == source_hash,
        source_hash,
    )
    record(
        "Rendered target is Left door",
        manifest["target"]["name"] == "Left door",
        f"{manifest['target']['occurrence_id']} {manifest['target']['name']}",
    )
    record(
        "Rendered camera is left",
        manifest["view"]["camera"]["preset"] == "left",
        json.dumps(manifest["view"]["camera"]),
    )
    record(
        "Front semantics remain assumed",
        manifest["view"]["semantic_intent"]["basis"] == "assumed",
        json.dumps(manifest["view"]["semantic_intent"], ensure_ascii=False),
    )
    record(
        "Manifest output hash and size match SVG bytes",
        manifest["output"]["sha256"] == hashlib.sha256(svg_bytes).hexdigest()
        and manifest["output"]["size_bytes"] == len(svg_bytes),
        f"{len(svg_bytes)} bytes",
    )
    record(
        "Render contains projected geometry evidence",
        manifest["render"]["point_count"] > 0
        and manifest["render"]["visible_edge_count"] > 0,
        json.dumps(manifest["render"]),
    )
    return {
        "status": "passed" if all(item["passed"] for item in checks) else "failed",
        "expectations": checks,
    }


if __name__ == "__main__":
    result = check(Path(sys.argv[1]), Path(sys.argv[2]))
    print(json.dumps(result, ensure_ascii=False, indent=2))
    raise SystemExit(0 if result["status"] == "passed" else 1)
