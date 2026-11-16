from cad_to_facts.artifact import register
from cad_to_facts.snapshot import read

from step_helpers import write_box


def test_read_analytic_step_box_discovers_one_solid_in_millimetres(tmp_path):
    path = tmp_path / "box.step"
    write_box(path)

    snapshot = read(register(path))

    assert snapshot.status == "ready"
    assert snapshot.entity_discovery == "complete"
    assert snapshot.units["length"] == "mm"
    assert len(snapshot.entities) == 1
    assert snapshot.entities[0].entity_kind == "solid"
    assert snapshot.entities[0].identity_scope == "snapshot"
