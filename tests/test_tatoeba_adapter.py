"""tatoeba.org is blocked from this sandbox, so these tests mock
requests.Session.get against Tatoeba's *documented* api_v0 response
shape — they do NOT prove the live API still returns this shape.
Re-verify against a real response before trusting this in production."""

from unittest.mock import MagicMock, patch

from pipeline.sources.tatoeba_adapter import TatoebaAdapter


def _mock_response(payload):
    resp = MagicMock()
    resp.raise_for_status.return_value = None
    resp.json.return_value = payload
    return resp


SAMPLE_RESULTS = {
    "results": [
        {
            "id": 12345,
            "text": "This is an example sentence.",
            "audios": [{"author": "someone"}],
            "translations": [
                [{"lang": "cmn", "text": "這是一個例句。"}],
            ],
        },
        {
            "id": 67890,
            "text": "Another example.",
            "audios": [],
            "translations": [],
        },
    ]
}


def test_parses_text_translation_and_audio():
    adapter = TatoebaAdapter()
    with patch.object(adapter.session, "get", return_value=_mock_response(SAMPLE_RESULTS)):
        result = adapter.get_example_sentences("example")
    assert result[0]["en"] == "This is an example sentence."
    assert result[0]["zh"] == "這是一個例句。"
    assert result[0]["audio_url"] == "https://audio.tatoeba.org/sentences/eng/12345.mp3"


def test_sentence_without_audio_or_translation():
    adapter = TatoebaAdapter()
    with patch.object(adapter.session, "get", return_value=_mock_response(SAMPLE_RESULTS)):
        result = adapter.get_example_sentences("example")
    assert result[1]["zh"] is None
    assert result[1]["audio_url"] is None


def test_network_error_returns_none_not_raise():
    import requests

    adapter = TatoebaAdapter()
    with patch.object(adapter.session, "get", side_effect=requests.RequestException("boom")):
        assert adapter.get_example_sentences("example") is None
