"""Our own trained material classifier (TrashNet), for photos of a single item.

"Which bin does this go in?" -> photo of one item -> material + SWM stream.
Loaded lazily; if the model file or scikit-learn is missing, the feature reports itself
unavailable instead of failing. Low-confidence predictions are returned as "not sure".
"""

from __future__ import annotations

import io
import json
import logging
from functools import lru_cache
from pathlib import Path

log = logging.getLogger("kachra.item_model")
MODEL_DIR = Path(__file__).resolve().parent.parent / "ml" / "model"
MIN_CONFIDENCE = 0.55


@lru_cache(maxsize=1)
def _load():
    try:
        import joblib

        return joblib.load(MODEL_DIR / "trashnet_svm.joblib")
    except Exception as e:  # missing file or library: feature off, app keeps working
        log.warning("item model unavailable: %s", e)
        return None


def available() -> bool:
    return _load() is not None


@lru_cache(maxsize=1)
def metrics() -> dict | None:
    try:
        return json.loads((MODEL_DIR / "metrics.json").read_text())
    except Exception:
        return None


def classify(image_bytes: bytes) -> dict:
    bundle = _load()
    if bundle is None:
        raise RuntimeError("The item model is not installed on this server.")
    from PIL import Image

    from ml.train_trashnet import features

    x = features(Image.open(io.BytesIO(image_bytes)))[None, :]
    probs = bundle["model"].predict_proba(x)[0]
    classes = bundle["classes"]
    order = probs.argsort()[::-1]
    top = [{"material": classes[i], "p": round(float(probs[i]), 3), "stream": bundle["to_stream"][classes[i]]}
           for i in order[:3]]
    best = top[0]
    sure = best["p"] >= MIN_CONFIDENCE and best["stream"] is not None
    return {"top": top, "material": best["material"] if sure else None, "stream": best["stream"] if sure else None,
            "confidence": best["p"], "sure": sure, "model": "TrashNet SVM (trained by us)"}
