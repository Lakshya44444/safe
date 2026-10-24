"""Train and evaluate a waste-material classifier on the real TrashNet dataset.

TrashNet (Thung & Yang, Stanford CS229, 2016; MIT licence): 2,527 photos of single waste items,
6 classes: cardboard, glass, metal, paper, plastic, trash.  https://github.com/garythung/trashnet

    git clone --depth 1 https://github.com/garythung/trashnet
    unzip trashnet/data/dataset-resized.zip -d trashnet_data
    python -m ml.train_trashnet trashnet_data/dataset-resized

Features: HSV colour histogram + HOG (shape/edges) + LBP (surface texture: corrugated cardboard,
shiny metal, crinkled plastic). Classifier: RBF-kernel SVM, chosen by cross-validation on the
training split only. The test split is held out and used once, for the final numbers.
Writes ml/model/trashnet_svm.joblib and ml/model/metrics.json.
"""

from __future__ import annotations

import json
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import joblib
import numpy as np
from PIL import Image, ImageOps
from skimage.feature import hog, local_binary_pattern
from sklearn.metrics import classification_report, confusion_matrix
from sklearn.model_selection import GridSearchCV, StratifiedKFold, train_test_split
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.svm import SVC

CLASSES = ["cardboard", "glass", "metal", "paper", "plastic", "trash"]
# TrashNet material -> SWM Rules 2026 stream. "trash" is TrashNet's mixed non-recyclable class,
# so it maps to no stream: the app asks the worker or falls back to the vision-language model.
TO_STREAM = {"cardboard": "dry", "glass": "dry", "metal": "dry", "paper": "dry", "plastic": "dry", "trash": None}
SIZE = (128, 96)
OUT = Path(__file__).parent / "model"


def features(img: Image.Image) -> np.ndarray:
    img = ImageOps.exif_transpose(img).convert("RGB").resize(SIZE, Image.BILINEAR)
    hsv = np.asarray(img.convert("HSV"), dtype=np.float32) / 255.0
    col, _ = np.histogramdd(hsv.reshape(-1, 3), bins=(12, 4, 4), range=((0, 1), (0, 1), (0, 1)))
    col = col.ravel() / col.sum()
    gray = np.asarray(img.convert("L"), dtype=np.float32) / 255.0
    h = hog(gray, orientations=9, pixels_per_cell=(16, 16), cells_per_block=(2, 2), feature_vector=True)
    lbp = local_binary_pattern((gray * 255).astype(np.uint8), P=8, R=1, method="uniform")
    lbp_h, _ = np.histogram(lbp, bins=10, range=(0, 10))
    lbp_h = lbp_h / lbp_h.sum()
    return np.concatenate([col, h, lbp_h]).astype(np.float32)


def _feat_file(args):
    path, flip = args
    img = Image.open(path)
    if flip:
        img = ImageOps.mirror(img)
    return features(img)


def main(root: str) -> None:
    t0 = time.time()
    paths, labels = [], []
    for i, c in enumerate(CLASSES):
        files = sorted((Path(root) / c).glob("*.jpg"))
        paths += files
        labels += [i] * len(files)
    y = np.array(labels)
    tr, te = train_test_split(np.arange(len(paths)), test_size=0.2, stratify=y, random_state=42)

    with ProcessPoolExecutor() as ex:
        X_te = np.stack(list(ex.map(_feat_file, [(paths[i], False) for i in te], chunksize=32)))
        X_tr = np.stack(list(ex.map(_feat_file, [(paths[i], f) for i in tr for f in (False, True)], chunksize=32)))
    y_tr, y_te = np.repeat(y[tr], 2), y[te]
    groups = np.repeat(tr, 2)  # keep an image and its mirror in the same CV fold
    print(f"features: {X_tr.shape[1]} dims, train {len(tr)} images (x2 with flips), test {len(te)}, {time.time() - t0:.0f}s")

    pipe = make_pipeline(StandardScaler(), SVC(kernel="rbf", class_weight="balanced", probability=True))
    # Group-aware folds: split on image ids, then expand to the flipped copies.
    skf = StratifiedKFold(n_splits=4, shuffle=True, random_state=0)
    folds = []
    for a, b in skf.split(tr, y[tr]):
        ia, ib = set(tr[a]), set(tr[b])
        folds.append((np.where(np.isin(groups, list(ia)))[0], np.where(np.isin(groups, list(ib)))[0]))
    grid = GridSearchCV(pipe, {"svc__C": [3, 10, 30], "svc__gamma": ["scale", 0.0005]}, cv=folds, n_jobs=-1)
    grid.fit(X_tr, y_tr)
    print(f"best {grid.best_params_}, cv accuracy {grid.best_score_:.3f}, {time.time() - t0:.0f}s")

    model = grid.best_estimator_
    pred = model.predict(X_te)
    acc = float((pred == y_te).mean())
    report = classification_report(y_te, pred, target_names=CLASSES, output_dict=True, zero_division=0)
    cm = confusion_matrix(y_te, pred).tolist()
    # The decision that matters for the app: is it a dry-bin recyclable, or not?
    dry_true = np.array([TO_STREAM[CLASSES[i]] == "dry" for i in y_te])
    dry_pred = np.array([TO_STREAM[CLASSES[i]] == "dry" for i in pred])
    stream_acc = float((dry_true == dry_pred).mean())
    print(classification_report(y_te, pred, target_names=CLASSES, zero_division=0))
    print("confusion (rows=true):", CLASSES)
    for c, row in zip(CLASSES, cm):
        print(f"  {c:9s} {row}")
    print(f"test accuracy {acc:.3f}; dry-vs-not accuracy {stream_acc:.3f}")

    OUT.mkdir(parents=True, exist_ok=True)
    joblib.dump({"model": model, "classes": CLASSES, "to_stream": TO_STREAM, "size": SIZE}, OUT / "trashnet_svm.joblib",
                compress=3)
    metrics = {
        "dataset": "TrashNet (Thung & Yang 2016), dataset-resized, 2,527 images, 6 classes, MIT licence",
        "split": "stratified 80/20, random_state=42; test split used once",
        "train_images": int(len(tr)), "test_images": int(len(te)),
        "features": "HSV histogram (12x4x4) + HOG (9 orientations, 16px cells) + uniform LBP (P=8, R=1)",
        "model": f"StandardScaler + RBF SVM, {grid.best_params_}, class_weight=balanced",
        "cv_accuracy": round(float(grid.best_score_), 3),
        "test_accuracy": round(acc, 3),
        "test_macro_f1": round(float(report["macro avg"]["f1-score"]), 3),
        "dry_vs_not_accuracy": round(stream_acc, 3),
        "per_class": {c: {k: round(float(report[c][k]), 3) for k in ("precision", "recall", "f1-score", "support")}
                      for c in CLASSES},
        "confusion_matrix": {"labels": CLASSES, "rows_true_cols_pred": cm},
        "reference": "Thung & Yang (2016) report 63% test accuracy for an SVM on SIFT features on this dataset",
        "train_seconds": round(time.time() - t0),
    }
    (OUT / "metrics.json").write_text(json.dumps(metrics, indent=2))
    print(f"saved to {OUT}, {time.time() - t0:.0f}s")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "trashnet_data/dataset-resized")
