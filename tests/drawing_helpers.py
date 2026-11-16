"""Analytic DXF fixtures; these establish repeatability, not converter fidelity."""

import ezdxf
from ezdxf import units


def write_drawing(path, *, drawing_units=units.MM):
    doc = ezdxf.new("R2018", units=drawing_units)
    doc.layers.add("Geometry")
    doc.layers.add("Annotation")
    msp = doc.modelspace()
    msp.add_line((0, 0), (3, 4), dxfattribs={"layer": "Geometry"})
    msp.add_text("PART-A", dxfattribs={"layer": "Annotation"}).set_placement((0, 10))
    msp.add_circle((20, 20), 2, dxfattribs={"layer": "Geometry"})
    msp.add_lwpolyline(
        [(0, 0), (10, 0), (10, 20), (0, 20)],
        close=True,
        dxfattribs={"layer": "Geometry"},
    )
    block = doc.blocks.new("Detail")
    block.add_line((0, 0), (0, 2), dxfattribs={"layer": "Geometry"})
    msp.add_blockref("Detail", (30, 0), dxfattribs={"layer": "Geometry"})
    doc.layouts.get("Layout1").add_text("A1", dxfattribs={"layer": "Annotation"})
    doc.saveas(path)


def write_unitless_line(path):
    doc = ezdxf.new("R2018", units=0)
    doc.modelspace().add_line((0, 0), (3, 4))
    doc.saveas(path)


def write_drawing_with_title_block(path):
    """Model-space block reference carrying attached ATTRIB values."""

    doc = ezdxf.new("R2018", units=units.MM)
    title = doc.blocks.new("TITLE")
    title.add_attdef("PART", (0, 0))
    title.add_attdef("MATERIAL", (0, 5))
    reference = doc.modelspace().add_blockref("TITLE", (0, 0))
    reference.add_attrib("PART", "A-123", (0, 0))
    reference.add_attrib("MATERIAL", "STEEL", (0, 5))
    doc.saveas(path)


def write_question_drawing(path):
    """Public-style analytic drawing with layers, blocks, attributes and dimensions."""

    doc = ezdxf.new("R2018", units=units.MM)
    for name in ("Geometry", "Annotation", "DoorLayer"):
        doc.layers.add(name)
    doc.layers.add("Hidden").off()
    doc.layers.add("Frozen").freeze()
    msp = doc.modelspace()
    paper = doc.layouts.get("Layout1")

    msp.add_line((0, 0), (3, 4), dxfattribs={"layer": "Geometry"})
    msp.add_line((10, 0), (10, 10), dxfattribs={"layer": "Geometry"})
    msp.add_circle((20, 20), 2, dxfattribs={"layer": "Geometry"})
    msp.add_lwpolyline(
        [(0, 0), (10, 0), (10, 20), (0, 20)],
        close=True,
        dxfattribs={"layer": "Geometry"},
    )
    msp.add_mtext("材料: {\\C1;STEEL}", dxfattribs={"layer": "Annotation"})
    msp.add_text("DOOR-A", dxfattribs={"layer": "Annotation"})
    msp.add_line((0, 30), (5, 30), dxfattribs={"layer": "Hidden"})
    msp.add_line((0, 40), (6, 40), dxfattribs={"layer": "Frozen"})
    msp.add_linear_dim(
        base=(0, 5),
        p1=(0, 0),
        p2=(10, 0),
        text="10.0",
        dxfattribs={"layer": "Annotation"},
    ).render()

    door = doc.blocks.new("DOOR")
    for start, end in (
        ((0, 0), (10, 0)),
        ((10, 0), (10, 20)),
        ((10, 20), (0, 20)),
        ((0, 20), (0, 0)),
    ):
        door.add_line(start, end, dxfattribs={"layer": "Geometry"})
    msp.add_blockref(
        "DOOR", (30, 0), dxfattribs={"layer": "DoorLayer"}
    )
    msp.add_blockref(
        "DOOR", (50, 0), dxfattribs={"layer": "DoorLayer"}
    )

    title = doc.blocks.new("TITLE")
    title.add_attdef("PART", (0, 0))
    title.add_attdef("MATERIAL", (0, 5))
    title.add_attdef("QTY", (0, 10))
    reference = paper.add_blockref("TITLE", (100, 100))
    reference.add_attrib("PART", "A-123", (100, 100))
    reference.add_attrib("MATERIAL", "STEEL", (100, 105))
    reference.add_attrib("QTY", "2", (100, 110))
    paper.add_text("PAPER-TEXT", dxfattribs={"layer": "Annotation"})
    doc.saveas(path)


def write_unitless_question_drawing(path):
    doc = ezdxf.new("R2018", units=0)
    msp = doc.modelspace()
    msp.add_line((0, 0), (3, 4))
    msp.add_text("UNITLESS")
    doc.saveas(path)


def write_unitless_dimension_drawing(path):
    doc = ezdxf.new("R2018", units=0)
    msp = doc.modelspace()
    msp.add_line((0, 0), (10, 0))
    msp.add_linear_dim(base=(0, 5), p1=(0, 0), p2=(10, 0)).render()
    doc.saveas(path)


def write_open_polyline_area_drawing(path):
    doc = ezdxf.new("R2018", units=units.MM)
    msp = doc.modelspace()
    msp.add_circle((20, 20), 2)
    msp.add_lwpolyline([(0, 0), (10, 0), (10, 10)])
    doc.saveas(path)




def add_unresolved_xref(path):
    doc = ezdxf.readfile(path)
    block = doc.blocks.new("External")
    block.block.dxf.flags = 4
    block.block.dxf.xref_path = "missing-reference.dwg"
    doc.saveas(path)

