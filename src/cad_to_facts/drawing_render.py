"""Optional SVG review rendering; never used as deterministic geometric proof."""

from cad_to_facts.domain.snapshot import ModelSnapshot


def render_svg(snapshot: ModelSnapshot, layout_name: str = "Model") -> str:
    """Render one cataloged layout through ezdxf's SVG backend."""

    if snapshot.drawing is None or snapshot.status == "failed":
        raise ValueError("SVG rendering requires a readable DWG/DXF snapshot")
    from ezdxf.addons.drawing import Frontend, RenderContext, layout
    from ezdxf.addons.drawing.config import Configuration, ImagePolicy
    from ezdxf.addons.drawing.svg import SVGBackend

    document = snapshot._adapter_payload["document"]
    try:
        drawing_layout = document.layouts.get(layout_name)
    except Exception as error:
        raise ValueError(f"Unknown drawing layout: {layout_name}") from error
    backend = SVGBackend()
    # Do not let an untrusted drawing cause implicit reads of external raster files.
    configuration = Configuration(image_policy=ImagePolicy.IGNORE)
    frontend = Frontend(RenderContext(document), backend, config=configuration)
    frontend.draw_layout(drawing_layout)
    # Ignoring every external image can legitimately leave an empty recording.
    # Supply a finite review page instead of asking ezdxf to auto-size an empty box.
    render_box = None
    if not backend.player().bbox().has_data:
        from ezdxf.math import BoundingBox2d

        render_box = BoundingBox2d([(0, 0), (1, 1)])
    return backend.get_string(layout.Page(0, 0), render_box=render_box)
