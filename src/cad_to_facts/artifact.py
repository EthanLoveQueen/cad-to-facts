import hashlib
import re
from pathlib import Path

from cad_to_facts.domain import SourceArtifact


def _format(content: bytes) -> str:
    stripped = content.lstrip()
    if stripped.startswith(b"\xef\xbb\xbf"):
        stripped = stripped[3:].lstrip()
    if stripped.startswith(b"ISO-10303-21;"):
        return "step"
    if re.match(br"AC\d{4}", stripped):
        return "dwg"
    if stripped.startswith(b"AutoCAD Binary DXF"):
        return "dxf"
    # A DXF may begin with comment groups (999) before the first SECTION.
    if re.search(br"(?:^|[\r\n])(?:0|  0)\r?\nSECTION\r?\n", stripped[:4096]):
        return "dxf"
    return "unknown"


def register(path: str | Path) -> SourceArtifact:
    """Register the exact bytes of a design file without modifying them."""

    source = Path(path)
    content = source.read_bytes()
    return SourceArtifact(
        sha256=hashlib.sha256(content).hexdigest(),
        size_bytes=len(content),
        format=_format(content),
        source_locator=str(source.resolve()),
    )
