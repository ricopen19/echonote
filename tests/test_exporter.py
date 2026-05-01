from echonote.exporter import segments_to_text, segments_to_transcript, to_markdown


def test_segments_to_text():
    segments = [
        {"start": 0.0, "end": 2.0, "text": "hello"},
        {"start": 2.0, "end": 4.5, "text": "world"},
    ]
    result = segments_to_text(segments)
    assert result == "hello\nworld"


def test_segments_to_transcript():
    segments = [
        {"start": 0.0, "end": 2.0, "text": "hello"},
        {"start": 62.0, "end": 65.5, "text": "world"},
    ]
    result = segments_to_transcript(segments)
    assert result == "[00:00 - 00:02] hello\n[01:02 - 01:05] world"


def test_to_markdown():
    content = "# Title\n\nBody"
    assert to_markdown(content) == content


def test_empty_segments():
    assert segments_to_text([]) == ""
    assert segments_to_transcript([]) == ""
