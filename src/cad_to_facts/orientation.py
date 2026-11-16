"""Explicit, heuristic model-orientation candidates; never source-declared front evidence."""

from cad_to_facts.domain.orientation import (
    OrientationCandidate,
    OrientationPolicy,
    OrientationReference,
    OrientationReport,
)
from cad_to_facts.domain.snapshot import Diagnostic, ModelSnapshot
from cad_to_facts.domain.view import (
    CameraSpecification,
    SemanticViewIntent,
    TargetCandidate,
    TargetSelector,
    ViewSpecification,
)
from cad_to_facts.frames import camera_basis
from cad_to_facts.identity import structured_hash
from cad_to_facts.resolution import resolve_target, target_candidate


_PRESETS = ("front", "back", "left", "right", "top", "bottom")


def _finish(report: OrientationReport) -> OrientationReport:
    return report.model_copy(update={
        "orientation_id": structured_hash("orientation", report, exclude={"orientation_id"})
    })


def _diagnostic(code: str, message: str, occurrence_id: str) -> Diagnostic:
    return Diagnostic(
        code=code,
        severity="warning",
        stage="measure",
        message=message,
        scope_refs=["orientation"],
        affects=["orientation"],
        impact="partial",
        entity_refs=[occurrence_id],
    )


def _reference(snapshot: ModelSnapshot) -> tuple[OrientationReference | None, list[TargetCandidate]]:
    roots = [
        item for item in snapshot.assembly.occurrences
        if item.occurrence_id in snapshot.assembly.root_occurrence_ids
    ]
    targets = [target_candidate(snapshot, item) for item in roots]
    measurable = [item for item in targets if item.bbox is not None]
    if len(measurable) != len(targets) or not measurable:
        return None, targets
    minimum = [min(item.bbox.minimum[index] for item in measurable) for index in range(3)]
    maximum = [max(item.bbox.maximum[index] for item in measurable) for index in range(3)]
    return OrientationReference(
        minimum=minimum,
        maximum=maximum,
        center=[(low + high) / 2.0 for low, high in zip(minimum, maximum, strict=True)],
    ), targets


def _candidate(target: TargetCandidate, reference: OrientationReference, preset: str):
    camera = CameraSpecification(preset=preset)
    normal, right, up = camera_basis(camera)
    extents = target.bbox.extents
    width = sum(value * abs(axis) for value, axis in zip(extents, right, strict=True))
    height = sum(value * abs(axis) for value, axis in zip(extents, up, strict=True))
    depth = sum(value * abs(axis) for value, axis in zip(extents, normal, strict=True))
    axis_index = max(range(3), key=lambda index: abs(normal[index]))
    return OrientationCandidate(
        camera=camera,
        axis="XYZ"[axis_index],
        projected_width_mm=width,
        projected_height_mm=height,
        projected_area_mm2=width * height,
        depth_mm=depth,
        center_offset_mm=target.bbox.center[axis_index] - reference.center[axis_index],
    )


def infer_orientation(
    snapshot: ModelSnapshot,
    selector: TargetSelector,
    policy: OrientationPolicy | None = None,
) -> OrientationReport:
    policy = policy or OrientationPolicy()
    resolution = resolve_target(snapshot, selector)
    if resolution.status != "resolved":
        return _finish(OrientationReport(
            orientation_id="0" * 64,
            status=resolution.status,
            complete=False if resolution.status == "failed" else resolution.complete,
            semantic_status="unresolved",
            policy=policy,
            target=resolution.resolved_target,
            candidates=[],
            diagnostics=resolution.diagnostics,
        ))
    target = resolution.resolved_target
    assert target is not None and target.bbox is not None
    reference, roots = _reference(snapshot)
    diagnostics = list(resolution.diagnostics)
    if reference is None:
        diagnostics.append(_diagnostic(
            "ORIENTATION_ASSEMBLY_REFERENCE_UNAVAILABLE",
            "A measurable root-occurrence bounding box is required for the outward heuristic",
            target.occurrence_id,
        ))
        return _finish(OrientationReport(
            orientation_id="0" * 64,
            status="unresolved",
            complete=False,
            semantic_status="unresolved",
            policy=policy,
            target=target,
            candidates=[],
            diagnostics=diagnostics,
        ))
    candidates = [_candidate(target, reference, preset) for preset in _PRESETS]
    axis_areas = {
        axis: max(item.projected_area_mm2 for item in candidates if item.axis == axis)
        for axis in "XYZ"
    }
    best_axis = max("XYZ", key=lambda axis: axis_areas[axis])
    best_area = axis_areas[best_axis]
    tolerance = policy.axis_absolute_tolerance_mm2 + policy.axis_relative_tolerance * best_area
    tied_axes = [axis for axis in "XYZ" if best_area - axis_areas[axis] <= tolerance]
    if len(tied_axes) != 1:
        diagnostics.append(_diagnostic(
            "ORIENTATION_AXIS_AMBIGUOUS",
            f"Largest projected bounding-box face is not unique across axes: {tied_axes}",
            target.occurrence_id,
        ))
        return _finish(OrientationReport(
            orientation_id="0" * 64,
            status="ambiguous",
            complete=resolution.complete,
            semantic_status="unresolved",
            policy=policy,
            target=target,
            assembly_reference=reference,
            candidates=candidates,
            diagnostics=diagnostics,
        ))
    axis_index = "XYZ".index(best_axis)
    center_offset = next(
        item.center_offset_mm for item in candidates if item.axis == best_axis
    )
    selected = None
    if abs(center_offset) > policy.outward_tolerance_mm:
        selected = next(
            item for item in candidates
            if item.axis == best_axis
            and camera_basis(item.camera)[0][axis_index] * center_offset > 0
        )
    if selected is None:
        diagnostics.append(_diagnostic(
            "ORIENTATION_OUTWARD_DIRECTION_AMBIGUOUS",
            "The target center is too close to the assembly reference center on the selected axis",
            target.occurrence_id,
        ))
        return _finish(OrientationReport(
            orientation_id="0" * 64,
            status="ambiguous",
            complete=resolution.complete,
            semantic_status="unresolved",
            policy=policy,
            target=target,
            assembly_reference=reference,
            candidates=candidates,
            diagnostics=diagnostics,
        ))
    view = ViewSpecification(
        title=f"Assumed {policy.semantic_label}: large face outward from assembly",
        camera=selected.camera,
        semantic_intent=SemanticViewIntent(
            label=policy.semantic_label,
            basis="assumed",
            note=(
                "Heuristic: unique largest target world-bbox projected face and outward direction "
                "from the assembly bbox center; not a source declaration or functional-front proof"
            ),
        ),
    )
    return _finish(OrientationReport(
        orientation_id="0" * 64,
        status="resolved",
        complete=resolution.complete,
        semantic_status="assumed",
        policy=policy,
        target=target,
        assembly_reference=reference,
        candidates=candidates,
        selected_candidate=selected,
        recommended_view=view,
        diagnostics=diagnostics,
    ))
