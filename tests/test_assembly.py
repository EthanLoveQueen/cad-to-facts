from cad_to_facts.artifact import register
from cad_to_facts.identity import structured_hash
from cad_to_facts.snapshot import read

from step_helpers import write_assembly, write_nested_assembly


def test_assembly_profile_preserves_definitions_occurrences_and_paths(tmp_path):
    path = tmp_path / "assembly.step"
    write_assembly(
        path,
        names=("Bracket", "Rail"),
        occurrences_per_part=2,
    )

    snapshot = read(register(path), {"read_scope": "assembly"})

    assert snapshot.status == "ready"
    assert snapshot.entity_discovery == "complete"
    assert snapshot.assembly is not None
    assert snapshot.assembly.discovery == "complete"
    assert snapshot.snapshot_id == structured_hash(
        "model-snapshot-id",
        {
            "artifact_sha256": snapshot.artifact_sha256,
            "adapter_id": snapshot.adapter_id,
            "adapter_version": snapshot.adapter_version,
            "parser_kernel_version": snapshot.parser_kernel_version,
            "parse_options": snapshot.parse_options,
        },
    )
    leaves = [item for item in snapshot.assembly.definitions if not item.is_assembly]
    assert {item.name for item in leaves} == {"Bracket", "Rail"}
    assert len(snapshot.assembly.occurrences) == 5
    roots = [item for item in snapshot.assembly.occurrences if item.parent_occurrence_id is None]
    assert len(roots) == 1
    leaf_occurrences = [
        item
        for item in snapshot.assembly.occurrences
        if item.definition_id in {definition.definition_id for definition in leaves}
    ]
    assert len(leaf_occurrences) == 4
    assert all(len(item.path) == 2 for item in leaf_occurrences)
    assert all(item.state == "active" for item in leaf_occurrences)
    assert len(snapshot.assembly.links) == 4


def test_nested_assembly_preserves_occurrence_paths_across_levels(tmp_path):
    path = tmp_path / "nested.step"
    write_nested_assembly(path)

    snapshot = read(register(path), {"read_scope": "assembly"})

    assert snapshot.status == "ready"
    assembly = snapshot.assembly
    assert len(assembly.definitions) == 3
    assert len(assembly.occurrences) == 5
    leaf = next(item for item in assembly.definitions if item.name == "Shared part")
    occurrences = [
        item for item in assembly.occurrences if item.definition_id == leaf.definition_id
    ]
    assert len(occurrences) == 3
    assert sorted(len(item.path) for item in occurrences) == [2, 3, 3]
    for occurrence in occurrences:
        if len(occurrence.path) == 3:
            parent = next(
                item
                for item in assembly.occurrences
                if item.occurrence_id == occurrence.parent_occurrence_id
            )
            assert occurrence.path[:2] == parent.path
