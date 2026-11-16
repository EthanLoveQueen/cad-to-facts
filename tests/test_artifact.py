from cad_to_facts.artifact import register


def test_register_identifies_artifact_by_exact_source_bytes(tmp_path):
    source = tmp_path / "sample.bin"
    source.write_bytes(b"abc")

    artifact = register(source)

    assert artifact.sha256 == "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"
    assert artifact.size_bytes == 3
    assert artifact.format == "unknown"


def test_register_detects_step_from_exchange_header(tmp_path):
    source = tmp_path / "part.step"
    source.write_bytes(b"ISO-10303-21;\nHEADER;\nENDSEC;\n")

    artifact = register(source)

    assert artifact.format == "step"
