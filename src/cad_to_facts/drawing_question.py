"""Execute explicit drawing questions without turning language into facts."""

from __future__ import annotations

from collections import Counter
import math
from typing import Any

from cad_to_facts.domain.answer import AnswerGap
from cad_to_facts.domain.drawing_question import (
    DrawingAnswerReport,
    DrawingBlockSummary,
    DrawingCandidateBasis,
    DrawingCandidateMatch,
    DrawingCandidateSummary,
    DrawingCountAnswer,
    DrawingDimensionInventory,
    DrawingDimensionValue,
    DrawingEntitySummary,
    DrawingInterpretationAnswer,
    DrawingLayerSummary,
    DrawingMeasurementPredicate,
    DrawingMeasurementSummary,
    DrawingMeasurementValue,
    DrawingQueryScope,
    DrawingQuestionInterpretation,
    DrawingQuestionSpec,
    DrawingSelector,
    DrawingSemanticEvidenceItem,
    DrawingSemanticEvidenceSummary,
)
from cad_to_facts.domain.facts import ExtractionQuery, FactRequest
from cad_to_facts.domain.snapshot import EntityRef, ModelSnapshot
from cad_to_facts.drawing_bom import extract_drawing_bom
from cad_to_facts.drawing_facts import extract_drawing
from cad_to_facts.identity import structured_hash


_TEXT_KINDS = ["text", "mtext", "attrib", "attdef"]
_MEASUREMENT_KINDS = {
    "length": ["line", "lwpolyline", "arc"],
    "area": ["circle", "lwpolyline"],
    "circumference": ["circle"],
}
_DIMENSION_TYPE_LABELS = {
    0: "linear",
    1: "aligned",
    2: "angular_2_lines",
    3: "diameter",
    4: "radius",
    5: "angular_3_points",
    6: "ordinate",
    8: "arc_length",
}
_ANGULAR_DIMENSION_TYPES = {2, 5}
_MM_PER_LENGTH_UNIT = {"mm": 1.0, "cm": 10.0, "m": 1000.0, "in": 25.4, "ft": 304.8}
_CANDIDATE_BASES = ["block_name", "layer_name", "text"]
_SEMANTIC_BASES = ["block_name", "layer_name", "text", "attribute_tag"]


def bind_drawing_question(spec: DrawingQuestionSpec) -> DrawingQuestionSpec:
    question_id = structured_hash("drawing-question", spec, exclude={"question_id"})
    return spec.model_copy(update={"question_id": question_id})


def _native(entity: EntityRef) -> dict[str, str]:
    return {item["type"]: item["value"] for item in entity.native_refs}


def _payload(snapshot: ModelSnapshot, entity: EntityRef) -> dict[str, Any]:
    return snapshot._adapter_payload["entities"][entity.entity_id]


def _item(snapshot: ModelSnapshot, entity: EntityRef) -> Any:
    return _payload(snapshot, entity)["entity"]


def _display_text(item: Any) -> str | None:
    dxf_type = item.dxftype()
    if dxf_type == "MTEXT":
        return item.plain_text()
    if dxf_type in {"TEXT", "ATTRIB", "ATTDEF"}:
        return item.dxf.text
    return None


def _source_hash(snapshot: ModelSnapshot, entity: EntityRef) -> str:
    return _native(entity).get("source_artifact_sha256", snapshot.artifact_sha256)


def _source_hashes(snapshot: ModelSnapshot, entities: list[EntityRef]) -> list[str]:
    return sorted({_source_hash(snapshot, entity) for entity in entities})


def _layer_map(snapshot: ModelSnapshot) -> dict[str, Any]:
    if snapshot.drawing is None:
        return {}
    return {layer.name: layer for layer in snapshot.drawing.layers}


def _matches_selector(
    snapshot: ModelSnapshot, entity: EntityRef, selector: DrawingSelector | None
) -> bool:
    if selector is None:
        return True
    values = _native(entity)
    if selector.kinds and entity.entity_kind not in selector.kinds:
        return False
    if selector.layers and values.get("layer") not in selector.layers:
        return False
    if selector.containers and values.get("container") not in selector.containers:
        return False
    if selector.handles and values.get("handle", "").upper() not in selector.handles:
        return False
    if selector.text_contains_any:
        text = _display_text(_item(snapshot, entity)) or ""
        haystack = text if selector.case_sensitive else text.casefold()
        terms = (
            selector.text_contains_any
            if selector.case_sensitive
            else [term.casefold() for term in selector.text_contains_any]
        )
        if not any(term in haystack for term in terms):
            return False
    return True


def _select(
    snapshot: ModelSnapshot, selector: DrawingSelector | None
) -> tuple[list[EntityRef], int, int]:
    layers = _layer_map(snapshot)
    selected: list[EntityRef] = []
    excluded = 0
    unknown_layer_state = 0
    for entity in snapshot.entities:
        if not _matches_selector(snapshot, entity, selector):
            continue
        layer_name = _native(entity).get("layer", "")
        layer = layers.get(layer_name)
        visible = True if layer is None else not layer.off and not layer.frozen
        if layer is None:
            unknown_layer_state += 1
        if selector is not None and selector.layer_state_policy == "visible" and not visible:
            excluded += 1
            continue
        selected.append(entity)
    return selected, excluded, unknown_layer_state


def _selector_filters(selector: DrawingSelector | None) -> dict[str, Any]:
    if selector is None:
        return {}
    return selector.model_dump(mode="json", exclude_none=True)


def _scope(
    snapshot: ModelSnapshot,
    selector: DrawingSelector | None,
    entities: list[EntityRef],
    *,
    container_scope: str | None = None,
    filters: dict[str, Any] | None = None,
    unknown_layer_state: int = 0,
    excluded_by_layer_state: int = 0,
) -> DrawingQueryScope:
    combined = _selector_filters(selector)
    if filters:
        combined.update(filters)
    return DrawingQueryScope(
        snapshot_id=snapshot.snapshot_id,
        artifact_sha256=snapshot.artifact_sha256,
        snapshot_content_hash=snapshot.snapshot_content_hash,
        parse_options=snapshot.parse_options,
        units=snapshot.units,
        discovery=snapshot.entity_discovery,
        filters=combined,
        container_scope=(
            container_scope
            or ("explicit" if selector is not None and selector.containers else "all_catalog")
        ),
        layer_state_policy=selector.layer_state_policy if selector else "all",
        source_artifact_sha256s=_source_hashes(snapshot, entities),
        unknown_layer_state_entities=unknown_layer_state,
        excluded_by_layer_state=excluded_by_layer_state,
    )


def _count_state(snapshot: ModelSnapshot) -> str:
    if snapshot.status == "failed":
        return "unknown"
    if snapshot.entity_discovery == "complete":
        return "known"
    if snapshot.entity_discovery == "partial":
        return "partial"
    return "unknown"


def _status(snapshot: ModelSnapshot) -> str:
    if snapshot.status == "failed":
        return "failed"
    if snapshot.entity_discovery == "complete":
        return "answered"
    return "partial"


def _discovery_gaps(snapshot: ModelSnapshot, interpretation_id: str) -> list[AnswerGap]:
    if snapshot.status == "failed":
        return [AnswerGap(
            code="DRAWING_SNAPSHOT_FAILED",
            message="The drawing snapshot failed; catalog values remain unknown rather than zero",
            interpretation_ids=[interpretation_id],
        )]
    if snapshot.entity_discovery == "partial":
        return [AnswerGap(
            code="DRAWING_DISCOVERY_PARTIAL",
            message=(
                "Entity discovery is partial, for example because an external reference is "
                "unresolved or recovery was incomplete; values are discovered-only"
            ),
            interpretation_ids=[interpretation_id],
        )]
    if snapshot.entity_discovery == "unknown":
        return [AnswerGap(
            code="DRAWING_DISCOVERY_UNKNOWN",
            message="Entity discovery is unknown; catalog values are not a complete drawing total",
            interpretation_ids=[interpretation_id],
        )]
    return []


def _limit_gap(
    interpretation_id: str, *, returned: int, total: int
) -> list[AnswerGap]:
    if returned >= total:
        return []
    return [AnswerGap(
        code="RESULT_LIMIT_APPLIED",
        message=(
            f"Returned {returned} of {total} matches; the matched total remains available and "
            "the sample limit is explicit in the query"
        ),
        interpretation_ids=[interpretation_id],
    )]


def _entity_summary(snapshot: ModelSnapshot, entity: EntityRef) -> DrawingEntitySummary:
    values = _native(entity)
    item = _item(snapshot, entity)
    dxf_type = item.dxftype()
    return DrawingEntitySummary(
        entity_id=entity.entity_id,
        kind=entity.entity_kind,
        layer=values.get("layer", ""),
        container=values.get("container", ""),
        container_kind=_payload(snapshot, entity).get("kind", "unknown"),
        handle=values.get("handle"),
        text=_display_text(item),
        attribute_tag=(
            item.dxf.tag if dxf_type in {"ATTRIB", "ATTDEF"} else None
        ),
        block_name=(
            item.dxf.name if dxf_type in {"INSERT", "MINSERT"} else None
        ),
        source_artifact_sha256=_source_hash(snapshot, entity),
        source_length_unit=values.get(
            "source_length_unit", snapshot.units.get("length", "unitless")
        ),
    )


def _count_answer(
    snapshot: ModelSnapshot,
    selector: DrawingSelector | None,
    selected: list[EntityRef],
    *,
    unit: str,
    include_layer_breakdown: bool,
    excluded_by_layer_state: int,
    unknown_layer_state: int,
) -> DrawingCountAnswer:
    state = _count_state(snapshot)
    value: int | None = len(selected)
    observed_value: int | None = None
    if state == "unknown":
        if snapshot.status == "failed":
            value = None
        else:
            observed_value = len(selected)
            value = None
    by_kind = Counter(entity.entity_kind for entity in selected)
    by_container_kind = Counter(
        _payload(snapshot, entity).get("kind", "unknown") for entity in selected
    )
    by_layer = (
        dict(sorted(Counter(
            _native(entity).get("layer", "") for entity in selected
        ).items()))
        if include_layer_breakdown
        else None
    )
    return DrawingCountAnswer(
        value=value,
        observed_value=observed_value,
        state=state,
        unit=unit,
        by_kind=dict(sorted(by_kind.items())),
        by_container_kind=dict(sorted(by_container_kind.items())),
        by_layer=by_layer,
        excluded_by_layer_state=excluded_by_layer_state,
        scope=_scope(
            snapshot,
            selector,
            selected,
            unknown_layer_state=unknown_layer_state,
            excluded_by_layer_state=excluded_by_layer_state,
        ),
    )


def _entity_count_answer(
    snapshot: ModelSnapshot, item: DrawingQuestionInterpretation
) -> DrawingInterpretationAnswer:
    selected, excluded, unknown_layer_state = _select(snapshot, item.selector)
    count = _count_answer(
        snapshot,
        item.selector,
        selected,
        unit="entities",
        include_layer_breakdown=item.include_layer_breakdown,
        excluded_by_layer_state=excluded,
        unknown_layer_state=unknown_layer_state,
    )
    gaps = _discovery_gaps(snapshot, item.interpretation_id)
    if unknown_layer_state:
        gaps.append(AnswerGap(
            code="LAYER_STATE_UNKNOWN",
            message=(
                f"{unknown_layer_state} matched entities reference layers absent from the layer "
                "table; visibility was treated as visible"
            ),
            interpretation_ids=[item.interpretation_id],
        ))
    return DrawingInterpretationAnswer(
        interpretation_id=item.interpretation_id,
        status=_status(snapshot),
        count=count,
        scope=count.scope,
        gaps=gaps,
    )


def _lookup_answer(
    snapshot: ModelSnapshot,
    item: DrawingQuestionInterpretation,
    *,
    text_only: bool,
) -> DrawingInterpretationAnswer:
    selector = item.selector
    if text_only and (selector is None or selector.kinds is None):
        selector = (selector or DrawingSelector()).model_copy(update={"kinds": _TEXT_KINDS})
    selected, excluded, unknown_layer_state = _select(snapshot, selector)
    if text_only:
        selected = [
            entity for entity in selected
            if _display_text(_item(snapshot, entity)) is not None
        ]
    count = _count_answer(
        snapshot,
        selector,
        selected,
        unit="text_matches" if text_only else "entities",
        include_layer_breakdown=False,
        excluded_by_layer_state=excluded,
        unknown_layer_state=unknown_layer_state,
    )
    returned = selected[: item.max_results]
    entities = [_entity_summary(snapshot, entity) for entity in returned]
    gaps = _discovery_gaps(snapshot, item.interpretation_id)
    gaps.extend(_limit_gap(
        item.interpretation_id, returned=len(returned), total=len(selected)
    ))
    if unknown_layer_state:
        gaps.append(AnswerGap(
            code="LAYER_STATE_UNKNOWN",
            message=(
                f"{unknown_layer_state} matched entities reference layers absent from the layer "
                "table; visibility was treated as visible"
            ),
            interpretation_ids=[item.interpretation_id],
        ))
    return DrawingInterpretationAnswer(
        interpretation_id=item.interpretation_id,
        status=_status(snapshot),
        count=count,
        entities=entities,
        entity_total=len(selected),
        entities_truncated=len(returned) < len(selected),
        scope=count.scope,
        gaps=gaps,
    )


def _layer_inventory_answer(
    snapshot: ModelSnapshot, item: DrawingQuestionInterpretation
) -> DrawingInterpretationAnswer:
    layer_filter = None
    if item.selector is not None and item.selector.layers:
        layer_filter = set(item.selector.layers)
    counts: Counter[str] = Counter()
    kind_counts: dict[str, Counter[str]] = {}
    for entity in snapshot.entities:
        name = _native(entity).get("layer", "")
        counts[name] += 1
        kind_counts.setdefault(name, Counter())[entity.entity_kind] += 1
    declared = {
        layer.name: layer for layer in (snapshot.drawing.layers if snapshot.drawing else [])
    }
    names = sorted(set(declared) | set(counts))
    if layer_filter is not None:
        names = [name for name in names if name in layer_filter]
    layers = [
        DrawingLayerSummary(
            name=name,
            declared=name in declared,
            off=declared[name].off if name in declared else None,
            frozen=declared[name].frozen if name in declared else None,
            entity_count=counts.get(name, 0),
            kind_counts=dict(sorted(kind_counts.get(name, Counter()).items())),
        )
        for name in names
    ]
    scope = _scope(
        snapshot,
        None,
        snapshot.entities,
        filters={
            "inventory": "layers",
            **({"layer_names": sorted(layer_filter)} if layer_filter is not None else {}),
        },
    )
    return DrawingInterpretationAnswer(
        interpretation_id=item.interpretation_id,
        status=_status(snapshot),
        layers=layers,
        scope=scope,
        gaps=_discovery_gaps(snapshot, item.interpretation_id),
    )


def _block_inventory_answer(
    snapshot: ModelSnapshot, item: DrawingQuestionInterpretation
) -> DrawingInterpretationAnswer:
    instances: dict[str, list[EntityRef]] = {}
    for entity in snapshot.entities:
        dxf_type = _item(snapshot, entity).dxftype()
        if dxf_type not in {"INSERT", "MINSERT"}:
            continue
        name = _item(snapshot, entity).dxf.name
        instances.setdefault(name.casefold(), []).append(entity)
    blocks: list[DrawingBlockSummary] = []
    declared_names: set[str] = set()
    minsert_array_count = 0
    for block in snapshot.drawing.blocks if snapshot.drawing else []:
        declared_names.add(block.name.casefold())
        refs = instances.get(block.name.casefold(), [])
        array_total = sum(
            int(getattr(_item(snapshot, entity), "mcount", 1))
            if _item(snapshot, entity).dxftype() == "MINSERT" else 1
            for entity in refs
        )
        minsert_array_count += sum(
            1 for entity in refs
            if _item(snapshot, entity).dxftype() == "MINSERT"
            and int(getattr(_item(snapshot, entity), "mcount", 1)) > 1
        )
        containers = Counter(
            _native(entity).get("container", "") for entity in refs
        )
        blocks.append(DrawingBlockSummary(
            name=block.name,
            declared=True,
            definition_entity_count=len(block.entity_ids),
            insert_entity_count=len(refs),
            minsert_array_total=array_total,
            is_xref=block.is_xref,
            xref_path=block.xref_path,
            instance_containers=dict(sorted(containers.items())),
        ))
    for key, refs in sorted(instances.items()):
        if key in declared_names:
            continue
        name = _item(snapshot, refs[0]).dxf.name
        containers = Counter(_native(entity).get("container", "") for entity in refs)
        array_total = sum(
            int(getattr(_item(snapshot, entity), "mcount", 1))
            if _item(snapshot, entity).dxftype() == "MINSERT" else 1
            for entity in refs
        )
        blocks.append(DrawingBlockSummary(
            name=name,
            declared=False,
            definition_entity_count=0,
            insert_entity_count=len(refs),
            minsert_array_total=array_total,
            instance_containers=dict(sorted(containers.items())),
        ))
    blocks.sort(key=lambda block: block.name.casefold())
    gaps = _discovery_gaps(snapshot, item.interpretation_id)
    gaps.append(AnswerGap(
        code="INSERT_GEOMETRY_NOT_EXPANDED",
        message=(
            "Block inventory counts block definitions and INSERT/MINSERT entities; it does not "
            "expand inserted geometry into the host catalog"
        ),
        interpretation_ids=[item.interpretation_id],
    ))
    if minsert_array_count:
        gaps.append(AnswerGap(
            code="MINSERT_ARRAY_NOT_EXPANDED",
            message=(
                f"{minsert_array_count} MINSERT arrays are counted as one insert entity each; "
                "minsert_array_total reports their declared array count without expanding geometry"
            ),
            interpretation_ids=[item.interpretation_id],
        ))
    return DrawingInterpretationAnswer(
        interpretation_id=item.interpretation_id,
        status=_status(snapshot),
        blocks=blocks,
        scope=_scope(
            snapshot, None, snapshot.entities, filters={"inventory": "blocks"}
        ),
        gaps=gaps,
    )


def _supports_measurement(item: Any, predicate: DrawingMeasurementPredicate) -> bool:
    dxf_type = item.dxftype()
    if predicate == "length":
        return dxf_type in {"LINE", "LWPOLYLINE", "ARC"}
    if predicate == "area":
        return dxf_type == "CIRCLE" or (dxf_type == "LWPOLYLINE" and item.closed)
    return dxf_type == "CIRCLE"


def _measurement_answer(
    snapshot: ModelSnapshot, item: DrawingQuestionInterpretation
) -> DrawingInterpretationAnswer:
    selector = item.selector
    default_kinds = selector is None or selector.kinds is None
    if default_kinds:
        selector = (selector or DrawingSelector()).model_copy(
            update={"kinds": _MEASUREMENT_KINDS[item.predicate]}
        )
    selected, excluded, unknown_layer_state = _select(snapshot, selector)
    if default_kinds:
        selected = [
            entity for entity in selected
            if _supports_measurement(_item(snapshot, entity), item.predicate)
        ]
    supported = [
        entity for entity in selected
        if _supports_measurement(_item(snapshot, entity), item.predicate)
    ]
    unsupported_count = len(selected) - len(supported)
    requests = [
        FactRequest(
            name=f"{entity.entity_id}:{item.predicate}",
            predicate=item.predicate,
            subject_id=entity.entity_id,
        )
        for entity in supported
    ]
    factset = extract_drawing(snapshot, ExtractionQuery(requests=requests))
    facts = factset.facts
    measured_ids = {fact.subject.entity_id for fact in facts}
    gap_counts = Counter(gap.reason_code for gap in factset.gaps)
    values: list[DrawingMeasurementValue] | None = None
    values_truncated = False
    if item.include_values:
        selected_values = facts[: item.max_results]
        values_truncated = len(facts) > len(selected_values)
        values = []
        for fact in selected_values:
            values.append(DrawingMeasurementValue(
                entity_id=fact.subject.entity_id,
                kind=fact.subject.entity_kind,
                layer=_native(fact.subject).get("layer", ""),
                container=_native(fact.subject).get("container", ""),
                handle=_native(fact.subject).get("handle"),
                value=float(fact.value),
                unit=fact.unit,
                source_artifact_sha256=fact.evidence.artifact_sha256,
            ))
    numeric = [float(fact.value) for fact in facts]
    total = sum(numeric) if numeric else None
    unit = "mm^2" if item.predicate == "area" else "mm"
    discovery_state = _count_state(snapshot)
    if discovery_state == "unknown":
        state = "unknown"
    elif not selected:
        state = "known" if discovery_state == "known" else "partial"
    elif not facts:
        state = "unknown"
    elif discovery_state == "known" and not unsupported_count and not gap_counts:
        state = "known"
    else:
        state = "partial"
    unmeasured = [entity.entity_id for entity in supported if entity.entity_id not in measured_ids]
    measurements = DrawingMeasurementSummary(
        predicate=item.predicate,
        selected_entity_count=len(selected),
        supported_entity_count=len(supported),
        unsupported_entity_count=unsupported_count,
        measured_entity_count=len(facts),
        value_count=len(facts),
        total=total,
        minimum=min(numeric) if numeric else None,
        maximum=max(numeric) if numeric else None,
        unit=unit,
        state=state,
        sum_scope=(
            "empty" if not facts or not supported
            else "all_selected_supported" if len(facts) == len(supported)
            else "measured_entities_only"
        ),
        values=values,
        values_truncated=values_truncated,
        unmeasured_entity_ids=unmeasured[: item.max_results],
        unmeasured_entity_count=len(unmeasured),
        gap_counts=dict(sorted(gap_counts.items())),
    )
    gaps = _discovery_gaps(snapshot, item.interpretation_id)
    if unsupported_count:
        gaps.append(AnswerGap(
            code="MEASUREMENT_NOT_APPLICABLE",
            message=(
                f"{unsupported_count} selected entities do not support the {item.predicate} "
                "predicate and were not measured"
            ),
            interpretation_ids=[item.interpretation_id],
        ))
    if supported and not facts:
        gaps.append(AnswerGap(
            code="MEASUREMENT_NO_VALUES",
            message=(
                "No selected entity produced a value for this predicate; unitless drawings and "
                "unsupported geometry remain unknown rather than numeric zero"
            ),
            interpretation_ids=[item.interpretation_id],
        ))
    if gap_counts:
        gaps.append(AnswerGap(
            code="DRAWING_MEASUREMENT_GAPS",
            message=(
                "Some or all measurements are missing: "
                + ", ".join(f"{code}={count}" for code, count in sorted(gap_counts.items()))
            ),
            interpretation_ids=[item.interpretation_id],
        ))
    if unknown_layer_state:
        gaps.append(AnswerGap(
            code="LAYER_STATE_UNKNOWN",
            message=(
                f"{unknown_layer_state} selected entities reference layers absent from the layer "
                "table; visibility was treated as visible"
            ),
            interpretation_ids=[item.interpretation_id],
        ))
    status = "failed" if snapshot.status == "failed" else (
        "answered" if state == "known" else "partial"
    )
    return DrawingInterpretationAnswer(
        interpretation_id=item.interpretation_id,
        status=status,
        measurements=measurements,
        scope=_scope(
            snapshot,
            selector,
            selected,
            filters=(
                {"measurement_entity_filter": item.predicate}
                if default_kinds else None
            ),
            unknown_layer_state=unknown_layer_state,
            excluded_by_layer_state=excluded,
        ),
        gaps=gaps,
    )


def _dimension_answer(
    snapshot: ModelSnapshot, item: DrawingQuestionInterpretation
) -> DrawingInterpretationAnswer:
    selected, excluded, unknown_layer_state = _select(snapshot, item.selector)
    dimensions_selected = [
        entity for entity in selected
        if _item(snapshot, entity).dxftype().upper().endswith("DIMENSION")
    ]
    dimensions: list[DrawingDimensionValue] = []
    gap_counts: Counter[str] = Counter()
    valued = 0
    for entity in dimensions_selected:
        source = _payload(snapshot, entity)
        dxf_item = source["entity"]
        raw_dimension_type = getattr(dxf_item, "dimtype", None)
        if raw_dimension_type is None:
            raw_dimension_type = dxf_item.dxf.get("dimtype", 0)
        dimension_type_code = int(raw_dimension_type) & 15
        measurement: float | None = None
        unit: str | None = None
        reason: str | None = None
        try:
            raw = dxf_item.get_measurement()
        except Exception:
            raw = None
            reason = "MEASUREMENT_UNAVAILABLE"
        if reason is None:
            if dimension_type_code == 6:
                reason = "NON_SCALAR_ORDINATE"
            elif not isinstance(raw, (int, float)) or not math.isfinite(raw):
                reason = "NON_SCALAR_MEASUREMENT"
            elif dimension_type_code in _ANGULAR_DIMENSION_TYPES:
                measurement = float(raw)
                unit = "deg"
            else:
                source_unit = source.get("length_unit", snapshot.units.get("length"))
                factor = _MM_PER_LENGTH_UNIT.get(source_unit)
                if factor is None:
                    reason = "UNKNOWN_UNIT"
                else:
                    measurement = float(raw) * factor
                    unit = "mm"
        if reason is not None:
            gap_counts[reason] += 1
        if measurement is not None:
            valued += 1
        if len(dimensions) >= item.max_results:
            continue
        text_override = str(dxf_item.dxf.get("text", "") or "")
        if text_override in {"", "<>"}:
            text_override = None
        dimensions.append(DrawingDimensionValue(
            entity_id=entity.entity_id,
            kind=entity.entity_kind,
            layer=_native(entity).get("layer", ""),
            container=_native(entity).get("container", ""),
            handle=_native(entity).get("handle"),
            dimension_type=_DIMENSION_TYPE_LABELS.get(
                dimension_type_code, f"type_{dimension_type_code}"
            ),
            dimension_type_code=dimension_type_code,
            measurement=measurement,
            unit=unit,
            state="known" if measurement is not None else "unknown",
            reason=reason,
            text_override=text_override,
            source_artifact_sha256=_source_hash(snapshot, entity),
        ))
    unknown = len(dimensions_selected) - valued
    discovery_state = _count_state(snapshot)
    if discovery_state == "unknown":
        state = "unknown"
    elif not dimensions_selected:
        state = "known" if discovery_state == "known" else "partial"
    elif valued == 0:
        state = "unknown"
    elif unknown or discovery_state != "known":
        state = "partial"
    else:
        state = "known"
    inventory = DrawingDimensionInventory(
        selected_entity_count=len(dimensions_selected),
        dimension_total=len(dimensions_selected),
        valued_count=valued,
        unknown_count=unknown,
        state=state,
        dimensions=dimensions,
        truncated=len(dimensions) < len(dimensions_selected),
        gap_counts=dict(sorted(gap_counts.items())),
    )
    gaps = _discovery_gaps(snapshot, item.interpretation_id)
    gaps.append(AnswerGap(
        code="DIMENSION_GEOMETRY_ASSOCIATION_UNSUPPORTED",
        message=(
            "Dimension values are read from DIMENSION entities; they are not associated with "
            "the model or paper-space geometry they annotate"
        ),
        interpretation_ids=[item.interpretation_id],
    ))
    if gap_counts:
        gaps.append(AnswerGap(
            code="DIMENSION_MEASUREMENT_GAPS",
            message=(
                "Some or all dimension values are unavailable: "
                + ", ".join(f"{code}={count}" for code, count in sorted(gap_counts.items()))
            ),
            interpretation_ids=[item.interpretation_id],
        ))
    status = "failed" if snapshot.status == "failed" else (
        "answered" if state == "known" else "partial"
    )
    return DrawingInterpretationAnswer(
        interpretation_id=item.interpretation_id,
        status=status,
        dimensions=inventory,
        scope=_scope(
            snapshot,
            item.selector,
            dimensions_selected,
            filters={"dimension_entities_only": True},
            unknown_layer_state=unknown_layer_state,
            excluded_by_layer_state=excluded,
        ),
        gaps=gaps,
    )


def _basis_value(dxf_item: Any, values: dict[str, str], basis: DrawingCandidateBasis) -> str | None:
    dxf_type = dxf_item.dxftype()
    if basis == "block_name":
        return dxf_item.dxf.name if dxf_type in {"INSERT", "MINSERT"} else None
    if basis == "layer_name":
        return values.get("layer", "")
    if basis == "text":
        return _display_text(dxf_item)
    if basis == "attribute_tag":
        return dxf_item.dxf.tag if dxf_type in {"ATTRIB", "ATTDEF"} else None
    return None


def _attached_attributes(dxf_item: Any) -> dict[str, list[str]]:
    if dxf_item.dxftype() not in {"INSERT", "MINSERT"}:
        return {}
    attributes: dict[str, list[str]] = {}
    for attribute in getattr(dxf_item, "attribs", ()):
        attributes.setdefault(attribute.dxf.tag, []).append(attribute.dxf.text)
    return attributes


def _candidate_matches(
    snapshot: ModelSnapshot,
    item: DrawingQuestionInterpretation,
    bases: list[DrawingCandidateBasis],
    terms: list[str],
) -> tuple[list[EntityRef], list[tuple[EntityRef, DrawingCandidateBasis, str, str]], int, int]:
    selected, excluded, unknown_layer_state = _select(snapshot, item.selector)
    case_sensitive = bool(item.selector and item.selector.case_sensitive)
    matches: list[tuple[EntityRef, DrawingCandidateBasis, str, str]] = []
    for entity in selected:
        values = _native(entity)
        dxf_item = _item(snapshot, entity)
        for basis in bases:
            value = _basis_value(dxf_item, values, basis)
            if not value:
                continue
            haystack = value if case_sensitive else value.casefold()
            matched_term = None
            for term in terms:
                needle = term if case_sensitive else term.casefold()
                if needle in haystack:
                    matched_term = term
                    break
            if matched_term is not None:
                matches.append((entity, basis, matched_term, value))
    return selected, matches, excluded, unknown_layer_state


def _candidate_answer(
    snapshot: ModelSnapshot, item: DrawingQuestionInterpretation
) -> DrawingInterpretationAnswer:
    bases = item.candidate_bases or list(_CANDIDATE_BASES)
    terms = item.candidate_terms or []
    selected, matches, excluded, unknown_layer_state = _candidate_matches(
        snapshot, item, bases, terms
    )
    distinct: set[str] = set()
    by_basis: dict[str, set[str]] = {basis: set() for basis in bases}
    rows: list[DrawingCandidateMatch] = []
    for entity, basis, matched_term, value in matches:
        values = _native(entity)
        distinct.add(entity.entity_id)
        by_basis[basis].add(entity.entity_id)
        rows.append(DrawingCandidateMatch(
            entity_id=entity.entity_id,
            kind=entity.entity_kind,
            layer=values.get("layer", ""),
            container=values.get("container", ""),
            handle=values.get("handle"),
            basis=basis,
            term=matched_term,
            declared_value=value,
            source_artifact_sha256=_source_hash(snapshot, entity),
        ))
    matches_sample = rows[: item.max_results]
    failed = snapshot.status == "failed"
    candidates = DrawingCandidateSummary(
        value=None if failed else len(distinct),
        state="unknown" if failed else "candidate",
        discovery=snapshot.entity_discovery,
        terms=terms,
        bases=bases,
        by_basis={basis: len(ids) for basis, ids in by_basis.items()},
        match_rows_total=len(rows),
        matches=matches_sample,
        matches_truncated=len(matches_sample) < len(rows),
    )
    gaps = _discovery_gaps(snapshot, item.interpretation_id)
    gaps.append(AnswerGap(
        code="SEMANTIC_CANDIDATES_UNVALIDATED",
        message=(
            "Matches use declared block names, layer names, text or attribute tags only; they "
            "do not validate a functional door, window, hole or other engineering feature"
        ),
        interpretation_ids=[item.interpretation_id],
    ))
    gaps.append(AnswerGap(
        code="SEMANTIC_COVERAGE_UNKNOWN",
        message=(
            "General drawing semantic coverage is unknown; an unmatched term is not proof that "
            "the intended feature is absent"
        ),
        interpretation_ids=[item.interpretation_id],
    ))
    gaps.extend(_limit_gap(
        item.interpretation_id, returned=len(matches_sample), total=len(rows)
    ))
    status = "failed" if failed else (
        "answered" if snapshot.entity_discovery == "complete" else "partial"
    )
    return DrawingInterpretationAnswer(
        interpretation_id=item.interpretation_id,
        status=status,
        candidates=candidates,
        scope=_scope(
            snapshot,
            item.selector,
            selected,
            filters={
                "candidate_terms": terms,
                "candidate_bases": bases,
            },
            unknown_layer_state=unknown_layer_state,
            excluded_by_layer_state=excluded,
        ),
        gaps=gaps,
    )


def _semantic_answer(
    snapshot: ModelSnapshot, item: DrawingQuestionInterpretation
) -> DrawingInterpretationAnswer:
    bases = item.candidate_bases or list(_SEMANTIC_BASES)
    terms = item.candidate_terms or []
    selected, matches, excluded, unknown_layer_state = _candidate_matches(
        snapshot, item, bases, terms
    )
    distinct: set[str] = set()
    by_basis: dict[str, set[str]] = {basis: set() for basis in bases}
    attributed_inserts: set[str] = set()
    all_evidence: list[DrawingSemanticEvidenceItem] = []
    for entity, basis, matched_term, value in matches:
        values = _native(entity)
        dxf_item = _item(snapshot, entity)
        dxf_type = dxf_item.dxftype()
        attributes = _attached_attributes(dxf_item)
        if attributes:
            attributed_inserts.add(entity.entity_id)
        distinct.add(entity.entity_id)
        by_basis[basis].add(entity.entity_id)
        all_evidence.append(DrawingSemanticEvidenceItem(
            entity_id=entity.entity_id,
            kind=entity.entity_kind,
            layer=values.get("layer", ""),
            container=values.get("container", ""),
            handle=values.get("handle"),
            basis=basis,
            term=matched_term,
            declared_value=value,
            source_artifact_sha256=_source_hash(snapshot, entity),
            block_name=(
                dxf_item.dxf.name if dxf_type in {"INSERT", "MINSERT"} else None
            ),
            text=_display_text(dxf_item),
            attribute_tag=(
                dxf_item.dxf.tag if dxf_type in {"ATTRIB", "ATTDEF"} else None
            ),
            attributes=attributes,
        ))
    evidence = all_evidence[: item.max_results]
    failed = snapshot.status == "failed"
    summary = DrawingSemanticEvidenceSummary(
        value=None if failed else len(distinct),
        state="unknown" if failed else "candidate",
        discovery=snapshot.entity_discovery,
        terms=terms,
        bases=bases,
        by_basis={basis: len(ids) for basis, ids in by_basis.items()},
        match_rows_total=len(all_evidence),
        evidence=evidence,
        evidence_truncated=len(evidence) < len(all_evidence),
        attributed_insert_count=len(attributed_inserts),
    )
    gaps = _discovery_gaps(snapshot, item.interpretation_id)
    gaps.append(AnswerGap(
        code="SEMANTIC_CANDIDATES_UNVALIDATED",
        message=(
            "Semantic evidence uses declared block names, layer names, text or attribute tags; "
            "it does not validate a functional door, window, hole or other engineering feature"
        ),
        interpretation_ids=[item.interpretation_id],
    ))
    gaps.append(AnswerGap(
        code="SEMANTIC_CONTEXT_DECLARED_ONLY",
        message=(
            "Attached ATTRIB values and matched text are declared source context; they are not "
            "inferred material, part, function or other semantic field facts"
        ),
        interpretation_ids=[item.interpretation_id],
    ))
    gaps.append(AnswerGap(
        code="SEMANTIC_COVERAGE_UNKNOWN",
        message=(
            "General drawing semantic coverage is unknown; an unmatched term is not proof that "
            "the intended feature, material or part is absent"
        ),
        interpretation_ids=[item.interpretation_id],
    ))
    gaps.extend(_limit_gap(
        item.interpretation_id, returned=len(evidence), total=len(all_evidence)
    ))
    status = "failed" if failed else (
        "answered" if snapshot.entity_discovery == "complete" else "partial"
    )
    return DrawingInterpretationAnswer(
        interpretation_id=item.interpretation_id,
        status=status,
        semantic_evidence=summary,
        scope=_scope(
            snapshot,
            item.selector,
            selected,
            filters={
                "semantic_terms": terms,
                "semantic_bases": bases,
            },
            unknown_layer_state=unknown_layer_state,
            excluded_by_layer_state=excluded,
        ),
        gaps=gaps,
    )



def _bom_answer(
    snapshot: ModelSnapshot, item: DrawingQuestionInterpretation
) -> DrawingInterpretationAnswer:
    scope = _scope(
        snapshot,
        None,
        snapshot.entities,
        container_scope="explicit",
        filters={"bom_options": item.bom.model_dump(mode="json")},
    )
    if snapshot.drawing is None:
        return DrawingInterpretationAnswer(
            interpretation_id=item.interpretation_id,
            status="failed",
            scope=scope,
            gaps=[AnswerGap(
                code="DRAWING_PROFILE_UNAVAILABLE",
                message="drawing_bom_lookup requires a DWG/DXF drawing snapshot",
                interpretation_ids=[item.interpretation_id],
            )],
        )
    try:
        bom = extract_drawing_bom(snapshot, item.bom)
    except Exception as error:
        return DrawingInterpretationAnswer(
            interpretation_id=item.interpretation_id,
            status="failed",
            scope=scope,
            gaps=[AnswerGap(
                code="DRAWING_BOM_FAILED",
                message=f"Drawing BOM extraction failed: {type(error).__name__}",
                interpretation_ids=[item.interpretation_id],
            )],
        )
    gaps = _discovery_gaps(snapshot, item.interpretation_id)
    if not bom.complete:
        gaps.append(AnswerGap(
            code="DRAWING_BOM_INCOMPLETE",
            message=(
                "The attribute BOM is incomplete; missing inputs, unresolved references or "
                "unknown quantities remain explicit"
            ),
            interpretation_ids=[item.interpretation_id],
        ))
    if bom.coverage.uncounted_external_reference_total:
        gaps.append(AnswerGap(
            code="DRAWING_BOM_EXTERNAL_REFERENCE_EXCLUDED",
            message=(
                f"{bom.coverage.uncounted_external_reference_total} external references have no "
                "occurrences in the configured BOM scope"
            ),
            interpretation_ids=[item.interpretation_id],
        ))
    return DrawingInterpretationAnswer(
        interpretation_id=item.interpretation_id,
        status="answered" if bom.complete else "partial",
        bom=bom,
        scope=scope,
        gaps=gaps,
    )


def _failed_answer(
    snapshot: ModelSnapshot, item: DrawingQuestionInterpretation
) -> DrawingInterpretationAnswer:
    scope = _scope(snapshot, item.selector, [])
    return DrawingInterpretationAnswer(
        interpretation_id=item.interpretation_id,
        status="failed",
        scope=scope,
        gaps=[AnswerGap(
            code="DRAWING_SNAPSHOT_FAILED",
            message="The drawing snapshot is unavailable; no catalog answer is asserted",
            interpretation_ids=[item.interpretation_id],
        )],
    )


def _answer_one(
    snapshot: ModelSnapshot, item: DrawingQuestionInterpretation
) -> DrawingInterpretationAnswer:
    if snapshot.drawing is None:
        return _failed_answer(snapshot, item)
    if item.intent == "entity_count":
        return _entity_count_answer(snapshot, item)
    if item.intent == "entity_lookup":
        return _lookup_answer(snapshot, item, text_only=False)
    if item.intent == "text_lookup":
        return _lookup_answer(snapshot, item, text_only=True)
    if item.intent == "layer_inventory":
        return _layer_inventory_answer(snapshot, item)
    if item.intent == "block_inventory":
        return _block_inventory_answer(snapshot, item)
    if item.intent == "measurement_summary":
        return _measurement_answer(snapshot, item)
    if item.intent == "dimension_inventory":
        return _dimension_answer(snapshot, item)
    if item.intent == "name_candidate_count":
        return _candidate_answer(snapshot, item)
    if item.intent == "semantic_evidence":
        return _semantic_answer(snapshot, item)
    if item.intent == "drawing_bom_lookup":
        return _bom_answer(snapshot, item)
    return DrawingInterpretationAnswer(
        interpretation_id=item.interpretation_id,
        status="unsupported",
        scope=_scope(snapshot, item.selector, []),
        gaps=[AnswerGap(
            code="DRAWING_QUESTION_INTENT_UNSUPPORTED",
            message=f"The {item.intent} executor is not available",
            interpretation_ids=[item.interpretation_id],
        )],
    )


def _finish(
    question: DrawingQuestionSpec,
    answers: list[DrawingInterpretationAnswer],
    gaps: list[AnswerGap],
) -> DrawingAnswerReport:
    statuses = {answer.status for answer in answers}
    if "failed" in statuses:
        status = "failed"
    elif statuses == {"answered"} and answers:
        status = "answered"
    elif "partial" in statuses or "answered" in statuses:
        status = "partial"
    elif "ambiguous" in statuses:
        status = "ambiguous"
    elif "unresolved" in statuses:
        status = "unresolved"
    else:
        status = "unsupported"
    report = DrawingAnswerReport(
        answer_id="0" * 64,
        status=status,
        complete=status == "answered",
        question=question,
        answers=answers,
        gaps=gaps,
    )
    return report.model_copy(update={
        "answer_id": structured_hash("drawing-answer", report, exclude={"answer_id"})
    })


def answer_drawing_question(
    snapshot: ModelSnapshot, spec: DrawingQuestionSpec
) -> DrawingAnswerReport:
    question = bind_drawing_question(spec)
    if not question.interpretations:
        messages = question.interpretation_gaps or [
            "No executable drawing question interpretation was supplied"
        ]
        return _finish(question, [], [AnswerGap(
            code="DRAWING_QUESTION_INTERPRETATION_UNSUPPORTED",
            message=message,
        ) for message in messages])
    answers = [_answer_one(snapshot, item) for item in question.interpretations]
    gaps = [gap for answer in answers for gap in answer.gaps]
    return _finish(question, answers, gaps)
