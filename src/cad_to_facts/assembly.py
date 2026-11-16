"""XCAF assembly-graph extraction for the STEP adapter."""

from OCP.TCollection import TCollection_AsciiString
from OCP.TDataStd import TDataStd_Name
from OCP.TDF import TDF_ChildIterator, TDF_Label, TDF_Tool
from OCP.TDocStd import TDocStd_Document
from OCP.TopLoc import TopLoc_Location
from OCP.TopoDS import TopoDS_Shape
from OCP.XCAFDoc import XCAFDoc_DocumentTool, XCAFDoc_ShapeTool

from cad_to_facts.domain.assembly import (
    AssemblyLink,
    AssemblyStructure,
    Occurrence,
    PartDefinition,
)
from cad_to_facts.domain.snapshot import Diagnostic


def _entry(label: TDF_Label) -> str:
    value = TCollection_AsciiString()
    TDF_Tool.Entry_s(label, value)
    return value.ToCString()


def _name(label: TDF_Label) -> str | None:
    attribute = TDataStd_Name()
    if not label.FindAttribute(TDataStd_Name.GetID_s(), attribute):
        return None
    value = attribute.Get().ToExtString()
    return str(value) if value else None


def _matrix(shape_tool: XCAFDoc_ShapeTool, label: TDF_Label) -> list[float]:
    transform = shape_tool.GetLocation_s(label).Transformation()
    return [
        float(transform.Value(row, column))
        for row in range(1, 4)
        for column in range(1, 5)
    ] + [0.0, 0.0, 0.0, 1.0]


def extract_structure(
    document: TDocStd_Document,
    snapshot_id: str,
    source_product_count: int | None = None,
    source_occurrence_count: int | None = None,
    occurrence_shapes: dict[str, TopoDS_Shape] | None = None,
) -> tuple[AssemblyStructure, list[Diagnostic]]:
    """Traverse every free XCAF shape without merging repeated definitions."""

    shape_tool = XCAFDoc_DocumentTool.ShapeTool_s(document.Main())
    definitions: list[PartDefinition] = []
    occurrences: list[Occurrence] = []
    links: list[AssemblyLink] = []
    roots: list[str] = []
    diagnostics: list[Diagnostic] = []
    definition_ids: dict[str, str] = {}

    def diagnostic(code: str, message: str, native_ref: str) -> None:
        diagnostics.append(
            Diagnostic(
                code=code,
                severity="warning",
                stage="read",
                message=message,
                scope_refs=["assembly"],
                affects=["discovery", "assembly"],
                impact="partial",
                discovery_impact="partial",
                details={"native_ref": native_ref},
            )
        )

    def definition_for(label: TDF_Label) -> PartDefinition:
        native_ref = _entry(label)
        existing = definition_ids.get(native_ref)
        if existing is not None:
            return next(item for item in definitions if item.definition_id == existing)
        definition = PartDefinition(
            definition_id=f"part:{len(definitions)}",
            native_ref=native_ref,
            name=_name(label),
            is_assembly=shape_tool.IsAssembly_s(label),
        )
        definition_ids[native_ref] = definition.definition_id
        definitions.append(definition)
        return definition

    def visit(
        definition_label: TDF_Label,
        occurrence_label: TDF_Label,
        parent: Occurrence | None,
        ancestors: tuple[str, ...],
        parent_location: TopLoc_Location | None = None,
    ) -> Occurrence:
        definition = definition_for(definition_label)
        occurrence_id = f"occurrence:{len(occurrences)}"
        path = [*(parent.path if parent else []), occurrence_id]
        if occurrence_shapes is not None:
            shape = shape_tool.GetShape_s(occurrence_label)
            if parent_location is not None and not shape.IsNull():
                shape = shape.Located(parent_location.Multiplied(shape.Location()))
            occurrence_shapes[occurrence_id] = shape
        state = "active"
        if shape_tool.IsExternRef_s(definition_label):
            state = "unknown"
            diagnostic(
                "ASSEMBLY_EXTERNAL_REFERENCE",
                "An assembly occurrence refers to an external shape whose resolution is not proven",
                definition.native_ref,
            )
        occurrence = Occurrence(
            occurrence_id=occurrence_id,
            definition_id=definition.definition_id,
            parent_occurrence_id=parent.occurrence_id if parent else None,
            path=path,
            native_ref=_entry(occurrence_label),
            name=_name(occurrence_label) or definition.name,
            transformation=_matrix(shape_tool, occurrence_label),
            state=state,
        )
        occurrences.append(occurrence)
        if parent is None:
            roots.append(occurrence_id)
        else:
            links.append(
                AssemblyLink(
                    parent_occurrence_id=parent.occurrence_id,
                    child_occurrence_id=occurrence_id,
                )
            )
        if not definition.is_assembly:
            return occurrence
        if definition.native_ref in ancestors:
            diagnostic(
                "ASSEMBLY_CYCLE",
                "The assembly graph contains a cyclic definition reference; traversal stopped",
                definition.native_ref,
            )
            return occurrence
        children = TDF_ChildIterator(definition_label, False)
        while children.More():
            child = children.Value()
            children.Next()
            if not shape_tool.IsComponent_s(child):
                continue
            referred = TDF_Label()
            if not shape_tool.GetReferredShape_s(child, referred):
                diagnostic(
                    "ASSEMBLY_OCCURRENCE_UNRESOLVED",
                    "An assembly component has no resolvable referred shape",
                    _entry(child),
                )
                continue
            visit(
                referred,
                child,
                occurrence,
                (*ancestors, definition.native_ref),
                occurrence_shapes[occurrence.occurrence_id].Location()
                if occurrence_shapes is not None
                else None,
            )
        return occurrence

    shape_roots = XCAFDoc_DocumentTool.ShapesLabel_s(document.Main())
    labels = TDF_ChildIterator(shape_roots, False)
    while labels.More():
        label = labels.Value()
        labels.Next()
        if shape_tool.IsShape_s(label) and shape_tool.IsFree_s(label):
            visit(label, label, None, ())

    if not roots:
        diagnostics.append(
            Diagnostic(
                code="ASSEMBLY_ROOTS_UNKNOWN",
                severity="warning",
                stage="read",
                message="The XCAF document contains no discovered free shape roots",
                scope_refs=["assembly"],
                affects=["discovery", "assembly"],
                impact="partial",
                discovery_impact="unknown",
            )
        )
    if source_product_count is not None and source_product_count != len(definitions):
        diagnostics.append(
            Diagnostic(
                code="ASSEMBLY_DEFINITION_RECONCILIATION",
                severity="warning",
                stage="read",
                message=(
                    "The XCAF definition count differs from the STEP PRODUCT count; "
                    "definition grouping requires independent reconciliation"
                ),
                scope_refs=["assembly"],
                affects=["discovery", "assembly"],
                impact="partial",
                discovery_impact="partial",
                details={
                    "source_product_count": source_product_count,
                    "xcaf_definition_count": len(definitions),
                },
            )
        )
    if source_occurrence_count is not None and source_occurrence_count != len(links):
        diagnostics.append(
            Diagnostic(
                code="ASSEMBLY_OCCURRENCE_RECONCILIATION",
                severity="warning",
                stage="read",
                message=(
                    "The XCAF component count differs from the STEP assembly-usage count; "
                    "occurrence quantities are not proven complete"
                ),
                scope_refs=["assembly"],
                affects=["discovery", "assembly"],
                impact="partial",
                discovery_impact="partial",
                details={
                    "source_occurrence_count": source_occurrence_count,
                    "xcaf_component_count": len(links),
                },
            )
        )
    structure = AssemblyStructure(
        snapshot_id=snapshot_id,
        discovery="partial" if diagnostics else "complete",
        root_occurrence_ids=roots,
        source_product_count=source_product_count,
        source_occurrence_count=source_occurrence_count,
        definitions=definitions,
        occurrences=occurrences,
        links=links,
    )
    if not roots:
        structure = structure.model_copy(update={"discovery": "unknown"})
    return structure, diagnostics
