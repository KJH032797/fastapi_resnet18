# Fine-tuning 결과 보고서

## 데이터 구성

- 데이터셋: Beans, `angular_leaf_spot`, `bean_rust`, `healthy` 3개 클래스
- 실행용 폴더: `dataset/train`, `dataset/val`, `dataset/test`
- 원본 `validation`을 `dataset/val`로 정리.

| 클래스 | Train | Validation (`val`) | Test |
|---|---:|---:|---:|
| `angular_leaf_spot` | 345 | 44 | 43 |
| `bean_rust` | 348 | 45 | 43 |
| `healthy` | 341 | 44 | 42 |
| **합계** | **1,034** | **133** | **128** |

- 중복 점검: 분할 간 파일명 중복 0건, 바이트 단위 완전 중복 0건. 근접 중복은 검사하지 않음.
- 학습·모델 선택: Train·Validation. Test: 후보 확정 전까지 보류, 후보 확정 뒤 Test 128장 최종 평가.

## 학습 설정

| 항목 | 값 | 근거 |
|---|---|---|
| 기본 모델 | `microsoft/resnet-18` | `training_report.json` |
| 클래스 순서 | 0=`angular_leaf_spot`, 1=`bean_rust`, 2=`healthy` | JSON의 `classes` 순서 |
| Train / Validation 수 | 1,034 / 133 | `training_report.json` |
| Epoch | 3 | JSON의 `history` 항목 수 |
| Batch size | 8 | Compose Trainer 설정 |
| Learning rate | 0.0002 | 학습 스크립트 기본값 |
| 학습 방식 | `--freeze-backbone` Head-only | Compose Trainer 설정 및 확인된 실행 명령 `docker compose --profile train run --rm trainer` |
| 출력 폴더 | `artifacts/beans_resnet18/` | Compose Trainer 설정 |

## 학습 결과

| Epoch | Train Loss | Validation Accuracy |
|---:|---:|---:|
| 1 | 0.9924 | 0.6617 |
| 2 | 0.8108 | 0.7669 |
| 3 | 0.7078 | 0.7669 |

- Best Validation Accuracy: **0.7669 (76.69%)**
- 별도 Full Fine-tuning 최종 후보의 Test Accuracy: **0.9453 (121/128)** (세부 지표는 아래 최종 Test 평가 참고)
- 값의 출처: `artifacts/beans_resnet18/training_report.json`

## 생성 모델 파일

- `config.json`
- `model.safetensors`
- `preprocessor_config.json`
- `training_report.json`

## 기준 모델의 전체 Validation 평가

Head-only 기준 모델 전체 Validation 재평가: `scripts/evaluate_validation.py` 실행. 133장 중 102장 정답, Accuracy 0.7669, 오답 31장.

| 클래스 | Precision | Recall | F1 | Support |
|---|---:|---:|---:|---:|
| `angular_leaf_spot` | 0.7857 | 0.7500 | 0.7674 | 44 |
| `bean_rust` | 0.7250 | 0.6444 | 0.6824 | 45 |
| `healthy` | 0.7843 | 0.9091 | 0.8421 | 44 |
| **Macro 평균** | **0.7650** | **0.7678** | **0.7640** | **133** |
| **Weighted 평균** | **0.7647** | **0.7669** | **0.7634** | **133** |

혼동행렬 기준: 행=정답, 열=예측.

| 정답 \ 예측 | `angular_leaf_spot` | `bean_rust` | `healthy` |
|---|---:|---:|---:|
| `angular_leaf_spot` | 33 | 8 | 3 |
| `bean_rust` | 8 | 29 | 8 |
| `healthy` | 1 | 3 | 40 |

- 병든 잎을 `healthy`로 놓친 사례는 11장: `angular_leaf_spot` 3장, `bean_rust` 8장.
- 병든 클래스 간 혼동은 16장: 두 방향 각각 8장.
- 건강한 잎의 재현율은 0.9091이며 `healthy` 44장 중 40장을 맞혔다.
- 범위: Validation 기준선 결과. Test 성능 아님.

산출물:
- 지표와 행렬 JSON: [`evidence/validation_baseline_metrics.json`](evidence/validation_baseline_metrics.json)
- 이미지별 정답·예측 CSV: [`data/validation_baseline_predictions.csv`](data/validation_baseline_predictions.csv)
- 혼동행렬 CSV: [`data/validation_baseline_confusion_matrix.csv`](data/validation_baseline_confusion_matrix.csv)

## Full Fine-tuning 후보의 전체 Validation 평가

비교 후보: microsoft/resnet-18에서 새로 시작, 분류기 초기화, Backbone 고정 없이 별도 경로에 학습. Train 1,034장, Validation 133장, 3 epoch, batch 8, learning rate 0.00005. 이미지 증강 미추가. 기준 모델 가중치 학습 전후 해시 동일, 보존.

| Epoch | Train Loss | Validation Accuracy |
|---:|---:|---:|
| 1 | 0.4399 | 0.9699 |
| 2 | 0.1550 | 0.9624 |
| 3 | 0.0856 | 0.9549 |

Epoch 1 가중치 저장: Validation 최고점. Train Loss 감소, Validation Accuracy 하락. 오답은 epoch별 4·5·6장. 과적합 단정 없이 주의 신호로 기록.

| 지표 | Head-only 기준 모델 | Full Fine-tuning 후보 |
|---|---:|---:|
| 정답 / 전체 | 102 / 133 | 129 / 133 |
| Accuracy | 0.7669 | 0.9699 |
| Macro F1 | 0.7640 | 0.9700 |
| 병든 잎 → healthy | 11장 | 2장 |
| 병든 클래스 간 혼동 | 16장 | 1장 |
| healthy → 병든 클래스 | 4장 | 1장 |
| 전체 오분류 | 31장 | 4장 |

후보 클래스별 지표:

| 클래스 | Precision | Recall | F1 | Support |
|---|---:|---:|---:|---:|
| angular_leaf_spot | 1.0000 | 0.9545 | 0.9767 | 44 |
| bean_rust | 0.9565 | 0.9778 | 0.9670 | 45 |
| healthy | 0.9556 | 0.9773 | 0.9663 | 44 |

후보 혼동행렬(행=정답, 열=예측):

| 정답 \ 예측 | angular_leaf_spot | bean_rust | healthy |
|---|---:|---:|---:|
| angular_leaf_spot | 42 | 1 | 1 |
| bean_rust | 0 | 44 | 1 |
| healthy | 0 | 1 | 43 |

남은 오분류 4건:
- dataset/val/angular_leaf_spot/angular_leaf_spot_val.18.jpg → healthy (Top-1 0.6095)
- dataset/val/angular_leaf_spot/angular_leaf_spot_val.37.jpg → bean_rust (Top-1 0.8392)
- dataset/val/bean_rust/bean_rust_val.5.jpg → healthy (Top-1 0.3470)
- dataset/val/healthy/healthy_val.1.jpg → bean_rust (Top-1 0.5505)

남은 오분류·Train 유사 조건 검토·추가 개선 미선정 근거: [09 모델 개선 실험 결과 및 검토](09_model_improvement_plan.md).

후보 지표와 이미지별 예측:
- 지표 JSON: [evidence/validation_full_finetune_metrics.json](evidence/validation_full_finetune_metrics.json)
- 예측 CSV: [data/validation_full_finetune_predictions.csv](data/validation_full_finetune_predictions.csv)
- 혼동행렬 CSV: [data/validation_full_finetune_confusion_matrix.csv](data/validation_full_finetune_confusion_matrix.csv)
- 후보 모델: artifacts/beans_resnet18_full/

범위: 같은 Validation으로 모델 선택·비교한 수치. Test 성능 아님.

## 최종 후보의 전체 Test 평가

최종 후보 확정 뒤 Test 128장 1회 평가. Test 지표 기반 모델 선택·추가 조정 미사용.

| 지표 | 결과 |
|---|---:|
| 정답 / 전체 | 121 / 128 |
| Accuracy | 0.9453 (94.53%) |
| Macro Precision | 0.9490 |
| Macro Recall | 0.9452 |
| Macro F1 | 0.9455 |

| 클래스 | Precision | Recall | F1 | Support |
|---|---:|---:|---:|---:|
| angular_leaf_spot | 0.8958 | 1.0000 | 0.9451 | 43 |
| bean_rust | 0.9512 | 0.9070 | 0.9286 | 43 |
| healthy | 1.0000 | 0.9286 | 0.9630 | 42 |

혼동행렬(행=정답, 열=예측):

| 정답 \\ 예측 | angular_leaf_spot | bean_rust | healthy |
|---|---:|---:|---:|
| angular_leaf_spot | 43 | 0 | 0 |
| bean_rust | 4 | 39 | 0 |
| healthy | 1 | 2 | 39 |

오분류 7건: 병든 잎 → healthy 0건, bean_rust → angular_leaf_spot 4건, healthy → 병든 클래스 3건. 이미지별 결과·점수는 예측 CSV 참고.

산출물:
- 지표 JSON: [evidence/test_final_metrics.json](evidence/test_final_metrics.json)
- 이미지별 예측 CSV: [data/test_final_predictions.csv](data/test_final_predictions.csv)
- 혼동행렬 CSV: [data/test_final_confusion_matrix.csv](data/test_final_confusion_matrix.csv)
- 평가 스크립트: [../scripts/evaluate_test.py](../scripts/evaluate_test.py)

평가 범위: 최종 후보의 Test 1회 결과. 다른 데이터·실제 재배지 성능으로 일반화 불가.

## Validation 서비스 확인

### 동기 분류

| 입력 이미지 | 정답 | Top-1 예측 | 점수 | 응답 시간 | `inference_ms` | 캐시 |
|---|---|---|---:|---:|---:|---|
| `angular_leaf_spot_val.3.jpg` | `angular_leaf_spot` | `angular_leaf_spot` | 0.5138 | 159ms | 118.92ms | MISS |
| `bean_rust_val.10.jpg` | `bean_rust` | `bean_rust` | 0.4295 | 47ms | 28.04ms | MISS |
| `healthy_val.7.jpg` | `healthy` | `healthy` | 0.9515 | 44ms | 25.04ms | MISS |

### 비동기 분류

| Job ID | 입력 이미지 | 접수 시간 | 전체 완료 시간 | 상태 | Top-1 | `inference_ms` | 캐시 |
|---:|---|---:|---:|---|---|---:|---|
| 15 | `angular_leaf_spot_val.3.jpg` | 71ms | 1,082ms | `done` | `angular_leaf_spot` (0.5138) | 78.81ms | MISS |
| 16 | `bean_rust_val.10.jpg` | 19ms | 1,041ms | `done` | `bean_rust` (0.4295) | 18.26ms | MISS |
| 17 | `healthy_val.7.jpg` | 16ms | 1,021ms | `done` | `healthy` (0.9515) | 20.12ms | MISS |

- Job 15–17 모두 `done`. PostgreSQL 저장 결과와 화면 응답 일치.
- 별도 캐시 확인 이미지 `bean_rust_val.27.jpg`는 `angular_leaf_spot`으로 오분류됐다. 동일 이미지의 MISS/HIT 결과 점수는 같았고 HIT의 `inference_ms`는 `null`이었다.
- 요청별 증빙: `reports/evidence/`. API 근거 목록: [03 API 명세서](03_API_명세서.md).

## 최종 후보 API 연결 재검증

Test 최종 평가 뒤 `.env`의 `MODEL_PATH`를 `artifacts/beans_resnet18_full`로 변경. Web·Worker 재생성. Validation 이미지로 후보 서비스 연결 재검증.

| 방식 | 이미지 | 응답 | 예측 | 모델 처리 |
|---|---|---|---|---|
| 동기 | angular_leaf_spot_val.3.jpg | HTTP 200, 전체 3,175ms | angular_leaf_spot (0.9890) | inference_ms 3,132.49ms, cache MISS |
| 비동기 | bean_rust_val.10.jpg | Job 31, 접수 46ms, 전체 3,071ms, done | bean_rust (0.9881) | inference_ms 2,152.33ms, cache MISS |

두 응답 `model_id`: `artifacts/beans_resnet18_full`. 동기·비동기 캡처: HTTP·상태·결과 증빙. Health HTTP 200. Test 데이터 서비스 재검증 미사용. [동기 캡처](evidence/final_model_sync_validation_angular_leaf_spot_val_3.jpeg), [비동기 캡처](evidence/final_model_async_validation_bean_rust_val_10.jpeg).

## 반복 성능 측정

측정 입력: Validation에서 무작위로 고른 서로 다른 이미지 5장. 동기·비동기 MISS/HIT 조건별 5회.

| 경로 | 캐시 | 응답/접수 중앙값 | 전체 완료 중앙값 | 추론 중앙값 |
|---|---|---:|---:|---:|
| 동기 | MISS | 21.37ms | 21.37ms | 16.82ms |
| 동기 | HIT | 1.71ms | 1.71ms | 해당 없음 |
| 비동기 | MISS | 7.75ms | 113.28ms | 18.55ms |
| 비동기 | HIT | 8.76ms | 116.80ms | 해당 없음 |

- 비동기 접수시간과 완료시간 구분. 전체 완료시간에 큐 처리·상태 조회 대기 포함.
- 상세 기록: [`data/timings_validation_benchmark_5x.csv`](data/timings_validation_benchmark_5x.csv), [`evidence/performance_validation_benchmark_5x.json`](evidence/performance_validation_benchmark_5x.json)
- 이 반복 측정은 Validation 기반 서비스 성능 확인이며 Test 정확도 평가는 아니다.
