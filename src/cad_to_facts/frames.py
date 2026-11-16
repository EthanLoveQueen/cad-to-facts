"""Shared orthographic camera-vector conventions without a geometry-kernel dependency."""

import math

from cad_to_facts.domain.view import CameraSpecification


_PRESET_FRAMES = {
    "front": ((0.0, -1.0, 0.0), (1.0, 0.0, 0.0)),
    "back": ((0.0, 1.0, 0.0), (-1.0, 0.0, 0.0)),
    "left": ((-1.0, 0.0, 0.0), (0.0, -1.0, 0.0)),
    "right": ((1.0, 0.0, 0.0), (0.0, 1.0, 0.0)),
    "top": ((0.0, 0.0, 1.0), (1.0, 0.0, 0.0)),
    "bottom": ((0.0, 0.0, -1.0), (1.0, 0.0, 0.0)),
    "iso": ((1.0, -1.0, 1.0), (1.0, 1.0, 0.0)),
}


def _unit(values):
    length = math.sqrt(sum(value * value for value in values))
    if length <= 1e-15:
        raise ValueError("Camera normal/right must be nonzero and non-parallel")
    return tuple(value / length for value in values)


def camera_basis(
    camera: CameraSpecification,
) -> tuple[tuple[float, float, float], tuple[float, float, float], tuple[float, float, float]]:
    """Return unit model-to-viewer normal, screen-right and screen-up vectors."""

    if camera.preset is not None:
        normal, right = _PRESET_FRAMES[camera.preset]
    else:
        normal, right = camera.normal, camera.right
    assert normal is not None and right is not None
    if any(not math.isfinite(value) for value in [*normal, *right]):
        raise ValueError("Camera vectors must contain only finite values")
    normal_unit = _unit(normal)
    right_unit = _unit(right)
    up = (
        normal_unit[1] * right_unit[2] - normal_unit[2] * right_unit[1],
        normal_unit[2] * right_unit[0] - normal_unit[0] * right_unit[2],
        normal_unit[0] * right_unit[1] - normal_unit[1] * right_unit[0],
    )
    up_unit = _unit(up)
    # Remove any component along the normal so explicit non-orthogonal input has
    # the same OCCT gp_Ax2 interpretation as the preset frames.
    projection = sum(right_unit[index] * normal_unit[index] for index in range(3))
    orthogonal_right = _unit(tuple(
        right_unit[index] - projection * normal_unit[index] for index in range(3)
    ))
    return normal_unit, orthogonal_right, up_unit
