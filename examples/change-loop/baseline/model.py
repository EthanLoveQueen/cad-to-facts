import build123d as bd
from cad import model

WIDTH = 10.0
DEPTH = 20.0
HEIGHT = 30.0


def make_box(height=HEIGHT):
    part = bd.Box(WIDTH, DEPTH, height)
    part.label = "review_box"
    return part


@model
def review_box():
    return make_box()


if __name__ == "__main__":
    review_box()
