from datetime import date, datetime
from pathlib import Path
import importlib.util
import sys
from zoneinfo import ZoneInfo
from xml.etree import ElementTree as ET


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "generate_feed.py"
SPEC = importlib.util.spec_from_file_location("generate_feed", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


def test_extracts_titles_dates_and_platforms():
    html = """
    <html><body>
      <h2>Jul 16th • Jul 16th •Today</h2>
      <div class="card">
        <a href="/p/descendants-wicked-wonderland"><img alt="Image"></a>
        <a href="/p/descendants-wicked-wonderland">Descendants: Wicked Wonderland</a>
        <span>Disney+</span><span>36</span>
      </div>
      <h2>Jul 17th Jul 17th Tomorrow</h2>
      <div class="card">
        <a href="/p/the-odyssey-movie">Very anticipated The Odyssey</a>
        <span>Cinema</span><span>647</span>
      </div>
      <div class="card">
        <a href="/p/heartstopper-forever"><img alt="Image"></a>
        <a href="/p/heartstopper-forever">Heartstopper Forever</a>
        <span>Netflix</span><span>26</span>
      </div>
    </body></html>
    """

    items = MODULE.parse_release_page(html, date(2026, 7, 16), "movie")
    result = [
        (item.release_date.isoformat(), item.title, item.platform)
        for item in items
    ]
    assert result == [
        ("2026-07-16", "Descendants: Wicked Wonderland", "Disney+"),
        ("2026-07-17", "Heartstopper Forever", "Netflix"),
        ("2026-07-17", "The Odyssey", "Cinema"),
    ]


def test_extracts_multi_platform_release():
    html = """
    <h2>25th 25th In 9 days</h2>
    <div>
      <a href="/p/avatar-aang-the-last-airbender">Avatar Aang: The Last Airbender</a>
      <span>VOD</span><span>/</span><span>Paramount+</span><span>311</span>
    </div>
    """
    items = MODULE.parse_release_page(html, date(2026, 7, 16), "movie")
    assert [(item.title, item.platform) for item in items] == [
        ("Avatar Aang: The Last Airbender", "VOD / Paramount+")
    ]


def test_same_title_can_have_cinema_and_streaming_releases():
    releases = MODULE.deduplicate_releases(
        [
            MODULE.Release(
                date(2026, 7, 17),
                "movie",
                "Example Movie",
                "https://www.releases.com/p/example-movie",
                "Cinema",
            ),
            MODULE.Release(
                date(2026, 8, 28),
                "movie",
                "Example Movie",
                "https://www.releases.com/p/example-movie",
                "Netflix",
            ),
        ]
    )
    assert len(releases) == 2
    assert MODULE.release_guid(releases[0]) != MODULE.release_guid(releases[1])


def test_physical_formats_are_removed_but_streaming_part_is_kept():
    releases = [
        MODULE.Release(
            date(2026, 7, 21),
            "tv",
            "Example Season 2",
            "https://www.releases.com/p/example-season-2",
            "Hulu / Blu-ray / DVD / 4K Blu-ray",
        ),
        MODULE.Release(
            date(2026, 7, 22),
            "movie",
            "Disc Only Movie",
            "https://www.releases.com/p/disc-only-movie",
            "DVD / Blu-ray",
        ),
    ]
    filtered = MODULE.filter_excluded_platforms(
        releases,
        ["DVD", "Blu-ray", "4K Blu-ray"],
    )
    assert [(item.title, item.platform) for item in filtered] == [
        ("Example Season 2", "Hulu")
    ]


def test_rss_titles_include_platform_and_guids_are_not_permalinks():
    releases = [
        MODULE.Release(
            date(2026, 7, 17),
            "movie",
            "The Odyssey",
            "https://www.releases.com/p/the-odyssey-movie",
            "Cinema",
        ),
        MODULE.Release(
            date(2026, 7, 21),
            "tv",
            "Example Series Season 2",
            "https://www.releases.com/p/example-series-season-2",
            "Netflix",
        ),
    ]
    config = {
        "feed_title": "Upcoming movie and TV releases",
        "feed_description": "Test",
        "language": "en-US",
        "timezone": "Europe/Stockholm",
        "date_format": "%-d/%-m",
        "movie_label": "Movie",
        "tv_label": "TV series",
        "include_platform": True,
        "minimum_kodi_items": 3,
    }
    xml = MODULE.build_rss(
        releases,
        config,
        datetime(2026, 7, 16, 12, tzinfo=ZoneInfo("Europe/Stockholm")),
    )
    root = ET.fromstring(xml)
    titles = [item.findtext("title") for item in root.findall("./channel/item")]
    assert titles[:2] == [
        "Movie (cinema): 17/7 – The Odyssey",
        "TV series (Netflix): 21/7 – Example Series Season 2",
    ]
    guids = root.findall("./channel/item/guid")
    assert guids[0].attrib["isPermaLink"] == "false"
    assert guids[0].text != guids[1].text


def test_missing_platform_uses_old_safe_format():
    release = MODULE.Release(
        date(2026, 7, 31),
        "movie",
        "Unknown Release",
        "https://www.releases.com/p/unknown-release",
        None,
    )
    config = {
        "feed_title": "Upcoming movie and TV releases",
        "feed_description": "Test",
        "language": "en-US",
        "timezone": "Europe/Stockholm",
        "date_format": "%-d/%-m",
        "movie_label": "Movie",
        "tv_label": "TV series",
        "include_platform": True,
        "minimum_kodi_items": 0,
    }
    xml = MODULE.build_rss(
        [release],
        config,
        datetime(2026, 7, 16, 12, tzinfo=ZoneInfo("Europe/Stockholm")),
    )
    root = ET.fromstring(xml)
    assert root.findtext("./channel/item/title") == "Movie: 31/7 – Unknown Release"


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
