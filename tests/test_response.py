"""Unit tests for ``browser_stealth.response`` (Response + StatusText)."""

import pytest

from browser_stealth.response import Response, StatusText


def make_response(**overrides) -> Response:
    """Build a Response with sane defaults, overriding only what a test cares about."""
    params = dict(
        url="https://example.com",
        content="<html></html>",
        status=200,
        reason="OK",
        cookies={},
        headers={},
        request_headers={},
    )
    params.update(overrides)
    return Response(**params)


class TestResponseBody:
    def test_str_content_is_encoded_to_bytes(self):
        assert make_response(content="<html></html>").body == b"<html></html>"

    def test_bytes_content_is_stored_unchanged(self):
        assert make_response(content=b"\x00\x01\x02").body == b"\x00\x01\x02"

    def test_text_decodes_the_body(self):
        assert make_response(content="café").text == "café"

    def test_text_respects_a_non_utf8_encoding(self):
        response = make_response(content="café".encode("latin-1"), encoding="latin-1")
        assert response.text == "café"

    def test_text_replaces_undecodable_bytes(self):
        # 0xff is not valid UTF-8; decoding uses errors="replace".
        assert "�" in make_response(content=b"\xff", encoding="utf-8").text

    def test_empty_encoding_falls_back_to_utf8(self):
        response = make_response(content="hi", encoding="")
        assert response.encoding == "utf-8"
        assert response.body == b"hi"


class TestResponseMetadata:
    def test_meta_defaults_to_empty_dict(self):
        assert make_response().meta == {}

    def test_non_dict_meta_raises_type_error(self):
        with pytest.raises(TypeError):
            make_response(meta=["not", "a", "dict"])

    def test_history_defaults_to_empty_list(self):
        assert make_response().history == []

    def test_captured_xhr_defaults_to_empty_list(self):
        assert make_response().captured_xhr == []

    def test_repr_includes_status_reason_and_url(self):
        assert repr(make_response()) == "<Response [200 OK] https://example.com>"

    def test_str_includes_status_and_url(self):
        assert str(make_response()) == "<200 https://example.com>"


class TestStatusText:
    @pytest.mark.parametrize(
        "code, phrase",
        [
            (200, "OK"),
            (301, "Moved Permanently"),
            (404, "Not Found"),
            (418, "I'm a teapot"),
            (503, "Service Unavailable"),
        ],
    )
    def test_maps_known_codes_to_reason_phrases(self, code, phrase):
        assert StatusText.get(code) == phrase

    def test_unknown_code_returns_placeholder(self):
        assert StatusText.get(799) == "Unknown Status Code"
