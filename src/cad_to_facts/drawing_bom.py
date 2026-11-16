"""Explicit attribute-block BOM extraction, separate from STEP assembly BOM."""

from collections import defaultdict

from cad_to_facts import __version__
from cad_to_facts.contract import verify_snapshot_identity
from cad_to_facts.domain.drawing_bom import (
    DrawingBOMCoverage,
    DrawingBOMExtract,
    DrawingBOMLineItem,
    DrawingBOMMissingInput,
    DrawingBOMOccurrence,
    DrawingBOMOptions,
)
from cad_to_facts.domain.snapshot import Diagnostic, ModelSnapshot
from cad_to_facts.identity import structured_hash


def _diagnostic(code: str, message: str, *, discovery: str = "none") -> Diagnostic:
    return Diagnostic(
        code=code,
        severity="warning",
        stage="translate",
        message=message,
        scope_refs=["drawing"],
        affects=["bom"],
        impact="partial",
        discovery_impact=discovery,
    )


def extract_drawing_bom(
    snapshot: ModelSnapshot, options: DrawingBOMOptions
) -> DrawingBOMExtract:
    snapshot = verify_snapshot_identity(snapshot)
    if snapshot.drawing is None:
        raise ValueError("drawing-bom requires a DWG/DXF snapshot")
    part_tag = options.part_tag.upper()
    quantity_tag = options.quantity_tag.upper() if options.quantity_tag else None
    material_tag = options.material_tag.upper() if options.material_tag else None
    description_tag = options.description_tag.upper() if options.description_tag else None
    property_tags = {
        tag
        for tag in (part_tag, material_tag, description_tag)
        if tag is not None
    }
    required_tags = {part_tag, *(tag.upper() for tag in options.required_tags)}
    if quantity_tag:
        required_tags.add(quantity_tag)
    containers = set(options.containers)
    xref_blocks = {block.name for block in snapshot.drawing.blocks if block.is_xref}
    diagnostics = list(snapshot.diagnostics)
    missing: list[DrawingBOMMissingInput] = []
    occurrences: list[DrawingBOMOccurrence] = []
    quantity_by_entity: dict[str, int | None] = {}

    def add_missing(entity_id: str, field: str, reason: str, message: str) -> None:
        missing.append(DrawingBOMMissingInput(
            subject_id=entity_id, field=field, reason_code=reason, message=message
        ))

    for entity in snapshot.entities:
        values = {item["type"]: item["value"] for item in entity.native_refs}
        if entity.entity_kind not in {"insert", "minsert"} or values.get("container") not in containers:
            continue
        item = snapshot._adapter_payload["entities"][entity.entity_id]["entity"]
        if item.dxf.name in xref_blocks:
            # The XREF attachment is not itself a part occurrence. Linked/flattened
            # reference coverage accounts for its inclusion or explicit exclusion.
            continue
        attributes: dict[str, list[str]] = defaultdict(list)
        for attribute in getattr(item, "attribs", ()):
            attributes[attribute.dxf.tag.upper()].append(attribute.dxf.text)
        properties: dict[str, str] = {}
        ambiguous: set[str] = set()
        for tag in property_tags | required_tags:
            values_for_tag = attributes.get(tag, [])
            if len(set(values_for_tag)) == 1:
                properties[tag] = values_for_tag[0]
            elif values_for_tag:
                ambiguous.add(tag)
                add_missing(entity.entity_id, tag, "AMBIGUOUS", "Conflicting values for one attribute tag")
        for tag in sorted(required_tags):
            value = properties.get(tag, "").strip()
            if not value and tag not in ambiguous:
                add_missing(entity.entity_id, tag, "ABSENT", "Required block attribute is absent or empty")
        part_number = properties.get(part_tag, "").strip() or None
        instance_count = int(getattr(item, "mcount", 1))
        row_count = int(item.dxf.get("row_count", 1))
        column_count = int(item.dxf.get("column_count", 1))
        ambiguous_spacing = (
            row_count > 1 and float(item.dxf.get("row_spacing", 0)) == 0
        ) or (
            column_count > 1 and float(item.dxf.get("column_spacing", 0)) == 0
        )
        quantity: int | None = instance_count
        if (instance_count < 1 or ambiguous_spacing) and not quantity_tag:
            quantity = None
            add_missing(
                entity.entity_id,
                "instance_count",
                "INVALID",
                "MINSERT instance count is non-positive or has ambiguous zero spacing",
            )
        if quantity_tag:
            raw = properties.get(quantity_tag, "").strip()
            if not raw:
                quantity = None
            else:
                try:
                    quantity = int(raw)
                    if quantity < 1 or raw != str(quantity):
                        raise ValueError
                except ValueError:
                    quantity = None
                    add_missing(
                        entity.entity_id,
                        quantity_tag,
                        "INVALID",
                        "Declared quantity must be a canonical positive integer",
                    )
        if part_number is None:
            quantity = None
        quantity_by_entity[entity.entity_id] = quantity
        occurrences.append(DrawingBOMOccurrence(
            entity_id=entity.entity_id,
            artifact_sha256=snapshot._adapter_payload["entities"][entity.entity_id].get(
                "artifact_sha256", snapshot.artifact_sha256
            ),
            block_name=item.dxf.name,
            part_number=part_number,
            declared_properties=properties,
            declared_quantity=quantity if quantity_tag and quantity is not None else None,
            instance_count=instance_count,
        ))

    groups: dict[str, list[DrawingBOMOccurrence]] = defaultdict(list)
    for occurrence in occurrences:
        key = occurrence.part_number if occurrence.part_number is not None else f"unknown:{occurrence.entity_id}"
        groups[key].append(occurrence)
    line_items: list[DrawingBOMLineItem] = []
    for key in sorted(groups):
        group = groups[key]
        properties: dict[str, str] = {}
        conflicts: list[str] = []
        for tag in sorted(property_tags):
            values = [item.declared_properties.get(tag) for item in group]
            present = {value for value in values if value is not None}
            if len(present) > 1:
                conflicts.append(tag)
            elif len(present) == 1 and all(value is not None for value in values):
                properties[tag] = present.pop()
        refs = [item.entity_id for item in group]
        counted = [item.entity_id for item in group if quantity_by_entity[item.entity_id] is not None]
        if len(counted) == len(refs):
            quantity: int | None = sum(quantity_by_entity[ref] for ref in refs)
            quantity_state = "known" if snapshot.entity_discovery == "complete" else "observed"
        else:
            quantity = None
            quantity_state = "unknown"
        if conflicts:
            diagnostics.append(_diagnostic(
                "BOM_PROPERTY_CONFLICT",
                f"{key}: conflicting declared properties: {', '.join(conflicts)}",
            ))
        line = DrawingBOMLineItem(
            line_item_id="0" * 64,
            part_number=group[0].part_number,
            block_names=sorted({item.block_name for item in group}),
            source_artifact_sha256s=sorted({item.artifact_sha256 for item in group}),
            declared_properties=properties,
            property_conflicts=conflicts,
            quantity=quantity,
            quantity_state=quantity_state,
            occurrence_refs=refs,
            counted_occurrence_refs=counted,
        )
        line_items.append(line.model_copy(update={
            "line_item_id": structured_hash("drawing-bom-line", line, exclude={"line_item_id"})
        }))
    if not line_items:
        diagnostics.append(_diagnostic(
            "BOM_EMPTY", "No INSERT/MINSERT occurrences matched the configured containers"
        ))
    for item in missing:
        diagnostics.append(_diagnostic(
            "BOM_REQUIRED_PROPERTY_MISSING", f"{item.subject_id}: {item.message} ({item.field})"
        ))
    referenced_sources = {item.artifact_sha256 for item in occurrences}
    references = snapshot.drawing.external_references
    counted_references = sum(
        reference.state == "resolved"
        and reference.artifact is not None
        and reference.artifact.sha256 in referenced_sources
        for reference in references
    )
    uncounted_references = len(references) - counted_references
    coverage = DrawingBOMCoverage(
        definition_total=len(line_items),
        occurrence_total=len(occurrences),
        counted_occurrence_total=sum(len(item.counted_occurrence_refs) for item in line_items),
        unknown_quantity_definition_total=sum(item.quantity_state == "unknown" for item in line_items),
        observed_quantity_definition_total=sum(item.quantity_state == "observed" for item in line_items),
        known_quantity_definition_total=sum(item.quantity_state == "known" for item in line_items),
        external_reference_total=len(references),
        counted_external_reference_total=counted_references,
        uncounted_external_reference_total=uncounted_references,
        structure_discovery=snapshot.entity_discovery,
    )
    if uncounted_references:
        diagnostics.append(Diagnostic(
            code="BOM_EXTERNAL_REFERENCE_EXCLUDED",
            severity="info" if options.allow_external_reference_exclusion else "warning",
            stage="translate",
            message=(
                f"{uncounted_references} external references have no occurrences in the BOM scope; "
                + ("their exclusion was explicitly accepted" if options.allow_external_reference_exclusion else "exclude them explicitly or include their containers")
            ),
            scope_refs=["drawing"],
            affects=["bom"],
            impact="partial",
            discovery_impact="none",
            disposition="resolved" if options.allow_external_reference_exclusion else "open",
            count=uncounted_references,
        ))
    blocking = any(
        item.disposition != "resolved" and (item.discovery_impact != "none" or "bom" in item.affects)
        for item in diagnostics
    )
    complete = bool(
        line_items
        and not missing
        and not any(item.property_conflicts or item.part_number is None for item in line_items)
        and coverage.unknown_quantity_definition_total == 0
        and snapshot.entity_discovery == "complete"
        and (uncounted_references == 0 or options.allow_external_reference_exclusion)
        and not blocking
    )
    bom = DrawingBOMExtract(
        bom_id="0" * 64,
        artifact_sha256=snapshot.artifact_sha256,
        snapshot_id=snapshot.snapshot_id,
        snapshot_content_hash=snapshot.snapshot_content_hash,
        extractor_version=__version__,
        options=options,
        line_items=line_items,
        occurrences=occurrences,
        missing_inputs=missing,
        coverage=coverage,
        diagnostics=diagnostics,
        complete=complete,
    )
    return bom.model_copy(update={
        "bom_id": structured_hash("drawing-bom-extract", bom, exclude={"bom_id"})
    })
