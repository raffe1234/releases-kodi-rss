from datetime import date
from pathlib import Path
import importlib.util
import sys


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "generate_feed.py"
SPEC = importlib.util.spec_from_file_location("generate_feed", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


def test_extracts_titles_under_correct_dates_and_ignores_badges():
    html = """
    <html><body>
      <h2>17th 17th Tomorrow</h2>
      <a href="/p/the-odyssey-movie">Very anticipated</a>
      <a href="/p/the-odyssey-movie">The Odyssey</a>
      <h2>21st 21st In 5 days</h2>
      <a href="/p/the-east-palace-season-1"><img alt="Image"></a>
      <a href="/p/the-east-palace-season-1">The East Palace Season 1</a>
      <a href="/calendar/movies">Movies</a>
    </body></html>
    """
    items = MODULE.parse_release_page(html, date(2026, 7, 20), "movie")
    result = [(item.release_date.isoformat(), item.title) for item in items]
    assert result == [
        ("2026-07-17", "The Odyssey"),
        ("2026-07-21", "The East Palace Season 1"),
    ]


def test_month_boundary_and_slug_fallback():
    html = """
    <h2>31st</h2>
    <a href="/p/july-title"><img alt="Image"></a>
    <h2>Aug 1st</h2>
    <a href="/p/a-test-title-season-2"><img alt="Image"></a>
    """
    items = MODULE.parse_release_page(html, date(2026, 8, 1), "tv")
    assert [(item.release_date, item.title) for item in items] == [
        (date(2026, 7, 31), "July Title"),
        (date(2026, 8, 1), "A Test Title Season 2"),
    ]


def test_date_url_has_no_leading_zero():
    assert MODULE.date_url("movies", date(2026, 7, 7)).endswith("/2026-jul-7")
