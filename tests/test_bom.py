from cad_to_facts.artifact import register
from cad_to_facts.bom import extract_bom
from cad_to_facts.contract import bind_snapshot
from cad_to_facts.domain.bom import BOMOptions
from cad_to_facts.snapshot import read

from step_helpers import write_assembly, write_nested_assembly


def test_bom_groups_repeated_occurrences_by_part_definition(tmp_path):
    path = tmp_path / "assembly.step"
    write_assembly(path, names=("Bracket", "Rail"), occurrences_per_part=2)

    snapshot = read(register(path), {"read_scope": "assembly"})
    bom = extract_bom(snapshot, BOMOptions(required_properties=["name"]))

    assert bom.complete is True
    assert bom.missing_inputs == []
    assert len(bom.line_items) == 2
    by_name = {item.name: item for item in bom.line_items}
    assert by_name["Bracket"].quantity == 2
    assert by_name["Rail"].quantity == 2
    assert all(item.quantity_state == "known" for item in bom.line_items)
    assert all(len(item.occurrence_refs) == 2 for item in bom.line_items)
    assert all(len(item.counted_occurrence_refs) == 2 for item in bom.line_items)
    assert bom.coverage.definition_total == 2
    assert bom.coverage.occurrence_total == 4
    assert bom.coverage.counted_occurrence_total == 4
    assert bom.coverage.known_quantity_definition_total == 2
    assert bom.coverage.observed_quantity_definition_total == 0
    assert bom.coverage.unknown_quantity_definition_total == 0
    assert (
        bom.coverage.known_quantity_definition_total
        + bom.coverage.observed_quantity_definition_total
        + bom.coverage.unknown_quantity_definition_total
        == bom.coverage.definition_total
    )
    assert len(bom.assembly_links) == 4
    assert len(bom.definitions) == 3
    assert len(bom.occurrences) == 5
    occurrence_ids = {item.occurrence_id for item in bom.occurrences}
    assert all(
        link.parent_occurrence_id in occurrence_ids
        and link.child_occurrence_id in occurrence_ids
        for link in bom.assembly_links
    )


def test_bom_reports_unsupported_required_property_without_blocking_names(tmp_path):
    path = tmp_path / "assembly.step"
    write_assembly(path)

    snapshot = read(register(path), {"read_scope": "assembly"})
    bom = extract_bom(snapshot, BOMOptions(required_properties=["material"]))

    assert bom.complete is False
    assert len(bom.line_items) == 2
    assert all(item.quantity == 1 for item in bom.line_items)
    assert len(bom.missing_inputs) == 2
    assert {item.field for item in bom.missing_inputs} == {"material"}
    assert {item.reason_code for item in bom.missing_inputs} == {"UNSUPPORTED"}


def test_bom_unknown_occurrence_state_makes_quantity_unknown(tmp_path):
    path = tmp_path / "assembly.step"
    write_assembly(path)
    snapshot = read(register(path), {"read_scope": "assembly"})
    assembly = snapshot.assembly
    leaf_ids = {
        item.definition_id for item in assembly.definitions if not item.is_assembly
    }
    occurrences = list(assembly.occurrences)
    target = next(item for item in occurrences if item.definition_id in leaf_ids)
    occurrences[occurrences.index(target)] = target.model_copy(update={"state": "unknown"})
    assembly = assembly.model_copy(update={"occurrences": occurrences})
    snapshot = bind_snapshot(snapshot.model_copy(update={"assembly": assembly}))

    bom = extract_bom(snapshot)

    item = next(
        item for item in bom.line_items if item.part_definition_id == target.definition_id
    )
    assert item.quantity is None
    assert item.quantity_state == "unknown"
    assert item.counted_occurrence_refs == []
    assert bom.coverage.known_quantity_definition_total == 1
    assert bom.coverage.observed_quantity_definition_total == 0
    assert bom.coverage.unknown_quantity_definition_total == 1
    assert (
        bom.coverage.known_quantity_definition_total
        + bom.coverage.observed_quantity_definition_total
        + bom.coverage.unknown_quantity_definition_total
        == bom.coverage.definition_total
    )
    assert bom.complete is False


def test_bom_counts_shared_definition_across_nested_levels(tmp_path):
    path = tmp_path / "nested.step"
    write_nested_assembly(path)

    snapshot = read(register(path), {"read_scope": "assembly"})
    bom = extract_bom(snapshot, BOMOptions(required_properties=["name"]))

    assert bom.complete is True
    assert len(bom.line_items) == 1
    assert bom.coverage.known_quantity_definition_total == 1
    item = bom.line_items[0]
    assert item.name == "Shared part"
    assert item.quantity == 3
    assert len(item.counted_occurrence_refs) == 3
    occurrences = {item.occurrence_id: item for item in bom.occurrences}
    paths = [occurrences[ref].path for ref in item.counted_occurrence_refs]
    assert sorted(len(path) for path in paths) == [2, 3, 3]
