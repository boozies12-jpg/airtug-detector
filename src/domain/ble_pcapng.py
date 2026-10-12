"""PCAPNG encoding for Wireshark LINKTYPE_BLUETOOTH_LE_LL_WITH_PHDR (256).

Radio header follows Wireshark packet-btle_rf.c. Uncalibrated dBFS is stored
in packet comments, never in the RF header's calibrated dBm field.
"""
import struct
import time


def padded(data):
    return data + b'\0' * (-len(data) % 4)


def option(code, value):
    return struct.pack('<HH', code, len(value)) + padded(value)


def block(kind, body):
    body = padded(body)
    length = len(body) + 12
    return struct.pack('<II', kind, length) + body + struct.pack('<I', length)


def capture_header():
    section = block(0x0A0D0D0A, struct.pack('<IHHq', 0x1A2B3C4D, 1, 0, -1))
    interface = struct.pack('<HHI', 256, 0, 65535)
    interface += option(2, b'Pluto SDR BLE channel 37')
    interface += option(3, b'BLE 1M; host export timestamps, not RF timestamps; dBFS in packet comments')
    interface += option(9, b'\x06') + option(0, b'')  # microseconds
    return section + block(1, interface)


def packet_block(packet, timestamp_ns=None):
    if not packet.get('crc_ok'):
        raise ValueError('Only CRC-validated decoded packets are supported')
    channel = packet['channel']
    # The RF pseudoheader uses frequency index, not logical BLE channel index.
    rf_channel = {37: 0, 38: 12, 39: 39}[channel]
    flags = 0x0001 | 0x0010 | 0x0400 | 0x0800  # dewhitened, reference AA, checked, valid
    radio = struct.pack('<BbbBIH', rf_channel, 0, 0, 0, 0x8E89BED6, flags)
    payload = radio + bytes.fromhex('d6be898e' + packet['pdu_hex'] + packet['crc_hex'])
    ns = time.time_ns() if timestamp_ns is None else timestamp_ns
    stamp = ns // 1000
    comment = (f"SDR power={packet['power_dbfs']:.2f} dBFS (uncalibrated); gain=40 dB; "
               f"BLE channel={channel}; host_sample_index={packet.get('sample_index_host', 'unknown')}; "
               f"clipped_fraction={packet.get('clipped_fraction', 0):.6f}; "
               "timestamp=host export time, not RF time; AA=canonical advertising reference; source continuity=unverified")
    body = struct.pack('<IIIII', 0, stamp >> 32, stamp & 0xFFFFFFFF, len(payload), len(payload))
    body += padded(payload) + option(1, comment.encode('utf-8')) + option(0, b'')
    return block(6, body)
