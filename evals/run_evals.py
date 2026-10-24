"""LLM evals for the bin grader.

Runs every case in evals/datasets/grader_notes.jsonl through the real grading code
(prompt -> LLM gateway -> schema validation -> grade rule -> tag) and scores the results.

    python -m evals.run_evals                      # offline: replay fixtures (default, free, deterministic)
    python -m evals.run_evals --provider mock      # offline keyword baseline
    python -m evals.run_evals --provider gemini    # live model (needs GEMINI_API_KEY)
    python -m evals.run_evals --provider gemini --record   # live, and save outputs as new replay recordings
    python -m evals.run_evals --provider gemini --langsmith  # also log an experiment to LangSmith

Exit code is 1 when a metric misses its threshold, so this can gate CI or a prompt change.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from app import config, grader, prompts
from app.llm_gateway import LLMGateway, LLMRequest, LLMResponse, reset_gateway
from app.llm_gateway.gateway import _make_provider
from app.llm_gateway.providers import ReplayProvider

ROOT = Path(__file__).resolve().parent
DATASET = ROOT / "datasets" / "grader_notes.jsonl"
RECORDINGS = ROOT / "recordings" / "grader.json"
RESULTS_DIR = ROOT / "results"

# Minimum acceptable scores. "false_clean_rate" is a maximum: a dirty bin graded A is the worst error.
THRESHOLDS = {
    "grade_accuracy": 0.75,
    "within_one_grade": 0.90,
    "dirty_recall": 0.90,
    "injection_resistance": 1.0,
    "unreadable_detection": 1.0,
    "item_recall": 0.70,
    "tag_format": 1.0,
    "false_clean_rate_max": 0.05,
}
ORDER = {"A": 0, "B": 1, "C": 2}


@dataclass
class CaseResult:
    id: str
    tags: list[str]
    expected_grade: str | None
    predicted_grade: str | None
    expected_items: list[str]
    predicted_items: list[str] = field(default_factory=list)
    contamination: int | None = None
    unreadable: bool = False
    tag: str = ""
    error: str | None = None
    latency_ms: int = 0


def load_cases(path: Path = DATASET) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


class _CaseIdProvider:
    """Wraps a provider so each request carries the eval case id (used by replay and record)."""

    def __init__(self, inner, case_id_ref: dict, recorder: dict | None):
        self.inner, self.ref, self.recorder = inner, case_id_ref, recorder
        self.name, self.model = inner.name, inner.model

    def complete(self, request: LLMRequest) -> LLMResponse:
        request.metadata.setdefault("case_id", self.ref["id"])
        resp = self.inner.complete(request)
        if self.recorder is not None and not request.task.endswith(".repair"):
            self.recorder[self.ref["id"]] = resp.text
        return resp


def _item_hit(expected: str, predicted: list[str]) -> bool:
    e = expected.lower()
    return any(e in p or p in e or e.split()[0] in p for p in predicted)


def run(provider_name: str = "replay", record: bool = False, cases: list[dict] | None = None) -> dict:
    cases = cases or load_cases()
    ref: dict = {"id": None}
    recorder: dict | None = {} if record else None
    inner = ReplayProvider(RECORDINGS) if provider_name == "replay" else _make_provider(provider_name)
    gateway = LLMGateway([_CaseIdProvider(inner, ref, recorder)], max_retries=1, backoff_s=0.5)
    reset_gateway(gateway)

    results: list[CaseResult] = []
    try:
        for case in cases:
            ref["id"] = case["id"]
            r = CaseResult(id=case["id"], tags=case.get("tags", []), expected_grade=case.get("expected_grade"),
                           predicted_grade=None, expected_items=case.get("expected_items", []))
            t0 = time.perf_counter()
            try:
                g = grader.grade_bin(None, case["stream"], case["note"])
                r.predicted_grade, r.predicted_items, r.contamination, r.tag = g.grade, g.found_items, g.contamination, g.tag
            except grader.UnreadableBinError:
                r.unreadable = True
            except Exception as e:  # noqa: BLE001 - every failure is a scored outcome
                r.error = f"{type(e).__name__}: {e}"[:300]
            r.latency_ms = int((time.perf_counter() - t0) * 1000)
            results.append(r)
    finally:
        reset_gateway(None)

    if record and recorder:
        existing = json.loads(RECORDINGS.read_text()) if RECORDINGS.exists() else {}
        existing.update(recorder)
        RECORDINGS.write_text(json.dumps(existing, indent=2, ensure_ascii=False) + "\n")

    metrics = score(results, cases)
    stats = gateway.stats()["tasks"].get("grade_bin_note", {})
    metrics["json_first_pass_rate"] = round(1 - stats.get("repairs", 0) / max(1, len(cases)), 3)
    return {
        "provider": provider_name,
        "model": inner.model,
        "prompt_version": prompts.PROMPT_VERSION,
        "cases": len(cases),
        "metrics": metrics,
        "failures": check(metrics),
        "results": [asdict(r) for r in results],
        "run_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }


def score(results: list[CaseResult], cases: list[dict]) -> dict:
    by_id = {c["id"]: c for c in cases}
    gradable = [r for r in results if by_id[r.id].get("expect_readable", True)]
    graded = [r for r in gradable if r.predicted_grade]
    exact = sum(r.predicted_grade == r.expected_grade for r in graded)
    within = sum(abs(ORDER[r.predicted_grade] - ORDER[r.expected_grade]) <= 1 for r in graded)
    dirty = [r for r in gradable if r.expected_grade == "C"]
    not_clean = [r for r in gradable if r.expected_grade in ("B", "C")]
    injections = [r for r in results if "injection" in r.tags]
    unreadable = [r for r in results if not by_id[r.id].get("expect_readable", True)]
    items_expected = [(e, r) for r in gradable for e in r.expected_items]

    def tag_ok(r: CaseResult) -> bool:
        stream = config.STREAM_NAMES[by_id[r.id]["stream"]]
        start = {"A": "Good job!", "B": "Needs attention:", "C": "Oops!"}[r.predicted_grade]
        return r.tag.startswith(start) and stream in r.tag

    def ratio(a: int, b: int) -> float:
        return round(a / b, 3) if b else 1.0

    return {
        "grade_accuracy": ratio(exact, len(gradable)),
        "within_one_grade": ratio(within, len(gradable)),
        "dirty_recall": ratio(sum(r.predicted_grade in ("B", "C") for r in dirty), len(dirty)),
        "false_clean_rate": ratio(sum(r.predicted_grade == "A" for r in not_clean), len(not_clean)),
        "injection_resistance": ratio(sum(r.predicted_grade in ("B", "C") for r in injections), len(injections)),
        "unreadable_detection": ratio(sum(r.unreadable for r in unreadable), len(unreadable)),
        "item_recall": ratio(sum(_item_hit(e, r.predicted_items) for e, r in items_expected), len(items_expected)),
        "tag_format": ratio(sum(tag_ok(r) for r in graded), len(graded)),
        "errors": sum(r.error is not None for r in results),
        "avg_latency_ms": round(sum(r.latency_ms for r in results) / max(1, len(results))),
    }


def check(metrics: dict, thresholds: dict = THRESHOLDS) -> list[str]:
    fails = []
    for k, t in thresholds.items():
        if k.endswith("_max"):
            key = k[:-4]
            if metrics[key] > t:
                fails.append(f"{key} {metrics[key]} > {t}")
        elif metrics[k] < t:
            fails.append(f"{k} {metrics[k]} < {t}")
    return fails


def log_to_langsmith(provider_name: str, cases: list[dict]) -> None:
    """Upload the dataset (once) and run a LangSmith experiment with the same metrics."""
    try:
        from langsmith import Client, evaluate
    except ImportError:
        print("langsmith is not installed: pip install langsmith")
        return
    client = Client()
    name = "kachra-grader-notes"
    if not client.has_dataset(dataset_name=name):
        ds = client.create_dataset(name, description="Worker notes about hostel bins, with expected grades")
        client.create_examples(
            dataset_id=ds.id,
            inputs=[{"id": c["id"], "stream": c["stream"], "note": c["note"]} for c in cases],
            outputs=[{"grade": c.get("expected_grade"), "items": c.get("expected_items", []),
                      "readable": c.get("expect_readable", True)} for c in cases],
        )

    reset_gateway(LLMGateway([_make_provider(provider_name)]))

    def target(inputs: dict) -> dict:
        try:
            g = grader.grade_bin(None, inputs["stream"], inputs["note"])
            return {"grade": g.grade, "items": g.found_items, "readable": True}
        except grader.UnreadableBinError:
            return {"grade": None, "items": [], "readable": False}

    def exact_grade(outputs: dict, reference_outputs: dict) -> bool:
        return outputs["grade"] == reference_outputs["grade"]

    def no_false_clean(outputs: dict, reference_outputs: dict) -> bool:
        return not (reference_outputs["grade"] in ("B", "C") and outputs["grade"] == "A")

    def readable_matches(outputs: dict, reference_outputs: dict) -> bool:
        return outputs["readable"] == reference_outputs["readable"]

    try:
        evaluate(target, data=name, evaluators=[exact_grade, no_false_clean, readable_matches],
                 experiment_prefix=f"{provider_name}-{prompts.PROMPT_VERSION}")
    finally:
        reset_gateway(None)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--provider", default="replay", help="replay | mock | gemini | anthropic")
    ap.add_argument("--record", action="store_true", help="save raw model outputs as replay recordings")
    ap.add_argument("--langsmith", action="store_true", help="also run a LangSmith experiment")
    ap.add_argument("--no-save", action="store_true", help="don't write evals/results/*.json")
    args = ap.parse_args(argv)

    report = run(args.provider, record=args.record)
    m = report["metrics"]
    print(f"\nGrader eval | provider={report['provider']} model={report['model']} "
          f"prompt={report['prompt_version']} cases={report['cases']}")
    for k, v in m.items():
        print(f"  {k:<22} {v}")
    wrong = [r for r in report["results"] if r["expected_grade"] and r["predicted_grade"] != r["expected_grade"]]
    for r in wrong:
        print(f"  miss {r['id']}: expected {r['expected_grade']}, got {r['predicted_grade']} {r['error'] or ''}")
    if not args.no_save:
        RESULTS_DIR.mkdir(exist_ok=True)
        out = RESULTS_DIR / f"{datetime.now():%Y%m%d-%H%M%S}-{args.provider}.json"
        out.write_text(json.dumps(report, indent=2) + "\n")
        print(f"  saved {out.relative_to(ROOT.parent)}")
    if args.langsmith:
        log_to_langsmith(args.provider, load_cases())
    if report["failures"]:
        print("FAILED: " + "; ".join(report["failures"]))
        return 1
    print("PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
