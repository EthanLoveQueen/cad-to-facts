import hashlib
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import OCP
from OCP.IFSelect import IFSelect_RetDone
from OCP.Message import Message, Message_Printer
from OCP.STEPCAFControl import STEPCAFControl_Reader
from OCP.STEPControl import STEPControl_Reader
from OCP.TCollection import TCollection_AsciiString, TCollection_ExtendedString
from OCP.TDocStd import TDocStd_Document
from OCP.TopAbs import TopAbs_SOLID
from OCP.TopExp import TopExp_Explorer
from OCP.TopoDS import TopoDS_Shape
from OCP.XCAFApp import XCAFApp_Application
from OCP.XCAFDoc import XCAFDoc_DocumentTool
from OCP.collections import Sequence_TCollection_AsciiString

from cad_to_facts.assembly import extract_structure

from cad_to_facts.domain import SourceArtifact
from cad_to_facts.domain.snapshot import Diagnostic, EntityRef, ModelSnapshot
from cad_to_facts.identity import structured_hash

_LENGTH_UNITS = {
    "MM": "mm",
    "MILLIMETRE": "mm",
    "MILLIMETER": "mm",
    "CM": "cm",
    "CENTIMETRE": "cm",
    "CENTIMETER": "cm",
    "IN": "in",
    "INCH": "in",
}
_ANGLE_UNITS = {"RAD": "rad", "RADIAN": "rad", "RADIANS": "rad"}
_SOLID_ANGLE_UNITS = {"SR": "sr", "STERADIAN": "sr", "STERADIANS": "sr"}


def _strings(values: Sequence_TCollection_AsciiString) -> list[str]:
    return [value.ToCString() for value in values]


def _file_units(reader: STEPControl_Reader) -> tuple[dict[str, str], bool]:
    """Return declared units and whether the length unit is in the verified set."""

    lengths = Sequence_TCollection_AsciiString()
    angles = Sequence_TCollection_AsciiString()
    solid_angles = Sequence_TCollection_AsciiString()
    reader.FileUnits(lengths, angles, solid_angles)
    length_names = _strings(lengths)
    angle_names = _strings(angles)
    solid_angle_names = _strings(solid_angles)
    if len(length_names) != 1:
        raise ValueError(f"Unsupported or ambiguous STEP length units: {length_names}")
    length_name = length_names[0]
    verified = length_name.upper() in _LENGTH_UNITS
    units = {"length": _LENGTH_UNITS.get(length_name.upper(), length_name.lower())}
    if angle_names:
        units["angle"] = _ANGLE_UNITS.get(angle_names[0].upper(), angle_names[0])
    if solid_angle_names:
        units["solid_angle"] = _SOLID_ANGLE_UNITS.get(solid_angle_names[0].upper(), solid_angle_names[0])
    return units, verified


def _solid_keys(shape: TopoDS_Shape) -> list[str]:
    keys: list[str] = []
    explorer = TopExp_Explorer(shape, TopAbs_SOLID)
    while explorer.More():
        keys.append(f"solid:{len(keys)}")
        explorer.Next()
    return keys


def _entity_type_count(reader: STEPControl_Reader, entity_type: str) -> int:
    model = reader.Model()
    return sum(
        1
        for index in range(1, model.NbEntities() + 1)
        if model.Value(index).DynamicType().Name() == entity_type
    )


def _assembly_occurrence_count(reader: STEPControl_Reader) -> int:
    """Count NAUO records in the loaded STEP model before topology is flattened."""

    return _entity_type_count(reader, "StepRepr_NextAssemblyUsageOccurrence")


@contextmanager
def _quiet_occt_messages():
    messenger = Message.DefaultMessenger_s()
    printers = list(messenger.Printers())
    messenger.RemovePrinters(Message_Printer.get_type_descriptor_s())
    try:
        yield
    finally:
        for printer in printers:
            messenger.AddPrinter(printer)


def _has_complete_step_framing(content: bytes) -> bool:
    """Reject inputs known to crash OCCT before its STEP parser is entered."""

    tokens = [
        b"ISO-10303-21;",
        b"HEADER;",
        b"FILE_DESCRIPTION",
        b"FILE_NAME",
        b"FILE_SCHEMA",
        b"ENDSEC;",
        b"DATA;",
        b"ENDSEC;",
        b"END-ISO-10303-21;",
    ]
    upper = content.upper()
    position = 0
    for token in tokens:
        position = upper.find(token, position)
        if position < 0:
            return False
        position += len(token)
    return True


def read(artifact: SourceArtifact, options: dict[str, Any] | None = None) -> ModelSnapshot:
    """Read one artifact through its format-specific adapter."""

    if artifact.format in {"dwg", "dxf"} or (options or {}).get("read_scope") == "drawing":
        from cad_to_facts.drawing import read_drawing

        if artifact.format not in {"dwg", "dxf"}:
            raise ValueError("read_scope=drawing requires a DWG or DXF artifact")
        return read_drawing(artifact, options)
    if options and "oda_executable" in options:
        raise ValueError("oda_executable is valid only for DWG artifacts")

    parse_options = {"read_scope": "single_part", "target_length_unit": "mm", **(options or {})}
    if parse_options["target_length_unit"] != "mm":
        raise ValueError("P1 currently supports only an explicit millimetre target unit")
    if parse_options["read_scope"] not in {"single_part", "assembly"}:
        raise ValueError("Supported STEP read scopes are single_part and assembly")
    path = Path(artifact.source_locator)
    content = path.read_bytes()
    if hashlib.sha256(content).hexdigest() != artifact.sha256:
        raise ValueError("Source artifact changed after registration")

    identity = {
        "artifact_sha256": artifact.sha256,
        "adapter_id": "occt-step",
        "adapter_version": "0.1.0",
        "parser_kernel_version": OCP.__version__,
        "parse_options": parse_options,
    }

    def failed(code: str, message: str) -> ModelSnapshot:
        failed_snapshot_id = structured_hash("model-snapshot-id", identity)
        snapshot = ModelSnapshot(
            artifact_sha256=artifact.sha256,
            snapshot_id=failed_snapshot_id,
            snapshot_content_hash="0" * 64,
            adapter_id="occt-step",
            adapter_version="0.1.0",
            parser_kernel_version=OCP.__version__,
            parse_options=parse_options,
            units={},
            status="failed",
            entity_discovery="unknown",
            entities=[],
            diagnostics=[
                Diagnostic(
                    code=code,
                    severity="fatal",
                    stage="read",
                    message=message,
                    scope_refs=[parse_options["read_scope"]],
                    affects=["discovery", "geometry"],
                    impact="fatal",
                    discovery_impact="unknown",
                )
            ],
        )
        object.__setattr__(
            snapshot,
            "snapshot_content_hash",
            structured_hash("model-snapshot", snapshot, exclude={"snapshot_content_hash"}),
        )
        return snapshot

    if artifact.format != "step":
        return failed(
            "UNSUPPORTED_FORMAT",
            f"The STEP adapter does not support artifact format {artifact.format!r}",
        )
    if not _has_complete_step_framing(content):
        return failed(
            "PARSE_FAILED",
            "The artifact lacks a complete STEP header/data envelope; OCCT was not entered",
        )

    assembly_structure = None
    assembly_diagnostics: list[Diagnostic] = []
    assembly_occurrences = 0
    if parse_options["read_scope"] == "assembly":
        application = XCAFApp_Application.GetApplication_s()
        document = TDocStd_Document(TCollection_ExtendedString("MDTV-XCAF"))
        application.NewDocument(TCollection_ExtendedString("MDTV-XCAF"), document)
        xcaf_reader = STEPCAFControl_Reader()
        xcaf_reader.SetNameMode(True)
        with _quiet_occt_messages():
            read_status = xcaf_reader.ReadFile(str(path))
        roots = xcaf_reader.NbRootsForTransfer()
        if read_status != IFSelect_RetDone or roots == 0:
            return failed("PARSE_FAILED", "OCCT could not read a STEP model from the artifact")
        reader = xcaf_reader.Reader()
        assembly_occurrences = _assembly_occurrence_count(reader)
        source_products = _entity_type_count(reader, "StepBasic_Product")
        parse_options["source_structure"] = (
            "assembly" if assembly_occurrences else "single_part"
        )
        try:
            units, length_unit_verified = _file_units(reader)
        except ValueError as error:
            return failed("UNIT_UNKNOWN", str(error))
        reader.SetSystemLengthUnit(1.0)
        with _quiet_occt_messages():
            transferred_ok = xcaf_reader.Transfer(document)
        if not transferred_ok:
            return failed("PARSE_FAILED", "OCCT did not transfer the STEP roots into XCAF")
        transferred = roots
        shape = XCAFDoc_DocumentTool.ShapeTool_s(document.Main()).GetOneShape()
    else:
        reader = STEPControl_Reader()
        with _quiet_occt_messages():
            read_status = reader.ReadFile(str(path))
        roots = reader.NbRootsForTransfer()
        if read_status != IFSelect_RetDone or roots == 0:
            return failed("PARSE_FAILED", "OCCT could not read a STEP model from the artifact")
        assembly_occurrences = _assembly_occurrence_count(reader)
        if assembly_occurrences:
            parse_options["source_structure"] = "assembly_flattened"
        try:
            units, length_unit_verified = _file_units(reader)
        except ValueError as error:
            return failed("UNIT_UNKNOWN", str(error))
        reader.SetSystemLengthUnit(1.0)
        with _quiet_occt_messages():
            transferred = reader.TransferRoots()
        if transferred <= 0:
            return failed("PARSE_FAILED", "OCCT did not transfer any STEP roots")
        shape = reader.OneShape()
    snapshot_id = structured_hash("model-snapshot-id", identity)
    occurrence_shapes = {}
    if parse_options["read_scope"] == "assembly":
        assembly_structure, assembly_diagnostics = extract_structure(
            document,
            snapshot_id,
            source_products,
            assembly_occurrences,
            occurrence_shapes,
        )
    keys = _solid_keys(shape)

    entities = [
        EntityRef(snapshot_id=snapshot_id, entity_id=key, entity_kind="solid", adapter_key=key)
        for key in keys
    ]
    discovery = assembly_structure.discovery if assembly_structure is not None else "complete"
    diagnostics: list[Diagnostic] = list(assembly_diagnostics)
    if assembly_occurrences and parse_options["read_scope"] == "single_part":
        discovery = "partial"
        diagnostics.append(
            Diagnostic(
                code="ASSEMBLY_STRUCTURE_NOT_REPRESENTED",
                severity="warning",
                stage="read",
                message=(
                    f"STEP contains {assembly_occurrences} assembly usage occurrences; the "
                    "single-part adapter flattens referenced solids and does not represent "
                    "assembly structure, occurrence paths, or component names"
                ),
                scope_refs=[parse_options["read_scope"]],
                affects=["discovery", "geometry"],
                impact="partial",
                discovery_impact="partial",
                count=assembly_occurrences,
            )
        )
    if not length_unit_verified:
        diagnostics.append(
            Diagnostic(
                code="UNIT_UNKNOWN",
                severity="warning",
                stage="read",
                message=(
                    f"STEP declares length unit {units['length']!r}, which is outside the "
                    "verified measurement units (mm, cm, in); length facts are blocked"
                ),
                scope_refs=[parse_options["read_scope"]],
                affects=["geometry", "measure"],
                impact="partial",
                discovery_impact="none",
                details={"declared_length_unit": units["length"]},
            )
        )
    if not entities:
        discovery = "unknown"
        diagnostics.append(
            Diagnostic(
                code="NO_SOLIDS",
                severity="warning",
                stage="read",
                message="The STEP model transferred successfully but contains no solid entities",
                scope_refs=[parse_options["read_scope"]],
                affects=["discovery", "geometry"],
                impact="partial",
                discovery_impact="unknown",
                count=0,
            )
        )
    if transferred < roots:
        discovery = "partial"
        diagnostics.append(
            Diagnostic(
                code="ROOTS_PARTIAL",
                severity="warning",
                stage="read",
                message="OCCT transferred fewer roots than the file declares",
                scope_refs=[parse_options["read_scope"]],
                affects=["discovery", "geometry"],
                impact="partial",
                discovery_impact="partial",
                details={"declared_roots": roots, "transferred_roots": transferred},
            )
        )
    snapshot = ModelSnapshot(
        artifact_sha256=artifact.sha256,
        snapshot_id=snapshot_id,
        snapshot_content_hash="0" * 64,
        adapter_id="occt-step",
        adapter_version="0.1.0",
        parser_kernel_version=OCP.__version__,
        parse_options=parse_options,
        units=units,
        status="partial" if diagnostics or discovery != "complete" else "ready",
        entity_discovery=discovery,
        entities=entities,
        assembly=assembly_structure,
        diagnostics=diagnostics,
    )
    object.__setattr__(
        snapshot,
        "snapshot_content_hash",
        structured_hash("model-snapshot", snapshot, exclude={"snapshot_content_hash"}),
    )
    snapshot.set_adapter_payload({
        "shape": shape,
        "solid_keys": keys,
        "occurrence_shapes": occurrence_shapes,
    })
    if hashlib.sha256(path.read_bytes()).hexdigest() != artifact.sha256:
        raise ValueError("Source artifact changed while it was being read")
    return snapshot
