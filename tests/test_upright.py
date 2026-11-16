"""Photos taken sideways or upside down are turned before homr or Claude reads them."""
import pytest
from PIL import Image

from support import REPO
from ml.api import upright

PAGE = REPO / "music-app-home/home_imgs/sheet-fur-elise.jpg"


@pytest.mark.parametrize("held", [0, 90, 180, 270])
def test_a_photo_ends_up_the_right_way_up(tmp_path, held):
    photo = tmp_path / "page.jpg"
    Image.open(PAGE).convert("RGB").rotate(held, expand=True).save(photo)
    out = upright(photo, tmp_path)
    if held == 0:
        assert out == photo   # a page that was fine is left alone
    else:
        assert out != photo and Image.open(out).size == Image.open(PAGE).size


def test_a_photo_with_no_staves_is_left_alone(tmp_path):
    photo = tmp_path / "board.jpg"
    Image.open(REPO / "music-app-home/home_imgs/whiteboard-sketch.jpg").convert("RGB").save(photo)
    assert upright(photo, tmp_path) == photo
