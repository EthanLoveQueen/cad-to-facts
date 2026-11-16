"""Selective, bounded JSON views over drawing snapshots."""

from collections import Counter
from typing import Any

from cad_to_facts.domain.snapshot import EntityRef, ModelSnapshot


def _native_values(entity: EntityRef) -> dict[str, str]:
    return {item["type"]: item["value"] for item in entity.native_refs}


def snapshot_summary(snapshot: ModelSnapshot) -> dict[str, Any]:
    """Return snapshot metadata and counts without its full entity catalog."""

    result: dict[str, Any] = {
        "schema_version": snapshot.schema_version,
        "artifact_sha256": snapshot.artifact_sha256,
        "snapshot_id": snapshot.snapshot_id,
        "snapshot_content_hash": snapshot.snapshot_content_hash,
        "adapter_id": snapshot.adapter_id,
        "adapter_version": snapshot.adapter_version,
        "parser_kernel_version": snapshot.parser_kernel_version,
        "parse_options": snapshot.parse_options,
        "units": snapshot.units,
        "status": snapshot.status,
        "entity_discovery": snapshot.entity_discovery,
        "entity_count": len(snapshot.entities),
        "entity_kind_counts": dict(
            sorted(Counter(entity.entity_kind for entity in snapshot.entities).items())
        ),
        "diagnostics": [item.model_dump(mode="json") for item in snapshot.diagnostics],
    }
    if snapshot.drawing is not None:
        drawing = snapshot.drawing
        layer_counts: Counter[str] = Counter()
        container_counts: Counter[str] = Counter()
        for entity in snapshot.entities:
            values = _native_values(entity)
            layer_counts[values.get("layer", "")] += 1
            container_counts[values.get("container", "")] += 1
        result["drawing"] = {
            "schema_version": drawing.schema_version,
            "source_format": drawing.source_format,
            "dxf_version": drawing.dxf_version,
            "entity_count": len(snapshot.entities),
            "entity_kind_counts": result["entity_kind_counts"],
            "layer_entity_counts": dict(sorted(layer_counts.items())),
            "container_entity_counts": dict(sorted(container_counts.items())),
            "layers": [item.model_dump(mode="json") for item in drawing.layers],
            "layouts": [
                {
                    "name": item.name,
                    "kind": item.kind,
                    "entity_count": len(item.entity_ids),
                }
                for item in drawing.layouts
            ],
            "block_count": len(drawing.blocks),
            "blocks": [
                {
                    "name": item.name,
                    "entity_count": len(item.entity_ids),
                    "is_xref": item.is_xref,
                    "xref_path": item.xref_path,
                }
                for item in drawing.blocks
            ],
            "external_references": [
                item.model_dump(mode="json") for item in drawing.external_references
            ],
            "conversion": (
                drawing.conversion.model_dump(mode="json") if drawing.conversion else None
            ),
        }
    return result


def select_entities(
    snapshot: ModelSnapshot,
    *,
    kinds: list[str] | None = None,
    layers: list[str] | None = None,
    containers: list[str] | None = None,
    text: str | None = None,
    cursor: str | None = None,
    limit: int = 20,
) -> tuple[list[EntityRef], dict[str, Any]]:
    """Filter in catalog order and return a page plus a snapshot-local cursor."""

    if snapshot.drawing is None:
        raise ValueError("Entity query currently supports only DWG/DXF snapshots")
    if limit <= 0:
        raise ValueError("--limit must be positive for query pagination")
    positions = {entity.entity_id: index for index, entity in enumerate(snapshot.entities)}
    if cursor is not None and cursor not in positions:
        raise ValueError(f"Unknown query cursor for this snapshot: {cursor}")
    start = positions[cursor] + 1 if cursor is not None else 0
    kind_filter = {item.lower() for item in kinds or []}
    layer_filter = set(layers or [])
    container_filter = set(containers or [])

    def matches(entity: EntityRef) -> bool:
        values = _native_values(entity)
        if kind_filter and entity.entity_kind not in kind_filter:
            return False
        if layer_filter and values.get("layer") not in layer_filter:
            return False
        if container_filter and values.get("container") not in container_filter:
            return False
        if text is not None:
            item = snapshot._adapter_payload["entities"][entity.entity_id]["entity"]
            dxf_type = item.dxftype()
            if dxf_type == "MTEXT":
                value = item.text
            elif dxf_type in {"TEXT", "ATTRIB", "ATTDEF"}:
                value = item.dxf.text
            else:
                value = ""
            if text not in value:
                return False
        return True

    all_matches = [entity for entity in snapshot.entities if matches(entity)]
    remaining = [entity for entity in snapshot.entities[start:] if matches(entity)]
    selected = remaining[:limit]
    truncated = len(selected) < len(remaining)
    next_cursor = (
        selected[-1].entity_id
        if selected and truncated
        else cursor
        if truncated
        else None
    )
    return selected, {
        "matched_total": len(all_matches),
        "remaining_total": len(remaining),
        "entities_returned": len(selected),
        "truncated": truncated,
        "next_cursor": next_cursor,
        "filters": {
            "kinds": sorted(kind_filter),
            "layers": sorted(layer_filter),
            "containers": sorted(container_filter),
            "text_contains": text,
        },
        "cursor_scope": "current_snapshot_only",
    }
