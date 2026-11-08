"""frontend/: the screen must use the server's AI, not make up its own verdicts."""
import re
from pathlib import Path

FRONT = Path(__file__).resolve().parent.parent / "frontend"


def test_api_js_points_at_the_server():
    js = (FRONT / "api.js").read_text()
    for url in ("/api/start", "/api/tick", "/api/offer"):
        assert url in js


def test_app_js_shows_the_servers_verdicts():
    js = (FRONT / "app.js").read_text()
    assert "carefulPositive" not in js and "naivePositive" not in js
    assert "verdict.label" in js and "verdict.text" in js


def test_game_page_links_to_evidence_and_has_no_dead_widgets():
    html = (FRONT / "game.html").read_text()
    assert 'href="evidence.html"' in html
    assert "deepseek" not in html.lower()


def test_evidence_page_images_exist():
    html = (FRONT / "evidence.html").read_text()
    for src in re.findall(r'src="([^"]+)"', html):
        assert (FRONT / src).exists(), src


def test_every_id_used_by_app_js_exists_in_game_html():
    js, html = (FRONT / "app.js").read_text(), (FRONT / "game.html").read_text()
    ids = set(re.findall(r"\$\('([\w-]+)'\)", js))
    missing = [i for i in ids if f'id="{i}"' not in html]
    assert not missing, missing
