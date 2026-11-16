"""Deterministic OCCT hidden-line STEP views; images are review WorkProducts."""

import html
import math

from OCP.BRepAdaptor import BRepAdaptor_Curve
from OCP.GCPnts import GCPnts_QuasiUniformDeflection
from OCP.gp import gp_Ax2, gp_Dir, gp_Pnt
from OCP.HLRAlgo import HLRAlgo_Projector
from OCP.HLRBRep import HLRBRep_Algo, HLRBRep_HLRToShape
from OCP.TopAbs import TopAbs_EDGE
from OCP.TopExp import TopExp_Explorer
from OCP.TopoDS import TopoDS

from cad_to_facts.domain.snapshot import Diagnostic, ModelSnapshot
from cad_to_facts.domain.view import (
    CameraSpecification,
    ImageSpecification,
    RenderStats,
    TargetCandidate,
    ViewSpecification,
)
from cad_to_facts.frames import camera_basis
from cad_to_facts.resolution import target_candidate


def _camera_frame(camera: CameraSpecification) -> gp_Ax2:
    try:
        normal, right, _ = camera_basis(camera)
        return gp_Ax2(gp_Pnt(0.0, 0.0, 0.0), gp_Dir(*normal), gp_Dir(*right))
    except Exception as error:
        raise ValueError("Camera normal/right must be nonzero and non-parallel") from error


def _points(edge, deflection: float) -> list[tuple[float, float]]:
    curve = BRepAdaptor_Curve(TopoDS.Edge(edge))
    discretized = GCPnts_QuasiUniformDeflection(curve, deflection)
    if discretized.IsDone() and discretized.NbPoints() >= 2:
        values = [discretized.Value(index) for index in range(1, discretized.NbPoints() + 1)]
    else:
        values = [curve.Value(curve.FirstParameter()), curve.Value(curve.LastParameter())]
    points = [(point.X(), point.Y()) for point in values]
    if len(points) < 2 or any(not math.isfinite(value) for point in points for value in point):
        return []
    return points


def _compound_paths(compound, deflection: float, budget: int) -> tuple[list[list[tuple[float, float]]], int, int]:
    paths: list[list[tuple[float, float]]] = []
    skipped = 0
    used_points = 0
    if compound is None or compound.IsNull():
        return paths, skipped, used_points
    explorer = TopExp_Explorer(compound, TopAbs_EDGE)
    while explorer.More():
        try:
            points = _points(explorer.Current(), deflection)
        except Exception:
            points = []
        if not points:
            skipped += 1
        else:
            if used_points + len(points) > budget:
                raise ValueError("STEP view exceeds the configured max_points budget")
            paths.append(points)
            used_points += len(points)
        explorer.Next()
    return paths, skipped, used_points


def _number(value: float) -> str:
    text = f"{value:.6f}".rstrip("0").rstrip(".")
    return "0" if text in {"-0", ""} else text


def _path_data(points: list[tuple[float, float]]) -> str:
    return " ".join(
        f"{'M' if index == 0 else 'L'}{_number(x)},{_number(y)}"
        for index, (x, y) in enumerate(points)
    )


def _svg(
    visible: list[list[tuple[float, float]]],
    hidden: list[list[tuple[float, float]]],
    image: ImageSpecification,
    title: str | None,
) -> tuple[str, list[float]]:
    all_points = [point for path in [*visible, *hidden] for point in path]
    if not all_points:
        raise ValueError("STEP view produced no drawable projected edges")
    min_x = min(point[0] for point in all_points)
    max_x = max(point[0] for point in all_points)
    min_y = min(point[1] for point in all_points)
    max_y = max(point[1] for point in all_points)
    delta_x = max_x - min_x
    delta_y = max_y - min_y
    available_x = image.width - 2 * image.padding
    available_y = image.height - 2 * image.padding
    scales = []
    if delta_x > 1e-12:
        scales.append(available_x / delta_x)
    if delta_y > 1e-12:
        scales.append(available_y / delta_y)
    if not scales:
        raise ValueError("STEP view projection has zero width and height")
    scale = min(scales)
    center_x = (min_x + max_x) / 2.0
    center_y = (min_y + max_y) / 2.0

    def place(path):
        return [
            (
                image.width / 2.0 + (x - center_x) * scale,
                image.height / 2.0 - (y - center_y) * scale,
            )
            for x, y in path
        ]

    title_element = f"<title>{html.escape(title)}</title>" if title else ""
    visible_paths = "".join(f'<path d="{_path_data(place(path))}"/>' for path in visible)
    hidden_paths = "".join(f'<path d="{_path_data(place(path))}"/>' for path in hidden)
    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{image.width}" '
        f'height="{image.height}" viewBox="0 0 {image.width} {image.height}" '
        'fill="none" role="img">'
        f'{title_element}<rect width="100%" height="100%" fill="white"/>'
        '<g id="hidden" stroke="#9ca3af" stroke-width="1" stroke-dasharray="5 4">'
        f'{hidden_paths}</g>'
        '<g id="visible" stroke="#111827" stroke-width="1.2">'
        f'{visible_paths}</g></svg>\n'
    )
    return svg, [delta_x, delta_y]


def render_step_svg(
    snapshot: ModelSnapshot,
    occurrence_id: str,
    view: ViewSpecification,
) -> tuple[str, TargetCandidate, RenderStats, list[Diagnostic]]:
    """Project one active occurrence into visible/hidden vector edge paths."""

    if snapshot.status == "failed" or snapshot.assembly is None:
        raise ValueError("STEP rendering requires a readable assembly-profile snapshot")
    occurrence = next(
        (item for item in snapshot.assembly.occurrences if item.occurrence_id == occurrence_id),
        None,
    )
    if occurrence is None:
        raise ValueError(f"Unknown occurrence for this snapshot: {occurrence_id}")
    if occurrence.state != "active":
        raise ValueError("STEP rendering currently requires an active occurrence")
    shape = snapshot._adapter_payload.get("occurrence_shapes", {}).get(occurrence_id)
    if shape is None or shape.IsNull():
        raise ValueError("The selected occurrence has no transferred shape to render")
    target = target_candidate(snapshot, occurrence)

    algorithm = HLRBRep_Algo()
    algorithm.Add(shape)
    algorithm.Projector(HLRAlgo_Projector(_camera_frame(view.camera)))
    algorithm.Update()
    algorithm.Hide()
    projected = HLRBRep_HLRToShape(algorithm)
    visible_paths = []
    hidden_paths = []
    skipped = 0
    used_points = 0
    for compound in (
        projected.VCompound(),
        projected.Rg1LineVCompound(),
        projected.RgNLineVCompound(),
        projected.OutLineVCompound(),
    ):
        paths, missed, count = _compound_paths(
            compound,
            view.image.curve_deflection_mm,
            view.image.max_points - used_points,
        )
        visible_paths.extend(paths)
        skipped += missed
        used_points += count
    if view.display.show_hidden_lines:
        for compound in (
            projected.HCompound(),
            projected.Rg1LineHCompound(),
            projected.RgNLineHCompound(),
            projected.OutLineHCompound(),
        ):
            paths, missed, count = _compound_paths(
                compound,
                view.image.curve_deflection_mm,
                view.image.max_points - used_points,
            )
            hidden_paths.extend(paths)
            skipped += missed
            used_points += count
    svg, extents = _svg(visible_paths, hidden_paths, view.image, view.title)
    stats = RenderStats(
        visible_edge_count=len(visible_paths),
        hidden_edge_count=len(hidden_paths),
        skipped_edge_count=skipped,
        point_count=used_points,
        projected_extents=extents,
    )
    diagnostics = list(snapshot.diagnostics)
    if skipped:
        diagnostics.append(
            Diagnostic(
                code="VIEW_EDGES_NOT_DISCRETIZED",
                severity="warning",
                stage="measure",
                message="Some projected edges could not be converted to SVG paths",
                scope_refs=["step_view_render"],
                affects=["render"],
                impact="partial",
                discovery_impact="none",
                entity_refs=[occurrence_id],
                count=skipped,
            )
        )
    return svg, target, stats, diagnostics
