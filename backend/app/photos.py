"""Photos guests send. The phone redraws them; the server only checks what arrived and drops the metadata segments
(no image library in the stack)."""

MAX_SIDE = 1600
# A 1600 px JPEG from the phone is well under this; anything bigger was not redrawn
MAX_BYTES = 1024 * 1024
# The phone's copy for the moderation list
THUMB_SIDE = 400
THUMB_MAX_BYTES = 100 * 1024
# The whole files request: the photo, its thumbnail and the multipart framing
MAX_BODY = MAX_BYTES + THUMB_MAX_BYTES + 64 * 1024

# Start-of-frame markers carry the size: baseline, progressive and the rarer coding modes, not DHT/JPG/DAC
_SOF = {0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF}


def jpeg_size(data: bytes) -> tuple[int, int] | None:
    """(width, height) read from the JPEG's frame header, or None when it is not a JPEG."""
    if not data.startswith(b"\xff\xd8"):
        return None
    i = 2
    while i + 4 <= len(data):
        if data[i] != 0xFF:
            return None
        marker = data[i + 1]
        if marker == 0xFF:  # fill byte
            i += 1
            continue
        if marker in (0x01, *range(0xD0, 0xD8)):  # markers without a length
            i += 2
            continue
        length = int.from_bytes(data[i + 2:i + 4], "big")
        if marker in _SOF:
            if i + 9 > len(data):
                return None
            height = int.from_bytes(data[i + 5:i + 7], "big")
            width = int.from_bytes(data[i + 7:i + 9], "big")
            return width, height
        if marker == 0xDA:  # image data started without a frame header
            return None
        i += 2 + length
    return None


def strip_metadata(data: bytes) -> bytes:
    """The JPEG without its APP1–APP15 segments (Exif with GPS and camera data, XMP, ICC …). APP0 (JFIF) and
    everything from the image data on are kept as they are. Called on a JPEG jpeg_size has read."""
    out = bytearray(data[:2])
    i = 2
    while i + 4 <= len(data):
        if data[i] != 0xFF:
            break
        marker = data[i + 1]
        if marker == 0xFF:  # fill byte
            i += 1
            continue
        if marker in (0x01, *range(0xD0, 0xD8)):  # markers without a length
            out += data[i:i + 2]
            i += 2
            continue
        if marker == 0xDA:  # image data: kept as it is to the end
            break
        end = i + 2 + int.from_bytes(data[i + 2:i + 4], "big")
        if not 0xE1 <= marker <= 0xEF:
            out += data[i:end]
        i = end
    return bytes(out + data[i:])
