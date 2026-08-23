"""Pure unit tests for match_logo() - no DB, no network, same spirit as test_merge.py."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.logo_matching import LogoCandidate, match_logo


def test_no_logos_no_match():
    assert match_logo(["plex.example.com"], []) is None


def test_no_matching_keyword():
    logos = [LogoCandidate(id=1, keywords=["sonarr"])]
    assert match_logo(["plex.example.com"], logos) is None


def test_case_insensitive_substring_match():
    logos = [LogoCandidate(id=1, keywords=["PLEX"])]
    assert match_logo(["plex.example.com"], logos) == 1


def test_longest_keyword_wins():
    # "web" matches generically, "plexweb" is more specific - the longer, more specific
    # keyword should win even though it's defined on a different logo and appears later.
    logos = [
        LogoCandidate(id=1, keywords=["web"]),
        LogoCandidate(id=2, keywords=["plexweb"]),
    ]
    assert match_logo(["plexweb.example.com"], logos) == 2


def test_tie_break_by_lowest_id():
    logos = [
        LogoCandidate(id=5, keywords=["plex"]),
        LogoCandidate(id=2, keywords=["plex"]),
    ]
    assert match_logo(["plex.example.com"], logos) == 2


def test_multiple_candidates_checked():
    logos = [LogoCandidate(id=1, keywords=["sonarr"])]
    assert match_logo(["10.0.0.5", "sonarr.example.com"], logos) == 1


def test_blank_and_whitespace_keywords_ignored():
    logos = [LogoCandidate(id=1, keywords=["", "  ", "plex"])]
    assert match_logo(["plex.example.com"], logos) == 1


def test_separators_ignored_when_matching():
    # a real case hit during development: catalog slug "home-assistant" (hyphenated) didn't match
    # a real container named "homeassistant" (no separator) - separators must be stripped from
    # both sides before comparing, not just casing.
    logos = [LogoCandidate(id=1, keywords=["home-assistant"])]
    assert match_logo(["homeassistant"], logos) == 1
    assert match_logo(["home_assistant"], logos) == 1
    assert match_logo(["home assistant"], logos) == 1


def test_short_keywords_ignored_to_avoid_false_positives():
    # a real case hit during development: "provider.example" coincidentally contains "ide" (an alias
    # for the "code"/VS Code catalog entry) - keywords under 4 chars must never match at all,
    # not just lose a length tie-break, since they're too likely to be pure coincidence.
    logos = [LogoCandidate(id=1, keywords=["ide"]), LogoCandidate(id=2, keywords=["r"])]
    assert match_logo(["auth.provider.example"], logos) is None
    assert match_logo(["hermesagent"], logos) is None


if __name__ == "__main__":
    test_no_logos_no_match()
    test_no_matching_keyword()
    test_case_insensitive_substring_match()
    test_longest_keyword_wins()
    test_tie_break_by_lowest_id()
    test_multiple_candidates_checked()
    test_blank_and_whitespace_keywords_ignored()
    test_separators_ignored_when_matching()
    test_short_keywords_ignored_to_avoid_false_positives()
    print("All logo_matching tests passed.")
