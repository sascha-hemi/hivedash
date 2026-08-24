"""Pure version-parsing/comparison logic, no network - see app/version_check.py."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.version_check import is_update_available, parse_version  # noqa: E402


def test_parse_version():
    assert parse_version("1.2.0") == (1, 2, 0)
    assert parse_version("v1.2.0") == (1, 2, 0)
    assert parse_version("V2.0") == (2, 0)
    assert parse_version("dev") is None
    assert parse_version("main") is None
    print("test_parse_version passed.")


def test_is_update_available():
    assert is_update_available("1.0.0", "v1.1.0") is True
    assert is_update_available("1.1.0", "v1.1.0") is False
    assert is_update_available("1.2.0", "v1.1.0") is False
    # a dev/branch build (unparseable current version) can never be reported as outdated
    assert is_update_available("dev", "v1.1.0") is None
    assert is_update_available("1.0.0", "not-a-version") is None
    print("test_is_update_available passed.")


test_parse_version()
test_is_update_available()
print("All version_check tests passed.")
