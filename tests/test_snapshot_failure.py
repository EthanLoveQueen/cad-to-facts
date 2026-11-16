from cad_to_facts.artifact import register
from cad_to_facts.snapshot import read


def test_invalid_step_returns_failed_snapshot_with_file_health_diagnostic(tmp_path):
    path = tmp_path / "broken.step"
    path.write_text("ISO-10303-21;\nHEADER;\nENDSEC;\nDATA;\nENDSEC;\nEND-ISO-10303-21;\n", encoding="ascii")

    snapshot = read(register(path))

    assert snapshot.status == "failed"
    assert snapshot.entity_discovery == "unknown"
    assert snapshot.entities == []
    assert [diagnostic.code for diagnostic in snapshot.diagnostics] == ["PARSE_FAILED"]
    assert snapshot.diagnostics[0].disposition == "open"


def test_unknown_format_is_rejected_before_occt(tmp_path):
    path = tmp_path / "drawing.bin"
    path.write_bytes(b"not-a-supported-design-file")

    snapshot = read(register(path))

    assert snapshot.status == "failed"
    assert snapshot.entity_discovery == "unknown"
    assert [diagnostic.code for diagnostic in snapshot.diagnostics] == [
        "UNSUPPORTED_FORMAT"
    ]


def test_incomplete_step_envelope_is_rejected_before_occt(tmp_path):
    path = tmp_path / "bare.step"
    path.write_text("ISO-10303-21;\n", encoding="ascii")

    snapshot = read(register(path))

    assert snapshot.status == "failed"
    assert [diagnostic.code for diagnostic in snapshot.diagnostics] == ["PARSE_FAILED"]
    assert "OCCT was not entered" in snapshot.diagnostics[0].message
