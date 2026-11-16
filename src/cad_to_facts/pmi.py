"""Read-only semantic PMI extraction for STEP AP242 files.

OCCT's XCAF GD&T projection supplies values and shape links; the raw STEP
model supplies the observed annotation inventory and measurement units. The
extractor never invents a dimension, tolerance, datum, unit or link that the
file does not declare.
"""

from collections import Counter
from contextlib import contextmanager
from dataclasses import dataclass
import hashlib
import math
from pathlib import Path
import re
from typing import Any

import OCP
from OCP.Bnd import Bnd_Box
from OCP.BRepBndLib import BRepBndLib
from OCP.BRepGProp import BRepGProp
from OCP.GProp import GProp_GProps
from OCP.IFSelect import IFSelect_RetDone
from OCP.Message import Message, Message_Printer
from OCP.STEPCAFControl import STEPCAFControl_Reader
from OCP.TCollection import TCollection_AsciiString, TCollection_ExtendedString
from OCP.TDF import TDF_AttributeIterator, TDF_Label, TDF_Tool
from OCP.TDocStd import TDocStd_Document
from OCP.TopAbs import TopAbs_EDGE, TopAbs_FACE, TopAbs_SOLID, TopAbs_VERTEX
from OCP.TopExp import TopExp_Explorer
from OCP.XCAFApp import XCAFApp_Application
from OCP.XCAFDoc import (
    XCAFDoc_Datum,
    XCAFDoc_DimTolTool,
    XCAFDoc_Dimension,
    XCAFDoc_DocumentTool,
    XCAFDoc_GeomTolerance,
    XCAFDoc_ShapeTool,
)
from OCP.XCAFDimTolObjects import XCAFDimTolObjects_DimensionType
from OCP.StepBasic import StepBasic_ConversionBasedUnit, StepBasic_SiUnit
from OCP.StepDimTol import (
    StepDimTol_Datum,
    StepDimTol_DatumFeature,
    StepDimTol_DatumSystem,
    StepDimTol_DatumTarget,
    StepDimTol_GeometricTolerance,
)
from OCP.StepShape import (
    StepShape_AngularLocation,
    StepShape_AngularSize,
    StepShape_DimensionalCharacteristicRepresentation,
    StepShape_DimensionalLocation,
    StepShape_DimensionalLocationWithPath,
    StepShape_DimensionalSize,
    StepShape_DimensionalSizeWithPath,
    StepShape_DirectedDimensionalLocation,
)
from OCP.collections import Sequence_TDF_Label

from cad_to_facts import __version__
from cad_to_facts.contract import bind_pmi_extract
from cad_to_facts.domain.pmi import (
    PmiAnnotation,
    PmiCoverage,
    PmiExtract,
    PmiGap,
    PmiSourceInventory,
    PmiTolerance,
    PmiUnitContext,
)
from cad_to_facts.domain.snapshot import Diagnostic, EntityRef, ModelSnapshot
from cad_to_facts.domain.source import SourceArtifact

_DIMENSION_CLASSES = (
    StepShape_DimensionalSize,
    StepShape_DimensionalSizeWithPath,
    StepShape_DimensionalLocation,
    StepShape_DimensionalLocationWithPath,
    StepShape_DirectedDimensionalLocation,
    StepShape_AngularLocation,
    StepShape_AngularSize,
)
_LENGTH_FACTORS = {
    1e-6: "nm",
    1e-3: "um",
    1.0: "mm",
    10.0: "cm",
    25.4: "in",
    304.8: "ft",
    914.4: "yd",
    1000.0: "m",
    1_000_000.0: "km",
}
_ANGLE_FACTORS = {
    1.0: "rad",
    math.pi / 180.0: "deg",
    math.pi / 10_800.0: "arcmin",
    math.pi / 648_000.0: "arcsec",
}
_LENGTH_FACTOR_BY_NAME = {name: factor for factor, name in _LENGTH_FACTORS.items()}
_ANGLE_FACTOR_BY_NAME = {name: factor for factor, name in _ANGLE_FACTORS.items()}

_PREFIX_FACTORS = {
    "StepBasic_spAtto": 1e-18,
    "StepBasic_spFemto": 1e-15,
    "StepBasic_spPico": 1e-12,
    "StepBasic_spNano": 1e-9,
    "StepBasic_spMicro": 1e-6,
    "StepBasic_spMilli": 1e-3,
    "StepBasic_spCenti": 1e-2,
    "StepBasic_spDeci": 1e-1,
    "StepBasic_spDeca": 1e1,
    "StepBasic_spHecto": 1e2,
    "StepBasic_spKilo": 1e3,
    "StepBasic_spMega": 1e6,
    "StepBasic_spGiga": 1e9,
    "StepBasic_spTera": 1e12,
    "StepBasic_spPeta": 1e15,
    "StepBasic_spExa": 1e18,
}
_UNSUPPORTED_CATEGORY_PATTERNS = {
    "surface_texture": re.compile(r"SURFACE_(TEXTURE|FINISH)"),
}


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


def _entry(label: TDF_Label) -> str:
    value = TCollection_AsciiString()
    TDF_Tool.Entry_s(label, value)
    return value.ToCString()


def _attribute(label: TDF_Label, attribute_type):
    iterator = TDF_AttributeIterator(label)
    while iterator.More():
        attribute = iterator.Value()
        if isinstance(attribute, attribute_type):
            return attribute
        iterator.Next()
    return None


def _label_sequence(getter) -> list[TDF_Label]:
    sequence = Sequence_TDF_Label()
    getter(sequence)
    return [sequence.Value(index) for index in range(1, sequence.Length() + 1)]


def _sequence_values(sequence) -> list[Any]:
    if sequence is None:
        return []
    if isinstance(sequence, (list, tuple)):
        return list(sequence)
    length = getattr(sequence, "Length", None)
    if callable(length):
        return [sequence.Value(index) for index in range(1, length() + 1)]
    try:
        return list(sequence)
    except TypeError:
        return []


def _enum_name(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        return value or None
    name = getattr(value, "name", None)
    return str(name) if name is not None else None


def _hstring(value: Any) -> str | None:
    if value is None:
        return None
    try:
        text = value.ToCString()
    except Exception:
        return None
    return str(text) if text else None


def _snake_case(value: str) -> str:
    first = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", "_", value)
    second = re.sub(r"(?<=[A-Z])(?=[A-Z][a-z])", "_", first)
    return second.lower()


def _canonical_type(enum_value: Any, prefix: str) -> tuple[str, str]:
    raw = _enum_name(enum_value) or "unknown"
    native = raw
    if raw.startswith(prefix):
        raw = raw[len(prefix) :]
    return ".".join(_snake_case(part) for part in raw.split("_") if part), native


def _is_presentation_dimension(enum_value: Any) -> bool:
    return _enum_name(enum_value) in {
        "XCAFDimTolObjects_DimensionType_DimensionPresentation",
        "XCAFDimTolObjects_DimensionType_CommonLabel",
    }


def _unwrap_select(value: Any) -> Any:
    if value is None:
        return None
    unwrap = getattr(value, "Value", None)
    if callable(unwrap):
        try:
            inner = unwrap()
        except Exception:
            return value
        if inner is not None:
            return inner
    return value


def _unit_kind(unit: Any) -> str | None:
    try:
        name = unit.DynamicType().Name()
    except Exception:
        name = type(unit).__name__
    if "LengthUnit" in name:
        return "length"
    if "PlaneAngleUnit" in name:
        return "angle"
    if "SolidAngleUnit" in name:
        return "solid_angle"
    return None


def _prefix_factor(unit: Any) -> float:
    has_prefix = getattr(unit, "HasPrefix", None)
    prefix = getattr(unit, "Prefix", None)
    if not callable(has_prefix) or not callable(prefix) or not has_prefix():
        return 1.0
    return _PREFIX_FACTORS.get(_enum_name(prefix()) or "", 1.0)


def _measure_with_unit_factor(unit: Any, kind: str, depth: int = 0) -> float | None:
    """Return the factor from one declared unit to mm or rad."""

    if unit is None or depth > 8 or _unit_kind(unit) != kind:
        return None
    if isinstance(unit, StepBasic_SiUnit) or "SiUnit" in type(unit).__name__:
        name = _enum_name(unit.Name()) or ""
        if kind == "length" and name.endswith("sunMetre"):
            return _prefix_factor(unit) * 1000.0
        if kind == "angle" and name.endswith("sunRadian"):
            return _prefix_factor(unit)
        return None
    conversion_factor = getattr(unit, "ConversionFactor", None)
    if callable(conversion_factor):
        measure = conversion_factor()
        if measure is None:
            return None
        value = getattr(measure, "ValueComponent", lambda: None)()
        if not isinstance(value, (int, float)) or not math.isfinite(value):
            return None
        base = _unwrap_select(getattr(measure, "UnitComponent", lambda: None)())
        base_factor = _measure_with_unit_factor(base, kind, depth + 1)
        if base_factor is None:
            return None
        return float(value) * base_factor
    return None


def _canonical_unit(factor: float | None, factors: dict[float, str]) -> str | None:
    if factor is None or not math.isfinite(factor) or factor <= 0:
        return None
    for known, name in factors.items():
        if math.isclose(factor, known, rel_tol=1e-9, abs_tol=0.0):
            return name
    return None


def _declared_length(value: float, unit: str | None) -> float | None:
    """Convert an XCAF system-length value (mm) back to the declared unit."""

    factor = _LENGTH_FACTOR_BY_NAME.get(unit) if unit is not None else None
    if factor is None or not math.isfinite(value):
        return None
    return value / factor


def _declared_angle(value: float, unit: str | None) -> float | None:
    """Convert an XCAF system-angle value (degrees) back to the declared unit."""

    factor = _ANGLE_FACTOR_BY_NAME.get(unit) if unit is not None else None
    if factor is None or not math.isfinite(value):
        return None
    return math.radians(value) / factor


def _decode_unit(unit: Any) -> tuple[str | None, str | None]:
    kind = _unit_kind(unit)
    if kind == "length":
        return kind, _canonical_unit(_measure_with_unit_factor(unit, "length"), _LENGTH_FACTORS)
    if kind == "angle":
        return kind, _canonical_unit(_measure_with_unit_factor(unit, "angle"), _ANGLE_FACTORS)
    return kind, None


@dataclass(frozen=True)
class _DimensionResult:
    annotation: PmiAnnotation | None
    gaps: list[PmiGap]
    presentation: bool
    has_magnitude_tolerance: bool


@dataclass(frozen=True)
class _ObservedInventory:
    dimension_entities: int
    dimension_representation_entities: int
    geometric_tolerance_entities: int
    datum_entities: int
    datum_feature_entities: int
    datum_system_entities: int
    unsupported_category_counts: dict[str, int]
    dimension_units: frozenset[str]
    angle_units: frozenset[str]
    tolerance_length_units: frozenset[str]
    unit_contexts: tuple[tuple[str | None, str | None, int], ...]


def _model_entities(reader: STEPCAFControl_Reader) -> list[Any]:
    model = reader.Reader().Model()
    return [model.Value(index) for index in range(1, model.NbEntities() + 1)]


def _tolerance_measure_unit(entity: Any) -> Any:
    measure = entity.Magnitude()
    getter = getattr(measure, "GetMeasureWithUnit", None)
    if callable(getter):
        return getter()
    return _unwrap_select(measure)


def _observe_inventory(reader: STEPCAFControl_Reader, presentation_count: int) -> _ObservedInventory:
    entities = _model_entities(reader)
    dimension_entities = sum(isinstance(entity, _DIMENSION_CLASSES) for entity in entities)
    representation_entities = sum(
        isinstance(entity, StepShape_DimensionalCharacteristicRepresentation)
        for entity in entities
    )
    tolerance_entities = sum(
        isinstance(entity, StepDimTol_GeometricTolerance) for entity in entities
    )
    datum_entities = sum(isinstance(entity, StepDimTol_Datum) for entity in entities)
    datum_feature_entities = sum(
        isinstance(entity, StepDimTol_DatumFeature) for entity in entities
    )
    datum_system_entities = sum(
        isinstance(entity, StepDimTol_DatumSystem) for entity in entities
    )
    unsupported: Counter[str] = Counter()
    if datum_system_entities:
        unsupported["datum_system"] = datum_system_entities
    datum_target_entities = sum(
        isinstance(entity, StepDimTol_DatumTarget) for entity in entities
    )
    if datum_target_entities:
        unsupported["datum_target"] = datum_target_entities
    for entity in entities:
        try:
            name = entity.DynamicType().Name().upper()
        except Exception:
            continue
        for category, pattern in _UNSUPPORTED_CATEGORY_PATTERNS.items():
            if pattern.search(name):
                unsupported[category] += 1

    dimension_units: set[str] = set()
    angle_units: set[str] = set()
    contexts: Counter[tuple[str | None, str | None]] = Counter()
    for entity in entities:
        if not isinstance(entity, StepShape_DimensionalCharacteristicRepresentation):
            continue
        representation = entity.Representation()
        if representation is None:
            continue
        try:
            context = representation.ContextOfItems()
        except Exception:
            continue
        units: list[Any] = []
        try:
            units = [
                context.UnitsValue(index)
                for index in range(1, context.NbUnits() + 1)
            ]
        except Exception:
            units = []
        length: str | None = None
        angle: str | None = None
        for unit in units:
            kind, canonical = _decode_unit(unit)
            if kind == "length" and canonical:
                dimension_units.add(canonical)
                length = canonical
            elif kind == "angle" and canonical:
                angle_units.add(canonical)
                angle = canonical
        contexts[(length, angle)] += 1

    tolerance_units: set[str] = set()
    for entity in entities:
        if not isinstance(entity, StepDimTol_GeometricTolerance):
            continue
        measure = _tolerance_measure_unit(entity)
        if measure is None:
            continue
        unit = _unwrap_select(getattr(measure, "UnitComponent", lambda: None)())
        kind, canonical = _decode_unit(unit)
        if kind == "length" and canonical:
            tolerance_units.add(canonical)

    return _ObservedInventory(
        dimension_entities=dimension_entities,
        dimension_representation_entities=representation_entities,
        geometric_tolerance_entities=tolerance_entities,
        datum_entities=datum_entities,
        datum_feature_entities=datum_feature_entities,
        datum_system_entities=datum_system_entities,
        unsupported_category_counts=dict(sorted(unsupported.items())),
        dimension_units=frozenset(dimension_units),
        angle_units=frozenset(angle_units),
        tolerance_length_units=frozenset(tolerance_units),
        unit_contexts=tuple(
            (length, angle, count) for (length, angle), count in sorted(contexts.items())
        ),
    )


def _presentation_count(document: TDocStd_Document) -> int:
    tool = XCAFDoc_DocumentTool.DimTolTool_s(document.Main())
    sequence = Sequence_TDF_Label()
    try:
        tool.GetGDTPresentations(sequence)
    except Exception:
        return 0
    return sequence.Length()


def _fingerprint(shape) -> tuple[float, ...]:
    volume_properties = GProp_GProps()
    BRepGProp.VolumeProperties_s(shape, volume_properties)
    area_properties = GProp_GProps()
    BRepGProp.SurfaceProperties_s(shape, area_properties)
    box = Bnd_Box()
    BRepBndLib.AddOptimal_s(shape, box, False, False)
    minimum = box.CornerMin()
    maximum = box.CornerMax()
    center = volume_properties.CentreOfMass()
    return (
        volume_properties.Mass(),
        area_properties.Mass(),
        center.X(),
        center.Y(),
        center.Z(),
        maximum.X() - minimum.X(),
        maximum.Y() - minimum.Y(),
        maximum.Z() - minimum.Z(),
    )


def _matches(left: tuple[float, ...], right: tuple[float, ...]) -> bool:
    return all(
        math.isclose(a, b, rel_tol=1e-6, abs_tol=1e-6)
        for a, b in zip(left, right, strict=True)
    )


def _solids(shape) -> list[Any]:
    if shape is None:
        return []
    solids: list[Any] = []
    explorer = TopExp_Explorer(shape, TopAbs_SOLID)
    while explorer.More():
        solids.append(explorer.Current())
        explorer.Next()
    return solids


def _solid_map(pmi_shape, snapshot_shape) -> dict[int, int]:
    """Map PMI-document solids to snapshot solids only when the match is unique."""

    pmi_fingerprints = [_fingerprint(solid) for solid in _solids(pmi_shape)]
    snapshot_fingerprints = [_fingerprint(solid) for solid in _solids(snapshot_shape)]
    candidates = {
        index: [
            other
            for other, fingerprint in enumerate(snapshot_fingerprints)
            if _matches(item, fingerprint)
        ]
        for index, item in enumerate(pmi_fingerprints)
    }
    usage = Counter(candidate for values in candidates.values() for candidate in values)
    mapping: dict[int, int] = {}
    for index, values in candidates.items():
        if len(values) == 1 and usage[values[0]] == 1:
            mapping[index] = values[0]
    return mapping


def _solid_owner_maps(pmi_shape) -> dict[Any, list[int]]:
    index: dict[Any, list[int]] = {}
    for solid_index, solid in enumerate(_solids(pmi_shape)):
        for shape_type in (TopAbs_FACE, TopAbs_EDGE, TopAbs_VERTEX):
            explorer = TopExp_Explorer(solid, shape_type)
            while explorer.More():
                shape = explorer.Current()
                owners = index.setdefault(shape, [])
                if solid_index not in owners:
                    owners.append(solid_index)
                explorer.Next()
    return index


def _owner_solids(shape, solid_shapes, owner_maps: dict[Any, list[int]]) -> list[int]:
    if shape is None:
        return []
    shape_type = shape.ShapeType()
    if shape_type == TopAbs_SOLID:
        return [
            index
            for index, solid in enumerate(solid_shapes)
            if solid.IsSame(shape)
        ]
    owners = owner_maps.get(shape)
    if owners is not None:
        return list(owners)
    for candidate, candidate_owners in owner_maps.items():
        if candidate.IsSame(shape):
            return list(candidate_owners)
    # A reference may point at a shell or compound rather than a face/edge/vertex.
    # Resolve it through its subshapes instead of treating the link as absent.
    resolved: list[int] = []
    for subshape_type in (TopAbs_FACE, TopAbs_EDGE, TopAbs_VERTEX):
        explorer = TopExp_Explorer(shape, subshape_type)
        while explorer.More():
            subshape = explorer.Current()
            subowners = owner_maps.get(subshape)
            if subowners is None:
                for candidate, candidate_owners in owner_maps.items():
                    if candidate.IsSame(subshape):
                        subowners = candidate_owners
                        break
            for owner in subowners or []:
                if owner not in resolved:
                    resolved.append(owner)
            explorer.Next()
    return resolved


def _short_shape_type(shape) -> str:
    try:
        name = shape.ShapeType().name
    except Exception:
        return "unknown"
    return {
        "TopAbs_FACE": "face",
        "TopAbs_EDGE": "edge",
        "TopAbs_VERTEX": "vertex",
        "TopAbs_SOLID": "solid",
    }.get(name, name.removeprefix("TopAbs_").lower())


def _link_info(
    label: TDF_Label,
    snapshot: ModelSnapshot,
    pmi_solid_mapping: dict[int, int],
    solid_shapes: list[Any],
    owner_maps: dict[Any, list[int]],
) -> tuple[list[EntityRef], list[dict[str, str]], str]:
    first = Sequence_TDF_Label()
    second = Sequence_TDF_Label()
    try:
        present = XCAFDoc_DimTolTool.GetRefShapeLabel_s(label, first, second)
    except Exception:
        present = False
    labels = (
        [first.Value(index) for index in range(1, first.Length() + 1)]
        + [second.Value(index) for index in range(1, second.Length() + 1)]
        if present
        else []
    )
    references: list[dict[str, str]] = []
    entity_ids: list[str] = []
    for linked in labels:
        try:
            shape = XCAFDoc_ShapeTool.GetShape_s(linked)
        except Exception:
            shape = None
        owners = _owner_solids(shape, solid_shapes, owner_maps) if shape is not None else []
        reference = {
            "kind": "xcaf_label",
            "entry": _entry(linked),
            "shape_type": _short_shape_type(shape) if shape is not None else "null",
        }
        reference_owners: list[str] = []
        for owner in owners:
            mapped = pmi_solid_mapping.get(owner)
            if mapped is None:
                continue
            entity_id = f"solid:{mapped}"
            if entity_id not in reference_owners:
                reference_owners.append(entity_id)
            if entity_id not in entity_ids:
                entity_ids.append(entity_id)
        if len(reference_owners) == 1:
            reference["owner_solid"] = reference_owners[0]
        elif reference_owners:
            reference["owner_solids"] = ",".join(reference_owners)
        references.append(reference)
    entities = [
        EntityRef(
            snapshot_id=snapshot.snapshot_id,
            entity_id=entity_id,
            entity_kind="solid",
            adapter_key=entity_id,
        )
        for entity_id in entity_ids
    ]
    if entities:
        status = "resolved"
    elif labels:
        status = "unresolved"
    else:
        status = "absent"
    return entities, references, status


def _canonical_modifiers(modifiers: Any, prefix: str) -> list[str]:
    values = []
    for modifier in _sequence_values(modifiers):
        canonical, _ = _canonical_type(modifier, prefix)
        if canonical and canonical != "none" and canonical not in values:
            values.append(canonical)
    return values


def _deviation_tolerance(lower: float, upper: float) -> PmiTolerance | None:
    if not (math.isfinite(lower) and math.isfinite(upper)):
        return None
    lower_magnitude = abs(lower)
    upper_magnitude = abs(upper)
    if lower_magnitude == 0.0 and upper_magnitude == 0.0:
        return None
    return PmiTolerance(
        form="deviation_magnitudes",
        lower_deviation_magnitude=lower_magnitude,
        upper_deviation_magnitude=upper_magnitude,
        sign_convention="not_reported_by_reader",
    )


def _limit_tolerance(lower: float, upper: float) -> tuple[PmiTolerance | None, bool]:
    if not (math.isfinite(lower) and math.isfinite(upper)):
        return None, False
    if lower == 0.0 and upper == 0.0:
        return None, False
    if lower > upper:
        return None, True
    return (
        PmiTolerance(
            form="limits",
            lower_limit=lower,
            upper_limit=upper,
        ),
        False,
    )


def _dimension_annotation(
    label: TDF_Label,
    snapshot: ModelSnapshot,
    length_unit: str | None,
    angle_unit: str | None,
    length_unit_ambiguous: bool,
    angle_unit_ambiguous: bool,
    pmi_solid_mapping: dict[int, int],
    solid_shapes: list[Any],
    owner_maps: dict[Any, list[int]],
) -> _DimensionResult:
    attribute = _attribute(label, XCAFDoc_Dimension)
    if attribute is None:
        return _DimensionResult(None, [], False, False)
    try:
        dimension = attribute.GetObject()
    except Exception:
        return _DimensionResult(None, [], False, False)
    if dimension is None:
        return _DimensionResult(None, [], False, False)
    semantic_name = _hstring(dimension.GetSemanticName())
    if _is_presentation_dimension(dimension.GetType()):
        return _DimensionResult(None, [], True, False)

    canonical_type, native_type = _canonical_type(
        dimension.GetType(), "XCAFDimTolObjects_DimensionType_"
    )
    native_ref = _entry(label)
    linked_entities, shape_refs, link_status = _link_info(
        label, snapshot, pmi_solid_mapping, solid_shapes, owner_maps
    )
    gaps: list[PmiGap] = []
    if link_status == "absent":
        gaps.append(
            PmiGap(
                kind="dimension",
                annotation_type=canonical_type,
                native_ref=native_ref,
                reason_code="PMI_GEOMETRY_LINK_ABSENT",
                message="The semantic dimension has no linked shape in the XCAF document",
                linked_entities=linked_entities,
            )
        )
    elif link_status == "unresolved":
        gaps.append(
            PmiGap(
                kind="dimension",
                annotation_type=canonical_type,
                native_ref=native_ref,
                reason_code="PMI_GEOMETRY_LINK_UNRESOLVED",
                message="Linked XCAF shapes could not be mapped to a snapshot solid",
                linked_entities=linked_entities,
            )
        )

    try:
        raw_value = float(dimension.GetValue())
        values = [float(item) for item in _sequence_values(dimension.GetValues())]
        lower_bound = float(dimension.GetLowerBound())
        upper_bound = float(dimension.GetUpperBound())
        lower_tolerance = float(dimension.GetLowerTolValue())
        upper_tolerance = float(dimension.GetUpperTolValue())
    except Exception:
        raw_value = float("nan")
        values = []
        lower_bound = upper_bound = 0.0
        lower_tolerance = upper_tolerance = 0.0

    is_angular = "angular" in canonical_type
    unit = angle_unit if is_angular else length_unit
    # OCCT's XCAF projection normalizes nominal values, length-based
    # tolerances and angular limits to system units: millimetres for length
    # and degrees for angles. Angular deviation magnitudes remain in the
    # representation's declared angle unit. Convert only the values XCAF
    # actually normalized.
    if unit is not None:
        if is_angular:
            converted_lower = _declared_angle(lower_bound, unit)
            converted_upper = _declared_angle(upper_bound, unit)
            if converted_lower is not None and converted_upper is not None:
                lower_bound = converted_lower
                upper_bound = converted_upper
        else:
            factor = _LENGTH_FACTOR_BY_NAME.get(unit)
            if factor is not None:
                lower_bound /= factor
                upper_bound /= factor
                lower_tolerance /= factor
                upper_tolerance /= factor

    tolerance, invalid_limits = _limit_tolerance(lower_bound, upper_bound)
    has_magnitude_tolerance = False
    if tolerance is None and not invalid_limits:
        tolerance = _deviation_tolerance(lower_tolerance, upper_tolerance)
        has_magnitude_tolerance = tolerance is not None
    if invalid_limits:
        gaps.append(
            PmiGap(
                kind="dimension",
                annotation_type=canonical_type,
                native_ref=native_ref,
                reason_code="PMI_TOLERANCE_INVALID",
                message="The dimension lower limit exceeds its upper limit",
                linked_entities=linked_entities,
            )
        )

    value_present = math.isfinite(raw_value) and not (
        raw_value == 0.0
        and not values
        and lower_bound == 0.0
        and upper_bound == 0.0
        and lower_tolerance == 0.0
        and upper_tolerance == 0.0
    )
    value: float | None = None
    if not value_present:
        gaps.append(
            PmiGap(
                kind="dimension",
                annotation_type=canonical_type,
                native_ref=native_ref,
                reason_code="PMI_VALUE_UNAVAILABLE",
                message="The semantic dimension carries no usable nominal value",
                linked_entities=linked_entities,
            )
        )
    elif not math.isfinite(raw_value) or (
        canonical_type.startswith("size.") and raw_value <= 0.0
    ):
        gaps.append(
            PmiGap(
                kind="dimension",
                annotation_type=canonical_type,
                native_ref=native_ref,
                reason_code="PMI_VALUE_INVALID",
                message="The semantic dimension value is not a valid finite size",
                linked_entities=linked_entities,
            )
        )
    elif unit is None:
        ambiguous = angle_unit_ambiguous if is_angular else length_unit_ambiguous
        gaps.append(
            PmiGap(
                kind="dimension",
                annotation_type=canonical_type,
                native_ref=native_ref,
                reason_code=(
                    "PMI_UNIT_AMBIGUOUS" if ambiguous else "PMI_UNIT_UNKNOWN"
                ),
                message=(
                    "The dimension value has no unambiguous unit context in the file"
                    if ambiguous
                    else "The dimension value has no readable unit context in the file"
                ),
                linked_entities=linked_entities,
            )
        )
    else:
        value = (
            _declared_angle(raw_value, unit)
            if is_angular
            else _declared_length(raw_value, unit)
        )
        if value is None:
            gaps.append(
                PmiGap(
                    kind="dimension",
                    annotation_type=canonical_type,
                    native_ref=native_ref,
                    reason_code="PMI_UNIT_UNKNOWN",
                    message="The dimension value could not be converted from the reader system unit",
                    linked_entities=linked_entities,
                )
            )

    if unit is None:
        # Tolerance magnitudes have no meaning without a resolved unit.
        tolerance = None
        has_magnitude_tolerance = False

    qualifier = _enum_name(dimension.GetQualifier())
    if qualifier:
        qualifier = _canonical_type(qualifier, "XCAFDimTolObjects_DimensionQualifier_")[0]
        if qualifier == "none":
            qualifier = None
    modifiers = _canonical_modifiers(
        getattr(dimension, "GetModifiers", lambda: [])(), "XCAFDimTolObjects_DimensionModif_"
    )
    annotation = PmiAnnotation(
        annotation_id="0" * 64,
        kind="dimension",
        annotation_type=canonical_type,
        native_type=native_type,
        name=_hstring(dimension.GetPresentationName()),
        semantic_name=semantic_name,
        value=value,
        unit=unit if value is not None else None,
        tolerance=tolerance,
        qualifier=qualifier,
        modifiers=modifiers,
        linked_entities=linked_entities,
        native_shape_refs=shape_refs,
        link_status=link_status,
        native_ref=native_ref,
    )
    return _DimensionResult(annotation, gaps, False, has_magnitude_tolerance)


def _geometric_tolerance_annotation(
    label: TDF_Label,
    snapshot: ModelSnapshot,
    tolerance_unit: str | None,
    tolerance_unit_ambiguous: bool,
    pmi_solid_mapping: dict[int, int],
    solid_shapes: list[Any],
    owner_maps: dict[Any, list[int]],
) -> tuple[PmiAnnotation | None, list[PmiGap]]:
    attribute = _attribute(label, XCAFDoc_GeomTolerance)
    if attribute is None:
        return None, []
    try:
        tolerance = attribute.GetObject()
    except Exception:
        return None, []
    if tolerance is None:
        return None, []

    canonical_type, native_type = _canonical_type(
        tolerance.GetType(), "XCAFDimTolObjects_GeomToleranceType_"
    )
    native_ref = _entry(label)
    linked_entities, shape_refs, link_status = _link_info(
        label, snapshot, pmi_solid_mapping, solid_shapes, owner_maps
    )
    gaps: list[PmiGap] = []
    if link_status == "absent":
        gaps.append(
            PmiGap(
                kind="geometric_tolerance",
                annotation_type=canonical_type,
                native_ref=native_ref,
                reason_code="PMI_GEOMETRY_LINK_ABSENT",
                message="The geometric tolerance has no linked shape in the XCAF document",
                linked_entities=linked_entities,
            )
        )
    elif link_status == "unresolved":
        gaps.append(
            PmiGap(
                kind="geometric_tolerance",
                annotation_type=canonical_type,
                native_ref=native_ref,
                reason_code="PMI_GEOMETRY_LINK_UNRESOLVED",
                message="Linked XCAF shapes could not be mapped to a snapshot solid",
                linked_entities=linked_entities,
            )
        )

    value: float | None = None
    try:
        raw_value = float(tolerance.GetValue())
    except Exception:
        raw_value = float("nan")
    if not math.isfinite(raw_value) or raw_value < 0.0:
        gaps.append(
            PmiGap(
                kind="geometric_tolerance",
                annotation_type=canonical_type,
                native_ref=native_ref,
                reason_code="PMI_VALUE_INVALID",
                message="The geometric tolerance magnitude is not a valid finite non-negative value",
                linked_entities=linked_entities,
            )
        )
    elif tolerance_unit is None:
        gaps.append(
            PmiGap(
                kind="geometric_tolerance",
                annotation_type=canonical_type,
                native_ref=native_ref,
                reason_code=(
                    "PMI_UNIT_AMBIGUOUS"
                    if tolerance_unit_ambiguous
                    else "PMI_UNIT_UNKNOWN"
                ),
                message=(
                    "The geometric tolerance magnitude has no unambiguous length unit"
                    if tolerance_unit_ambiguous
                    else "The geometric tolerance magnitude has no readable length unit"
                ),
                linked_entities=linked_entities,
            )
        )
    else:
        # XCAF reports geometric-tolerance magnitudes in system millimetres.
        value = raw_value / _LENGTH_FACTOR_BY_NAME[tolerance_unit]

    datums: list[str] = []
    datum_sequence = Sequence_TDF_Label()
    try:
        has_datums = XCAFDoc_DimTolTool.GetDatumOfTolerLabels_s(label, datum_sequence)
    except Exception:
        has_datums = False
    if has_datums:
        for datum_label in (
            datum_sequence.Value(index)
            for index in range(1, datum_sequence.Length() + 1)
        ):
            datum_attribute = _attribute(datum_label, XCAFDoc_Datum)
            identification = (
                _hstring(datum_attribute.GetIdentification())
                if datum_attribute is not None
                else None
            )
            if identification is None:
                gaps.append(
                    PmiGap(
                        kind="geometric_tolerance",
                        annotation_type=canonical_type,
                        native_ref=_entry(datum_label),
                        reason_code="PMI_DATUM_REFERENCE_UNRESOLVED",
                        message="A geometric tolerance datum reference has no identification",
                    )
                )
            elif identification not in datums:
                datums.append(identification)

    modifiers = _canonical_modifiers(
        getattr(tolerance, "GetModifiers", lambda: [])(),
        "XCAFDimTolObjects_GeomToleranceModif_",
    )
    material_requirement = _enum_name(tolerance.GetMaterialRequirementModifier())
    if material_requirement:
        material_requirement = _canonical_type(
            material_requirement, "XCAFDimTolObjects_GeomToleranceMatReqModif_"
        )[0]
        if material_requirement == "none":
            material_requirement = None
    zone_modifier = _enum_name(tolerance.GetZoneModifier())
    if zone_modifier:
        zone_modifier = _canonical_type(
            zone_modifier, "XCAFDimTolObjects_GeomToleranceZoneModif_"
        )[0]
        if zone_modifier == "none":
            zone_modifier = None

    annotation = PmiAnnotation(
        annotation_id="0" * 64,
        kind="geometric_tolerance",
        annotation_type=canonical_type,
        native_type=native_type,
        name=_hstring(tolerance.GetPresentationName()),
        semantic_name=_hstring(tolerance.GetSemanticName()),
        value=value,
        unit=tolerance_unit if value is not None else None,
        qualifier=None,
        modifiers=modifiers,
        material_requirement_modifier=material_requirement,
        zone_modifier=zone_modifier,
        datums=datums,
        linked_entities=linked_entities,
        native_shape_refs=shape_refs,
        link_status=link_status,
        native_ref=native_ref,
    )
    return annotation, gaps


def _datum_annotations(
    document: TDocStd_Document,
    snapshot: ModelSnapshot,
    pmi_solid_mapping: dict[int, int],
    solid_shapes: list[Any],
    owner_maps: dict[Any, list[int]],
) -> tuple[list[PmiAnnotation], list[PmiGap]]:
    tool = XCAFDoc_DocumentTool.DimTolTool_s(document.Main())
    labels = _label_sequence(tool.GetDatumLabels)
    merged: dict[tuple[str, str, str], dict[str, Any]] = {}
    gaps: list[PmiGap] = []
    for label in labels:
        attribute = _attribute(label, XCAFDoc_Datum)
        if attribute is None:
            continue
        identification = _hstring(attribute.GetIdentification())
        name = _hstring(attribute.GetName()) or ""
        description = _hstring(attribute.GetDescription()) or ""
        linked_entities, shape_refs, link_status = _link_info(
            label, snapshot, pmi_solid_mapping, solid_shapes, owner_maps
        )
        if not identification:
            gaps.append(
                PmiGap(
                    kind="datum",
                    annotation_type="datum",
                    native_ref=_entry(label),
                    reason_code="PMI_DATUM_IDENTIFICATION_MISSING",
                    message="A datum label has no identification and cannot be referenced",
                    linked_entities=linked_entities,
                )
            )
            continue
        key = (identification, name, description)
        entry = merged.setdefault(
            key,
            {
                "native_ref": _entry(label),
                "linked_entities": [],
                "shape_refs": [],
                "link_statuses": [],
            },
        )
        for entity in linked_entities:
            if entity not in entry["linked_entities"]:
                entry["linked_entities"].append(entity)
        entry["shape_refs"].extend(shape_refs)
        entry["link_statuses"].append(link_status)

    annotations: list[PmiAnnotation] = []
    for (identification, name, description), entry in sorted(
        merged.items(), key=lambda item: item[1]["native_ref"]
    ):
        statuses = entry["link_statuses"]
        if "resolved" in statuses:
            link_status = "resolved"
        elif "unresolved" in statuses:
            link_status = "unresolved"
        else:
            link_status = "absent"
        if link_status != "resolved":
            gaps.append(
                PmiGap(
                    kind="datum",
                    annotation_type="datum",
                    native_ref=entry["native_ref"],
                    reason_code=(
                        "PMI_GEOMETRY_LINK_ABSENT"
                        if link_status == "absent"
                        else "PMI_GEOMETRY_LINK_UNRESOLVED"
                    ),
                    message=(
                        "The datum has no linked datum feature in the XCAF document"
                        if link_status == "absent"
                        else "The datum datum-feature link could not be mapped to a snapshot solid"
                    ),
                    linked_entities=entry["linked_entities"],
                )
            )
        annotations.append(
            PmiAnnotation(
                annotation_id="0" * 64,
                kind="datum",
                annotation_type="datum",
                native_type="datum",
                name=description or None,
                semantic_name=identification,
                linked_entities=entry["linked_entities"],
                native_shape_refs=entry["shape_refs"],
                link_status=link_status,
                native_ref=entry["native_ref"],
            )
        )
    return annotations, gaps


def _empty_extract(
    snapshot: ModelSnapshot,
    artifact_sha256: str,
    status: str,
    message: str,
) -> PmiExtract:
    diagnostic = Diagnostic(
        code="PMI_READ_FAILED",
        severity="fatal",
        stage="read",
        message=message,
        scope_refs=["pmi"],
        affects=["pmi"],
        impact="fatal",
        discovery_impact="unknown",
    )
    extract = PmiExtract(
        pmi_id="0" * 64,
        artifact_sha256=artifact_sha256,
        snapshot_id=snapshot.snapshot_id,
        snapshot_content_hash=snapshot.snapshot_content_hash,
        extractor_version=__version__,
        inventory=PmiSourceInventory(
            dimension_entities=0,
            dimension_representation_entities=0,
            geometric_tolerance_entities=0,
            datum_entities=0,
            datum_feature_entities=0,
            datum_system_entities=0,
            presentation_entities=0,
        ),
        coverage=PmiCoverage(
            dimension_observed=0,
            dimension_annotations=0,
            dimension_with_value=0,
            geometric_tolerance_observed=0,
            geometric_tolerance_annotations=0,
            geometric_tolerance_with_value=0,
            datum_observed=0,
            datum_annotations=0,
            datum_with_identification=0,
            link_resolved=0,
            link_unresolved=0,
            link_absent=0,
            discovery="unknown",
        ),
        diagnostics=[diagnostic],
        status=status,
        complete=False,
    )
    return bind_pmi_extract(extract)


def extract_pmi(artifact: SourceArtifact, snapshot: ModelSnapshot) -> PmiExtract:
    """Extract semantic PMI from a STEP artifact without modifying the source."""

    if artifact.format != "step":
        raise ValueError("Semantic PMI extraction currently supports STEP artifacts only")
    if artifact.sha256 != snapshot.artifact_sha256:
        raise ValueError("The artifact and snapshot identities do not match")
    if snapshot.drawing is not None:
        raise ValueError("Semantic PMI extraction requires a STEP snapshot, not a drawing")
    path = Path(artifact.source_locator)
    content = path.read_bytes()
    if hashlib.sha256(content).hexdigest() != artifact.sha256:
        raise ValueError("Source artifact changed after registration")

    application = XCAFApp_Application.GetApplication_s()
    document = TDocStd_Document(TCollection_ExtendedString("MDTV-XCAF"))
    application.NewDocument(TCollection_ExtendedString("MDTV-XCAF"), document)
    reader = STEPCAFControl_Reader()
    reader.SetGDTMode(True)
    reader.SetNameMode(True)
    try:
        with _quiet_occt_messages():
            read_status = reader.ReadFile(str(path))
        roots = reader.NbRootsForTransfer()
    except Exception as error:
        return _empty_extract(
            snapshot,
            artifact.sha256,
            "failed",
            f"OCCT could not read the STEP file for PMI: {type(error).__name__}",
        )
    if read_status != IFSelect_RetDone or roots == 0:
        return _empty_extract(
            snapshot, artifact.sha256, "failed", "OCCT could not read the STEP file for PMI"
        )
    reader.Reader().SetSystemLengthUnit(1.0)
    try:
        with _quiet_occt_messages():
            transferred = reader.Transfer(document)
    except Exception as error:
        return _empty_extract(
            snapshot,
            artifact.sha256,
            "failed",
            f"OCCT could not transfer the STEP roots for PMI: {type(error).__name__}",
        )
    if not transferred:
        return _empty_extract(
            snapshot,
            artifact.sha256,
            "failed",
            "OCCT could not transfer the STEP roots into the XCAF document for PMI",
        )

    presentation_count = _presentation_count(document)
    observed = _observe_inventory(reader, presentation_count)
    tool = XCAFDoc_DocumentTool.DimTolTool_s(document.Main())
    shape_tool = XCAFDoc_DocumentTool.ShapeTool_s(document.Main())
    has_semantic_pmi = bool(
        observed.dimension_entities
        or observed.geometric_tolerance_entities
        or observed.datum_entities
    )
    if has_semantic_pmi:
        pmi_shape = shape_tool.GetOneShape()
        payload = getattr(snapshot, "_adapter_payload", None) or {}
        snapshot_shape = payload.get("shape")
        pmi_solid_mapping = (
            _solid_map(pmi_shape, snapshot_shape)
            if pmi_shape is not None and snapshot_shape is not None
            else {}
        )
        solid_shapes = _solids(pmi_shape)
        owner_maps = _solid_owner_maps(pmi_shape)
    else:
        pmi_solid_mapping = {}
        solid_shapes = []
        owner_maps = {}

    dimension_length_unit = (
        next(iter(observed.dimension_units)) if len(observed.dimension_units) == 1 else None
    )
    dimension_angle_unit = (
        next(iter(observed.angle_units)) if len(observed.angle_units) == 1 else None
    )
    tolerance_length_unit = (
        next(iter(observed.tolerance_length_units))
        if len(observed.tolerance_length_units) == 1
        else None
    )
    dimension_length_unit_ambiguous = len(observed.dimension_units) > 1
    dimension_angle_unit_ambiguous = len(observed.angle_units) > 1
    tolerance_length_unit_ambiguous = len(observed.tolerance_length_units) > 1

    annotations: list[PmiAnnotation] = []
    gaps: list[PmiGap] = []
    magnitude_tolerance_count = 0
    presentation_labels = 0
    for label in _label_sequence(tool.GetDimensionLabels):
        result = _dimension_annotation(
            label,
            snapshot,
            dimension_length_unit,
            dimension_angle_unit,
            dimension_length_unit_ambiguous,
            dimension_angle_unit_ambiguous,
            pmi_solid_mapping,
            solid_shapes,
            owner_maps,
        )
        if result.annotation is not None:
            annotations.append(result.annotation)
        gaps.extend(result.gaps)
        presentation_labels += int(result.presentation)
        magnitude_tolerance_count += int(result.has_magnitude_tolerance)
    for label in _label_sequence(tool.GetGeomToleranceLabels):
        annotation, annotation_gaps = _geometric_tolerance_annotation(
            label,
            snapshot,
            tolerance_length_unit,
            tolerance_length_unit_ambiguous,
            pmi_solid_mapping,
            solid_shapes,
            owner_maps,
        )
        if annotation is not None:
            annotations.append(annotation)
        gaps.extend(annotation_gaps)
    datum_annotations, datum_gaps = _datum_annotations(
        document, snapshot, pmi_solid_mapping, solid_shapes, owner_maps
    )
    annotations.extend(datum_annotations)
    gaps.extend(datum_gaps)

    for category, count in observed.unsupported_category_counts.items():
        gaps.append(
            PmiGap(
                kind=None,
                annotation_type=category,
                native_ref="model",
                reason_code="PMI_UNSUPPORTED_TYPE",
                message=(
                    f"The file declares {count} {category} entities that this PMI profile "
                    "does not extract"
                ),
            )
        )

    dimension_annotations = [item for item in annotations if item.kind == "dimension"]
    tolerance_annotations = [
        item for item in annotations if item.kind == "geometric_tolerance"
    ]
    datum_annotations = [item for item in annotations if item.kind == "datum"]
    dimension_with_value = sum(item.value is not None for item in dimension_annotations)
    tolerance_with_value = sum(item.value is not None for item in tolerance_annotations)
    datum_with_identification = sum(
        bool(item.semantic_name) for item in datum_annotations
    )

    diagnostics: list[Diagnostic] = []
    if magnitude_tolerance_count:
        diagnostics.append(
            Diagnostic(
                code="PMI_TOLERANCE_SIGN_NOT_REPORTED",
                severity="info",
                stage="read",
                message=(
                    "OCCT exposes dimension tolerance values as magnitudes; the signed "
                    "deviation direction is not preserved and is not inferred"
                ),
                scope_refs=["pmi"],
                affects=["pmi"],
                impact="partial",
                discovery_impact="none",
                count=magnitude_tolerance_count,
            )
        )
    if len(observed.dimension_units) > 1:
        diagnostics.append(
            Diagnostic(
                code="PMI_UNIT_CONTEXT_AMBIGUOUS",
                severity="warning",
                stage="read",
                message=(
                    "Dimension representations use more than one length unit; unitless "
                    "dimension values are not emitted"
                ),
                scope_refs=["pmi"],
                affects=["pmi"],
                impact="partial",
                discovery_impact="none",
                details={"length_units": sorted(observed.dimension_units)},
            )
        )
    if len(observed.angle_units) > 1:
        diagnostics.append(
            Diagnostic(
                code="PMI_UNIT_CONTEXT_AMBIGUOUS",
                severity="warning",
                stage="read",
                message=(
                    "Dimension representations use more than one angle unit; angular "
                    "dimension values are not emitted"
                ),
                scope_refs=["pmi"],
                affects=["pmi"],
                impact="partial",
                discovery_impact="none",
                details={"angle_units": sorted(observed.angle_units)},
            )
        )
    if len(observed.tolerance_length_units) > 1:
        diagnostics.append(
            Diagnostic(
                code="PMI_UNIT_CONTEXT_AMBIGUOUS",
                severity="warning",
                stage="read",
                message=(
                    "Geometric tolerances use more than one length unit; tolerance values "
                    "without a single unit are not emitted"
                ),
                scope_refs=["pmi"],
                affects=["pmi"],
                impact="partial",
                discovery_impact="none",
                details={"length_units": sorted(observed.tolerance_length_units)},
            )
        )

    coverage = PmiCoverage(
        dimension_observed=observed.dimension_entities,
        dimension_annotations=len(dimension_annotations),
        dimension_with_value=dimension_with_value,
        geometric_tolerance_observed=observed.geometric_tolerance_entities,
        geometric_tolerance_annotations=len(tolerance_annotations),
        geometric_tolerance_with_value=tolerance_with_value,
        datum_observed=observed.datum_entities,
        datum_annotations=len(datum_annotations),
        datum_with_identification=datum_with_identification,
        link_resolved=sum(item.link_status == "resolved" for item in annotations),
        link_unresolved=sum(item.link_status == "unresolved" for item in annotations),
        link_absent=sum(item.link_status == "absent" for item in annotations),
        discovery=(
            "complete"
            if not observed.unsupported_category_counts
            and len(dimension_annotations) >= observed.dimension_entities
            and len(tolerance_annotations) >= observed.geometric_tolerance_entities
            and len(datum_annotations) >= observed.datum_entities
            else "partial"
        ),
    )
    if coverage.discovery != "complete":
        diagnostics.append(
            Diagnostic(
                code="PMI_COVERAGE_INCOMPLETE",
                severity="warning",
                stage="read",
                message=(
                    "The extracted PMI annotation counts do not account for every observed "
                    "semantic PMI entity"
                ),
                scope_refs=["pmi"],
                affects=["pmi"],
                impact="partial",
                discovery_impact="partial",
                details={
                    "dimension_observed": observed.dimension_entities,
                    "dimension_annotations": len(dimension_annotations),
                    "geometric_tolerance_observed": observed.geometric_tolerance_entities,
                    "geometric_tolerance_annotations": len(tolerance_annotations),
                    "datum_observed": observed.datum_entities,
                    "datum_annotations": len(datum_annotations),
                },
            )
        )

    units: dict[str, str] = {}
    if dimension_length_unit:
        units["dimension_length"] = dimension_length_unit
    if dimension_angle_unit:
        units["dimension_angle"] = dimension_angle_unit
    if tolerance_length_unit:
        units["geometric_tolerance_length"] = tolerance_length_unit
    unit_contexts = [
        PmiUnitContext(
            length=length,
            angle=angle,
            dimension_representation_count=count,
        )
        for length, angle, count in observed.unit_contexts
    ]
    status = "partial" if gaps or coverage.discovery != "complete" else "ready"
    extract = PmiExtract(
        pmi_id="0" * 64,
        artifact_sha256=artifact.sha256,
        snapshot_id=snapshot.snapshot_id,
        snapshot_content_hash=snapshot.snapshot_content_hash,
        extractor_version=__version__,
        units=units,
        unit_contexts=unit_contexts,
        inventory=PmiSourceInventory(
            dimension_entities=observed.dimension_entities,
            dimension_representation_entities=observed.dimension_representation_entities,
            geometric_tolerance_entities=observed.geometric_tolerance_entities,
            datum_entities=observed.datum_entities,
            datum_feature_entities=observed.datum_feature_entities,
            datum_system_entities=observed.datum_system_entities,
            presentation_entities=max(presentation_count, presentation_labels),
            unsupported_category_counts=observed.unsupported_category_counts,
        ),
        annotations=annotations,
        gaps=gaps,
        coverage=coverage,
        diagnostics=diagnostics,
        status=status,
        complete=(
            status == "ready"
            and coverage.discovery == "complete"
            and not gaps
            and not observed.unsupported_category_counts
        ),
    )
    if hashlib.sha256(path.read_bytes()).hexdigest() != artifact.sha256:
        raise ValueError("Source artifact changed while PMI was being read")
    return bind_pmi_extract(extract)
