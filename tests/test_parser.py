"""API parsing and RSS tests; no real network traffic or TMDB key needed."""
from datetime import date, datetime
from pathlib import Path
import importlib.util
import sys
from unittest.mock import patch
from xml.etree import ElementTree as ET
from zoneinfo import ZoneInfo

import pytest


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "generate_feed.py"
SPEC = importlib.util.spec_from_file_location("generate_feed", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


def example_config():
    return {
        "feed_title": "Upcoming movie and TV releases",
        "feed_link": "https://example.org/",
        "feed_description": "Test",
        "language": "en-US",
        "timezone": "Europe/Stockholm",
        "date_format": "%-d/%-m",
        "movie_label": "Movie",
        "tv_label": "TV series",
        "include_platform": True,
        "minimum_kodi_items": 3,
        "days_ahead": 7,
    }


def show_episode(number=1, season=2, airdate="2026-11-18", web=True):
    channel = {"name": "Netflix"} if web else {"name": "FOX"}
    show = {
        "id": 123,
        "name": "Example Series",
        "url": "https://www.tvmaze.com/shows/123/example-series",
        "webChannel": channel if web else None,
        "network": None if web else channel,
    }
    return {
        "season": season, "number": number, "airdate": airdate,
        "_embedded": {"show": show},
    }


def test_tvmaze_keeps_only_season_premieres_and_channel():
    entries = MODULE.parse_tvmaze_schedule(
        [
            show_episode(number=1),
            show_episode(number=2),
            show_episode(number=None),
            show_episode(season=0),
            show_episode(airdate="2026-11-19"),
        ],
        date(2026, 11, 18),
    )
    assert [(x.title, x.platform, x.source) for x in entries] == [
        ("Example Series Season 2", "Netflix", "TVmaze")
    ]


def test_tvmaze_network_fallback_and_deduplication():
    item = show_episode(web=False)
    actual = MODULE.deduplicate_releases(
        MODULE.parse_tvmaze_schedule([item, item], date(2026, 11, 18))
    )
    assert len(actual) == 1
    assert actual[0].platform == "FOX"


def test_tvmaze_schedules_request_broadcast_and_global_web():
    session = object()
    with patch.object(MODULE, "get_json", side_effect=[
        [show_episode(web=False)], [show_episode(web=True)]
    ]) as get:
        actual = MODULE.fetch_tvmaze_premieres(
            session, [date(2026, 11, 18)], "US", 0.5
        )
    assert len(actual) == 2
    assert get.call_args_list[0].args[2] == {
        "country": "US", "date": "2026-11-18"
    }
    assert get.call_args_list[1].args[2] == {"date": "2026-11-18"}


def test_tmdb_separate_types_and_regional_release_dates():
    first, last = date(2026, 11, 18), date(2026, 11, 24)
    payloads = [
        {"total_pages": 1, "results": [
            {"id": 10, "title": "Example Movie", "release_date": "2026-11-18"},
            {"id": 11, "title": "Outside", "release_date": "2026-11-30"},
        ]},
        {"total_pages": 1, "results": [
            {"id": 10, "title": "Example Movie", "release_date": "2026-11-19"},
        ]},
        {"total_pages": 1, "results": [
            {"id": 10, "title": "Example Movie", "release_date": "2026-11-22"},
        ]},
    ]
    with patch.object(MODULE, "get_json", side_effect=payloads) as get:
        releases = MODULE.fetch_tmdb_movies(
            object(), "test", first, last, "US", 0, 50
        )
    assert [(x.release_date.isoformat(), x.platform) for x in releases] == [
        ("2026-11-18", "cinema"),
        ("2026-11-19", "digital"),
        ("2026-11-22", "disc"),
    ]
    assert [call.args[2]["with_release_type"] for call in get.call_args_list] == [
        "3|2", "4", "5"
    ]
    assert all(call.args[2]["region"] == "US" for call in get.call_args_list)
    assert releases[0].url == "https://www.themoviedb.org/movie/10"


def test_tmdb_pagination_does_not_truncate_silently():
    with patch.object(MODULE, "get_json", return_value={
        "total_pages": 51, "results": []
    }):
        with pytest.raises(RuntimeError, match="tmdb_max_pages"):
            MODULE.fetch_tmdb_movies(
                object(), "test", date(2026, 11, 18),
                date(2026, 11, 24), "US", 0, 50
            )


def test_tmdb_fetches_all_pages():
    with patch.object(MODULE, "get_json", side_effect=[
        {"total_pages": 2, "results": [
            {"id": 1, "title": "One", "release_date": "2026-11-18"}
        ]},
        {"total_pages": 2, "results": [
            {"id": 2, "title": "Two", "release_date": "2026-11-19"}
        ]},
        {"total_pages": 0, "results": []},
        {"total_pages": 0, "results": []},
    ]) as get:
        movies = MODULE.fetch_tmdb_movies(
            object(), "test", date(2026, 11, 18),
            date(2026, 11, 24), "US", 0, 50
        )
    assert len(movies) == 2
    assert [call.args[2]["page"] for call in get.call_args_list] == [1, 2, 1, 1]


def test_rss_format_disc_and_source_links():
    releases = [
        MODULE.Release(
            date(2026, 11, 18), "movie", "Example Movie",
            "https://www.themoviedb.org/movie/10", "disc", "TMDB",
        ),
        MODULE.Release(
            date(2026, 11, 19), "tv", "Example Series Season 2",
            "https://www.tvmaze.com/shows/123/example-series", "Netflix", "TVmaze",
        ),
    ]
    content = MODULE.build_rss(
        releases, example_config(),
        datetime(2026, 11, 17, 12, tzinfo=ZoneInfo("Europe/Stockholm")),
    )
    rss = ET.fromstring(content)
    assert [item.findtext("title") for item in rss.findall("./channel/item")][:2] == [
        ">> [Movie · disc · 18/11] Example Movie",
        ">> [TV series · Netflix · 19/11] Example Series Season 2",
    ]
    assert rss.findtext("./channel/link") == "https://example.org/"
    items = rss.findall("./channel/item")
    assert items[0].findtext("description") == "Source: TMDB"
    assert items[1].findtext("description") == "Source: TVmaze"
    assert items[0].find("guid").attrib["isPermaLink"] == "false"
    assert len(items) == 3  # Kodi filler line


def test_platform_exclusions_apply_to_new_disc_label():
    items = [
        MODULE.Release(date(2026, 11, 18), "movie", "A", "https://x/1", "disc"),
        MODULE.Release(date(2026, 11, 18), "movie", "A", "https://x/1", "digital"),
    ]
    actual = MODULE.filter_excluded_platforms(items, ["disc"])
    assert [(x.platform, x.title) for x in actual] == [("digital", "A")]


def test_missing_api_key_keeps_existing_feed_unchanged(tmp_path, monkeypatch):
    monkeypatch.delenv("TMDB_API_KEY", raising=False)
    feed = tmp_path / "releases.xml"
    feed.write_text("existing feed", encoding="utf-8")
    cfg = example_config() | {
        "output_file": "releases.xml", "days_ahead": 7,
        "start_offset_days": 0, "request_delay_seconds": 0,
    }
    monkeypatch.setattr(MODULE, "load_config", lambda: cfg)
    monkeypatch.setattr(MODULE, "project_root", lambda: tmp_path)
    with pytest.raises(RuntimeError, match="TMDB_API_KEY"):
        MODULE.main()
    assert feed.read_text(encoding="utf-8") == "existing feed"


def test_failed_tvmaze_call_keeps_existing_feed_unchanged(tmp_path, monkeypatch):
    monkeypatch.setenv("TMDB_API_KEY", "test-key")
    feed = tmp_path / "releases.xml"
    feed.write_text("existing feed", encoding="utf-8")
    cfg = example_config() | {
        "output_file": "releases.xml", "request_delay_seconds": 0,
    }
    monkeypatch.setattr(MODULE, "load_config", lambda: cfg)
    monkeypatch.setattr(MODULE, "project_root", lambda: tmp_path)
    monkeypatch.setattr(MODULE, "fetch_tmdb_movies", lambda *args: [
        MODULE.Release(date.today(), "movie", "Example", "https://a/1", "disc")
    ])
    monkeypatch.setattr(MODULE, "fetch_tvmaze_premieres", lambda *args: (
        _ for _ in ()
    ).throw(RuntimeError("TVmaze is down")))
    with pytest.raises(RuntimeError, match="TVmaze is down"):
        MODULE.main()
    assert feed.read_text(encoding="utf-8") == "existing feed"
