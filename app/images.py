"""Check and normalise uploaded bin photos.

* The real type comes from the file's bytes, never from its name.
* Photos are rotated upright (EXIF), shrunk to at most MAX_SIDE px and re-saved as JPEG.
  Phone photos are 3-8 MB; Anthropic rejects images over 5 MB and big images cost more tokens.
* Re-encoding drops EXIF metadata, including the GPS location phones embed.
"""

from __future__ import annotations

import io

MAX_SIDE = 1600

_SIGNATURES = {
    "image/jpeg": lambda b: b.startswith(b"\xff\xd8\xff"),
    "image/png": lambda b: b.startswith(b"\x89PNG\r\n\x1a\n"),
    "image/webp": lambda b: b[:4] == b"RIFF" and b[8:12] == b"WEBP",
}
EXT = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp"}


class BadImage(ValueError):
    pass


def sniff(data: bytes) -> str | None:
    """Return the image MIME type from magic bytes, or None if it is not a supported image."""
    return next((mime for mime, test in _SIGNATURES.items() if test(data)), None)


def normalise(data: bytes) -> tuple[bytes, str]:
    """Return (bytes, mime) ready to store and send to a model."""
    mime = sniff(data)
    if mime is None:
        raise BadImage("The photo must be a JPEG, PNG or WebP image.")
    try:
        from PIL import Image, ImageOps
    except ImportError:  # Pillow missing: keep the original bytes, type is still verified
        return data, mime
    try:
        with Image.open(io.BytesIO(data)) as im:
            im = ImageOps.exif_transpose(im)
            im.thumbnail((MAX_SIDE, MAX_SIDE))
            if im.mode not in ("RGB", "L"):
                im = im.convert("RGB")
            out = io.BytesIO()
            im.save(out, format="JPEG", quality=85, optimize=True)
    except Exception as e:  # truncated or corrupt file that only looks like an image
        raise BadImage("The photo could not be read. Please take it again.") from e
    return out.getvalue(), "image/jpeg"
