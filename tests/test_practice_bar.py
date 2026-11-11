"""The practice page's bar stays small: playing in the bar, everything else in the menu."""
from support import AIR, db


def test_the_bar_only_has_what_playing_needs(user):
    client, uid = user
    db.addPiece(uid, "Air", None, xml=AIR)
    page = client.get("/practice").get_data(as_text=True)
    for gone in ('id="cursor-prev"', 'id="cursor-next"', 'id="take-name"', 'id="takes-dock"'):
        assert gone not in page
    for kept in ('id="play"', 'id="record"', 'id="tempo"', 'id="metro"', 'id="live-lane"', 'id="coach-toggle"', 'id="take-pick"'):
        assert kept in page
