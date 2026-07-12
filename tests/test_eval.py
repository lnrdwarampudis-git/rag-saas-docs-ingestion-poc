from pathlib import Path

from app.eval.run import run_eval


def test_offline_eval_dataset_passes_quality_targets() -> None:
    report = run_eval(Path("data/eval/retrieval_cases.json"))

    assert report["summary"]["cases"] == 3
    assert report["summary"]["failed"] == 0
    assert report["summary"]["context_precision"] >= 0.85
    assert report["summary"]["context_recall"] >= 0.80
    assert report["summary"]["answer_relevance"] >= 0.85
