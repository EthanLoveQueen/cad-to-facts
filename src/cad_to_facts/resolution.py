"""Snapshot-scoped occurrence reference resolution."""

from OCP.Bnd import Bnd_Box
from OCP.BRepBndLib import BRepBndLib

from cad_to_facts.domain.snapshot import Diagnostic, ModelSnapshot
from cad_to_facts.domain.view import (
    BoundingBox,
    SpatialConstraint,
    SpatialMatchEvidence,
    TargetCandidate,
    TargetResolution,
    TargetSelector,
)
from cad_to_facts.frames import camera_basis
from cad_to_facts.identity import structured_hash


def _placed_bbox(snapshot: ModelSnapshot, occurrence_id: str) -> BoundingBox:
    shape = snapshot._adapter_payload.get("occurrence_shapes", {}).get(occurrence_id)
    if shape is None or shape.IsNull():
        raise ValueError("No transferred shape is available for this occurrence")
    box = Bnd_Box()
    BRepBndLib.AddOptimal_s(shape, box, False, False)
    if box.IsVoid():
        raise ValueError("The occurrence shape has no measurable bounding box")
    minimum = box.CornerMin()
    maximum = box.CornerMax()
    minima = [minimum.X(), minimum.Y(), minimum.Z()]
    maxima = [maximum.X(), maximum.Y(), maximum.Z()]
    return BoundingBox(
        minimum=minima,
        maximum=maxima,
        extents=[high - low for low, high in zip(minima, maxima, strict=True)],
        center=[(low + high) / 2.0 for low, high in zip(minima, maxima, strict=True)],
    )


def target_candidate(snapshot: ModelSnapshot, occurrence) -> TargetCandidate:
    assembly = snapshot.assembly
    assert assembly is not None
    occurrences = {item.occurrence_id: item for item in assembly.occurrences}
    definitions = {item.definition_id: item for item in assembly.definitions}
    definition = definitions[occurrence.definition_id]
    bbox = None
    geometry_diagnostic = None
    try:
        bbox = _placed_bbox(snapshot, occurrence.occurrence_id)
    except Exception as error:
        geometry_diagnostic = str(error)
    return TargetCandidate(
        occurrence_id=occurrence.occurrence_id,
        path="/".join(occurrence.path),
        name_path=[
            occurrences[item].name or occurrences[item].occurrence_id for item in occurrence.path
        ],
        native_ref=occurrence.native_ref,
        name=occurrence.name,
        definition_id=occurrence.definition_id,
        definition_name=definition.name,
        is_assembly=definition.is_assembly,
        state=occurrence.state,
        transformation=occurrence.transformation,
        bbox=bbox,
        geometry_diagnostic=geometry_diagnostic,
    )


def _declared_matches(snapshot: ModelSnapshot, selector: TargetSelector):
    assert snapshot.assembly is not None
    definitions = {item.definition_id: item for item in snapshot.assembly.definitions}
    matches = []
    for occurrence in snapshot.assembly.occurrences:
        definition = definitions[occurrence.definition_id]
        path = "/".join(occurrence.path)
        if selector.occurrence_id is not None and occurrence.occurrence_id != selector.occurrence_id:
            continue
        if selector.path is not None and path != selector.path:
            continue
        names = [value for value in (occurrence.name, definition.name) if value is not None]
        if selector.name is not None and selector.name not in names:
            continue
        if selector.name_contains is not None and not any(
            selector.name_contains.casefold() in value.casefold() for value in names
        ):
            continue
        if selector.name_contains_any is not None and not any(
            alias.casefold() in value.casefold()
            for alias in selector.name_contains_any
            for value in names
        ):
            continue
        if selector.definition_id is not None and occurrence.definition_id != selector.definition_id:
            continue
        if selector.is_assembly is not None and definition.is_assembly != selector.is_assembly:
            continue
        if selector.is_root is not None and (len(occurrence.path) == 1) != selector.is_root:
            continue
        if selector.state is not None and occurrence.state != selector.state:
            continue
        matches.append(occurrence)
    return matches


def _dot(left, right):
    return sum(a * b for a, b in zip(left, right, strict=True))


def _bbox_gap(candidate: BoundingBox, reference: BoundingBox) -> float:
    gaps = [
        max(candidate.minimum[index] - reference.maximum[index],
            reference.minimum[index] - candidate.maximum[index], 0.0)
        for index in range(3)
    ]
    return sum(value * value for value in gaps) ** 0.5


def _spatial_evidence(
    candidate: TargetCandidate,
    reference_id: str,
    reference_bbox: BoundingBox,
    constraint: SpatialConstraint,
) -> SpatialMatchEvidence | None:
    if candidate.occurrence_id == reference_id:
        return None
    if candidate.bbox is None:
        return None
    if constraint.relation == "near":
        distance = _bbox_gap(candidate.bbox, reference_bbox)
        if distance > constraint.max_distance_mm + constraint.tolerance_mm:
            return None
        return SpatialMatchEvidence(
            relation=constraint.relation,
            reference_occurrence_id=reference_id,
            distance_mm=distance,
            frame=constraint.frame,
            method="world_bbox_gap",
        )
    normal, right, up = camera_basis(constraint.frame)
    axis = {
        "left_of": right,
        "right_of": right,
        "above": up,
        "below": up,
        "in_front_of": normal,
        "behind": normal,
    }[constraint.relation]
    candidate_coordinate = _dot(candidate.bbox.center, axis)
    reference_coordinate = _dot(reference_bbox.center, axis)
    positive = constraint.relation in {"right_of", "above", "in_front_of"}
    delta = candidate_coordinate - reference_coordinate
    if (positive and delta <= constraint.tolerance_mm) or (
        not positive and delta >= -constraint.tolerance_mm
    ):
        return None
    return SpatialMatchEvidence(
        relation=constraint.relation,
        reference_occurrence_id=reference_id,
        candidate_coordinate=candidate_coordinate,
        reference_coordinate=reference_coordinate,
        frame=constraint.frame,
        method="world_bbox_center_projection",
    )


def _assembly_reference(snapshot: ModelSnapshot, selector: TargetSelector):
    """Return the unique virtual whole-assembly reference requested by is_root alone."""
    ordinary_fields = (
        selector.occurrence_id, selector.path, selector.name, selector.name_contains,
        selector.name_contains_any, selector.definition_id, selector.is_assembly, selector.state,
    )
    if selector.is_root is not True or selector.spatial or any(
        value is not None for value in ordinary_fields
    ):
        return None
    roots = [
        item for item in snapshot.assembly.occurrences
        if item.occurrence_id in snapshot.assembly.root_occurrence_ids
    ]
    candidates = [target_candidate(snapshot, item) for item in roots]
    measurable = [item.bbox for item in candidates if item.bbox is not None]
    if not measurable or len(measurable) != len(candidates):
        return "assembly:root", None, candidates
    minimum = [min(box.minimum[index] for box in measurable) for index in range(3)]
    maximum = [max(box.maximum[index] for box in measurable) for index in range(3)]
    bbox = BoundingBox(
        minimum=minimum,
        maximum=maximum,
        extents=[high - low for low, high in zip(minimum, maximum, strict=True)],
        center=[(low + high) / 2.0 for low, high in zip(minimum, maximum, strict=True)],
    )
    return "assembly:root", bbox, candidates


def resolve_target(snapshot: ModelSnapshot, selector: TargetSelector) -> TargetResolution:
    """Resolve occurrence candidates without choosing among ambiguous matches."""

    diagnostics = list(snapshot.diagnostics)
    if snapshot.status == "failed":
        resolution = TargetResolution(
            resolution_id="0" * 64,
            status="failed",
            complete=False,
            discovery=snapshot.entity_discovery,
            selector=selector,
            candidate_total=0,
            candidates=[],
            diagnostics=diagnostics,
        )
        return resolution.model_copy(
            update={
                "resolution_id": structured_hash(
                    "target-resolution", resolution, exclude={"resolution_id"}
                )
            }
        )
    if snapshot.drawing is not None or snapshot.assembly is None:
        raise ValueError("Target resolution requires a STEP assembly-profile snapshot")

    matches = _declared_matches(snapshot, selector)
    candidates = [target_candidate(snapshot, item) for item in matches]
    candidate_geometry_incomplete = any(
        candidate.geometry_diagnostic is not None for candidate in candidates
    )
    for candidate in candidates:
        if candidate.geometry_diagnostic:
            diagnostics.append(
                Diagnostic(
                    code="TARGET_GEOMETRY_UNAVAILABLE",
                    severity="warning",
                    stage="measure",
                    message=candidate.geometry_diagnostic,
                    scope_refs=["target_resolution"],
                    affects=["target_geometry"],
                    impact="partial",
                    discovery_impact="none",
                    entity_refs=[candidate.occurrence_id],
                )
            )
    spatial_failed = False
    for constraint in selector.spatial:
        assembly_reference = _assembly_reference(snapshot, constraint.reference)
        reference_matches = []
        if assembly_reference is not None:
            reference_id, reference_bbox, reference_matches = assembly_reference
        else:
            reference_matches = _declared_matches(snapshot, constraint.reference)
            if len(reference_matches) != 1:
                ambiguous = bool(reference_matches)
                diagnostics.append(Diagnostic(
                    code=(
                        "SPATIAL_REFERENCE_AMBIGUOUS" if ambiguous
                        else "SPATIAL_REFERENCE_UNRESOLVED"
                    ),
                    severity="warning",
                    stage="measure",
                    message=(
                        "A spatial relation requires exactly one discovered reference occurrence; "
                        f"found {len(reference_matches)}"
                    ),
                    scope_refs=["target_resolution"],
                    affects=["target_resolution"],
                    impact="partial",
                    entity_refs=[item.occurrence_id for item in reference_matches],
                ))
                candidates = []
                spatial_failed = True
                break
            reference = target_candidate(snapshot, reference_matches[0])
            reference_id = reference.occurrence_id
            reference_bbox = reference.bbox
        if reference_bbox is None:
            diagnostics.append(Diagnostic(
                code="SPATIAL_REFERENCE_GEOMETRY_UNAVAILABLE",
                severity="warning",
                stage="measure",
                message="Spatial reference bounding box is unavailable",
                scope_refs=["target_resolution"],
                affects=["target_resolution"],
                impact="partial",
                entity_refs=[item.occurrence_id for item in reference_matches],
            ))
            candidates = []
            spatial_failed = True
            break
        filtered = []
        for candidate in candidates:
            evidence = _spatial_evidence(
                candidate, reference_id, reference_bbox, constraint
            )
            if evidence is None:
                continue
            existing = candidate.spatial_evidence or []
            filtered.append(candidate.model_copy(update={
                "spatial_evidence": [*existing, evidence]
            }))
        candidates = filtered

    status = "resolved" if len(candidates) == 1 else "ambiguous" if candidates else "unresolved"
    complete = (
        not spatial_failed
        and not candidate_geometry_incomplete
        and snapshot.entity_discovery == "complete"
    )
    resolution = TargetResolution(
        resolution_id="0" * 64,
        status=status,
        complete=complete,
        discovery=snapshot.entity_discovery,
        selector=selector,
        candidate_total=len(candidates),
        candidates=candidates,
        resolved_target=candidates[0] if status == "resolved" else None,
        diagnostics=diagnostics,
    )
    return resolution.model_copy(
        update={
            "resolution_id": structured_hash(
                "target-resolution", resolution, exclude={"resolution_id"}
            )
        }
    )
