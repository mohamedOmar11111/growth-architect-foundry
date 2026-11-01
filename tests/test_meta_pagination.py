"""Meta list endpoints must be followed past the first page, and must fail closed at the page cap."""
from unittest.mock import MagicMock, patch

import pytest

from commands import live
from loops import meta_ads


def _page(rows, after=None):
    body = {"data": rows}
    if after:
        body["paging"] = {"cursors": {"after": after}, "next": "https://graph.facebook.com/next"}
    return body


def test_live_follows_cursors_and_joins_pages():
    pages = [_page([{"id": "1"}], after="A"), _page([{"id": "2"}], after="B"), _page([{"id": "3"}])]
    with patch.object(live, "_meta_get", side_effect=pages) as get:
        rows = live._meta_get_all("http://x", {"access_token": "T", "limit": 200})
    assert [r["id"] for r in rows] == ["1", "2", "3"]
    assert get.call_args_list[1].args[1]["after"] == "A"
    assert get.call_args_list[2].args[1]["after"] == "B"
    assert get.call_args_list[0].args[1].get("after") is None


def test_live_refuses_partial_data_past_page_cap():
    endless = _page([{"id": "x"}], after="A")
    with patch.object(live, "_meta_get", return_value=endless):
        with pytest.raises(live.LiveFetchError, match="refusing to report partial data"):
            live._meta_get_all("http://x", {"access_token": "T"})


def _response(body):
    resp = MagicMock()
    resp.json.return_value = body
    resp.raise_for_status.return_value = None
    return resp


def test_loop_follows_cursors():
    pages = [_response(_page([{"id": "1"}], after="A")), _response(_page([{"id": "2"}]))]
    with patch.object(meta_ads.requests, "get", side_effect=pages) as get:
        rows = meta_ads._get_all("http://x", {"access_token": "T"})
    assert [r["id"] for r in rows] == ["1", "2"]
    assert get.call_args_list[1].kwargs["params"]["after"] == "A"


def test_loop_refuses_partial_data_past_page_cap():
    with patch.object(meta_ads.requests, "get", return_value=_response(_page([{"id": "x"}], after="A"))):
        with pytest.raises(RuntimeError, match="refusing to report partial data"):
            meta_ads._get_all("http://x", {})


def test_graph_version_is_not_the_expiring_one():
    assert live.GRAPH_API_VERSION == meta_ads.GRAPH_API_VERSION == "v25.0"
