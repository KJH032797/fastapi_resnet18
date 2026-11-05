# API 명세서

| Method | Endpoint                    | 목적          | 확인 결과                                 |
| ------ | --------------------------- | ----------- | ------------------------------------- |
| GET    | `/health`                   | 서비스 상태      | HTTP 200 확인                           |
| POST   | `/api/sync/classify/`       | 이미지 즉시 분류   | Validation 이미지 3건과 캐시 MISS/HIT 확인     |
| POST   | `/api/async/classify/`      | 비동기 작업 접수   | Validation 이미지 3건 접수, Job 15–17 모두 완료 |
| GET    | `/api/async/jobs/{job_id}/` | 작업 상태·결과 조회 | Job 15–17 `done` 화면 JSON 및 DB 근거 확인   |

## 동기 분류 결과

- `angular_leaf_spot_val.3.jpg`: Top-1 `angular_leaf_spot` (0.5138), MISS. [JSON](evidence/sync_inference_angular_leaf_spot_val_3.json), [화면](evidence/sync_inference_angular_leaf_spot_val_3.jpeg)
- `bean_rust_val.10.jpg`: Top-1 `bean_rust` (0.4295), MISS. [JSON](evidence/sync_inference_bean_rust_val_10.json), [화면](evidence/sync_inference_bean_rust_val_10.jpeg)
- `healthy_val.7.jpg`: Top-1 `healthy` (0.9515), MISS. [JSON](evidence/sync_inference_healthy_val_7.json), [화면](evidence/sync_inference_healthy_val.7.jpeg)
- `bean_rust_val.27.jpg`: Top-1 `angular_leaf_spot` (0.5447), 오분류. 같은 입력에서 MISS와 HIT 결과 점수가 같고 HIT의 `inference_ms`는 `null`. [MISS JSON](evidence/sync_cache_miss_bean_rust_val_27.json), [HIT JSON](evidence/sync_cache_hit_bean_rust_val_27.json)

## 비동기 분류 결과

- Job 15 `angular_leaf_spot_val.3.jpg`: `done`, Top-1 `angular_leaf_spot` (0.5138), MISS. [JSON](evidence/async_inference_angular_leaf_spot_val_3.json), [화면](evidence/async_inference_angular_leaf_spot_val_3.jpeg)
- Job 16 `bean_rust_val.10.jpg`: `done`, Top-1 `bean_rust` (0.4295), MISS. [JSON](evidence/async_inference_bean_rust_val_10.json), [화면](evidence/async_inference_bean_rust_val_10.jpeg)
- Job 17 `healthy_val.7.jpg`: `done`, Top-1 `healthy` (0.9515), MISS. [JSON](evidence/async_inference_healthy_val_7.json), [화면](evidence/async_inference_healthy_val.7.jpeg)

비동기 접수 응답: HTTP 202, `job_id`, `status=queued`, `check_url`. 완료 여부: 상태 조회로 확인. 반복 성능 측정: [06 성능 비교](06_성능비교_보고서.md).
