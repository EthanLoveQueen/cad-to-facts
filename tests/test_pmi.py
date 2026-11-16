import contextlib
import io
import json
import math
from pathlib import Path

import pytest

from cad_to_facts import cli
from cad_to_facts.artifact import register
from cad_to_facts.contract import verify_pmi_identity
from cad_to_facts.domain.pmi import PmiExtract
from cad_to_facts.errors import ConfigurationError
from cad_to_facts.pmi import (
    _canonical_modifiers,
    _canonical_type,
    _declared_angle,
    _declared_length,
    extract_pmi,
)
from cad_to_facts.snapshot import read

ROOT = Path(__file__).resolve().parents[1]
BOX_PATH = ROOT / "examples" / "box.step"
NIST_AP242 = ROOT / "test-data" / "external" / "nist_ctc_01_asme1_ap242-e1.stp"
NIST_AP203 = ROOT / "test-data" / "external" / "nist_ctc_01_asme1_rd_ap203.stp"
requires_nist_ap242 = pytest.mark.skipif(
    not NIST_AP242.is_file(),
    reason="NIST AP242 PMI corpus file absent (test-data is not redistributed)",
)
requires_nist_ap203 = pytest.mark.skipif(
    not NIST_AP203.is_file(),
    reason="NIST AP203 corpus file absent (test-data is not redistributed)",
)


def _extract(path):
    artifact = register(path)
    snapshot = read(artifact, {"read_scope": "single_part"})
    return artifact, snapshot, extract_pmi(artifact, snapshot)


def _run(arguments):
    output = io.StringIO()
    with contextlib.redirect_stdout(output):
        exit_code = cli.main(arguments)
    return exit_code, json.loads(output.getvalue())


def test_pmi_extraction_is_empty_and_complete_without_declared_pmi():
    artifact, snapshot, pmi = _extract(BOX_PATH)

    assert pmi.status == "ready"
    assert pmi.complete is True
    assert pmi.artifact_sha256 == artifact.sha256
    assert pmi.snapshot_id == snapshot.snapshot_id
    assert pmi.snapshot_content_hash == snapshot.snapshot_content_hash
    assert pmi.annotations == []
    assert pmi.gaps == []
    assert pmi.units == {}
    assert pmi.unit_contexts == []
    assert pmi.inventory.dimension_entities == 0
    assert pmi.inventory.geometric_tolerance_entities == 0
    assert pmi.inventory.datum_entities == 0
    assert pmi.coverage.discovery == "complete"
    assert pmi.coverage.dimension_observed == 0


def test_pmi_on_malformed_step_returns_a_failed_extract_instead_of_crashing(tmp_path):
    path = tmp_path / "broken.step"
    path.write_text(
        "ISO-10303-21;\nHEADER;\nENDSEC;\nDATA;\nENDSEC;\nEND-ISO-10303-21;\n",
        encoding="ascii",
    )
    artifact = register(path)
    snapshot = read(artifact, {"read_scope": "single_part"})

    pmi = extract_pmi(artifact, snapshot)

    assert pmi.status == "failed"
    assert pmi.complete is False
    assert pmi.annotations == []
    assert pmi.coverage.discovery == "unknown"
    assert [diagnostic.code for diagnostic in pmi.diagnostics] == ["PMI_READ_FAILED"]
    assert pmi.pmi_id != "0" * 64


def test_pmi_identity_is_deterministic_and_verifiable():
    _, _, first = _extract(BOX_PATH)
    _, _, second = _extract(BOX_PATH)

    assert first.pmi_id == second.pmi_id
    assert verify_pmi_identity(first).pmi_id == first.pmi_id


@requires_nist_ap242
def test_pmi_identity_detects_tampered_annotation():
    _, _, pmi = _extract(NIST_AP242)
    tampered = pmi.model_copy(
        update={
            "annotations": [
                pmi.annotations[0].model_copy(
                    update={"value": (pmi.annotations[0].value or 0.0) + 1.0}
                )
            ]
        }
    )
    with pytest.raises(ConfigurationError):
        verify_pmi_identity(tampered)


def test_reader_system_units_are_converted_to_declared_units():
    assert _declared_length(1e-6, "nm") == pytest.approx(1.0)
    assert _declared_length(1e-3, "um") == pytest.approx(1.0)
    assert _declared_length(1.0, "mm") == pytest.approx(1.0)
    assert _declared_length(10.0, "cm") == pytest.approx(1.0)
    assert _declared_length(1000.0, "m") == pytest.approx(1.0)
    assert _declared_length(1e6, "km") == pytest.approx(1.0)
    assert _declared_length(25.4, "in") == pytest.approx(1.0)
    assert _declared_length(304.8, "ft") == pytest.approx(1.0)
    assert _declared_length(914.4, "yd") == pytest.approx(1.0)
    assert _declared_angle(180.0, "rad") == pytest.approx(math.pi)
    assert _declared_angle(1.0, "deg") == pytest.approx(1.0)
    assert _declared_angle(1.0, "arcmin") == pytest.approx(60.0)
    assert _declared_angle(1.0, "arcsec") == pytest.approx(3600.0)
    assert _declared_length(1.0, None) is None
    assert _declared_angle(1.0, None) is None


def test_native_enum_names_are_canonicalized_without_losing_the_raw_name():
    class _Enum:
        name = "XCAFDimTolObjects_DimensionQualifier_AllAround"

    assert _canonical_type(_Enum(), "XCAFDimTolObjects_DimensionQualifier_") == (
        "all_around",
        "XCAFDimTolObjects_DimensionQualifier_AllAround",
    )
    assert _canonical_type(
        "XCAFDimTolObjects_DimensionQualifier_AllAround",
        "XCAFDimTolObjects_DimensionQualifier_",
    )[0] == "all_around"
    assert _canonical_modifiers(
        [
            "XCAFDimTolObjects_DimensionModif_None",
            "XCAFDimTolObjects_DimensionModif_AllAround",
            "XCAFDimTolObjects_DimensionModif_AllAround",
        ],
        "XCAFDimTolObjects_DimensionModif_",
    ) == ["all_around"]


def test_pmi_cli_returns_artifact_snapshot_and_pmi():
    exit_code, payload = _run(["pmi", str(BOX_PATH)])

    assert exit_code == 0
    assert set(payload) == {"artifact", "snapshot", "pmi"}
    assert payload["artifact"]["sha256"] == register(BOX_PATH).sha256
    assert payload["pmi"]["status"] == "ready"
    loaded = PmiExtract.model_validate(payload["pmi"])
    assert verify_pmi_identity(loaded).pmi_id == loaded.pmi_id


@requires_nist_ap203
def test_ap203_geometry_without_pmi_is_an_explicit_empty_result():
    _, _, pmi = _extract(NIST_AP203)

    assert pmi.status == "ready"
    assert pmi.complete is True
    assert pmi.annotations == []
    assert pmi.gaps == []
    assert pmi.coverage.dimension_observed == 0
    assert pmi.coverage.geometric_tolerance_observed == 0


@requires_nist_ap242
def test_nist_ap242_inventory_and_coverage_are_reconciled():
    _, _, pmi = _extract(NIST_AP242)

    assert pmi.status == "partial"
    assert pmi.complete is False
    assert pmi.inventory.dimension_entities == 12
    assert pmi.inventory.dimension_representation_entities == 8
    assert pmi.inventory.geometric_tolerance_entities == 6
    assert pmi.inventory.datum_entities == 3
    assert pmi.inventory.datum_feature_entities == 3
    assert pmi.inventory.datum_system_entities == 2
    assert pmi.inventory.presentation_entities == 9
    assert pmi.inventory.unsupported_category_counts == {"datum_system": 2}
    assert pmi.coverage.dimension_observed == 12
    assert pmi.coverage.dimension_annotations == 12
    assert pmi.coverage.dimension_with_value == 8
    assert pmi.coverage.geometric_tolerance_observed == 6
    assert pmi.coverage.geometric_tolerance_annotations == 6
    assert pmi.coverage.geometric_tolerance_with_value == 6
    assert pmi.coverage.datum_observed == 3
    assert pmi.coverage.datum_annotations == 3
    assert pmi.coverage.datum_with_identification == 3
    assert pmi.coverage.discovery == "partial"
    assert pmi.coverage.link_resolved == 19
    assert pmi.coverage.link_unresolved == 0
    assert pmi.coverage.link_absent == 2
    unsupported = [
        gap for gap in pmi.gaps if gap.reason_code == "PMI_UNSUPPORTED_TYPE"
    ]
    assert len(unsupported) == 1
    assert unsupported[0].annotation_type == "datum_system"
    assert unsupported[0].kind is None
    assert pmi.units == {
        "dimension_length": "mm",
        "dimension_angle": "deg",
        "geometric_tolerance_length": "mm",
    }


@requires_nist_ap242
def test_nist_ap242_dimensions_keep_values_units_and_unsupported_gaps():
    _, _, pmi = _extract(NIST_AP242)
    dimensions = [item for item in pmi.annotations if item.kind == "dimension"]

    assert len(dimensions) == 12
    valued = [item for item in dimensions if item.value is not None]
    assert len(valued) == 8
    by_type = {}
    for item in valued:
        by_type.setdefault(item.annotation_type, []).append(item)
    assert len(by_type["size.diameter"]) == 7
    assert len(by_type["location.angular"]) == 1
    angular = by_type["location.angular"][0]
    assert angular.value == pytest.approx(60.0)
    assert angular.unit == "deg"
    assert angular.tolerance.form == "deviation_magnitudes"
    assert angular.tolerance.lower_deviation_magnitude == pytest.approx(0.5)
    assert angular.tolerance.upper_deviation_magnitude == pytest.approx(0.5)

    diameters = sorted(item.value for item in by_type["size.diameter"])
    assert diameters == pytest.approx([20.0, 20.0, 25.0, 35.0, 35.0, 35.0, 35.0])
    limit_dimensions = [
        item
        for item in by_type["size.diameter"]
        if item.tolerance is not None and item.tolerance.form == "limits"
    ]
    assert len(limit_dimensions) == 2
    assert all(
        item.tolerance.lower_limit == pytest.approx(34.8)
        and item.tolerance.upper_limit == pytest.approx(35.2)
        for item in limit_dimensions
    )
    deviation_dimensions = [
        item
        for item in by_type["size.diameter"]
        if item.tolerance is not None
        and item.tolerance.form == "deviation_magnitudes"
    ]
    assert len(deviation_dimensions) == 5
    assert all(
        item.tolerance.sign_convention == "not_reported_by_reader"
        for item in deviation_dimensions
    )

    unvalued_gaps = [
        gap for gap in pmi.gaps if gap.reason_code == "PMI_VALUE_UNAVAILABLE"
    ]
    assert len(unvalued_gaps) == 4
    assert all(gap.kind == "dimension" for gap in unvalued_gaps)
    assert all(gap.annotation_type == "location.none" for gap in unvalued_gaps)
    assert all(item.value is None for item in dimensions if item.annotation_type == "location.none")
    assert all(item.qualifier is None for item in dimensions)
    assert all(item.link_status == "resolved" for item in dimensions)
    assert all(
        [entity.entity_id for entity in item.linked_entities] == ["solid:0"]
        for item in dimensions
    )
    assert all(
        {"kind": "xcaf_label", "shape_type": "face"}.items()
        <= item.native_shape_refs[0].items()
        for item in dimensions
    )


@requires_nist_ap242
def test_nist_ap242_geometric_tolerances_and_datums_are_declared():
    _, _, pmi = _extract(NIST_AP242)
    tolerances = [
        item for item in pmi.annotations if item.kind == "geometric_tolerance"
    ]
    by_type = {}
    for item in tolerances:
        by_type.setdefault(item.annotation_type, []).append(item)
    assert {key: len(value) for key, value in by_type.items()} == {
        "position": 2,
        "profile_of_surface": 2,
        "perpendicularity": 1,
        "flatness": 1,
    }
    assert sorted(item.value for item in tolerances) == pytest.approx(
        [0.2, 0.5, 0.75, 0.75, 1.25, 1.5]
    )
    assert all(item.unit == "mm" for item in tolerances)
    assert all(item.link_status == "resolved" for item in tolerances)
    assert all(item.material_requirement_modifier is None for item in tolerances)
    assert all(item.zone_modifier is None for item in tolerances)
    all_around = next(
        item
        for item in tolerances
        if item.annotation_type == "profile_of_surface"
        and item.value == pytest.approx(0.5)
    )
    assert all_around.modifiers == ["all.around"]
    datum_sets = sorted(tuple(item.datums) for item in tolerances)
    assert datum_sets == [(), ("A",), ("A",), ("A", "B", "C"), ("A", "B", "C"), ("A", "B", "C")]

    datums = [item for item in pmi.annotations if item.kind == "datum"]
    assert [item.semantic_name for item in datums] == ["A", "B", "C"]
    assert [item.link_status for item in datums] == ["resolved", "absent", "absent"]
    assert [entity.entity_id for entity in datums[0].linked_entities] == ["solid:0"]
    assert [item for item in datums if item.link_status == "absent"][0].linked_entities == []
    absent_gaps = [
        gap for gap in pmi.gaps if gap.reason_code == "PMI_GEOMETRY_LINK_ABSENT"
    ]
    assert len(absent_gaps) == 2
    assert all(gap.kind == "datum" for gap in absent_gaps)


@requires_nist_ap242
def test_nist_ap242_reports_the_reader_sign_limitation():
    _, _, pmi = _extract(NIST_AP242)

    sign = next(
        item for item in pmi.diagnostics if item.code == "PMI_TOLERANCE_SIGN_NOT_REPORTED"
    )
    assert sign.count == 6
    assert sign.severity == "info"
    assert sign.affects == ["pmi"]


@requires_nist_ap242
def test_nist_ap242_pmi_identity_is_stable():
    _, _, first = _extract(NIST_AP242)
    _, _, second = _extract(NIST_AP242)

    assert first.pmi_id == second.pmi_id
    assert all(item.annotation_id != "0" * 64 for item in first.annotations)
    assert verify_pmi_identity(first).pmi_id == first.pmi_id


@requires_nist_ap242
def test_pmi_cli_extracts_nist_semantic_values():
    exit_code, payload = _run(["pmi", str(NIST_AP242)])

    assert exit_code == 0
    pmi = payload["pmi"]
    assert pmi["coverage"]["dimension_with_value"] == 8
    assert pmi["coverage"]["geometric_tolerance_with_value"] == 6
    assert pmi["complete"] is False
