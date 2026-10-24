"""Measure how well the grader matches human grades, for the impact slide.

1. Put bin photos in a folder.
2. Make a CSV with columns: file,stream,grade   (grade = what a person says: A, B or C)
       bin01.jpg,wet,A
       bin02.jpg,dry,C
3. Run (with GRADER_PROVIDER and the API key set):
       python -m scripts.eval_grader photos/labels.csv

Prints a short summary and saves every prediction to eval_results.csv next to the labels.
"""

import csv
import sys
import time
from pathlib import Path

from app import grader

GRADES = ["A", "B", "C"]


def main(labels_csv: str) -> None:
    labels_path = Path(labels_csv)
    rows = list(csv.DictReader(labels_path.open()))
    out_rows, confusion = [], {t: {p: 0 for p in GRADES + ["err"]} for t in GRADES}
    for i, row in enumerate(rows, 1):
        photo = labels_path.parent / row["file"]
        truth = row["grade"].strip().upper()
        try:
            g = grader.grade_bin(str(photo), row["stream"].strip(), None)
            pred, pct = g.grade, g.contamination
        except Exception as e:  # noqa: BLE001
            pred, pct = "err", None
            print(f"  {row['file']}: {str(e)[:80]}")
        confusion[truth][pred] += 1
        out_rows.append({**row, "predicted": pred, "contamination": pct})
        print(f"\r{i}/{len(rows)}", end="", flush=True)
        time.sleep(0.3)
    print()

    n = len(rows)
    exact = sum(confusion[g][g] for g in GRADES)
    off_by_one = confusion["A"]["B"] + confusion["B"]["A"] + confusion["B"]["C"] + confusion["C"]["B"]
    # "Did it catch dirty bins?" = C bins not graded A.
    c_total = sum(confusion["C"].values())
    c_caught = c_total - confusion["C"]["A"] - confusion["C"]["err"]

    print(f"photos: {n}")
    print(f"exact grade match: {exact}/{n} ({100 * exact / n:.0f}%)")
    print(f"within one grade:  {exact + off_by_one}/{n} ({100 * (exact + off_by_one) / n:.0f}%)")
    if c_total:
        print(f"dirty (C) bins flagged as B or C: {c_caught}/{c_total} ({100 * c_caught / c_total:.0f}%)")
    print("confusion (rows = human, cols = model):")
    print("      " + "  ".join(f"{p:>3}" for p in GRADES + ["err"]))
    for t in GRADES:
        print(f"  {t}   " + "  ".join(f"{confusion[t][p]:>3}" for p in GRADES + ["err"]))

    out = labels_path.parent / "eval_results.csv"
    with out.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(out_rows[0].keys()))
        w.writeheader()
        w.writerows(out_rows)
    print(f"saved {out}")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    main(sys.argv[1])
