# 모델 개선 실험 결과 및 검토

## 개선 목표와 우선순위

기준 모델 Validation 오분류: 병든 잎 → healthy 11건, 병든 클래스 간 혼동 16건. 우선 개선: 병든 잎 → healthy 오류 감소.

각진잎반점병: 잎·줄기·꼬투리의 각진 갈색 병반. 조기·심한 발병 시 낙엽·수량 저하 가능. Embrapa: 감수성 품종에서 최대 80% 손실 보고(특정 조건의 사례).

콩녹병: 잎의 적갈색 포자 농포. 생육 초기 심한 감염 시 낙엽, 꼬투리 형성·종자 크기 영향 가능. Colorado State University Extension: 일부 지역의 심한 유행에서 50% 초과 손실 보고. 특정 재배 조건의 사례, 일반화 불가.

방제 고려: 저항성 품종·잔재 관리 등 일부 공통. 윤작, 발생 시기·전염 조건 등 병별 고려사항 존재. 일부 살균제도 겹치지만 완전 대체 관계 아님. 병명 오분류가 곧 잘못된 방제를 뜻하지는 않음. 실제 병해 대응 누락·지연 우려. `healthy` 오분류는 병든 잎 자체를 놓칠 수 있어 우선 개선 대상으로 선정.

다음 검토 대상: 병든 두 클래스 간 혼동. 점수가 비슷한 사례의 `확인 필요` 분기 가능성 검토.

## 실험 구성

- 기준 모델: 필수 Head-only Fine-tuning, artifacts/beans_resnet18/
- 후보 시작점: microsoft/resnet-18 사전학습 가중치에서 새로 초기화; 기준 모델에서 이어 학습하지 않음
- 학습 자료: Train 1,034장
- 비교 자료: Validation 133장
- 실행 조건: 3 epoch, batch size 8, learning rate 0.00005, --freeze-backbone 생략
- 이미지 변형·증강: 추가하지 않음
- 평가 도구: scripts/evaluate_validation.py
- Test: 학습·모델 선택에 사용하지 않고 후보 확정 뒤 128장 전체를 한 차례 평가
- 기준 모델 가중치 해시: 학습 전후 동일

## Validation 결과

| 지표 | Head-only 기준 모델 | Full Fine-tuning 후보 |
|---|---:|---:|
| 정답 / 전체 | 102 / 133 | 129 / 133 |
| Accuracy | 0.7669 | 0.9699 |
| Macro Precision | 0.7650 | 0.9707 |
| Macro Recall | 0.7678 | 0.9699 |
| Macro F1 | 0.7640 | 0.9700 |
| 병든 잎 → healthy | 11건 | 2건 |
| 병든 클래스 간 혼동 | 16건 | 1건 |
| healthy → 병든 클래스 | 4건 | 1건 |
| 전체 오분류 | 31건 | 4건 |

후보 클래스별 지표:

| 클래스 | Precision | Recall | F1 | Support |
|---|---:|---:|---:|---:|
| angular_leaf_spot | 1.0000 | 0.9545 | 0.9767 | 44 |
| bean_rust | 0.9565 | 0.9778 | 0.9670 | 45 |
| healthy | 0.9556 | 0.9773 | 0.9663 | 44 |

후보 epoch 기록:

| Epoch | Train Loss | Validation Accuracy | 저장 여부 |
|---:|---:|---:|---|
| 1 | 0.4399 | 0.9699 | 최고 점수, 저장 |
| 2 | 0.1550 | 0.9624 | 저장하지 않음 |
| 3 | 0.0856 | 0.9549 | 저장하지 않음 |

Train Loss 감소. Validation Accuracy는 epoch 1 이후 하락. 오답은 epoch별 4·5·6장. 과적합 단정 없이 주의 신호로 기록. 후보 가중치: Validation 최고점인 epoch 1.

후보 혼동행렬(행=정답, 열=예측):

| 정답 / 예측 | angular_leaf_spot | bean_rust | healthy |
|---|---:|---:|---:|
| angular_leaf_spot (44) | 42 | 1 | 1 |
| bean_rust (45) | 0 | 44 | 1 |
| healthy (44) | 0 | 1 | 43 |

산출물:
- 후보 모델: artifacts/beans_resnet18_full/
- 학습 기록: artifacts/beans_resnet18_full/training_report.json
- Validation 지표: reports/evidence/validation_full_finetune_metrics.json
- 이미지별 예측: reports/data/validation_full_finetune_predictions.csv
- 혼동행렬: reports/data/validation_full_finetune_confusion_matrix.csv
- 기준선 지표: reports/evidence/validation_baseline_metrics.json
- 기준선 예측·혼동행렬: reports/data/validation_baseline_*.csv

## 남은 오류 검토

| Validation 이미지 | 정답 → 예측 | Top-1 점수 | 확인 내용 |
|---|---|---:|---|
| angular_leaf_spot_val.18.jpg | angular_leaf_spot → healthy | 0.6095 | 여러 잎이 함께 있어 병든 부위가 두드러지지 않았을 가능성 |
| angular_leaf_spot_val.37.jpg | angular_leaf_spot → bean_rust | 0.8392 (angular_leaf_spot 0.1320, healthy 0.0288) | 갈색 병반이 구멍처럼 보여 혼동할 가능성 |
| bean_rust_val.5.jpg | bean_rust → healthy | 0.3470 | 여러 잎과 밝은 촬영으로 병든 부분이 덜 보였을 가능성 |
| healthy_val.1.jpg | healthy → bean_rust | 0.5505 | 원인 미분석 |

Train 유사 조건 육안 확인: angular_leaf_spot 345장, bean_rust 348장 연락 시트 검토. `angular_leaf_spot_train.10.jpg`·`angular_leaf_spot_train.108.jpg`: 여러 잎과 병반. `bean_rust_train.100.jpg`·`bean_rust_train.119.jpg`: 여러 잎과 강한 햇빛·그림자. 유사 조건 존재, 수량 정량 집계 미실시.

## 추가 개선 판단

병든 클래스 간 잔여 오분류: `angular_leaf_spot_val.37.jpg` 1건. `bean_rust` 점수가 크게 우세. 점수 유사 사례용 `확인 필요` 기준으로 해결하기 어려운 유형. 사례 1건·후보 성능 고려, 추가 개선 미선정.

병든 잎 → healthy 잔여 사례: 여러 잎 구도와 병반의 낮은 두드러짐이 가능한 원인. Train 유사 조건 존재, 수량 집계·원인 확정 미실시. `healthy_val.1.jpg`(healthy → 병든 클래스) 원인 미분석. 이번 개선 목표 범위 밖.

최종 판단: Validation 결과·이미지 검토·잔여 시간 고려. 추가 학습·임계값 조정 미실시. HSV·Mask 후처리, Grad-CAM, CNN+ML 결합 미구현·미측정.

## Test 최종 평가와 현재 판단

평가 시점: 최종 후보 확정 뒤 Test 128장 전체 1회.

| 정답 클래스 | 정답 / 전체 | 오분류 |
|---|---:|---|
| angular_leaf_spot | 43 / 43 | 없음 |
| bean_rust | 39 / 43 | 4건을 angular_leaf_spot으로 예측 |
| healthy | 39 / 42 | 1건을 angular_leaf_spot, 2건을 bean_rust로 예측 |
| 전체 | 121 / 128 | 7건 |

결과: Accuracy 0.9453, Macro F1 0.9455, 병든 잎 → healthy 0건. Test 결과 기반 모델·임계값 조정 미실시. 해당 Test 분할의 평가치, 실제 재배지 성능으로 일반화 불가.

산출물:
- 평가 스크립트: scripts/evaluate_test.py
- 지표: reports/evidence/test_final_metrics.json
- 예측: reports/data/test_final_predictions.csv
- 혼동행렬: reports/data/test_final_confusion_matrix.csv

농업 근거:
- Embrapa, Doenças fúngicas da parte aérea: https://www.embrapa.br/en/web/agencia-de-informacao-tecnologica/cultivos/feijao/producao/doencas/doencas-fungicas/doencas-fungicas-da-parte-aerea
- Embrapa Infoteca, Mancha-angular: https://www.infoteca.cnptia.embrapa.br/infoteca/bitstream/doc/1102266/1/CNPAF2018ManIdentDoenFeijao.pdf
- Colorado State University Extension, Rust of Dry Beans: https://extension.colostate.edu/resource/rust-of-dry-beans/

해석 한계: 두 병해 피해는 품종·지역·발병 조건에 따라 다름. 프로젝트 오분류만으로 실제 작물 피해·방제 결과 입증 불가.
