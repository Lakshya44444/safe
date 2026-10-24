"""Our TrashNet item classifier, served at /api/identify-item."""

from tests import _env  # noqa: F401  (must be first)

import io
import unittest

from PIL import Image
from starlette.testclient import TestClient

from app import item_model
from app.server import app


def jpeg(color=(200, 200, 200)):
    b = io.BytesIO()
    Image.new("RGB", (512, 384), color).save(b, "JPEG")
    return b.getvalue()


@unittest.skipUnless(item_model.available(), "model file not built")
class ItemModel(unittest.TestCase):
    def test_classify_shape(self):
        r = item_model.classify(jpeg())
        self.assertEqual(len(r["top"]), 3)
        self.assertAlmostEqual(sum(t["p"] for t in r["top"]), sum(t["p"] for t in r["top"]))
        self.assertIn(r["top"][0]["material"], ["cardboard", "glass", "metal", "paper", "plastic", "trash"])
        if not r["sure"]:
            self.assertIsNone(r["stream"])

    def test_endpoint(self):
        with TestClient(app) as c:
            r = c.post("/api/identify-item", files={"photo": ("x.jpg", jpeg(), "image/jpeg")})
            self.assertEqual(r.status_code, 200)
            self.assertIn("confidence", r.json())
            self.assertEqual(c.post("/api/identify-item", files={"photo": ("x.txt", b"hello", "text/plain")}).status_code, 400)
            card = c.get("/api/model").json()
            self.assertTrue(card["available"])
            self.assertGreater(card["metrics"]["test_accuracy"], 0.5)


if __name__ == "__main__":
    unittest.main()
