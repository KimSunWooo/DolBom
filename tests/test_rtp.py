from dolbom.rtp_jpeg import packetize_jpeg, parse_rtp, reassemble, MAX_PAYLOAD


def test_fragments_large_payload():
    jpeg = bytes(range(256)) * 20  # 5120 bytes
    packets, seq = packetize_jpeg(
        jpeg, seq_start=10, timestamp=99, ssrc=7, width=320, height=180
    )
    assert len(packets) > 1
    assert all(len(p) <= 12 + 8 + MAX_PAYLOAD for p in packets)
    last = parse_rtp(packets[-1])
    first = parse_rtp(packets[0])
    assert first["seq"] == 10
    assert last["marker"] is True
    assert first["marker"] is False
    assert reassemble(packets) == jpeg
    assert seq == 10 + len(packets)


def test_empty():
    packets, seq = packetize_jpeg(b"", seq_start=0, timestamp=0, ssrc=1, width=8, height=8)
    assert packets == []
    assert seq == 0
