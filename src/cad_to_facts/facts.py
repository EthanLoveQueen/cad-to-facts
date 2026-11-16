from collections.abc import Callable
import math

import OCP
from OCP.Bnd import Bnd_Box
from OCP.BRepBndLib import BRepBndLib
from OCP.BRepGProp import BRepGProp
from OCP.GProp import GProp_GProps
from OCP.TopAbs import TopAbs_SOLID
from OCP.TopExp import TopExp_Explorer
from OCP.TopoDS import TopoDS_Shape

from cad_to_facts.contract import bind_factset
from cad_to_facts.domain.facts import Evidence, ExtractionQuery, Fact, FactGap, FactSet, Method
from cad_to_facts.domain.snapshot import Diagnostic, EntityRef, ModelSnapshot


def _shape_for(snapshot: ModelSnapshot, subject_id: str) -> TopoDS_Shape:
    explorer = TopExp_Explorer(snapshot._adapter_payload["shape"], TopAbs_SOLID)
    index = 0
    while explorer.More():
        if f"solid:{index}" == subject_id:
            return explorer.Current()
        index += 1
        explorer.Next()
    raise ValueError(f"Unknown snapshot entity: {subject_id}")


def _volume(shape: TopoDS_Shape) -> tuple[float, str, str, dict]:
    properties = GProp_GProps()
    BRepGProp.VolumeProperties_s(shape, properties)
    return properties.Mass(), "mm^3", "BRepGProp.VolumeProperties", {}


def _area(shape: TopoDS_Shape) -> tuple[float, str, str, dict]:
    properties = GProp_GProps()
    BRepGProp.SurfaceProperties_s(shape, properties)
    return properties.Mass(), "mm^2", "BRepGProp.SurfaceProperties", {}


def _bbox_extent(axis: str) -> Callable[[TopoDS_Shape], tuple[float, str, str, dict]]:
    def measure(shape: TopoDS_Shape) -> tuple[float, str, str, dict]:
        box = Bnd_Box()
        BRepBndLib.AddOptimal_s(shape, box, False, False)
        minimum = box.CornerMin()
        maximum = box.CornerMax()
        extents = {"x": maximum.X() - minimum.X(), "y": maximum.Y() - minimum.Y(), "z": maximum.Z() - minimum.Z()}
        return extents[axis], "mm", "BRepBndLib.AddOptimal", {"axis": axis, "use_triangulation": False, "use_shape_tolerance": False}

    return measure


_MEASURERS = {
    "volume": _volume,
    "area": _area,
    "bbox.extent.x": _bbox_extent("x"),
    "bbox.extent.y": _bbox_extent("y"),
    "bbox.extent.z": _bbox_extent("z"),
}
_LENGTH_PREDICATES = set(_MEASURERS)
_VERIFIED_LENGTH_UNITS = {"mm", "cm", "in"}
_LENGTH_UNIT_TO_MM = {"mm": 1.0, "cm": 10.0, "in": 25.4}
_DIMENSION_EXPONENT = {"volume": 3, "area": 2}


def extract(snapshot: ModelSnapshot, query: ExtractionQuery) -> FactSet:
    """Extract facts through the snapshot's format-specific profile."""

    if snapshot.drawing is not None:
        from cad_to_facts.drawing_facts import extract_drawing

        return extract_drawing(snapshot, query)
    return _extract_step(snapshot, query)


def _extract_step(snapshot: ModelSnapshot, query: ExtractionQuery) -> FactSet:
    """Measure explicitly requested facts through OCCT."""

    facts: list[Fact] = []
    gaps: list[FactGap] = []
    diagnostics: list[Diagnostic] = []
    subjects = {entity.entity_id: entity for entity in snapshot.entities}
    declared_length_unit = snapshot.units.get("length")
    for request in query.requests:
        if request.predicate not in _MEASURERS:
            gaps.append(
                FactGap(
                    request=request,
                    subject=subjects.get(request.subject_id),
                    reason_code="UNSUPPORTED",
                    blocking_capabilities=[request.predicate],
                    evidence=Evidence(artifact_sha256=snapshot.artifact_sha256),
                )
            )
            continue
        subject = subjects.get(request.subject_id)
        if subject is None:
            raise ValueError(f"Unknown snapshot entity: {request.subject_id}")
        if request.predicate in _LENGTH_PREDICATES and declared_length_unit not in _VERIFIED_LENGTH_UNITS:
            gaps.append(
                FactGap(
                    request=request,
                    subject=subject,
                    reason_code="UNKNOWN_UNIT",
                    blocking_capabilities=[request.predicate],
                    evidence=Evidence(
                        artifact_sha256=snapshot.artifact_sha256, entity_refs=[subject]
                    ),
                )
            )
            continue
        try:
            shape = _shape_for(snapshot, request.subject_id)
            value, unit, algorithm, parameters = _MEASURERS[request.predicate](shape)
            if not math.isfinite(value) or value < 0:
                raise ValueError(
                    f"OCCT returned an invalid non-negative measurement: {value!r}"
                )
        except Exception as error:
            gaps.append(
                FactGap(
                    request=request,
                    subject=subject,
                    reason_code="MEASUREMENT_FAILED",
                    blocking_capabilities=[request.predicate],
                    evidence=Evidence(
                        artifact_sha256=snapshot.artifact_sha256, entity_refs=[subject]
                    ),
                )
            )
            diagnostics.append(
                Diagnostic(
                    code="MEASUREMENT_FAILED",
                    severity="error",
                    stage="measure",
                    message=(
                        f"{request.predicate} failed for {subject.entity_id}: "
                        f"{type(error).__name__}: {error}"
                    ),
                    scope_refs=[subject.entity_id],
                    affects=["measure"],
                    impact="partial",
                    discovery_impact="none",
                    entity_refs=[subject.entity_id],
                    details={
                        "predicate": request.predicate,
                        "error_type": type(error).__name__,
                    },
                )
            )
            continue
        conversion_factor = _LENGTH_UNIT_TO_MM[declared_length_unit] ** _DIMENSION_EXPONENT.get(
            request.predicate, 1
        )
        parameters = {
            **parameters,
            "declared_length_unit": declared_length_unit,
            "system_length_unit": "mm",
            "conversion_factor": conversion_factor,
            "derived_source_value": value / conversion_factor,
            "unit_conversion": "occt_step_reader",
        }
        fact = Fact(
            fact_id="0" * 64,
            kind="measured",
            subject=subject,
            predicate=request.predicate,
            value=value,
            unit=unit,
            evidence=Evidence(artifact_sha256=snapshot.artifact_sha256, entity_refs=[subject]),
            method=Method(library="OCCT", algorithm=algorithm, version=OCP.__version__, parameters=parameters),
        )
        facts.append(fact)

    factset = FactSet(
        factset_id="0" * 64,
        snapshot_id=snapshot.snapshot_id,
        snapshot_content_hash=snapshot.snapshot_content_hash,
        extraction_query=query,
        extractor_version="0.1.0",
        facts=facts,
        gaps=gaps,
        diagnostics=diagnostics,
    )
    return bind_factset(factset)
