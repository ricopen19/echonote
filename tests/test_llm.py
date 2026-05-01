from unittest.mock import MagicMock, patch

import pytest
from requests.exceptions import ConnectionError

from echonote.llm import LLMConnectionError, LLMError, check_endpoint, complete


def test_check_endpoint_success():
    with patch("requests.get") as mock_get:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_get.return_value = mock_resp

        assert check_endpoint("http://localhost:11434") is True
        mock_get.assert_called_once()


def test_check_endpoint_connection_error():
    with patch("requests.get", side_effect=ConnectionError):
        assert check_endpoint("http://localhost:11434") is False


def test_complete_normal_non_stream():
    with patch("echonote.llm.check_endpoint", return_value=True), patch("requests.post") as mock_post:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"choices": [{"message": {"content": "response text"}}]}

        # Context manager support
        mock_post.return_value.__enter__.return_value = mock_resp

        # Since complete is a generator, we use list() to exhaust it
        result = list(complete("hello", "http://localhost", "dummy", stream=False))
        assert result == ["response text"]


def test_complete_connection_error_on_check():
    with (
        patch("echonote.llm.check_endpoint", return_value=False),
        pytest.raises(LLMConnectionError, match="LLM サーバーに接続できません"),
    ):
        list(complete("hello", "http://localhost", "dummy"))


def test_complete_http_500():
    with patch("echonote.llm.check_endpoint", return_value=True), patch("requests.post") as mock_post:
        mock_resp = MagicMock()
        mock_resp.status_code = 500
        mock_resp.text = "Internal Server Error"

        mock_post.return_value.__enter__.return_value = mock_resp

        with pytest.raises(LLMError, match="LLM エラー \\(HTTP 500\\): Internal Server Error"):
            list(complete("hello", "http://localhost", "dummy"))
