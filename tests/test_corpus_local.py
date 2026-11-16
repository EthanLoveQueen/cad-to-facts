"""Local corpus regressions that use only public fixtures.

Covers malformed STEP input, generated unit variants, and the optional ODA
adapter's deterministic unavailable path for any local DWG files. Regressions
that bind user-supplied production files live in private, git-ignored modules
and are not part of the published test suite.
"""

from pathlib import Path

import pytest

from cad_to_facts.artifact import register
from cad_to_facts.domain.facts import ExtractionQuery, FactRequest
from cad_to_facts.facts import extract
from cad_to_facts.snapshot import read

from step_helpers import write_box, write_face

REPO_ROOT = Path(__file__).resolve().parent.parent
DWG_PATHS = sorted((REPO_ROOT / "test-data").glob("*.dwg"))

MALFORMED_SKELETON = (
    "ISO-10303-21;\nHEADER;\nENDSEC;\nDATA;\nENDSEC;\nEND-ISO-10303-21;\n"
)
MALFORMED_BAD_ENTITY = (
    "ISO-10303-21;\nHEADER;\nFILE_DESCRIPTION(('x'),'2;1');\n"
    "FILE_NAME('n','t',('a'),('o'),'p','s','a');\n"
    "FILE_SCHEMA(('AUTOMOTIVE_DESIGN'));\nENDSEC;\nDATA;\n#1=GARBAGE();\n"
    "ENDSEC;\nEND-ISO-10303-21;\n"
)


@pytest.mark.parametrize("dwg_path", DWG_PATHS, ids=[p.name for p in DWG_PATHS])
def test_dwg_without_converter_is_an_explicit_unavailable_capability(dwg_path, tmp_path):
    artifact = register(dwg_path)
    assert artifact.format == "dwg"
    assert not artifact.sha256 == "0" * 64
    snapshot = read(artifact, {"oda_executable": str(tmp_path / "missing.exe")})
    assert snapshot.status == "failed"
    assert snapshot.entity_discovery == "unknown"
    assert [item.code for item in snapshot.diagnostics] == ["ADAPTER_UNAVAILABLE"]


@pytest.mark.parametrize(
    "content",
    [MALFORMED_SKELETON, MALFORMED_BAD_ENTITY],
    ids=["skeleton", "bad-entity"],
)
def test_malformed_step_fails_with_parse_failed(tmp_path, content):
    path = tmp_path / "malformed.step"
    path.write_text(content, encoding="ascii")
    snapshot = read(register(path))
    assert snapshot.status == "failed"
    assert snapshot.entity_discovery == "unknown"
    assert snapshot.entities == []
    assert [d.code for d in snapshot.diagnostics] == ["PARSE_FAILED"]


def test_generated_face_only_step_reports_no_solids(tmp_path):
    path = tmp_path / "face.step"
    write_face(path)
    snapshot = read(register(path))
    assert snapshot.status == "partial"
    assert snapshot.entity_discovery == "unknown"
    assert snapshot.entities == []
    assert [d.code for d in snapshot.diagnostics] == ["NO_SOLIDS"]


def test_generated_box_declared_units(tmp_path):
    cases = [
        ("CM", "cm", 24_000.0, 1_000.0, 40.0, 10.0),
        ("INCH", "in", 32_774.128, 16_387.064, 25.4, 25.4),
    ]
    for unit, expected_unit, volume, volume_factor, height, height_factor in cases:
        path = tmp_path / f"box-{unit.lower()}.step"
        write_box(path, (20.0, 30.0, 40.0) if unit == "CM" else (25.4, 50.8, 25.4), unit)
        snapshot = read(register(path))
        assert snapshot.status == "ready"
        assert snapshot.units["length"] == expected_unit
        factset = extract(
            snapshot,
            ExtractionQuery(
                requests=[
                    FactRequest(name="volume", predicate="volume", subject_id="solid:0"),
                    FactRequest(name="height", predicate="bbox.extent.z", subject_id="solid:0"),
                ]
            ),
        )
        facts = {fact.predicate: fact for fact in factset.facts}
        assert facts["volume"].value == pytest.approx(volume, rel=1e-9)
        assert facts["volume"].method.parameters["conversion_factor"] == pytest.approx(
            volume_factor, rel=1e-9
        )
        assert facts["bbox.extent.z"].value == pytest.approx(height, rel=1e-9)
        assert facts["bbox.extent.z"].method.parameters["conversion_factor"] == pytest.approx(
            height_factor, rel=1e-9
        )


def test_generated_box_unverified_unit_blocks_length_facts(tmp_path):
    path = tmp_path / "box-metre.step"
    write_box(path, (1000.0, 1000.0, 1000.0), "M")
    snapshot = read(register(path))
    assert snapshot.status == "partial"
    assert snapshot.entity_discovery == "complete"
    assert snapshot.units["length"] == "metre"
    assert [d.code for d in snapshot.diagnostics] == ["UNIT_UNKNOWN"]
    factset = extract(
        snapshot,
        ExtractionQuery(
            requests=[
                FactRequest(name="volume", predicate="volume", subject_id="solid:0"),
                FactRequest(name="height", predicate="bbox.extent.z", subject_id="solid:0"),
            ]
        ),
    )
    assert factset.facts == []
    assert [gap.reason_code for gap in factset.gaps] == ["UNKNOWN_UNIT", "UNKNOWN_UNIT"]
