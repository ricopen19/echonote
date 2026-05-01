from unittest.mock import MagicMock, patch

import pytest

from echonote.transcriber import transcribe


def test_transcribe_normal():
    # Arrange
    mock_segment = MagicMock()
    mock_segment.start = 0.0
    mock_segment.end = 2.0
    mock_segment.text = "hello"

    with (
        patch("shutil.which", return_value="/usr/bin/ffmpeg"),
        patch("sys.platform", "linux"),  # Force fallback to faster-whisper
        patch("faster_whisper.WhisperModel") as mock_whisper_class,
    ):
        mock_model = mock_whisper_class.return_value

        mock_model.transcribe.return_value = ([mock_segment], None)

        # Act
        result = transcribe("dummy.wav", "tiny", "ja")

        # Assert
        assert result == [{"start": 0.0, "end": 2.0, "text": "hello"}]
        mock_whisper_class.assert_called_once_with("tiny", device="cpu", compute_type="int8")
        mock_model.transcribe.assert_called_once_with("dummy.wav", language="ja", beam_size=5)


def test_transcribe_ffmpeg_not_installed():
    with patch("shutil.which", return_value=None), pytest.raises(
        RuntimeError, match="ffmpeg が見つかりません。"
    ):
        transcribe("dummy.wav", "tiny", "ja")
