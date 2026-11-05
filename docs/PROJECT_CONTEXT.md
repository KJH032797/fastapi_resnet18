# fastapi_resnet18 프로젝트 컨텍스트

## 과제 목적

Beans 잎 이미지의 angular_leaf_spot, bean_rust, healthy 3개 클래스를 microsoft/resnet-18로 분류하고, FastAPI 동기·비동기 서비스의 동작과 평가 산출물을 확인한다. 필수 기준 모델은 Head-only Fine-tuning이며, Full Fine-tuning은 별도 출력 경로에 비교 후보로 학습했다. Train은 학습, Validation은 모델 선택·비교에 사용했고, 최종 후보 확정 후 Test 전체 평가를 한 차례 완료했다.

## 실제 구조와 주요 코드

프로젝트 원본 WSL 경로: /home/user27/fastapi_resnet18

- training/finetune.py: Train 학습, 매 epoch Validation Accuracy 평가, 최고 점수 checkpoint 저장
- scripts/evaluate_validation.py: 선택된 MODEL_PATH를 Validation 전체에서 평가하고 이미지별 CSV·혼동행렬 CSV·지표 JSON 생성
- scripts/benchmark_validation.py: 동기·비동기 지연시간 및 Redis cache HIT/MISS 비교; 분류 정확도 평가와 구분
- ai/hf_model.py, ai/services.py: Transformers 모델 로딩과 이미지 입력 처리
- ai/router_sync.py, ai/router_async.py, ai/router_web.py: 동기·비동기 API 및 화면
- ai/database.py, ai/models.py: PostgreSQL 연결과 image_jobs
- ai/celery_app.py, ai/tasks.py: Celery 설정과 비동기 작업
- compose.yaml: Redis, PostgreSQL, FastAPI, Worker, Trainer 서비스
- dataset/{train,val,test}/{클래스명}/: 이미지 분할
- artifacts/beans_resnet18/: 필수 Head-only 기준 모델
- artifacts/beans_resnet18_full/: 별도 Full Fine-tuning 후보
- reports/01–09, reports/data/, reports/evidence/: 보고서와 평가 원본

## 데이터와 모델 결과

| 분할 | angular_leaf_spot | bean_rust | healthy | 합계 |
|---|---:|---:|---:|---:|
| Train | 345 | 348 | 341 | 1,034 |
| Validation | 44 | 45 | 44 | 133 |
| Test | 43 | 43 | 42 | 128 |

| 지표 | Head-only 기준 | Full Fine-tuning 후보 |
|---|---:|---:|
| Validation Accuracy | 0.7669 (102/133) | 0.9699 (129/133) |
| Test Accuracy | 미측정 | 0.9453 (121/128) |
| Macro F1 | 0.7640 | 0.9700 |
| 병든 잎 → healthy | 11건 | 2건 |
| 병든 클래스 간 혼동 | 16건 | 1건 |
| 전체 오분류 | 31건 | 4건 |

후보는 microsoft/resnet-18에서 새로 시작하고 새 3-class classifier를 초기화했다. Full Fine-tuning 3 epoch, batch 8, learning rate 0.00005로 학습했으며 최고 Validation 점수는 epoch 1에서 나왔다. Train loss는 epoch마다 낮아졌지만 Validation Accuracy는 0.9699, 0.9624, 0.9549로 내려갔다. 기준 모델 가중치는 보존됐다.

## 오분류 검토 및 현재 판단

후보의 남은 오분류:
- angular_leaf_spot_val.18: angular_leaf_spot → healthy; 여러 잎 구성으로 병든 부위가 덜 두드러졌을 가능성
- angular_leaf_spot_val.37: angular_leaf_spot → bean_rust; 갈색 병반이 구멍과 비슷해 보였을 가능성. 추가 개선 대상으로 삼지 않음
- bean_rust_val.5: bean_rust → healthy; 여러 잎과 밝은 촬영으로 병반이 덜 보였을 가능성
- healthy_val.1: healthy → bean_rust; 원인 미분석

Train에서 두 클래스의 다엽 구성과 강한 햇빛·그림자 사례도 시각적으로 확인했다. 비슷한 조건이 학습 데이터에 전혀 없었다고 보기는 어렵고, 원인 가설을 확정하지 않는다. 잔여 오분류 4건을 이유로 추가 학습을 반복할 필요성은 현재 낮게 판단한다. Full Fine-tuning 후보를 최종 후보로 확정했고 Test Accuracy는 0.9453이다. Test 결과로 추가 튜닝하지 않는다.

## 서비스 흐름과 현재 연결 모델

동기 API는 요청 안에서 캐시 조회·분류 후 결과를 반환한다. 비동기 API는 작업 접수(HTTP 202)와 Job ID를 반환하고 Worker가 분류 결과를 DB에 저장한다. Redis DB 1은 캐시, DB 2는 Celery Broker, DB 3은 Celery 결과 백엔드이며 작업 상태 API는 PostgreSQL을 조회한다.

현재 .env의 MODEL_PATH는 artifacts/beans_resnet18_full이다. Web·Worker를 재생성하고 Validation 이미지로 동기·비동기 추론을 재검증했다.

## 작업 시 지킬 조건과 남은 단계

- 개선 후보는 기준 모델과 별도 출력 폴더에 학습하고 기준 가중치를 보존한다.
- 같은 Train/Validation 분할로 비교하고, Test는 모델·정책 선택에 사용하지 않는다.
- Validation 결과는 작은 표본에서의 후보 비교이며 실제 재배지 성능으로 일반화하지 않는다.
- 학습·모델 선택은 Train과 Validation으로 수행했고, 최종 후보 확정 뒤 Test 전체 평가를 한 차례 완료했다.
- 남은 Validation 오분류의 시각적 원인은 가설이다. 추가 증강·임계값·확인 필요 정책은 적용하지 않았다.
- 현재 서비스 MODEL_PATH는 Full Fine-tuning 최종 후보를 가리킨다. Test 평가는 최종 후보 고정 후 한 차례만 수행했다.
- .env 자격 증명은 출력하거나 문서에 기록하지 않는다.

실험 상세와 농업 근거: reports/09_model_improvement_plan.md
