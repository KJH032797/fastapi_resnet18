# FastAPI Beans ResNet18 동기·비동기 평가 프로젝트

콩잎 이미지의 `angular_leaf_spot`, `bean_rust`, `healthy` 3개 클래스를 분류하는 ResNet18 모델과 FastAPI 동기·비동기 서비스를 평가한다. 학습 및 모델 선택에는 Train과 Validation을 사용한다. Test는 개선 후보를 확정한 뒤 최종 평가에 남겨둔다.

## 환경과 실행

- Docker Engine 및 Docker Compose
- FastAPI, Celery Worker, Redis, PostgreSQL
- 모델 추론: CPU
- 현재 서비스 모델: artifacts/beans_resnet18_full/; .env의 MODEL_PATH도 이 경로로 맞춘다.
- 로컬 포트: FastAPI `8000`, Redis `6379`, PostgreSQL `5432`

일반 서비스 실행에는 WSL 가상환경 활성화가 필요하지 않다. 학습은 Docker의 `trainer` 프로필로 수행한다.

```bash
docker compose build trainer
docker compose --profile train run --rm trainer
docker compose up -d --build
curl http://127.0.0.1:8000/health
```

동기 화면: http://127.0.0.1:8000/vision/sync/
비동기 화면: http://127.0.0.1:8000/vision/async/
API 문서: http://127.0.0.1:8000/docs

Trainer는 Head-only(`--freeze-backbone`) 방식으로 `artifacts/beans_resnet18/`에 저장한다. 기본 산출물을 덮어쓰지 않도록 개선 비교는 별도 출력 경로를 사용한다.

## 데이터 분할

```text
dataset/{train,val,test}/{angular_leaf_spot,bean_rust,healthy}/
```

| Split | 수량 |
|---|---:|
| Train | 1,034 |
| Validation | 133 |
| Test | 128 |

모델 개선·선택은 Validation으로 진행했고, 최종 후보 확정 뒤 Test 전체를 한 차례 평가했다.

## 현재 모델 결과

필수 Head-only 기준 모델은 Validation 전체에서 102/133 정답, Accuracy 0.7669, Macro F1 0.7640이었다. 이후 별도 Full Fine-tuning 후보를 학습해 같은 Validation 전체로 비교했다.

- Full Fine-tuning 후보: 129/133 정답, Accuracy **0.9699**, Macro F1 **0.9700**
- 병든 잎을 healthy로 놓친 사례: 기준선 11건 → 후보 2건
- 병든 클래스 간 혼동: 기준선 16건 → 후보 1건
- healthy → 병든 클래스 오분류: 기준선 4건 → 후보 1건 (후보 전체 오분류 4건)
- 후보의 최고 Validation Accuracy는 epoch 1에서 나왔으며, epoch 2·3에서는 낮아졌다.
- Full Fine-tuning 최종 후보는 artifacts/beans_resnet18_full/이며 Test Accuracy는 0.9453이다. 현재 .env의 MODEL_PATH와 Web·Worker는 이 최종 후보를 사용한다.
- 최종 후보 Test 평가: 121/128 정답, Accuracy **0.9453**, Macro F1 **0.9455**. Test 결과를 사용한 추가 조정은 하지 않았다.

건강 오탐을 우선한 근거, Full Fine-tuning 결과, 남은 병 클래스 혼동을 추가 개선하지 않은 판단은 [개선 실험 결과와 검토](reports/09_model_improvement_plan.md)에 기록했다. [후보의 Validation 지표](reports/evidence/validation_full_finetune_metrics.json), [최종 Test 지표](reports/evidence/test_final_metrics.json), [최종 기술 보고서](reports/08_최종기술보고서.md)를 참고한다.

## 서비스

- 동기 분류: `POST /api/sync/classify/`, 화면 `/vision/sync/`
- 비동기 접수: `POST /api/async/classify/`, 상태 조회 `GET /api/async/jobs/{job_id}/`
- 비동기 결과는 PostgreSQL `image_jobs`에 기록한다.

## 보고서와 증빙

- 산출물 1–8: [`reports/`](reports/)
- 추가 개선 계획: [`reports/09_model_improvement_plan.md`](reports/09_model_improvement_plan.md)
- Validation 이미지별 결과·혼동행렬: `reports/data/validation_baseline_*.csv`
- Validation 반복 서비스 측정: `reports/data/timings_validation_benchmark_5x.csv`
- 실행 증빙: `reports/evidence/`

## 추가 검증 스크립트

아래 스크립트는 보고서와 증빙에 사용한 보조 검증 도구다. 중복 점검은 고정 파일명으로 저장하며, 평가·성능 스크립트는 기존 결과를 덮어쓰지 않으므로 재실행 때 새 `--name`을 지정한다.

| 스크립트 | 실행 예 | 용도·결과 |
|---|---|---|
| 데이터 중복 점검 | `python scripts/audit_dataset_duplicates.py` | 분할 간 파일명·바이트 완전 중복 점검. 근접 중복 검사는 아님. `reports/data/filename_cross_split_duplicates.csv`, `reports/data/exact_cross_split_duplicates.csv` 생성 |
| Validation 전체 평가 | `python scripts/evaluate_validation.py --name validation_run` | 현재 `MODEL_PATH` 모델의 Validation 지표·예측·혼동행렬 생성. `reports/evidence/<name>_metrics.json`, `reports/data/<name>_predictions.csv`, `reports/data/<name>_confusion_matrix.csv` |
| 최종 Test 평가 | `python scripts/evaluate_test.py --name test_run` | 후보 확정 후 1회 평가. `reports/evidence/<name>_metrics.json`, `reports/data/<name>_predictions.csv`, `reports/data/<name>_confusion_matrix.csv` 생성. Test 결과로 추가 조정 금지 |
| 서비스 성능 측정 | `python scripts/benchmark_validation.py --name validation_benchmark_run` | 실행 중인 로컬 서버에서 Validation 이미지 5장의 동기·비동기 MISS/HIT 측정. `reports/data/timings_<name>.csv`, `reports/evidence/performance_<name>.json` 생성. 측정 전 모델 워밍업 필요; 선택된 이미지의 Redis DB 1 캐시 키 삭제 |

`evaluate_validation.py`와 `evaluate_test.py`는 `--name`이 지정한 결과 파일이 이미 있으면 중단한다. 재실행 시 새 이름 사용.

`.env`, 데이터셋, 모델 가중치 및 업로드 이미지의 공유는 이용 조건과 수업 제출 지침에 따른다. `.env`와 자격 증명은 공개 저장소에 올리지 않는다.
