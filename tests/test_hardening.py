"""Image handling, rate limiting, name matching and campus-time days."""

from tests import _env  # noqa: F401  (must be first)

import asyncio
import io
import unittest
from datetime import datetime, timezone

from PIL import Image

from app import images, scoring
from app.matching import match_bhawan
from app.ratelimit import WriteGuard


def jpeg_with_gps(size=(3000, 2000)) -> bytes:
    im = Image.new("RGB", size, (200, 120, 40))
    exif = Image.Exif()
    exif[0x8825] = {1: "N", 2: (29.0, 52.0, 0.0)}  # GPSInfo
    exif[0x0112] = 1  # Orientation
    buf = io.BytesIO()
    im.save(buf, format="JPEG", exif=exif)
    return buf.getvalue()


class Images(unittest.TestCase):
    def test_sniff_by_content_not_name(self):
        self.assertEqual(images.sniff(b"\xff\xd8\xff\xe0rest"), "image/jpeg")
        self.assertEqual(images.sniff(b"RIFF\x00\x00\x00\x00WEBPVP8 "), "image/webp")
        self.assertIsNone(images.sniff(b"<html>"))

    def test_normalise_shrinks_and_strips_location(self):
        raw = jpeg_with_gps()
        self.assertIn(0x8825, Image.open(io.BytesIO(raw)).getexif())
        out, mime = images.normalise(raw)
        im = Image.open(io.BytesIO(out))
        self.assertEqual(mime, "image/jpeg")
        self.assertLessEqual(max(im.size), images.MAX_SIDE)
        self.assertNotIn(0x8825, im.getexif())  # no GPS left in the stored file
        self.assertLess(len(out), len(raw))

    def test_rejects_non_images_and_corrupt_files(self):
        with self.assertRaises(images.BadImage):
            images.normalise(b"not an image")
        with self.assertRaises(images.BadImage):
            images.normalise(b"\xff\xd8\xff" + b"\x00" * 50)


class RateLimit(unittest.TestCase):
    def test_sliding_window(self):
        g = WriteGuard(app=None, max_body=10, per_minute=3)
        self.assertEqual([g.allow("ip", now=t) for t in (0, 1, 2, 3)], [True, True, True, False])
        self.assertTrue(g.allow("other-ip", now=3))
        self.assertTrue(g.allow("ip", now=61))  # oldest hit expired

    def test_returns_429(self):
        calls = []

        async def inner(scope, receive, send):
            calls.append(1)

        g = WriteGuard(inner, max_body=100, per_minute=1)
        sent = []

        async def send(msg):
            sent.append(msg)

        scope = {"type": "http", "method": "POST", "path": "/api/reports", "headers": [], "client": ("1.2.3.4", 1)}
        asyncio.run(g(scope, None, send))
        asyncio.run(g(scope, None, send))
        self.assertEqual(len(calls), 1)
        self.assertEqual(sent[0]["status"], 429)

    def test_forwarded_ip(self):
        scope = {"headers": [(b"x-forwarded-for", b"9.9.9.9, 10.0.0.1")], "client": ("10.0.0.1", 1)}
        self.assertEqual(WriteGuard.client_ip(scope), "9.9.9.9")


class Names(unittest.TestCase):
    def test_ambiguous_prefix_is_rejected(self):
        self.assertIsNone(match_bhawan("raj"))          # Rajendra or Rajiv?
        self.assertEqual(match_bhawan("raje"), "Rajendra")
        self.assertEqual(match_bhawan("Rajiv Bhawan"), "Rajiv")
        self.assertEqual(match_bhawan("vigyan  kunj"), "Vigyan Kunj")


class CampusTime(unittest.TestCase):
    def test_local_day_uses_ist(self):
        # 20:00 UTC on 23 Oct is 01:30 IST on 24 Oct.
        self.assertEqual(scoring.local_day("2026-10-23T20:00:00+00:00"), "2026-10-24")

    def test_window_starts_at_local_midnight(self):
        now = datetime(2026, 10, 24, 4, 0, tzinfo=timezone.utc)  # 09:30 IST
        self.assertEqual(scoring.window_start(1, now), "2026-10-23T18:30:00+00:00")
        self.assertEqual(scoring.window_start(7, now), "2026-10-17T18:30:00+00:00")


if __name__ == "__main__":
    unittest.main()
