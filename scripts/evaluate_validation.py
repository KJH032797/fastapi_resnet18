#!/usr/bin/env python3
"""Evaluate the configured fine-tuned classifier on the Validation split only."""
from __future__ import annotations
import argparse, csv, io, json, os, re, sys, tempfile
from collections import Counter
from pathlib import Path
PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))
from ai.config import MODEL_PATH
from ai.hf_model import get_classifier
from ai.services import load_rgb_image
VAL_ROOT = PROJECT_ROOT / "dataset" / "val"
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}

def score_metrics(labels, truth, predictions):
    matrix = {actual: {predicted: 0 for predicted in labels} for actual in labels}
    for actual, predicted in zip(truth, predictions): matrix[actual][predicted] += 1
    per_class, total = {}, len(truth)
    correct = sum(a == p for a, p in zip(truth, predictions))
    weighted = {m: 0.0 for m in ("precision", "recall", "f1")}
    for label in labels:
        tp = matrix[label][label]
        support = sum(matrix[label].values())
        predicted_count = sum(matrix[actual][label] for actual in labels)
        precision = tp / predicted_count if predicted_count else 0.0
        recall = tp / support if support else 0.0
        f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
        per_class[label] = {"precision": precision, "recall": recall, "f1": f1, "support": support}
        for metric, value in (("precision", precision), ("recall", recall), ("f1", f1)):
            weighted[metric] += value * support
    macro = {metric: sum(per_class[label][metric] for label in labels) / len(labels)
             for metric in ("precision", "recall", "f1")}
    weighted = {metric: value / total for metric, value in weighted.items()}
    return {"accuracy": correct / total, "correct": correct, "total": total,
            "per_class": per_class, "macro_average": macro, "weighted_average": weighted,
            "confusion_matrix": {"label_order": labels,
                                 "rows_actual_columns_predicted": matrix}}

def evaluate():
    if not VAL_ROOT.is_dir(): raise FileNotFoundError(f"Validation 폴더가 없습니다: {VAL_ROOT}")
    classifier = get_classifier()
    labels = list(classifier.model.config.id2label.values())
    if not labels or len(set(labels)) != len(labels):
        raise ValueError("모델의 id2label 클래스 정의가 올바르지 않습니다.")
    class_dirs = {p.name: p for p in VAL_ROOT.iterdir() if p.is_dir()}
    if set(class_dirs) != set(labels):
        raise ValueError(f"Validation 클래스({sorted(class_dirs)})와 모델 클래스({labels})가 다릅니다.")
    rows, truth, predictions = [], [], []
    for label in labels:
        paths = sorted(p for p in class_dirs[label].rglob("*")
                       if p.is_file() and p.suffix.lower() in IMAGE_EXTENSIONS)
        if not paths: raise ValueError(f"이미지가 없는 클래스: {label}")
        for path in paths:
            image = load_rgb_image(path.read_bytes())
            output = classifier(image, top_k=1)
            while isinstance(output, list) and len(output) == 1 and isinstance(output[0], list):
                output = output[0]
            if not isinstance(output, list) or not output:
                raise RuntimeError(f"모델 결과가 비어 있습니다: {path}")
            predicted = str(output[0]["label"])
            if predicted not in labels: raise ValueError(f"알 수 없는 클래스: {predicted}")
            score = float(output[0]["score"])
            truth.append(label); predictions.append(predicted)
            rows.append({"path": path.relative_to(PROJECT_ROOT).as_posix(),
                         "true_label": label, "predicted_label": predicted,
                         "correct": label == predicted, "top1_score": score})
    metrics = score_metrics(labels, truth, predictions)
    metrics.update({"model_path": str(MODEL_PATH), "source_split": "val",
                    "class_counts": dict(Counter(truth)),
                    "note": "Validation 전체 평가. Test 데이터는 열거나 사용하지 않았습니다."})
    return metrics, rows, labels

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--name", default="validation_baseline",
                        help="산출물 접두사(기존 파일은 덮어쓰지 않음)")
    args = parser.parse_args()
    if not re.fullmatch(r"[A-Za-z0-9_-]+", args.name):
        parser.error("--name에는 영문자, 숫자, 밑줄, 하이픈만 사용할 수 있습니다.")
    data_dir, evidence_dir = PROJECT_ROOT / "reports/data", PROJECT_ROOT / "reports/evidence"
    pred_path = data_dir / f"{args.name}_predictions.csv"
    matrix_path = data_dir / f"{args.name}_confusion_matrix.csv"
    metrics_path = evidence_dir / f"{args.name}_metrics.json"
    if any(p.exists() for p in (pred_path, matrix_path, metrics_path)):
        print("기존 산출물이 있어 중단합니다. --name을 바꿔 주세요.", file=sys.stderr); return 1
    try:
        metrics, rows, labels = evaluate()
        data_dir.mkdir(parents=True, exist_ok=True); evidence_dir.mkdir(parents=True, exist_ok=True)
        predictions_buffer = io.StringIO(newline="")
        writer = csv.DictWriter(predictions_buffer, fieldnames=[
            "path", "true_label", "predicted_label", "correct", "top1_score"
        ])
        writer.writeheader()
        writer.writerows(rows)

        matrix = metrics["confusion_matrix"]["rows_actual_columns_predicted"]
        matrix_buffer = io.StringIO(newline="")
        writer = csv.writer(matrix_buffer)
        writer.writerow(["actual / predicted", *labels])
        for actual in labels:
            writer.writerow([actual, *(matrix[actual][pred] for pred in labels)])

        outputs = [
            (pred_path, predictions_buffer.getvalue().encode("utf-8")),
            (matrix_path, matrix_buffer.getvalue().encode("utf-8")),
            (metrics_path, (json.dumps(metrics, ensure_ascii=False, indent=2) + "\n").encode("utf-8")),
        ]
        temporary_paths = []
        created_paths = []
        try:
            for final_path, content in outputs:
                fd, temp_name = tempfile.mkstemp(prefix=f".{final_path.name}.", suffix=".tmp",
                                                 dir=final_path.parent)
                temp_path = Path(temp_name)
                temporary_paths.append(temp_path)
                with os.fdopen(fd, "wb") as file:
                    file.write(content)
            # 하드링크 생성은 대상 파일이 이미 있으면 실패하므로 기존 결과를 덮어쓰지 않는다.
            for (final_path, _), temp_path in zip(outputs, temporary_paths):
                os.link(temp_path, final_path)
                created_paths.append(final_path)
        except Exception:
            for created_path in created_paths:
                created_path.unlink(missing_ok=True)
            raise
        finally:
            for temp_path in temporary_paths:
                temp_path.unlink(missing_ok=True)

        print(json.dumps(metrics, ensure_ascii=False, indent=2))
        print(f"예측별 CSV: {pred_path.relative_to(PROJECT_ROOT)}")
        print(f"혼동행렬 CSV: {matrix_path.relative_to(PROJECT_ROOT)}")
        print(f"지표 JSON: {metrics_path.relative_to(PROJECT_ROOT)}")
        return 0
    except Exception as exc:
        print(f"평가 중단: {exc}", file=sys.stderr); return 1

if __name__ == "__main__": raise SystemExit(main())
