# FastAPI Beans ResNet18 동기·비동기 분류 서비스

콩잎 이미지 세 클래스(angular_leaf_spot, bean_rust, healthy)를 분류하고 결과를 FastAPI 동기·비동기 API로 제공하는 교과 9 평가 프로젝트.

- 모델: microsoft/resnet-18 기반 ResNet18 fine-tuning
- 서비스: FastAPI, Celery Worker, Redis, PostgreSQL
- 최종 서비스 후보: artifacts/beans_resnet18_full/
- 추론 장치: CPU
- 필수 산출물과 증빙: reports/

## 현재 결과 요약

| 모델 | Validation Accuracy | Validation Macro F1 | Test Accuracy | Test Macro F1 |
|---|---:|---:|---:|---:|
| Head-only 기준 모델 | 0.7669 | 0.7640 | — | — |
| Full Fine-tuning 최종 후보 | 0.9699 | 0.9700 | 0.9453 (121/128) | 0.9455 |

- 병든 잎 → healthy 오분류: 기준 모델 11건 → 후보 2건 (Validation)
- 병든 클래스 간 혼동: 기준 모델 16건 → 후보 1건 (Validation)
- Test: 후보 확정 뒤 128장 전체 1회 평가. 추가 튜닝 미실시.
- 결과 상세: [08 최종 기술 보고서](reports/08_최종기술보고서.md), [09 개선 실험 검토](reports/09_model_improvement_plan.md)

## 준비물

### 저장소 받기

```bash
git clone https://github.com/KJH032797/fastapi_resnet18.git
cd fastapi_resnet18
```

### 실행 환경

- Windows + WSL2 Ubuntu 또는 Linux
- Windows: [Docker Desktop 설치](https://docs.docker.com/desktop/setup/install/windows-install/) 후 Ubuntu의 WSL Integration 활성화. [공식 WSL 안내](https://docs.docker.com/desktop/features/wsl/)
- Linux: Docker Engine 및 Docker Compose v2
- 학습 시 Hugging Face 사전학습 모델을 받을 인터넷 연결 또는 사전 캐시
- Docker 방식의 API·학습 실행에는 호스트 WSL 가상환경 불필요
- 아래 검증 스크립트를 호스트에서 직접 실행할 때만 Python 3.11 가상환경 필요

### 데이터 준비

수업 제공 Beans 데이터셋 또는 [AI-Lab-Makerere Beans 데이터셋](https://huggingface.co/datasets/AI-Lab-Makerere/beans)을 별도로 확보. 공유·재배포 시 이용 조건 확인.

프로젝트에서 사용하는 구조:

```text
dataset/
├── train/
│   ├── angular_leaf_spot/
│   ├── bean_rust/
│   └── healthy/
├── val/
│   ├── angular_leaf_spot/
│   ├── bean_rust/
│   └── healthy/
└── test/
    ├── angular_leaf_spot/
    ├── bean_rust/
    └── healthy/
```

- 원본 validation/ 이미지는 실행 경로 dataset/val/에 배치.
- Train 1,034장, Validation 133장, Test 128장.
- GitHub에는 데이터셋을 포함하지 않음. 허용된 경로에서 확보해 위 위치에 배치.
- Test는 모델 선택·튜닝에 사용하지 않음. 최종 후보 확정 뒤 최종 평가에만 사용.

### 모델과 환경 파일

최종 API 실행에는 Full Fine-tuning 모델을 artifacts/beans_resnet18_full/에 배치. 필요한 파일: config.json, model.safetensors, preprocessor_config.json.

- 데이터·모델 가중치: GitHub에 포함하지 않음. 허용된 별도 전달 경로에서 확보.
- 저장소를 새로 받은 뒤 환경 파일 생성:

```bash
cp .env.example .env
```

- .env의 모델 경로를 최종 후보로 설정:

```env
MODEL_PATH=artifacts/beans_resnet18_full
```

.env.example의 기본 경로는 Head-only 기준 모델(artifacts/beans_resnet18). 기준 모델만 실행할 때는 이 경로 유지. 최종 후보 서비스에는 Full Fine-tuning 모델 파일 필요.

## 빠른 실행

데이터·모델 파일을 준비하고 .env를 설정한 뒤 프로젝트 루트에서 실행:

```bash
docker compose up -d --build
docker compose ps
docker compose exec redis redis-cli ping
```

Redis 확인 결과 PONG, Web·Worker·PostgreSQL 컨테이너 상태 정상인지 확인.

- 동기 화면: http://127.0.0.1:8000/vision/sync/
- 비동기 화면: http://127.0.0.1:8000/vision/async/
- API 문서: http://127.0.0.1:8000/docs
- 상태 확인: http://127.0.0.1:8000/health

동기 API: 분류 완료 후 결과 반환. 비동기 API: HTTP 202와 Job ID를 먼저 반환. 상태 조회에서 done 확인.

서비스 종료:

```bash
docker compose down
```

## 학습 재현

### Head-only 기준 모델

Train·Validation 데이터와 .env 준비. 결과 경로: artifacts/beans_resnet18/.

```bash
docker compose build trainer
docker compose --profile train run --rm trainer
```

### Full Fine-tuning 후보

같은 Train·Validation 데이터로 Backbone을 고정하지 않고 학습. 결과 경로: artifacts/beans_resnet18_full/. 학습 후 .env의 MODEL_PATH를 이 경로로 바꾸고 Web·Worker 재생성.

```bash
docker compose --profile train run --rm trainer python -m training.finetune --data dataset --output artifacts/beans_resnet18_full --epochs 3 --batch-size 8 --lr 0.00005
docker compose up -d --force-recreate web worker
```

Trainer는 Validation Accuracy 최고 epoch의 모델을 저장. Head-only와 Full Fine-tuning은 별도 경로로 보존.

## 로컬 검증 스크립트 실행

scripts/를 Docker 밖에서 직접 실행할 때만 호스트 가상환경 설치. Docker 기반 서비스·학습에는 불필요.

```bash
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
export MODEL_PATH=artifacts/beans_resnet18_full
```

호스트에서 실행하는 Python 스크립트는 .env를 자동으로 읽지 않음. 평가할 모델 경로를 MODEL_PATH로 지정.

| 스크립트 | 실행 예 | 용도·결과 |
|---|---|---|
| 데이터 중복 점검 | python scripts/audit_dataset_duplicates.py | 분할 간 파일명·바이트 완전 중복 점검. 근접 중복 미검사. reports/data/filename_cross_split_duplicates.csv, reports/data/exact_cross_split_duplicates.csv 생성 |
| Validation 전체 평가 | python scripts/evaluate_validation.py --name validation_run | 현재 MODEL_PATH 모델 지표·예측·혼동행렬. reports/evidence/<name>_metrics.json, reports/data/<name>_predictions.csv, reports/data/<name>_confusion_matrix.csv |
| 최종 Test 평가 | python scripts/evaluate_test.py --name test_run | 후보 확정 뒤 1회 실행. reports/evidence/<name>_metrics.json, reports/data/<name>_predictions.csv, reports/data/<name>_confusion_matrix.csv 생성. Test 결과 기반 추가 튜닝 금지 |
| 서비스 성능 측정 | python scripts/benchmark_validation.py --name validation_benchmark_run | 실행 중인 로컬 API·Redis 필요. 워밍업 후 Validation 이미지 5장 동기·비동기 MISS/HIT 측정. 선택 이미지의 Redis DB 1 캐시 키 삭제. CSV·JSON은 reports/data/ 및 reports/evidence/에 저장 |

평가·성능 스크립트는 기존 결과를 덮어쓰지 않음. 재실행 시 새 --name 사용.

## 서비스 처리 흐름

- 동기: 이미지 업로드 → 입력 검증 → Redis 조회 → MISS면 모델 추론·캐시 저장 → 결과 응답
- 비동기: 이미지 업로드 → 입력 검증·작업 등록 → HTTP 202·Job ID 반환 → Celery Worker 추론 → PostgreSQL 저장 → 상태 조회
- Redis DB 1: 추론 결과 캐시 / DB 2: Celery Broker / DB 3: Celery 결과 백엔드
- PostgreSQL image_jobs: 비동기 작업 상태·결과 저장

## 산출물과 증빙

- 필수 산출물 1–8: [reports/](reports/)
- 추가 개선 기록: [09 모델 개선 실험 결과 및 검토](reports/09_model_improvement_plan.md)
- Validation/Test 지표: reports/evidence/*_metrics.json
- 이미지별 예측·혼동행렬·중복 점검: reports/data/
- 성능 원본: reports/data/timings_validation_benchmark_5x.csv
- 실행 캡처·API 응답·작업 기록: reports/evidence/
- 시스템 구조·처리 흐름: [02 시스템 아키텍처](reports/02_시스템_아키텍처.md)
- API·DB·기능 검증: [03 API 명세서](reports/03_API_명세서.md), [04 DB 구조·작업 이력](reports/04_DB_구조_작업이력.md), [07 기능 테스트·오류 분석](reports/07_기능테스트_오류분석.md)

## GitHub 업로드에서 제외할 항목

- .env: 개인 환경 설정·자격 증명. 공개 저장소 업로드 금지.
- .venv/, __pycache__/, *.pyc: 로컬 가상환경·생성 캐시.
- dataset/, artifacts/, media/jobs/: 데이터·모델 가중치·실행 업로드 파일. 허용된 별도 제출·공유 경로 이용.
- .env.example, 소스·설정, 보고서·증빙: 저장소에 포함.
- 제외 파일은 별도로 확보한 뒤 이 README의 경로에 배치.

.env, 비밀번호, API 키, 공개 권한이 확인되지 않은 데이터는 GitHub에 올리지 않는다.
