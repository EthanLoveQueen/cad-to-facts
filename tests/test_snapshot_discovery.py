from cad_to_facts.artifact import register
from cad_to_facts.snapshot import read

from step_helpers import write_assembly, write_face


def test_face_only_step_does_not_claim_complete_solid_discovery(tmp_path):
    path = tmp_path / "face-only.step"
    write_face(path)

    snapshot = read(register(path))

    assert snapshot.status == "partial"
    assert snapshot.entity_discovery == "unknown"
    assert snapshot.entities == []
    assert [diagnostic.code for diagnostic in snapshot.diagnostics] == ["NO_SOLIDS"]
    assert snapshot.diagnostics[0].discovery_impact == "unknown"


def test_assembly_step_is_reported_as_flattened_and_incomplete(tmp_path):
    path = tmp_path / "assembly.step"
    write_assembly(path)

    snapshot = read(register(path))

    assert snapshot.status == "partial"
    assert snapshot.entity_discovery == "partial"
    assert [entity.entity_id for entity in snapshot.entities] == ["solid:0", "solid:1"]
    assert all(entity.assembly_path == [] for entity in snapshot.entities)
    assert snapshot.parse_options["source_structure"] == "assembly_flattened"
    by_code = {diagnostic.code: diagnostic for diagnostic in snapshot.diagnostics}
    assert set(by_code) == {"ASSEMBLY_STRUCTURE_NOT_REPRESENTED"}
    diagnostic = by_code["ASSEMBLY_STRUCTURE_NOT_REPRESENTED"]
    assert diagnostic.count == 2
    assert diagnostic.impact == "partial"
    assert diagnostic.discovery_impact == "partial"
