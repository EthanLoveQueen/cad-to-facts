"""DWG/DXF drawing adapter using optional ODA conversion and ezdxf parsing."""

import hashlib
import os
from pathlib import Path
import subprocess
import tempfile
from typing import Any

import ezdxf
from ezdxf import recover

from cad_to_facts.artifact import register
from cad_to_facts.contract import bind_snapshot
from cad_to_facts.domain import SourceArtifact
from cad_to_facts.domain.drawing import (
    DrawingBlock,
    DrawingConversion,
    DrawingLayer,
    DrawingLayout,
    DrawingStructure,
)
from cad_to_facts.domain.snapshot import Diagnostic, EntityRef, ModelSnapshot
from cad_to_facts.identity import structured_hash

_PROVENANCE_APPID = "CAD_TO_FACTS"

_UNIT_NAMES = {0: "unitless", 1: "in", 2: "ft", 4: "mm", 5: "cm", 6: "m"}
_VERIFIED_UNITS = {"mm", "cm", "m", "in", "ft"}


def _diagnostic(
    code: str,
    message: str,
    *,
    severity: str = "warning",
    impact: str = "partial",
    discovery: str = "none",
    count: int | None = None,
) -> Diagnostic:
    return Diagnostic(
        code=code,
        severity=severity,
        stage="read",
        message=message,
        scope_refs=["drawing"],
        affects=["discovery", "geometry"],
        impact=impact,
        discovery_impact=discovery,
        count=count,
    )


def _failed(
    artifact: SourceArtifact,
    parse_options: dict[str, Any],
    adapter_id: str,
    parser_version: str,
    code: str,
    message: str,
) -> ModelSnapshot:
    identity = {
        "artifact_sha256": artifact.sha256,
        "adapter_id": adapter_id,
        "adapter_version": "0.1.0",
        "parser_kernel_version": parser_version,
        "parse_options": parse_options,
    }
    snapshot = ModelSnapshot(
        artifact_sha256=artifact.sha256,
        snapshot_id=structured_hash("model-snapshot-id", identity),
        snapshot_content_hash="0" * 64,
        adapter_id=adapter_id,
        adapter_version="0.1.0",
        parser_kernel_version=parser_version,
        parse_options=parse_options,
        units={},
        status="failed",
        entity_discovery="unknown",
        entities=[],
        diagnostics=[
            _diagnostic(
                code,
                message,
                severity="fatal",
                impact="fatal",
                discovery="unknown",
            )
        ],
    )
    return bind_snapshot(snapshot)


def _oda_executable(configured: str | None) -> Path | None:
    """Use only an explicitly configured converter; never guess install locations."""

    if not configured:
        return None
    candidate = Path(configured).resolve()
    return candidate if candidate.is_file() else None


def _convert_dwg(
    content: bytes, options: dict[str, Any]
) -> tuple[bytes, DrawingConversion]:
    executable = _oda_executable(options.get("oda_executable"))
    if executable is None:
        raise FileNotFoundError(
            "ODA File Converter is not available; supply an explicit oda_executable"
        )
    timeout = options.get("oda_timeout_seconds", 120)
    if isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or timeout <= 0:
        raise ValueError("oda_timeout_seconds must be a positive number")
    executable_bytes = executable.read_bytes()
    converter_identity = f"exe-sha256:{hashlib.sha256(executable_bytes).hexdigest()}"
    with tempfile.TemporaryDirectory(prefix="cad-to-facts-oda-") as temporary:
        root = Path(temporary)
        input_directory = root / "input"
        output_directory = root / "output"
        input_directory.mkdir()
        output_directory.mkdir()
        # A fixed ASCII name avoids Unicode/filter ambiguity and isolates the source directory.
        (input_directory / "input.dwg").write_bytes(content)
        arguments = [
            str(executable),
            str(input_directory),
            str(output_directory),
            "ACAD2018",
            "DXF",
            "0",
            "1",
            "input.dwg",
        ]
        run_options: dict[str, Any] = {
            "capture_output": True,
            "timeout": float(timeout),
            "check": False,
            # Keep the working directory away from user files so DLL lookups cannot
            # pick up a planted library from the caller's current directory.
            "cwd": str(root),
        }
        if os.name == "nt":
            run_options["creationflags"] = subprocess.CREATE_NO_WINDOW
        result = subprocess.run(arguments, **run_options)
        output_path = output_directory / "input.dxf"
        if result.returncode != 0 or not output_path.is_file():
            raise ValueError(
                "ODA File Converter did not produce the expected DXF "
                f"(exit code {result.returncode})"
            )
        output = output_path.read_bytes()
    conversion = DrawingConversion(
        converter_identity=converter_identity,
        output_sha256=hashlib.sha256(output).hexdigest(),
        output_size_bytes=len(output),
    )
    return output, conversion


def _read_document(
    artifact: SourceArtifact, content: bytes, options: dict[str, Any]
) -> tuple[Any, Any, DrawingConversion | None, str]:
    conversion = None
    if artifact.format == "dwg":
        content, conversion = _convert_dwg(content, options)
        with tempfile.TemporaryDirectory(prefix="cad-to-facts-dxf-") as temporary:
            dxf_path = Path(temporary) / "derived.dxf"
            dxf_path.write_bytes(content)
            document, auditor = recover.readfile(str(dxf_path))
    else:
        document, auditor = recover.readfile(str(Path(artifact.source_locator)))
    return document, auditor, conversion, f"ezdxf {ezdxf.__version__}"


def _unit_name(document: Any) -> str:
    return _UNIT_NAMES.get(document.units, f"insunits_{document.units}")


def _clear_provenance(document: Any) -> None:
    """Remove source-supplied tags before creating adapter-owned provenance."""

    for item in document.entitydb.values():
        try:
            if item.has_xdata(_PROVENANCE_APPID):
                item.discard_xdata(_PROVENANCE_APPID)
        except (AttributeError, ezdxf.DXFError):
            continue


def _tag_provenance(
    document: Any,
    artifact: SourceArtifact,
    unit_name: str,
    conversion: DrawingConversion | None,
) -> None:
    """Tag in-memory copies so flattened facts retain their real source artifact."""

    if _PROVENANCE_APPID not in doc_appids(document):
        document.appids.add(_PROVENANCE_APPID)
    values = [
        (1000, artifact.sha256),
        (1000, unit_name),
        (1000, conversion.output_sha256 if conversion else ""),
    ]
    for item in document.entitydb.values():
        try:
            if not item.has_xdata(_PROVENANCE_APPID):
                item.set_xdata(_PROVENANCE_APPID, values)
        except (AttributeError, ezdxf.DXFError):
            continue


def doc_appids(document: Any) -> set[str]:
    return {item.dxf.name for item in document.appids}


def _entity_provenance(
    item: Any, artifact: SourceArtifact, unit_name: str, conversion: DrawingConversion | None
) -> tuple[str, str, str | None]:
    try:
        tags = item.get_xdata(_PROVENANCE_APPID)
        values = [tag.value for tag in tags]
        return values[0], values[1], values[2] or None
    except (AttributeError, ezdxf.DXFError, IndexError):
        return artifact.sha256, unit_name, conversion.output_sha256 if conversion else None


def read_drawing(
    artifact: SourceArtifact, options: dict[str, Any] | None = None
) -> ModelSnapshot:
    """Read a DXF directly or a DWG through an explicitly available ODA converter."""

    supplied = options or {}
    parse_options: dict[str, Any] = {
        "read_scope": supplied.get("read_scope", "drawing"),
        "target_length_unit": supplied.get("target_length_unit", "mm"),
        "xref_mode": supplied.get("xref_mode", "unresolved"),
    }
    if parse_options["xref_mode"] not in {"unresolved", "linked", "flatten"}:
        raise ValueError("xref_mode must be unresolved, linked or flatten")
    if parse_options["xref_mode"] != "unresolved":
        parse_options.update({
            "xref_roots": list(supplied.get("xref_roots", [])),
            "xref_max_depth": supplied.get("xref_max_depth", 8),
            "xref_max_files": supplied.get("xref_max_files", 64),
            "xref_max_bytes": supplied.get("xref_max_bytes", 256 * 1024 * 1024),
            "xref_timeout_seconds": supplied.get("xref_timeout_seconds", 120),
        })
    if parse_options["read_scope"] != "drawing":
        raise ValueError("DWG/DXF artifacts support only read_scope=drawing")
    if parse_options["target_length_unit"] != "mm":
        raise ValueError("Drawing facts currently support only a millimetre target unit")
    adapter_id = "oda-ezdxf-drawing" if artifact.format == "dwg" else "ezdxf-drawing"
    parser_version = f"ezdxf {ezdxf.__version__}"
    if artifact.format == "dwg":
        parse_options.update(
            {"conversion_output": "ACAD2018 DXF", "conversion_audit": True}
        )
        executable = _oda_executable(supplied.get("oda_executable"))
        if executable is None:
            return _failed(
                artifact,
                parse_options,
                adapter_id,
                f"{parser_version}; ODA File Converter unavailable",
                "ADAPTER_UNAVAILABLE",
                "DWG support requires an explicit ODA File Converter path "
                "(--oda-path or oda_executable); install locations are not searched automatically",
            )
        parser_version += f"; ODA File Converter exe-sha256:{hashlib.sha256(executable.read_bytes()).hexdigest()}"
    path = Path(artifact.source_locator)
    content = path.read_bytes()
    if hashlib.sha256(content).hexdigest() != artifact.sha256:
        raise ValueError("Source artifact changed after registration")
    try:
        document, auditor, conversion, _ = _read_document(artifact, content, supplied)
    except subprocess.TimeoutExpired:
        return _failed(
            artifact,
            parse_options,
            adapter_id,
            parser_version,
            "CONVERSION_FAILED",
            "ODA File Converter exceeded the configured timeout",
        )
    except (OSError, ValueError, ezdxf.DXFError) as error:
        code = "CONVERSION_FAILED" if artifact.format == "dwg" else "PARSE_FAILED"
        return _failed(
            artifact,
            parse_options,
            adapter_id,
            parser_version,
            code,
            f"Drawing could not be read: {type(error).__name__}: {error}",
        )

    external_references = []
    _clear_provenance(document)
    declared_xrefs = {
        block.name: block.block.dxf.xref_path
        for block in document.blocks
        if not block.is_any_layout and (block.block.is_xref or block.block.is_xref_overlay)
    }
    if parse_options["xref_mode"] != "unresolved":
        from cad_to_facts.drawing_xref import LoadedXref, XRefLoadError, XRefResolver

        def load_xref(xref_path: Path, remaining: float) -> LoadedXref:
            child_artifact = register(xref_path)
            if child_artifact.format not in {"dwg", "dxf"}:
                raise XRefLoadError("unsupported_format", "XREF is neither DWG nor DXF")
            child_options = dict(supplied)
            child_options["oda_timeout_seconds"] = min(
                float(supplied.get("oda_timeout_seconds", 120)), remaining
            )
            child_content = xref_path.read_bytes()
            if hashlib.sha256(child_content).hexdigest() != child_artifact.sha256:
                raise XRefLoadError("parse_failed", "XREF changed after registration")
            try:
                child_document, child_auditor, child_conversion, _ = _read_document(
                    child_artifact, child_content, child_options
                )
            except FileNotFoundError as error:
                raise XRefLoadError("adapter_unavailable", str(error)) from error
            except subprocess.TimeoutExpired as error:
                raise XRefLoadError("limit_exceeded", "XREF conversion timed out") from error
            except (OSError, ValueError, ezdxf.DXFError) as error:
                raise XRefLoadError(
                    "parse_failed", f"XREF parse failed: {type(error).__name__}: {error}"
                ) from error
            if hashlib.sha256(xref_path.read_bytes()).hexdigest() != child_artifact.sha256:
                raise XRefLoadError("parse_failed", "XREF changed while being parsed")
            _clear_provenance(child_document)
            return LoadedXref(child_artifact, child_document, child_auditor, child_conversion)

        resolver = XRefResolver(
            mode=parse_options["xref_mode"],
            roots=parse_options["xref_roots"],
            loader=load_xref,
            unit_name=_unit_name,
            tagger=_tag_provenance,
            max_depth=parse_options["xref_max_depth"],
            max_files=parse_options["xref_max_files"],
            max_bytes=parse_options["xref_max_bytes"],
            timeout_seconds=parse_options["xref_timeout_seconds"],
        )
        external_references = resolver.process(
            document,
            owner_artifact=artifact,
            owner_path=path,
            owner_conversion=conversion,
        )
        parse_options["xref_roots"] = [str(root) for root in resolver.roots]

    entities: list[EntityRef] = []
    entity_payload: dict[str, Any] = {}
    unit_name = _unit_name(document)
    layouts: list[DrawingLayout] = []
    blocks: list[DrawingBlock] = []
    diagnostics: list[Diagnostic] = []
    for reference in external_references:
        if reference.state != "resolved":
            diagnostics.append(_diagnostic(
                "DRAWING_EXTERNAL_REFERENCE",
                f"External reference {reference.block_name!r} is {reference.state}",
                discovery="partial",
            ))
        elif reference.entity_discovery != "complete" or reference.diagnostics:
            diagnostics.append(_diagnostic(
                "DRAWING_EXTERNAL_REFERENCE_PARTIAL",
                f"Resolved external reference {reference.block_name!r} has incomplete structure or diagnostics",
                discovery=reference.entity_discovery
                if reference.entity_discovery != "complete"
                else "none",
            ))

    def add_entity(item: Any, name: str, kind: str) -> str:
        entity_id = f"drawing:{len(entities)}"
        handle = item.dxf.handle
        native_refs = [
            {"type": "dxf_type", "value": item.dxftype()},
            {"type": "container", "value": name},
            {"type": "container_kind", "value": kind},
            {"type": "layer", "value": item.dxf.layer},
        ]
        if handle:
            native_refs.append({"type": "handle", "value": handle})
        source_hash, source_unit, derived_hash = _entity_provenance(
            item, artifact, unit_name, conversion
        )
        native_refs.extend([
            {"type": "source_artifact_sha256", "value": source_hash},
            {"type": "source_length_unit", "value": source_unit},
        ])
        entity = EntityRef(
            snapshot_id="0" * 64,
            entity_id=entity_id,
            entity_kind=item.dxftype().lower(),
            native_refs=native_refs,
            adapter_key=f"{kind}:{name}:{source_hash[:16]}:{handle or entity_id}",
        )
        entities.append(entity)
        entity_payload[entity_id] = {
            "entity": item,
            "container": name,
            "kind": kind,
            "artifact_sha256": source_hash,
            "length_unit": source_unit,
            "derived_dxf_sha256": derived_hash,
        }
        return entity_id

    def add_container(container: Any, name: str, kind: str) -> list[str]:
        ids: list[str] = []
        for item in container:
            ids.append(add_entity(item, name, kind))
            # Attached ATTRIB values are owned by the INSERT and are not yielded by
            # layout/block iteration; catalog them once in the referencing container.
            if item.dxftype() in {"INSERT", "MINSERT"}:
                for attribute in getattr(item, "attribs", ()):
                    ids.append(add_entity(attribute, name, kind))
        return ids

    for layout in document.layouts:
        kind = "model_space" if layout.is_modelspace else "paper_space"
        layouts.append(
            DrawingLayout(
                name=layout.name,
                kind=kind,
                entity_ids=add_container(layout, layout.name, kind),
            )
        )
    for block in document.blocks:
        if block.is_any_layout:
            continue
        name = block.name
        is_xref = name in declared_xrefs
        xref_path = declared_xrefs.get(name)
        if is_xref and parse_options["xref_mode"] == "unresolved":
            diagnostics.append(
                _diagnostic(
                    "DRAWING_EXTERNAL_REFERENCE",
                    f"External block reference {name!r} was not resolved",
                    discovery="partial",
                )
            )
        blocks.append(
            DrawingBlock(
                name=name,
                entity_ids=add_container(block, name, "block"),
                is_xref=is_xref,
                xref_path=xref_path,
            )
        )

    if auditor.has_errors:
        diagnostics.append(
            _diagnostic(
                "DRAWING_AUDIT_ERROR",
                "ezdxf recovery reported drawing audit errors",
                severity="error",
                discovery="partial",
                count=len(auditor.errors),
            )
        )
    if auditor.has_fixes:
        diagnostics.append(
            _diagnostic(
                "DRAWING_AUDIT_FIX",
                "ezdxf applied recovery fixes while loading the drawing",
                count=len(auditor.fixes),
            )
        )
    if not entities:
        diagnostics.append(
            _diagnostic(
                "NO_DRAWING_ENTITIES",
                "The drawing contains no cataloged entities; an empty catalog is not complete discovery",
                discovery="unknown",
            )
        )
    unit_name = _unit_name(document)
    if unit_name not in _VERIFIED_UNITS:
        diagnostics.append(
            _diagnostic(
                "UNIT_UNKNOWN",
                f"Drawing length unit {unit_name!r} is not verified; numeric lengths remain unknown",
            )
        )
    discovery = (
        "unknown"
        if not entities
        else "partial"
        if any(item.discovery_impact != "none" for item in diagnostics)
        else "complete"
    )
    status = "ready" if not diagnostics else "partial"
    drawing = DrawingStructure(
        source_format=artifact.format,
        dxf_version=document.dxfversion,
        layers=[
            DrawingLayer(name=layer.dxf.name, off=layer.is_off(), frozen=layer.is_frozen())
            for layer in document.layers
        ],
        layouts=layouts,
        blocks=blocks,
        external_references=external_references,
        conversion=conversion,
    )
    identity = {
        "artifact_sha256": artifact.sha256,
        "adapter_id": adapter_id,
        "adapter_version": "0.1.0",
        "parser_kernel_version": parser_version,
        "parse_options": parse_options,
    }
    snapshot_id = structured_hash("model-snapshot-id", identity)
    entities = [item.model_copy(update={"snapshot_id": snapshot_id}) for item in entities]
    snapshot = ModelSnapshot(
        artifact_sha256=artifact.sha256,
        snapshot_id=snapshot_id,
        snapshot_content_hash="0" * 64,
        adapter_id=adapter_id,
        adapter_version="0.1.0",
        parser_kernel_version=parser_version,
        parse_options=parse_options,
        units={"length": unit_name},
        status=status,
        entity_discovery=discovery,
        entities=entities,
        drawing=drawing,
        diagnostics=diagnostics,
    )
    if hashlib.sha256(path.read_bytes()).hexdigest() != artifact.sha256:
        raise ValueError("Source artifact changed during drawing parsing")
    snapshot.set_adapter_payload({"document": document, "entities": entity_payload})
    return bind_snapshot(snapshot)
