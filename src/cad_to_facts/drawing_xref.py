"""Explicit-root, resource-bounded XREF resolution for drawing adapters."""

from dataclasses import dataclass
import os
import re
import time
from pathlib import Path
from typing import Any, Callable, Literal

from ezdxf import xref
from ezdxf.xref import ConflictPolicy

from cad_to_facts.domain import SourceArtifact
from cad_to_facts.domain.drawing import DrawingConversion, DrawingExternalReference


@dataclass
class LoadedXref:
    artifact: SourceArtifact
    document: Any
    auditor: Any
    conversion: DrawingConversion | None


class XRefLoadError(Exception):
    def __init__(self, state: str, message: str):
        super().__init__(message)
        self.state = state


def _diagnostic(code: str, message: str, *, discovery: str = "none") -> dict[str, Any]:
    return {
        "code": code,
        "severity": "warning" if code != "DRAWING_AUDIT_ERROR" else "error",
        "stage": "read",
        "message": message,
        "scope_refs": ["drawing"],
        "affects": ["discovery", "geometry"],
        "impact": "partial",
        "discovery_impact": discovery,
        "disposition": "open",
        "entity_refs": [],
        "details": {},
    }


def _validate_local_path(value: str) -> Path:
    value = os.fspath(value)
    if not value or "\x00" in value:
        raise XRefLoadError("invalid_path", "XREF path is empty or contains a null character")
    if value.startswith(("\\\\", "//")) or (os.name == "nt" and value.startswith("/")):
        raise XRefLoadError("invalid_path", "UNC, network and rooted paths are not accepted")
    if re.match(r"^[A-Za-z][A-Za-z0-9+.-]*:", value) and not re.match(r"^[A-Za-z]:[\\/]", value):
        raise XRefLoadError("invalid_path", "URL-style XREF locations are not accepted")
    return Path(value)


def _catalog_count(document: Any) -> int:
    count = 0

    def container_count(container: Any) -> int:
        total = 0
        for item in container:
            total += 1
            if item.dxftype() in {"INSERT", "MINSERT"}:
                total += len(getattr(item, "attribs", ()))
        return total

    for layout in document.layouts:
        count += container_count(layout)
    for block in document.blocks:
        if not block.is_any_layout:
            count += container_count(block)
    return count


class XRefResolver:
    """Resolve a drawing's XREF graph without ambient filesystem discovery."""

    def __init__(
        self,
        *,
        mode: Literal["linked", "flatten"],
        roots: list[str],
        loader: Callable[[Path, float], LoadedXref],
        unit_name: Callable[[Any], str],
        tagger: Callable[[Any, SourceArtifact, str, DrawingConversion | None], None],
        max_depth: int = 8,
        max_files: int = 64,
        max_bytes: int = 256 * 1024 * 1024,
        timeout_seconds: float = 120.0,
    ):
        if isinstance(max_depth, bool) or not isinstance(max_depth, int) or not 0 <= max_depth <= 32:
            raise ValueError("xref_max_depth must be an integer between 0 and 32")
        if isinstance(max_files, bool) or not isinstance(max_files, int) or not 1 <= max_files <= 1024:
            raise ValueError("xref_max_files must be an integer between 1 and 1024")
        if isinstance(max_bytes, bool) or not isinstance(max_bytes, int) or max_bytes <= 0:
            raise ValueError("xref_max_bytes must be a positive integer")
        if isinstance(timeout_seconds, bool) or not isinstance(timeout_seconds, (int, float)) or timeout_seconds <= 0:
            raise ValueError("xref_timeout_seconds must be a positive number")
        self.mode = mode
        self.roots = [self._root(value) for value in roots]
        self.loader = loader
        self.unit_name = unit_name
        self.tagger = tagger
        self.max_depth = max_depth
        self.max_files = max_files
        self.max_bytes = max_bytes
        self.deadline = time.monotonic() + float(timeout_seconds)
        self.loaded_files = 0
        self.loaded_bytes = 0
        self.records: list[DrawingExternalReference] = []
        self.active: list[Path] = []

    @staticmethod
    def _root(value: str) -> Path:
        path = _validate_local_path(value).resolve()
        if not path.is_dir():
            raise ValueError(f"XREF root is not a directory: {value}")
        return path

    def _remaining(self) -> float:
        remaining = self.deadline - time.monotonic()
        if remaining <= 0:
            raise XRefLoadError("limit_exceeded", "XREF resolution exceeded its time budget")
        return remaining

    def _resolve(self, declared: str, owner: Path) -> tuple[Path | None, str | None]:
        path = _validate_local_path(declared)
        candidates = [path] if path.is_absolute() else [owner.parent / path]
        if not path.is_absolute():
            candidates.extend(root / path for root in self.roots)
        local: list[Path] = []
        for candidate in candidates:
            resolved = candidate.resolve()
            if any(resolved == root or root in resolved.parents for root in self.roots):
                local.append(resolved)
        if not local:
            return None, "outside_root"
        for candidate in local:
            if candidate.is_file():
                return candidate, None
        return None, "missing"

    def _update(self, index: int, **values: Any) -> None:
        self.records[index] = self.records[index].model_copy(update=values)

    def process(
        self,
        document: Any,
        *,
        owner_artifact: SourceArtifact,
        owner_path: Path,
        owner_conversion: DrawingConversion | None,
    ) -> list[DrawingExternalReference]:
        self.active = [owner_path.resolve()]
        self._process(document, owner_artifact, owner_path, owner_conversion, 0, None)
        self.tagger(document, owner_artifact, self.unit_name(document), owner_conversion)
        return self.records

    def _process(
        self,
        document: Any,
        owner_artifact: SourceArtifact,
        owner_path: Path,
        owner_conversion: DrawingConversion | None,
        depth: int,
        parent_id: str | None,
    ) -> None:
        self._remaining()
        declared_blocks = [
            block
            for block in document.blocks
            if not block.is_any_layout and (block.block.is_xref or block.block.is_xref_overlay)
        ]
        for block in declared_blocks:
            reference_id = f"xref:{len(self.records)}"
            index = len(self.records)
            declared_path = block.block.dxf.xref_path or ""
            self.records.append(
                DrawingExternalReference(
                    reference_id=reference_id,
                    parent_reference_id=parent_id,
                    owner_artifact_sha256=owner_artifact.sha256,
                    block_name=block.name,
                    declared_path=declared_path,
                    depth=depth,
                    state="missing",
                )
            )
            diagnostics: list[dict[str, Any]] = []
            try:
                if depth > self.max_depth:
                    raise XRefLoadError("limit_exceeded", "XREF maximum nesting depth exceeded")
                resolved, failure = self._resolve(declared_path, owner_path)
                if failure is not None:
                    raise XRefLoadError(failure, f"XREF resolution state: {failure}")
                assert resolved is not None
                self._update(index, resolved_locator=str(resolved))
                if resolved in self.active:
                    raise XRefLoadError("cycle", "XREF dependency cycle detected")
                if self.loaded_files >= self.max_files:
                    raise XRefLoadError("limit_exceeded", "XREF file-count budget exceeded")
                size = resolved.stat().st_size
                if self.loaded_bytes + size > self.max_bytes:
                    raise XRefLoadError("limit_exceeded", "XREF byte budget exceeded")
                self.loaded_files += 1
                self.loaded_bytes += size
                loaded = self.loader(resolved, self._remaining())
                self._remaining()  # in-process parsers are cooperative, not preemptively killed
                child_unit = self.unit_name(loaded.document)
                self._update(index, artifact=loaded.artifact, units={"length": child_unit})
                self.active.append(resolved)
                try:
                    self._process(
                        loaded.document,
                        loaded.artifact,
                        resolved,
                        loaded.conversion,
                        depth + 1,
                        reference_id,
                    )
                finally:
                    self.active.pop()
                self.tagger(loaded.document, loaded.artifact, child_unit, loaded.conversion)
                auditor = loaded.auditor
                if auditor.has_errors:
                    diagnostics.append(_diagnostic(
                        "DRAWING_AUDIT_ERROR",
                        "Referenced drawing has audit errors",
                        discovery="partial",
                    ))
                if auditor.has_fixes:
                    diagnostics.append(_diagnostic(
                        "DRAWING_AUDIT_FIX", "Referenced drawing required recovery fixes"
                    ))
                if child_unit not in {"mm", "cm", "m", "in", "ft"}:
                    diagnostics.append(_diagnostic(
                        "UNIT_UNKNOWN", "Referenced drawing has an unverified length unit"
                    ))
                nested = [item for item in self.records if item.parent_reference_id == reference_id]
                count = _catalog_count(loaded.document)
                if count == 0:
                    discovery = "unknown"
                    diagnostics.append(_diagnostic(
                        "NO_DRAWING_ENTITIES", "Referenced drawing has no cataloged entities", discovery="unknown"
                    ))
                elif auditor.has_errors or any(
                    item.state != "resolved" or item.entity_discovery != "complete"
                    for item in nested
                ):
                    discovery = "partial"
                else:
                    discovery = "complete"
                if self.mode == "flatten":
                    xref.embed(
                        block,
                        load_fn=lambda *_args, doc=loaded.document: doc,
                        conflict_policy=ConflictPolicy.XREF_PREFIX,
                    )
                self._update(
                    index,
                    state="resolved",
                    entity_count=count,
                    entity_discovery=discovery,
                    conversion=loaded.conversion,
                    diagnostics=diagnostics,
                )
            except XRefLoadError as error:
                diagnostics.append(_diagnostic("DRAWING_EXTERNAL_REFERENCE", str(error), discovery="partial"))
                self._update(index, state=error.state, diagnostics=diagnostics)
            except Exception as error:
                diagnostics.append(_diagnostic(
                    "DRAWING_EXTERNAL_REFERENCE",
                    f"XREF could not be loaded: {type(error).__name__}: {error}",
                    discovery="partial",
                ))
                self._update(index, state="parse_failed", diagnostics=diagnostics)
