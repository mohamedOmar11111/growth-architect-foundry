"""Arabic number agreement in the client report sentence."""
import pytest

from commands.perf_text import ar_conversions_phrase


@pytest.mark.parametrize("n, expected", [
    (0, "ولم نحقق أي تحويل"),
    (1, "وحققنا تحويلًا واحدًا"),
    (2, "وحققنا تحويلين"),
    (3, "وحققنا 3 تحويلات"),
    (10, "وحققنا 10 تحويلات"),
    (11, "وحققنا 11 تحويلًا"),
    (37, "وحققنا 37 تحويلًا"),
    (1234, "وحققنا 1,234 تحويلًا"),
])
def test_conversions_phrase_agrees_with_count(n, expected):
    assert ar_conversions_phrase(n) == expected
