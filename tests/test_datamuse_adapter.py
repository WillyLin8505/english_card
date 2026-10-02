"""api.datamuse.com is blocked from this sandbox, so these tests mock
requests.Session.get and only verify the adapter's parsing/param logic —
they do NOT prove the live API still returns this shape. Re-run against
a real endpoint from a network-unrestricted environment before trusting
this in production."""

from unittest.mock import MagicMock, patch

from pipeline.sources.datamuse_adapter import DatamuseAdapter


def _mock_response(payload):
    resp = MagicMock()
    resp.raise_for_status.return_value = None
    resp.json.return_value = payload
    return resp


def test_get_synonyms_parses_word_field():
    adapter = DatamuseAdapter()
    with patch.object(adapter.session, "get", return_value=_mock_response(
        [{"word": "instance", "score": 100}, {"word": "illustration", "score": 90}]
    )) as mock_get:
        result = adapter.get_synonyms("example")
        assert result == ["instance", "illustration"]
        assert mock_get.call_args.kwargs["params"]["rel_syn"] == "example"


def test_get_homophones_uses_rel_hom():
    adapter = DatamuseAdapter()
    with patch.object(adapter.session, "get", return_value=_mock_response(
        [{"word": "flower"}]
    )) as mock_get:
        result = adapter.get_homophones("flour")
        assert result == ["flower"]
        assert mock_get.call_args.kwargs["params"]["rel_hom"] == "flour"


def test_empty_response_returns_none():
    adapter = DatamuseAdapter()
    with patch.object(adapter.session, "get", return_value=_mock_response([])):
        assert adapter.get_synonyms("zzznotaword") is None


def test_network_error_returns_none_not_raise():
    import requests

    adapter = DatamuseAdapter()
    with patch.object(adapter.session, "get", side_effect=requests.RequestException("boom")):
        assert adapter.get_synonyms("example") is None
