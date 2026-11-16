"""Self-written AP242 semantic-PMI fixtures generated through OCCT XCAF.

These helpers exercise cad-to-facts' owned reader and contract behavior. They
are self-written and self-read, so they do not establish exporter
interoperability, full AP242 conformance or external-corpus evidence. The
generated files carry a current writer timestamp and are intended for temporary
test directories, not as pinned corpus bytes.
"""

from pathlib import Path
import math
import re
from typing import Literal

from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox
from OCP.IFSelect import IFSelect_RetDone
from OCP.Interface import Interface_Static
from OCP.STEPCAFControl import STEPCAFControl_Writer
from OCP.STEPControl import STEPControl_AsIs
from OCP.TCollection import TCollection_ExtendedString, TCollection_HAsciiString
from OCP.TDocStd import TDocStd_Document
from OCP.XCAFApp import XCAFApp_Application
from OCP.XCAFDoc import (
    XCAFDoc_Datum,
    XCAFDoc_Dimension,
    XCAFDoc_DocumentTool,
    XCAFDoc_GeomTolerance,
)
from OCP.XCAFDimTolObjects import (
    XCAFDimTolObjects_DatumObject,
    XCAFDimTolObjects_DimensionObject,
    XCAFDimTolObjects_DimensionType_Size_Angular,
    XCAFDimTolObjects_DimensionType_Size_Thickness,
    XCAFDimTolObjects_GeomToleranceMatReqModif_M,
    XCAFDimTolObjects_GeomToleranceObject,
    XCAFDimTolObjects_GeomToleranceType_Flatness,
    XCAFDimTolObjects_GeomToleranceType_Position,
    XCAFDimTolObjects_GeomToleranceTypeValue_Diameter,
)
from OCP.collections import HArray1_double, Sequence_TDF_Label

_MILLIMETRE_UNIT = re.compile(
    r"(?m)^#(?P<id>\d+)\s*=\s*\(\s*LENGTH_UNIT\(\)\s+NAMED_UNIT\(\*\)\s+"
    r"SI_UNIT\(\.MILLI\.,\.METRE\.\)\s*\);\s*$"
)


def _document_with_box():
    application = XCAFApp_Application.GetApplication_s()
    document = TDocStd_Document(TCollection_ExtendedString("MDTV-XCAF"))
    application.NewDocument(TCollection_ExtendedString("MDTV-XCAF"), document)
    shape_tool = XCAFDoc_DocumentTool.ShapeTool_s(document.Main())
    shape_label = shape_tool.AddShape(
        BRepPrimAPI_MakeBox(10.0, 20.0, 30.0).Shape(), False
    )
    return document, shape_label, XCAFDoc_DocumentTool.DimTolTool_s(document.Main())


def _write_ap242(document: TDocStd_Document, path: Path) -> None:
    if path.exists():
        raise FileExistsError(path)
    writer = STEPCAFControl_Writer()
    previous_schema = Interface_Static.CVal_s("write.step.schema")
    previous_unit = Interface_Static.CVal_s("write.step.unit")
    try:
        Interface_Static.SetCVal_s("write.step.schema", "AP242DIS")
        Interface_Static.SetCVal_s("write.step.unit", "MM")
        writer.SetDimTolMode(True)
        if not writer.Transfer(document, STEPControl_AsIs):
            raise RuntimeError("OCCT failed to transfer the synthetic PMI document")
        status = writer.Write(str(path))
        if status != IFSelect_RetDone:
            raise RuntimeError(f"OCCT failed to write the synthetic PMI file: {status}")
    finally:
        Interface_Static.SetCVal_s("write.step.schema", previous_schema)
        Interface_Static.SetCVal_s("write.step.unit", previous_unit)


def _add_dimension(
    tool,
    shape_label,
    *,
    dimension_type,
    value: float,
    semantic_name: str,
    lower_tolerance: float = 0.0,
    upper_tolerance: float = 0.0,
    bounds: tuple[float, float] | None = None,
) -> None:
    label = tool.AddDimension()
    dimension = XCAFDimTolObjects_DimensionObject()
    dimension.SetType(dimension_type)
    dimension.SetValue(value)
    dimension.SetSemanticName(TCollection_HAsciiString(semantic_name))
    if bounds is not None:
        values = HArray1_double(1, 2)
        values.SetValue(1, bounds[0])
        values.SetValue(2, bounds[1])
        dimension.SetValues(values)
        dimension.SetLowerBound(bounds[0])
        dimension.SetUpperBound(bounds[1])
    dimension.SetLowerTolValue(lower_tolerance)
    dimension.SetUpperTolValue(upper_tolerance)
    XCAFDoc_Dimension.Set_s(label).SetObject(dimension)
    tool.SetDimension(shape_label, label)


def _add_geometric_tolerance(tool, shape_label, *, tolerance_type, value: float):
    label = tool.AddGeomTolerance()
    tolerance = XCAFDimTolObjects_GeomToleranceObject()
    tolerance.SetType(tolerance_type)
    tolerance.SetValue(value)
    if tolerance_type == XCAFDimTolObjects_GeomToleranceType_Position:
        tolerance.SetTypeOfValue(XCAFDimTolObjects_GeomToleranceTypeValue_Diameter)
        tolerance.SetMaterialRequirementModifier(
            XCAFDimTolObjects_GeomToleranceMatReqModif_M
        )
    XCAFDoc_GeomTolerance.Set_s(label).SetObject(tolerance)
    tool.SetGeomTolerance(shape_label, label)
    return label


def _add_datum(tool, shape_label, tolerance_label, identification: str, position: int) -> None:
    label = tool.AddDatum(
        TCollection_HAsciiString(identification),
        TCollection_HAsciiString(""),
        TCollection_HAsciiString(identification),
    )
    datum = XCAFDimTolObjects_DatumObject()
    datum.SetName(TCollection_HAsciiString(identification))
    datum.SetPosition(position)
    datum.SetSemanticName(TCollection_HAsciiString(f"datum_{identification}"))
    XCAFDoc_Datum.Set_s(label).SetObject(datum)
    shape_labels = Sequence_TDF_Label()
    shape_labels.Append(shape_label)
    tool.SetDatum(shape_labels, label)
    tool.SetDatumToGeomTol(label, tolerance_label)


def write_pmi_dimensions(path: Path) -> None:
    """Write a one-solid AP242 file with deviation, limit and angular dimensions."""

    document, shape_label, tool = _document_with_box()
    _add_dimension(
        tool,
        shape_label,
        dimension_type=XCAFDimTolObjects_DimensionType_Size_Thickness,
        value=12.5,
        semantic_name="thickness",
        lower_tolerance=-0.1,
        upper_tolerance=0.1,
    )
    _add_dimension(
        tool,
        shape_label,
        dimension_type=XCAFDimTolObjects_DimensionType_Size_Thickness,
        value=20.0,
        semantic_name="thickness_limits",
        bounds=(19.8, 20.2),
    )
    _add_dimension(
        tool,
        shape_label,
        dimension_type=XCAFDimTolObjects_DimensionType_Size_Angular,
        value=math.radians(60.0),
        semantic_name="angle",
        lower_tolerance=-0.01,
        upper_tolerance=0.01,
    )
    _add_dimension(
        tool,
        shape_label,
        dimension_type=XCAFDimTolObjects_DimensionType_Size_Angular,
        value=math.radians(45.0),
        semantic_name="angle_limits",
        bounds=(math.radians(44.0), math.radians(46.0)),
    )
    _write_ap242(document, path)


def write_pmi_tolerances(path: Path) -> None:
    """Write a one-solid AP242 file with flatness and datum-referenced position."""

    document, shape_label, tool = _document_with_box()
    # The writer anchors geometric-tolerance measures to the document length
    # unit only when a dimensional representation is present; without this
    # anchor it falls back to metres for the tolerance magnitude.
    _add_dimension(
        tool,
        shape_label,
        dimension_type=XCAFDimTolObjects_DimensionType_Size_Thickness,
        value=10.0,
        semantic_name="base_thickness",
    )
    _add_geometric_tolerance(
        tool,
        shape_label,
        tolerance_type=XCAFDimTolObjects_GeomToleranceType_Flatness,
        value=0.05,
    )
    position_label = _add_geometric_tolerance(
        tool,
        shape_label,
        tolerance_type=XCAFDimTolObjects_GeomToleranceType_Position,
        value=0.2,
    )
    for position, identification in enumerate(("A", "B", "C"), start=1):
        _add_datum(tool, shape_label, position_label, identification, position)
    _write_ap242(document, path)


def _rewrite_length_unit(source: Path, target: Path, unit: Literal["INCH", "CM"]) -> None:
    if source == target:
        raise ValueError("source and target must differ; source fixtures are never overwritten")
    if target.exists():
        raise FileExistsError(target)
    text = source.read_bytes().decode("latin-1")
    matches = list(_MILLIMETRE_UNIT.finditer(text))
    if len(matches) != 1:
        raise RuntimeError(
            f"expected exactly one millimetre unit definition, found {len(matches)}"
        )
    match = matches[0]
    unit_id = match.group("id")
    if unit == "CM":
        replacement = (
            f"#{unit_id} = ( LENGTH_UNIT() NAMED_UNIT(*) SI_UNIT(.CENTI.,.METRE.) );"
        )
    else:
        max_id = max(int(value) for value in re.findall(r"#(\d+)\s*=", text))
        exponents = max_id + 1
        millimetre = max_id + 2
        conversion = max_id + 3
        replacement = (
            f"#{exponents} = DIMENSIONAL_EXPONENTS(1.,0.,0.,0.,0.,0.,0.);\n"
            f"#{millimetre} = ( LENGTH_UNIT() NAMED_UNIT(*) SI_UNIT(.MILLI.,.METRE.) );\n"
            f"#{conversion} = LENGTH_MEASURE_WITH_UNIT(LENGTH_MEASURE(25.4),#{millimetre});\n"
            f"#{unit_id} = ( CONVERSION_BASED_UNIT('INCH',#{conversion}) "
            f"LENGTH_UNIT() NAMED_UNIT(#{exponents}) );"
        )
    rewritten = text[: match.start()] + replacement + text[match.end() :]
    target.write_bytes(rewritten.encode("latin-1"))


def write_pmi_dimensions_in_unit(
    source: Path, target: Path, unit: Literal["INCH", "CM"]
) -> None:
    write_pmi_dimensions(source)
    _rewrite_length_unit(source, target, unit)


def write_pmi_tolerances_in_unit(
    source: Path, target: Path, unit: Literal["INCH", "CM"]
) -> None:
    write_pmi_tolerances(source)
    _rewrite_length_unit(source, target, unit)
