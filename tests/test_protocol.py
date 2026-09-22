from dolbom.protocol import encode_message, try_decode, ProtocolError, hello
import pytest


def test_roundtrip():
    packed = encode_message(hello("client-1"))
    buf = bytearray(packed)
    msg, rest = try_decode(buf)
    assert rest == bytearray()
    assert msg["type"] == "hello"
    assert msg["client_id"] == "client-1"
    assert msg["protocol_status"] == "draft"


def test_partial_buffer():
    packed = encode_message({"type": "ping"})
    half = bytearray(packed[:5])
    msg, rest = try_decode(half)
    assert msg is None
    assert rest == half


def test_two_messages():
    a = encode_message({"type": "a", "n": 1})
    b = encode_message({"type": "b", "n": 2})
    buf = bytearray(a + b)
    first, buf = try_decode(buf)
    second, buf = try_decode(buf)
    assert first["type"] == "a"
    assert second["type"] == "b"
    assert buf == bytearray()


def test_rejects_huge():
    buf = bytearray((3_000_000).to_bytes(4, "big") + b"x")
    with pytest.raises(ProtocolError):
        try_decode(buf)
