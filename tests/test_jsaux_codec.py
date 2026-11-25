import struct
import zlib

from accessories.jsaux_pixel import codec


def test_frames_match_bytes_captured_from_the_official_app():
    assert codec.frame(1, codec.Cmd.BRIGHTNESS, b"\x50").hex() == "44590102000150b40d"
    assert codec.frame(1, codec.Cmd.POWER, b"\x01").hex() == "44590101000101d2cc"
    assert codec.frame(1, codec.Cmd.TEST, b"\x00").hex() == "445901f0000100a8d5"
    assert codec.frame(1, codec.Cmd.GIF_END, b"\x01").hex() == "4459010b0001010e62"


def test_gif_begin_matches_capture():
    begin = codec.frame(1, codec.Cmd.GIF_BEGIN, struct.pack(">II", 434, 0x1A8F9B2A))
    assert begin.hex() == "4459010400080000" "01b21a8f9b2a63f6"


def test_upload_splits_gif_into_498_byte_chunks_with_sequence():
    gif = bytes(range(256)) * 4
    frames = codec.gif_upload(gif)
    assert frames[0] == codec.frame(1, codec.Cmd.GIF_BEGIN, struct.pack(">II", len(gif), zlib.crc32(gif)))
    chunks = frames[1:-1]
    assert [len(c) - 10 for c in chunks] == [498, 498, 28]
    assert [struct.unpack(">H", c[6:8])[0] for c in chunks] == [0, 1, 2]
    assert all(c[2:4] == b"\x02\x02" for c in chunks)
    assert b"".join(c[8:-2] for c in chunks) == gif
    assert frames[-1].hex() == "4459010b0001010e62"


def test_ack_recognises_echo_and_rejects_nak():
    assert codec.is_ack(bytes.fromhex("44590101000101d2cc"), 1, codec.Cmd.POWER)
    assert not codec.is_ack(bytes.fromhex("4459012100010 04c16".replace(" ", "")), 1, codec.Cmd.ANIMATION)
    assert not codec.is_ack(b"", 1, codec.Cmd.POWER)
    assert not codec.is_ack(bytes.fromhex("44590101000101d2cd"), 1, codec.Cmd.POWER)
