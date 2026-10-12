import struct
import pytest
from src.domain.ble_pcapng import capture_header, packet_block


def blocks(raw):
    offset = 0
    result = []
    while offset < len(raw):
        kind, length = struct.unpack_from('<II', raw, offset)
        assert length % 4 == 0
        assert struct.unpack_from('<I', raw, offset + length - 4)[0] == length
        result.append((kind, raw[offset + 8:offset + length - 4]))
        offset += length
    assert offset == len(raw)
    return result


def test_capture_contains_radio_header_and_honest_power_comment():
    packet = dict(crc_ok=True, channel=37, pdu_hex='4206665544332211', crc_hex='010203',
                  power_dbfs=-23.45, sample_index_host=100, clipped_fraction=0)
    data = capture_header() + packet_block(packet, timestamp_ns=1234567000)
    parts = blocks(data)
    assert [p[0] for p in parts] == [0x0A0D0D0A, 1, 6]
    assert struct.unpack_from('<H', parts[1][1])[0] == 256
    body = parts[2][1]
    assert struct.unpack_from('<III', body) == (0, 0, 1234567)
    radio = body[20:30]
    assert radio[0] == 0  # frequency index 0 means logical advertising channel 37
    flags = struct.unpack_from('<H', radio, 8)[0]
    assert flags & 0x0C01 == 0x0C01
    assert not flags & 2  # never claim measured dBm
    assert body[30:34] == bytes.fromhex('d6be898e')
    assert b'-23.45 dBFS' in body
    assert b'not RF time' in body


def test_bad_crc_is_not_exported_as_valid():
    with pytest.raises(ValueError):
        packet_block({'crc_ok': False})
