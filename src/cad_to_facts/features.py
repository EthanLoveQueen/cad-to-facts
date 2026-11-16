"""Bounded semantic-feature candidates and conservative analytic through-hole recognition."""

import math

from OCP.BRepAdaptor import BRepAdaptor_Curve, BRepAdaptor_Surface
from OCP.BRepGProp import BRepGProp
from OCP.GeomAbs import GeomAbs_Circle, GeomAbs_Cylinder, GeomAbs_Plane
from OCP.GProp import GProp_GProps
from OCP.TopAbs import TopAbs_EDGE, TopAbs_FACE, TopAbs_REVERSED
from OCP.TopExp import TopExp_Explorer
from OCP.TopoDS import TopoDS

from cad_to_facts.domain.feature import (
    FeatureCandidate,
    FeatureGap,
    FeatureQuery,
    FeatureRecognitionReport,
    ThroughHoleGeometry,
)
from cad_to_facts.domain.snapshot import Diagnostic, ModelSnapshot
from cad_to_facts.identity import structured_hash
from cad_to_facts.resolution import resolve_target, target_candidate


_DEFAULT_ALIASES = {
    "door": ("door", "门"),
    "window": ("window", "窗"),
    "hole": ("hole", "孔"),
}


def _items(explorer):
    while explorer.More():
        yield explorer.Current()
        explorer.Next()


def _parallel(left, right, tolerance=1e-7):
    dot = abs(sum(a * b for a, b in zip(left, right, strict=True)))
    left_length = math.sqrt(sum(value * value for value in left))
    right_length = math.sqrt(sum(value * value for value in right))
    return left_length > 0 and right_length > 0 and abs(dot / (left_length * right_length) - 1.0) <= tolerance


def _through_holes(shape, occurrence_id: str) -> list[ThroughHoleGeometry]:
    """Recognize only full internal cylinders with two open planar endpoints."""

    shape_faces = [
        TopoDS.Face(item) for item in _items(TopExp_Explorer(shape, TopAbs_FACE))
    ]
    face_edges = [
        [TopoDS.Edge(edge) for edge in _items(TopExp_Explorer(face, TopAbs_EDGE))]
        for face in shape_faces
    ]
    holes = []
    face_explorer = TopExp_Explorer(shape, TopAbs_FACE)
    face_index = 0
    while face_explorer.More():
        face = TopoDS.Face(face_explorer.Current())
        surface = BRepAdaptor_Surface(face)
        if surface.GetType() != GeomAbs_Cylinder or face.Orientation() != TopAbs_REVERSED:
            face_index += 1
            face_explorer.Next()
            continue
        cylinder = surface.Cylinder()
        radius = cylinder.Radius()
        axis_direction = cylinder.Axis().Direction()
        axis = [axis_direction.X(), axis_direction.Y(), axis_direction.Z()]
        properties = GProp_GProps()
        BRepGProp.SurfaceProperties_s(face, properties)
        area = properties.Mass()
        circles = []
        endpoint_planes = []
        for edge_shape in _items(TopExp_Explorer(face, TopAbs_EDGE)):
            edge = TopoDS.Edge(edge_shape)
            curve = BRepAdaptor_Curve(edge)
            if curve.GetType() != GeomAbs_Circle:
                continue
            adjacent_faces = [
                other
                for other, other_edges in zip(shape_faces, face_edges, strict=True)
                if any(edge.IsSame(other_edge) for other_edge in other_edges)
            ]
            if len(adjacent_faces) != 2:
                circles = []
                break
            other_shape = adjacent_faces[0] if not adjacent_faces[0].IsSame(face) else adjacent_faces[1]
            other_face = TopoDS.Face(other_shape)
            other_surface = BRepAdaptor_Surface(other_face)
            if other_surface.GetType() != GeomAbs_Plane:
                circles = []
                break
            plane_direction = other_surface.Plane().Axis().Direction()
            plane_normal = [plane_direction.X(), plane_direction.Y(), plane_direction.Z()]
            if not _parallel(axis, plane_normal):
                circles = []
                break
            circle = curve.Circle()
            if abs(circle.Radius() - radius) > 1e-6:
                circles = []
                break
            location = circle.Location()
            circles.append((location.X(), location.Y(), location.Z()))
            endpoint_planes.append(other_face)
        if len(circles) != 2 or circles[0] == circles[1]:
            face_index += 1
            face_explorer.Next()
            continue
        length = math.sqrt(sum((a - b) ** 2 for a, b in zip(circles[0], circles[1], strict=True)))
        if (
            radius <= 0
            or length <= 1e-7
            or not math.isclose(area, 2.0 * math.pi * radius * length, rel_tol=1e-6, abs_tol=1e-7)
            or not math.isclose(
                abs((surface.LastUParameter() - surface.FirstUParameter()) / (2.0 * math.pi)),
                1.0,
                rel_tol=0.0,
                abs_tol=1e-6,
            )
        ):
            face_index += 1
            face_explorer.Next()
            continue
        center = [(a + b) / 2.0 for a, b in zip(circles[0], circles[1], strict=True)]
        holes.append(ThroughHoleGeometry(
            face_ref=f"{occurrence_id}/face:{face_index}",
            radius_mm=radius,
            length_mm=length,
            axis=axis,
            area_mm2=area,
            center=center,
        ))
        face_index += 1
        face_explorer.Next()
    return holes


def _name_candidates(targets, query: FeatureQuery) -> list[FeatureCandidate]:
    candidates = []
    for target in targets:
        names = [value for value in (target.name, target.definition_name) if value]
        for kind in query.kinds:
            aliases = [*_DEFAULT_ALIASES[kind], *query.additional_aliases.get(kind, [])]
            matches = [
                (alias, text)
                for alias in aliases
                for text in names
                if alias.casefold() in text.casefold()
            ]
            if not matches:
                continue
            alias, text = matches[0]
            candidates.append(FeatureCandidate(
                feature_id="",
                kind=kind,
                target=target,
                validation="unvalidated",
                recognition_method="declared_name_alias",
                matched_alias=alias,
                matched_text=text,
            ))
    return candidates


def recognize_features(
    snapshot: ModelSnapshot, query: FeatureQuery
) -> FeatureRecognitionReport:
    counts = {kind: 0 for kind in query.kinds}
    validated_counts = {kind: 0 for kind in query.kinds}
    gaps = []
    if snapshot.status == "failed" or snapshot.assembly is None:
        diagnostics = list(snapshot.diagnostics)
        if snapshot.status != "failed":
            diagnostics.append(Diagnostic(
                code="FEATURE_ASSEMBLY_PROFILE_REQUIRED",
                severity="error",
                stage="read",
                message="Feature recognition requires a STEP assembly-profile snapshot",
                scope_refs=["feature_recognition"],
                affects=["feature_recognition"],
                impact="fatal",
            ))
        report = FeatureRecognitionReport(
            feature_recognition_id="0" * 64,
            status="failed",
            complete=False,
            discovery=snapshot.entity_discovery,
            query=query,
            candidate_total=0,
            validated_total=0,
            candidate_counts=counts,
            validated_counts=validated_counts,
            candidates=[],
            gaps=gaps,
            diagnostics=diagnostics,
        )
        return report.model_copy(update={
            "feature_recognition_id": structured_hash(
                "feature-recognition", report, exclude={"feature_recognition_id"}
            )
        })

    if query.selector is None:
        targets = [target_candidate(snapshot, item) for item in snapshot.assembly.occurrences]
        diagnostics = list(snapshot.diagnostics)
        selection_complete = snapshot.entity_discovery == "complete"
    else:
        resolution = resolve_target(snapshot, query.selector)
        targets = resolution.candidates
        diagnostics = resolution.diagnostics
        selection_complete = resolution.complete
    candidates = []
    if "declared_name_alias" in query.recognition_methods:
        candidates.extend(_name_candidates(targets, query))
    shape_failures = []
    if "hole" in query.kinds and "occt_full_cylinder_open_endpoints" in query.recognition_methods:
        for target in targets:
            if target.is_assembly or target.state != "active":
                continue
            shape = snapshot._adapter_payload.get("occurrence_shapes", {}).get(target.occurrence_id)
            if shape is None or shape.IsNull():
                shape_failures.append(target.occurrence_id)
                continue
            try:
                holes = _through_holes(shape, target.occurrence_id)
            except Exception:
                shape_failures.append(target.occurrence_id)
                continue
            for geometry in holes:
                candidates.append(FeatureCandidate(
                    feature_id="",
                    kind="hole",
                    target=target,
                    validation="validated",
                    recognition_method="occt_full_cylinder_open_endpoints",
                    geometry=geometry,
                ))
    for index, candidate in enumerate(candidates):
        candidates[index] = candidate.model_copy(update={"feature_id": f"feature:{index}"})
    for candidate in candidates:
        counts[candidate.kind] += 1
        if candidate.validation == "validated":
            validated_counts[candidate.kind] += 1
    if "door" in query.kinds:
        gaps.append(FeatureGap(
            code="DOOR_GEOMETRY_VALIDATION_UNSUPPORTED",
            kind="door",
            message="Door names produce candidates only; general geometric door validation is unsupported",
        ))
    if "window" in query.kinds:
        gaps.append(FeatureGap(
            code="WINDOW_GEOMETRY_VALIDATION_UNSUPPORTED",
            kind="window",
            message="Window names produce candidates only; general geometric window validation is unsupported",
        ))
    if "hole" in query.kinds:
        gaps.append(FeatureGap(
            code="GENERAL_HOLE_RECOGNITION_UNSUPPORTED",
            kind="hole",
            message=(
                "Only conservative full cylindrical through holes are validated; blind, counterbored, "
                "rectangular, intersecting and other holes remain outside recognition coverage"
            ),
        ))
    if snapshot.entity_discovery != "complete":
        gaps.append(FeatureGap(
            code="FEATURE_DISCOVERY_INCOMPLETE",
            message="Assembly discovery is not complete; discovered feature counts are not complete quantities",
        ))
    if shape_failures:
        gaps.append(FeatureGap(
            code="FEATURE_SHAPE_UNAVAILABLE",
            kind="hole",
            message="Some selected leaf occurrence shapes could not be inspected for through holes",
            occurrence_ids=shape_failures,
        ))
    complete = selection_complete and not shape_failures
    status = "ready" if complete else "partial"
    report = FeatureRecognitionReport(
        feature_recognition_id="0" * 64,
        status=status,
        complete=complete,
        discovery=snapshot.entity_discovery,
        query=query,
        candidate_total=len(candidates),
        validated_total=sum(validated_counts.values()),
        candidate_counts=counts,
        validated_counts=validated_counts,
        candidates=candidates,
        gaps=gaps,
        diagnostics=diagnostics,
    )
    return report.model_copy(update={
        "feature_recognition_id": structured_hash(
            "feature-recognition", report, exclude={"feature_recognition_id"}
        )
    })
