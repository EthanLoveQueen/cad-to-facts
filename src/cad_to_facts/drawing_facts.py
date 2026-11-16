"""Deterministic declared and measured facts for drawing snapshots."""

import math
from typing import Any

import ezdxf

from cad_to_facts.contract import bind_factset
from cad_to_facts.domain.facts import Evidence, ExtractionQuery, Fact, FactGap, FactSet, Method
from cad_to_facts.domain.snapshot import Diagnostic, ModelSnapshot

_UNIT_TO_MM = {"mm": 1.0, "cm": 10.0, "m": 1000.0, "in": 25.4, "ft": 304.8}
_NUMERIC_PREDICATES = {"length", "area", "circumference"}
_DECLARED_PREDICATES = {
    "entity_type",
    "layer",
    "container",
    "text",
    "block_name",
    "attribute_tag",
}
_SUPPORTED_PREDICATES = _NUMERIC_PREDICATES | _DECLARED_PREDICATES
_MEASURED_TYPES = {"LINE", "LWPOLYLINE", "CIRCLE", "ARC"}


def _lwpolyline_metrics(item: Any) -> tuple[float, float] | None:
    """Return exact length and signed area for straight and bulge segments."""

    vertices = list(item.get_points("xyseb"))
    if len(vertices) < 2:
        return None
    pairs = list(zip(vertices, vertices[1:]))
    if item.closed:
        pairs.append((vertices[-1], vertices[0]))
    length = 0.0
    twice_signed_area = 0.0
    for a, b in pairs:
        dx = b[0] - a[0]
        dy = b[1] - a[1]
        chord = math.hypot(dx, dy)
        bulge = a[4]
        twice_signed_area += a[0] * b[1] - b[0] * a[1]
        if bulge == 0:
            length += chord
            continue
        if chord == 0:
            raise ValueError("A bulge segment must have distinct endpoints")
        # DXF bulge is tan(theta/4), with sign giving the arc direction.
        theta = 4.0 * math.atan(bulge)
        radius = chord * (1.0 + bulge * bulge) / (4.0 * abs(bulge))
        length += radius * abs(theta)
        # Signed circular-segment area; theta carries the direction, including
        # major arcs, so no straight-line approximation is introduced.
        twice_signed_area += radius * radius * (theta - math.sin(theta))
    return length, twice_signed_area / 2.0


def _fact_value(item: Any, predicate: str) -> tuple[Any, str, str, str] | None:
    """Return value, source unit, algorithm and kind for one supported predicate."""

    dxf_type = item.dxftype()
    if predicate == "entity_type":
        return dxf_type, "dimensionless", "DXF entity type", "declared"
    if predicate == "layer":
        return item.dxf.layer, "dimensionless", "DXF layer attribute", "declared"
    if predicate == "text":
        if dxf_type in {"TEXT", "ATTRIB", "ATTDEF"}:
            return item.dxf.text, "dimensionless", "DXF text attribute", "declared"
        if dxf_type == "MTEXT":
            return item.text, "dimensionless", "DXF MTEXT content", "declared"
        return None
    if predicate == "block_name" and dxf_type in {"INSERT", "MINSERT"}:
        return item.dxf.name, "dimensionless", "DXF block-name attribute", "declared"
    if predicate == "attribute_tag" and dxf_type in {"ATTRIB", "ATTDEF"}:
        return item.dxf.tag, "dimensionless", "DXF attribute tag", "declared"
    if predicate == "length":
        if dxf_type == "LINE":
            return (
                (item.dxf.end - item.dxf.start).magnitude,
                "length",
                "Euclidean LINE endpoint distance",
                "measured",
            )
        if dxf_type == "LWPOLYLINE":
            metrics = _lwpolyline_metrics(item)
            if metrics is None:
                return None
            return (
                metrics[0],
                "length",
                "Exact LWPOLYLINE straight-segment and bulge-arc lengths",
                "measured",
            )
        if dxf_type == "ARC":
            angle = math.radians((item.dxf.end_angle - item.dxf.start_angle) % 360.0)
            return item.dxf.radius * angle, "length", "ARC radius times angle", "measured"
        return None
    if predicate == "circumference" and dxf_type == "CIRCLE":
        return 2 * math.pi * item.dxf.radius, "length", "CIRCLE circumference", "measured"
    if predicate == "area":
        if dxf_type == "CIRCLE":
            return math.pi * item.dxf.radius**2, "area", "CIRCLE area", "measured"
        if dxf_type == "LWPOLYLINE" and item.closed:
            metrics = _lwpolyline_metrics(item)
            if metrics is None:
                return None
            if all(vertex[4] == 0 for vertex in item.get_points("xyseb")) and len(item) < 3:
                return None
            return (
                abs(metrics[1]),
                "area",
                "Closed LWPOLYLINE shoelace plus exact signed bulge-arc segment areas",
                "measured",
            )
    return None


def default_requests(snapshot: ModelSnapshot, entities: list) -> ExtractionQuery:
    """Select useful drawing predicates without producing STEP-only volume gaps."""

    from cad_to_facts.domain.facts import FactRequest

    requests: list[FactRequest] = []
    for entity in entities:
        info = snapshot._adapter_payload["entities"][entity.entity_id]
        item = info["entity"]
        predicates = ["entity_type", "layer", "container"]
        dxf_type = item.dxftype()
        if dxf_type in {"TEXT", "MTEXT", "ATTRIB", "ATTDEF"}:
            predicates.append("text")
        if dxf_type in {"ATTRIB", "ATTDEF"}:
            predicates.append("attribute_tag")
        if dxf_type in {"INSERT", "MINSERT"}:
            predicates.append("block_name")
        if dxf_type in {"LINE", "LWPOLYLINE", "ARC"}:
            predicates.append("length")
        if dxf_type == "CIRCLE":
            predicates.extend(["area", "circumference"])
        if dxf_type == "LWPOLYLINE" and item.closed:
            predicates.append("area")
        for predicate in predicates:
            requests.append(
                FactRequest(
                    name=f"{entity.entity_id}:{predicate}",
                    predicate=predicate,
                    subject_id=entity.entity_id,
                )
            )
    return ExtractionQuery(requests=requests)


def extract_drawing(snapshot: ModelSnapshot, query: ExtractionQuery) -> FactSet:
    facts: list[Fact] = []
    gaps: list[FactGap] = []
    diagnostics: list[Diagnostic] = []
    subjects = {entity.entity_id: entity for entity in snapshot.entities}
    for request in query.requests:
        subject = subjects.get(request.subject_id)
        if subject is None:
            raise ValueError(f"Unknown snapshot entity: {request.subject_id}")
        info = snapshot._adapter_payload["entities"][request.subject_id]
        item = info["entity"]
        source_artifact = info.get("artifact_sha256", snapshot.artifact_sha256)
        declared_unit = info.get("length_unit", snapshot.units.get("length"))
        if request.predicate not in _SUPPORTED_PREDICATES:
            result = None
        else:
            if request.predicate == "container":
                result = (info["container"], "dimensionless", "DXF container membership", "declared")
            else:
                try:
                    result = _fact_value(item, request.predicate)
                except Exception as error:
                    gaps.append(
                        FactGap(
                            request=request,
                            subject=subject,
                            reason_code="MEASUREMENT_FAILED",
                            blocking_capabilities=[request.predicate],
                            evidence=Evidence(
                                artifact_sha256=source_artifact, entity_refs=[subject]
                            ),
                        )
                    )
                    diagnostics.append(
                        Diagnostic(
                            code="MEASUREMENT_FAILED",
                            severity="error",
                            stage="measure",
                            message=f"{request.predicate} failed for {subject.entity_id}: {type(error).__name__}",
                            scope_refs=[subject.entity_id],
                            affects=["measure"],
                            impact="partial",
                            entity_refs=[subject.entity_id],
                            details={"predicate": request.predicate, "error_type": type(error).__name__},
                        )
                    )
                    continue
        if result is None:
            gaps.append(
                FactGap(
                    request=request,
                    subject=subject,
                    reason_code="UNSUPPORTED",
                    blocking_capabilities=[request.predicate],
                    evidence=Evidence(
                        artifact_sha256=source_artifact, entity_refs=[subject]
                    ),
                )
            )
            continue
        source_value, source_dimension, algorithm, kind = result
        parameters = {}
        if info.get("derived_dxf_sha256"):
            parameters["derived_dxf_sha256"] = info["derived_dxf_sha256"]
        if source_artifact != snapshot.artifact_sha256:
            parameters["host_artifact_sha256"] = snapshot.artifact_sha256
            parameters["xref_mode"] = "flatten"
        if source_dimension in {"length", "area"}:
            if declared_unit not in _UNIT_TO_MM:
                gaps.append(
                    FactGap(
                        request=request,
                        subject=subject,
                        reason_code="UNKNOWN_UNIT",
                        blocking_capabilities=[request.predicate],
                        evidence=Evidence(
                            artifact_sha256=source_artifact, entity_refs=[subject]
                        ),
                    )
                )
                continue
            exponent = 2 if source_dimension == "area" else 1
            factor = _UNIT_TO_MM[declared_unit] ** exponent
            value = source_value * factor
            unit = "mm^2" if exponent == 2 else "mm"
            if not math.isfinite(value) or value < 0:
                gaps.append(
                    FactGap(
                        request=request,
                        subject=subject,
                        reason_code="MEASUREMENT_FAILED",
                        blocking_capabilities=[request.predicate],
                        evidence=Evidence(
                            artifact_sha256=source_artifact, entity_refs=[subject]
                        ),
                    )
                )
                continue
            parameters.update(
                {
                    "declared_length_unit": declared_unit,
                    "system_length_unit": "mm",
                    "conversion_factor": factor,
                    "derived_source_value": source_value,
                    "unit_conversion": "dxf_header_insunits",
                }
            )
        else:
            value = source_value
            unit = "dimensionless"
        facts.append(
            Fact(
                fact_id="0" * 64,
                kind=kind,
                subject=subject,
                predicate=request.predicate,
                value=value,
                unit=unit,
                evidence=Evidence(artifact_sha256=source_artifact, entity_refs=[subject]),
                method=Method(
                    library="ezdxf",
                    algorithm=algorithm,
                    version=ezdxf.__version__,
                    parameters=parameters,
                ),
            )
        )
    return bind_factset(
        FactSet(
            factset_id="0" * 64,
            snapshot_id=snapshot.snapshot_id,
            snapshot_content_hash=snapshot.snapshot_content_hash,
            extraction_query=query,
            extractor_version="0.1.0",
            facts=facts,
            gaps=gaps,
            diagnostics=diagnostics,
        )
    )
