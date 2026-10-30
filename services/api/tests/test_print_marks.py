"""Label text, leader lines and ink found in code: on drawn test images, and on the Japan map,
which has labels and no leader lines."""

import numpy as np
import numpy.typing as npt
from PIL import Image, ImageDraw, ImageFont

from app.geometry import print_marks as pm
from app.meta import s2_bakeoff as bake

FONT = ImageFont.load_default(size=40)


def page(text_color: tuple[int, int, int], ground: tuple[int, int, int]) -> Image.Image:
    img = Image.new("RGB", (900, 400), ground)
    ImageDraw.Draw(img).text((40, 60), "Left ventricle", fill=text_color, font=FONT)
    return img


def array(img: Image.Image) -> npt.NDArray[np.uint8]:
    return np.asarray(img, np.uint8)


def test_black_text_on_a_page_is_text_and_ink() -> None:
    img = page((0, 0, 0), (255, 255, 255))
    marks = pm.find(array(img))
    x0 = min(w[0] for w in marks.words)
    x1 = max(w[2] for w in marks.words)
    assert x0 <= 45 and x1 >= 265  # the label is about 230 px wide
    assert marks.text[80, 120] and not marks.text[300, 600]
    assert marks.ink[array(img)[..., 0] < 64].all()


def test_white_text_on_a_sea_is_text() -> None:
    marks = pm.find(array(page((255, 255, 255), (42, 122, 177))))
    assert marks.words and marks.text[80, 120]
    assert not marks.ink.any()


def test_a_line_from_a_label_with_a_dot_at_its_far_end_is_a_leader_line() -> None:
    img = page((0, 0, 0), (255, 255, 255))
    draw = ImageDraw.Draw(img)
    draw.ellipse((560, 160, 860, 380), fill=(240, 200, 60))  # a part
    draw.line((285, 85, 700, 270), fill=(230, 0, 0), width=3)
    draw.ellipse((692, 262, 708, 278), fill=(230, 0, 0))  # the end dot, on the part
    marks = pm.find(array(img))
    assert len(marks.segments) >= 1
    assert marks.line[178, 493]  # on the line, between the label and the part
    assert marks.line[270, 700]  # the dot
    assert not marks.line[300, 780]  # the part itself


def test_a_line_far_from_any_label_is_not_a_leader_line() -> None:
    img = page((0, 0, 0), (255, 255, 255))
    ImageDraw.Draw(img).line((500, 250, 880, 390), fill=(0, 0, 0), width=3)
    marks = pm.find(array(img))
    assert marks.segments == [] and not marks.line.any()


def test_a_shape_with_no_text_has_no_words() -> None:
    img = Image.new("RGB", (600, 400), (255, 255, 255))
    draw = ImageDraw.Draw(img)
    for i in range(6):
        draw.ellipse((40 + 90 * i, 150, 100 + 90 * i, 260), fill=(200, 40, 40), outline=(0, 0, 0))
    assert pm.find(array(img)).words == []


def test_the_japan_map_has_its_nine_labels_and_no_leader_lines() -> None:
    fig = bake.load_figure("japan_regions", bake.FIGURES["japan_regions"])
    marks = pm.find(fig.image)
    assert marks.segments == []
    # "Hokkaido" sits near (1000, 400) and "Kyushu" near (140, 1545) in the 1796 x 2048 map.
    assert marks.text[400, 1000] and marks.text[1545, 140]
