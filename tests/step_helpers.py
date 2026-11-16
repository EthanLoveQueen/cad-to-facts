from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeFace, BRepBuilderAPI_MakePolygon
from OCP.BRepAlgoAPI import BRepAlgoAPI_Cut
from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox, BRepPrimAPI_MakeCylinder
from OCP.BRep import BRep_Builder
from OCP.gp import gp_Ax2, gp_Dir, gp_Pnt, gp_Trsf, gp_Vec
from OCP.IFSelect import IFSelect_RetDone
from OCP.Interface import Interface_Static
from OCP.STEPCAFControl import STEPCAFControl_Writer
from OCP.STEPControl import STEPControl_AsIs, STEPControl_Writer
from OCP.TCollection import TCollection_ExtendedString
from OCP.TDataStd import TDataStd_Name
from OCP.TDocStd import TDocStd_Document
from OCP.TopLoc import TopLoc_Location
from OCP.TopoDS import TopoDS_Compound
from OCP.XCAFApp import XCAFApp_Application
from OCP.XCAFDoc import XCAFDoc_DocumentTool


def write_box(path, size_mm=(10.0, 20.0, 30.0), unit="MM"):
    """Write an analytic box, always restoring the global STEP unit to mm."""

    writer = STEPControl_Writer()
    assert Interface_Static.SetCVal_s("write.step.unit", unit)
    try:
        assert writer.Transfer(BRepPrimAPI_MakeBox(*size_mm).Shape(), STEPControl_AsIs) == IFSelect_RetDone
        assert writer.Write(str(path)) == IFSelect_RetDone
    finally:
        Interface_Static.SetCVal_s("write.step.unit", "MM")


def write_boxes(path, sizes_mm=((10.0, 20.0, 30.0), (10.0, 20.0, 30.0))):
    """Write one STEP compound containing the requested analytic boxes."""

    builder = BRep_Builder()
    compound = TopoDS_Compound()
    builder.MakeCompound(compound)
    for size in sizes_mm:
        builder.Add(compound, BRepPrimAPI_MakeBox(*size).Shape())
    writer = STEPControl_Writer()
    assert Interface_Static.SetCVal_s("write.step.assembly", "Off")
    assert Interface_Static.SetCVal_s("write.step.unit", "MM")
    try:
        assert writer.Transfer(compound, STEPControl_AsIs) == IFSelect_RetDone
        assert writer.Write(str(path)) == IFSelect_RetDone
    finally:
        Interface_Static.SetCVal_s("write.step.assembly", "Auto")
        Interface_Static.SetCVal_s("write.step.unit", "MM")


def write_assembly(
    path,
    sizes_mm=((10.0, 10.0, 10.0), (20.0, 5.0, 5.0)),
    names=None,
    occurrences_per_part=1,
    occurrence_names=None,
):
    """Write an analytic STEP assembly with definition and optional occurrence names."""

    app = XCAFApp_Application.GetApplication_s()
    document = TDocStd_Document(TCollection_ExtendedString("MDTV-XCAF"))
    app.NewDocument(TCollection_ExtendedString("MDTV-XCAF"), document)
    shapes = XCAFDoc_DocumentTool.ShapeTool_s(document.Main())
    assembly = shapes.NewShape()
    TDataStd_Name.Set_s(assembly, TCollection_ExtendedString("Test assembly"))
    for index, size in enumerate(sizes_mm):
        component = shapes.AddShape(BRepPrimAPI_MakeBox(*size).Shape())
        name = names[index] if names is not None else f"Part {index + 1}"
        TDataStd_Name.Set_s(component, TCollection_ExtendedString(name))
        for occurrence in range(occurrences_per_part):
            transform = gp_Trsf()
            transform.SetTranslation(
                gp_Vec(100.0 * (index * occurrences_per_part + occurrence), 0.0, 0.0)
            )
            placed = shapes.AddComponent(assembly, component, TopLoc_Location(transform))
            if occurrence_names is not None:
                occurrence_name = occurrence_names[
                    index * occurrences_per_part + occurrence
                ]
                TDataStd_Name.Set_s(placed, TCollection_ExtendedString(occurrence_name))
    shapes.UpdateAssemblies()
    writer = STEPCAFControl_Writer()
    assert Interface_Static.SetCVal_s("write.step.unit", "MM")
    try:
        assert writer.Transfer(document, STEPControl_AsIs)
        assert writer.Write(str(path)) == IFSelect_RetDone
    finally:
        Interface_Static.SetCVal_s("write.step.unit", "MM")


def write_nested_assembly(path, subassembly_x=0.0):
    """Write one part used twice in a translated subassembly and once at the root."""

    app = XCAFApp_Application.GetApplication_s()
    document = TDocStd_Document(TCollection_ExtendedString("MDTV-XCAF"))
    app.NewDocument(TCollection_ExtendedString("MDTV-XCAF"), document)
    shapes = XCAFDoc_DocumentTool.ShapeTool_s(document.Main())
    part = shapes.AddShape(BRepPrimAPI_MakeBox(10.0, 10.0, 10.0).Shape())
    TDataStd_Name.Set_s(part, TCollection_ExtendedString("Shared part"))
    subassembly = shapes.NewShape()
    TDataStd_Name.Set_s(subassembly, TCollection_ExtendedString("Subassembly"))
    for index in range(2):
        transform = gp_Trsf()
        transform.SetTranslation(gp_Vec(20.0 * index, 0.0, 0.0))
        shapes.AddComponent(subassembly, part, TopLoc_Location(transform))
    root = shapes.NewShape()
    TDataStd_Name.Set_s(root, TCollection_ExtendedString("Root assembly"))
    subassembly_location = gp_Trsf()
    subassembly_location.SetTranslation(gp_Vec(subassembly_x, 0.0, 0.0))
    shapes.AddComponent(root, subassembly, TopLoc_Location(subassembly_location))
    transform = gp_Trsf()
    transform.SetTranslation(gp_Vec(100.0, 0.0, 0.0))
    shapes.AddComponent(root, part, TopLoc_Location(transform))
    shapes.UpdateAssemblies()
    writer = STEPCAFControl_Writer()
    assert Interface_Static.SetCVal_s("write.step.unit", "MM")
    try:
        assert writer.Transfer(document, STEPControl_AsIs)
        assert writer.Write(str(path)) == IFSelect_RetDone
    finally:
        Interface_Static.SetCVal_s("write.step.unit", "MM")


def write_feature_assembly(path):
    """Write one analytic through-hole plate plus named door/window candidates."""

    plate = BRepAlgoAPI_Cut(
        BRepPrimAPI_MakeBox(20.0, 20.0, 10.0).Shape(),
        BRepPrimAPI_MakeCylinder(
            gp_Ax2(gp_Pnt(10.0, 10.0, -5.0), gp_Dir(0.0, 0.0, 1.0)), 3.0, 20.0
        ).Shape(),
    ).Shape()
    app = XCAFApp_Application.GetApplication_s()
    document = TDocStd_Document(TCollection_ExtendedString("MDTV-XCAF"))
    app.NewDocument(TCollection_ExtendedString("MDTV-XCAF"), document)
    shapes = XCAFDoc_DocumentTool.ShapeTool_s(document.Main())
    assembly = shapes.NewShape()
    TDataStd_Name.Set_s(assembly, TCollection_ExtendedString("Feature assembly"))
    for index, (shape, name) in enumerate((
        (plate, "Plate"),
        (BRepPrimAPI_MakeBox(30.0, 10.0, 2.0).Shape(), "Door Panel"),
        (BRepPrimAPI_MakeBox(15.0, 12.0, 1.0).Shape(), "Window Frame"),
        (BRepPrimAPI_MakeCylinder(4.0, 10.0).Shape(), "Cylindrical Pin"),
    )):
        component = shapes.AddShape(shape)
        TDataStd_Name.Set_s(component, TCollection_ExtendedString(name))
        transform = gp_Trsf()
        transform.SetTranslation(gp_Vec(100.0 * index, 0.0, 0.0))
        placed = shapes.AddComponent(assembly, component, TopLoc_Location(transform))
        TDataStd_Name.Set_s(placed, TCollection_ExtendedString(name))
    shapes.UpdateAssemblies()
    writer = STEPCAFControl_Writer()
    assert Interface_Static.SetCVal_s("write.step.unit", "MM")
    try:
        assert writer.Transfer(document, STEPControl_AsIs)
        assert writer.Write(str(path)) == IFSelect_RetDone
    finally:
        Interface_Static.SetCVal_s("write.step.unit", "MM")


def write_question_assembly(path):
    """Write the public agent-workflow eval assembly with two doors and one through hole."""
    plate = BRepAlgoAPI_Cut(
        BRepPrimAPI_MakeBox(20.0, 20.0, 10.0).Shape(),
        BRepPrimAPI_MakeCylinder(
            gp_Ax2(gp_Pnt(10.0, 10.0, -5.0), gp_Dir(0.0, 0.0, 1.0)), 3.0, 20.0
        ).Shape(),
    ).Shape()
    app = XCAFApp_Application.GetApplication_s()
    document = TDocStd_Document(TCollection_ExtendedString("MDTV-XCAF"))
    app.NewDocument(TCollection_ExtendedString("MDTV-XCAF"), document)
    shapes = XCAFDoc_DocumentTool.ShapeTool_s(document.Main())
    assembly = shapes.NewShape()
    TDataStd_Name.Set_s(assembly, TCollection_ExtendedString("Question assembly"))
    items = (
        (BRepPrimAPI_MakeBox(2.0, 30.0, 40.0).Shape(), "Left door", (0.0, 0.0, 0.0)),
        (BRepPrimAPI_MakeBox(2.0, 30.0, 40.0).Shape(), "Right door", (200.0, 0.0, 0.0)),
        (BRepPrimAPI_MakeBox(2.0, 20.0, 20.0).Shape(), "Window Frame", (100.0, -100.0, 0.0)),
        (plate, "Hole Plate", (100.0, 100.0, 0.0)),
    )
    for shape, name, translation in items:
        component = shapes.AddShape(shape)
        TDataStd_Name.Set_s(component, TCollection_ExtendedString(name))
        transform = gp_Trsf()
        transform.SetTranslation(gp_Vec(*translation))
        placed = shapes.AddComponent(assembly, component, TopLoc_Location(transform))
        TDataStd_Name.Set_s(placed, TCollection_ExtendedString(name))
    shapes.UpdateAssemblies()
    writer = STEPCAFControl_Writer()
    assert Interface_Static.SetCVal_s("write.step.unit", "MM")
    try:
        assert writer.Transfer(document, STEPControl_AsIs)
        assert writer.Write(str(path)) == IFSelect_RetDone
    finally:
        Interface_Static.SetCVal_s("write.step.unit", "MM")


def write_face(path, unit="MM"):
    """Write a single planar face (no solid), restoring the global STEP unit to mm."""

    polygon = BRepBuilderAPI_MakePolygon()
    for x, y in ((0.0, 0.0), (10.0, 0.0), (10.0, 10.0), (0.0, 10.0)):
        polygon.Add(gp_Pnt(x, y, 0.0))
    polygon.Close()
    face = BRepBuilderAPI_MakeFace(polygon.Wire()).Face()
    writer = STEPControl_Writer()
    assert Interface_Static.SetCVal_s("write.step.unit", unit)
    try:
        assert writer.Transfer(face, STEPControl_AsIs) == IFSelect_RetDone
        assert writer.Write(str(path)) == IFSelect_RetDone
    finally:
        Interface_Static.SetCVal_s("write.step.unit", "MM")
