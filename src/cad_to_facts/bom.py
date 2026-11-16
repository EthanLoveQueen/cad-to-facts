"""Deterministic, neutral BOM extraction from an assembly-aware snapshot."""

from cad_to_facts import __version__
from cad_to_facts.contract import bind_bom_extract, verify_snapshot_identity
from cad_to_facts.domain.bom import (
    BOMCoverage,
    BOMExtract,
    BOMLineItem,
    BOMMissingInput,
    BOMOptions,
)
from cad_to_facts.domain.snapshot import Diagnostic, ModelSnapshot


def _diagnostic(code: str, message: str, discovery: str = "none") -> Diagnostic:
    return Diagnostic(
        code=code,
        severity="warning",
        stage="translate",
        message=message,
        scope_refs=["assembly"],
        affects=["bom"],
        impact="partial",
        discovery_impact=discovery,
    )


def extract_bom(snapshot: ModelSnapshot, options: BOMOptions | None = None) -> BOMExtract:
    """Group active occurrences by leaf PartDefinition without inferring quantities."""

    snapshot = verify_snapshot_identity(snapshot)
    options = options or BOMOptions()
    diagnostics = list(snapshot.diagnostics)
    missing_inputs: list[BOMMissingInput] = []
    line_items: list[BOMLineItem] = []
    definitions = []
    occurrences = []
    links = []
    discovery = "unknown"

    if snapshot.assembly is None:
        diagnostics.append(
            _diagnostic(
                "BOM_ASSEMBLY_NOT_REPRESENTED",
                "BOM extraction requires a snapshot read with read_scope=assembly",
                "unknown",
            )
        )
    else:
        assembly = snapshot.assembly
        discovery = assembly.discovery
        links = list(assembly.links)
        definitions = list(assembly.definitions)
        occurrences = list(assembly.occurrences)
        occurrences_by_definition: dict[str, list] = {}
        for occurrence in occurrences:
            occurrences_by_definition.setdefault(occurrence.definition_id, []).append(occurrence)

        for definition in definitions:
            if definition.is_assembly:
                continue
            definition_occurrences = occurrences_by_definition.get(definition.definition_id, [])
            properties = {"name": definition.name} if definition.name is not None else {}
            for field in sorted(set(options.required_properties)):
                if field in properties:
                    continue
                reason = "ABSENT" if field == "name" else "UNSUPPORTED"
                message = (
                    "The required name is absent from the completely discovered definition"
                    if reason == "ABSENT"
                    else f"The STEP XCAF extractor does not declare the property {field!r}"
                )
                missing_inputs.append(
                    BOMMissingInput(
                        subject_id=definition.definition_id,
                        field=field,
                        reason_code=reason,
                        message=message,
                    )
                )
                diagnostics.append(
                    _diagnostic(
                        "BOM_REQUIRED_PROPERTY_MISSING",
                        f"{definition.definition_id}: {message}",
                    )
                )
            unknown = any(item.state == "unknown" for item in definition_occurrences)
            counted = [item.occurrence_id for item in definition_occurrences if item.state == "active"]
            quantity_state = (
                "unknown"
                if unknown
                else "known"
                if assembly.discovery == "complete"
                else "observed"
            )
            line_items.append(
                BOMLineItem(
                    part_definition_id=definition.definition_id,
                    name=definition.name,
                    declared_properties=properties,
                    quantity=None if unknown else len(counted),
                    quantity_state=quantity_state,
                    occurrence_refs=[item.occurrence_id for item in definition_occurrences],
                    counted_occurrence_refs=counted,
                )
            )
        if not line_items:
            diagnostics.append(
                _diagnostic("BOM_EMPTY", "The assembly contains no leaf part definitions")
            )

    coverage = BOMCoverage(
        definition_total=len(line_items),
        occurrence_total=sum(len(item.occurrence_refs) for item in line_items),
        counted_occurrence_total=sum(len(item.counted_occurrence_refs) for item in line_items),
        unknown_quantity_definition_total=sum(
            item.quantity_state == "unknown" for item in line_items
        ),
        observed_quantity_definition_total=sum(
            item.quantity_state == "observed" for item in line_items
        ),
        known_quantity_definition_total=sum(
            item.quantity_state == "known" for item in line_items
        ),
        structure_discovery=discovery,
    )
    blocking_diagnostics = any(
        diagnostic.disposition != "resolved"
        and (
            diagnostic.discovery_impact != "none"
            or "assembly" in diagnostic.affects
            or "bom" in diagnostic.affects
        )
        for diagnostic in diagnostics
    )
    complete = bool(
        snapshot.assembly is not None
        and discovery == "complete"
        and line_items
        and not missing_inputs
        and coverage.unknown_quantity_definition_total == 0
        and not blocking_diagnostics
    )
    return bind_bom_extract(
        BOMExtract(
            bom_id="0" * 64,
            artifact_sha256=snapshot.artifact_sha256,
            snapshot_id=snapshot.snapshot_id,
            snapshot_content_hash=snapshot.snapshot_content_hash,
            extractor_version=__version__,
            options=options,
            line_items=line_items,
            definitions=definitions,
            occurrences=occurrences,
            assembly_links=links,
            missing_inputs=missing_inputs,
            coverage=coverage,
            diagnostics=diagnostics,
            complete=complete,
        )
    )
