# Development History

이 문서는 실제로 확인 가능한 소스 파일, 내부 APP_BUILD 값, Git 커밋 및 태그를 기준으로 작성한 개발 이력입니다.
존재가 확인되지 않은 버전 번호는 임의로 복원하지 않습니다.

## 1. 복구된 초기/중기 소스

| 확인된 빌드 | 원본 파일명 | 보관 시점 | 확인 내용 |
|---|---|---|---|
| 2026.09.13.7 | elevator_calc.py | 2026-09-13 | 초기 통합 계산기 계열. 전동기 용량·트랙션비·브레이크 제동·교통량 분석의 4개 핵심 계산 기능 |
| 2026.09.13.30 | elevator_calc_38(1).py | 2026-09-14 | 파일명 숫자와 내부 APP_BUILD가 다름. 내부 빌드값을 우선 기록 |
| 2026.09.16.39 | elevator_calc_39.py | 2026-09-16 | FORMULA_VERSION 2026.09.13-F3 계열 |
| 2026.09.16.41 | elevator_calc_41.py | 2026-09-16 | 영문 UI 및 계산식 이미지/표시 계열 개선 |
| 2026.09.18.48 | elevator_calc_52.py | 2026-09-22 보관본 | 파일명은 52지만 내부 APP_BUILD는 2026.09.18.48 |

> 파일명의 숫자를 버전 번호로 간주하지 않습니다. 예: elevator_calc_52.py는 내부 APP_BUILD 기준 Build 48입니다.

## 2. Git 태그로 검증된 주요 버전

| 태그 | Commit | 날짜(UTC) | 커밋 메시지 |
|---|---|---|---|
| v66.0.0 | 8c96040 | 2026-09-24 | feat: publish elevator calculator v66 source, tests, and graphs |
| v68.0.0 | b8c86c4 | 2026-09-24 | fix: align criteria layout and select next tab after Enter (v68) |
| v69.0.0 | 5c52d6c | 2026-09-24 | fix: install Pillow for CI plot regression tests |
| v81.0.0 | 22ef3c1 | 2026-09-25 | feat: compare simulation charts and animate floor-to-floor trips |
| v82.0.0 | b93c60a | 2026-09-25 | feat: scroll hoistway floors and route from current stop |

## 3. 태그 간 실제 변경 내용

### v66.0.0 — 공개 저장소 기준점
- main.py와 계산/검토/에너지/그래프 모듈 공개
- 전동기·트랙션·브레이크·교통량 계산 기반
- 기준검토 엔진과 에너지 모델 포함
- 단위 테스트 및 UI/상태/시뮬레이션 테스트 포함
- 그래프 예시 이미지와 개발 의존성 구성

### v66 → v68
- 기준검토 레이아웃 정렬 수정
- Enter 입력 후 다음 입력칸/탭 선택 동작 개선
- main.py 110라인 규모 변경
- 키보드/레이아웃 회귀 테스트 보강

### v68 → v69
이 구간에는 2개 커밋이 포함됩니다.
- GitHub Actions verify 워크플로 추가
- 기존 루트 계산 모듈을 src/core 중심 구조로 이전
- src/config, src/core, src/ui 패키지 구조 도입
- motor_dynamics, capacity, rope_traction 등 공학 계산 모듈 확장
- VALIDATION_PLAN 추가
- 그래프 엔진 및 모터 동역학 테스트 추가
- Pillow를 개발 의존성에 추가하여 CI 그래프 회귀 테스트 환경 보완

### v69 → v81
8개 커밋에 걸친 대규모 확장 구간입니다.
- 단일 main.py 중심 구조를 기능별 패널/모듈 구조로 대폭 분리
- 설계 후보 탐색(component_spec, design_explorer) 추가
- 도면/문서 필드 추출(document_fields, document_reader) 추가
- 실측 속도·에너지 비교(measured_speed) 계열 추가
- 진동 분석(vibration_analysis) 추가
- trajectory 및 S-Curve UI 확장
- 전동기, 트랙션, 브레이크, 교통량 패널 분리
- 프로젝트 스냅샷 및 기록 관리자 추가
- 그래프 작업공간과 축/PNG 저장 기능 확장
- KC 출처 매트릭스, 측정 프로토콜, 공학 데이터 도구 문서화
- pre-commit, verify script, CI 및 테스트 체계 확대
- v81에서 시뮬레이션 차트 비교와 층간 운행 애니메이션 추가

### v81 → v82
- 승강로 UI를 별도 hoistway_view 모듈로 분리
- 승강로 geometry 모듈 추가
- 층 표시 스크롤 지원
- 현재 정지층을 기준으로 목적층 이동 경로 계산/표시
- 승강로 UI 전용 테스트 추가

## 4. 현재까지 확인되는 개발 흐름

초기 4개 계산 기능
→ 입력/UI 및 프로젝트 관리 개선
→ 기준검토와 에너지/그래프 기능
→ 테스트 및 모듈 구조화
→ 공학 계산·S-Curve·설계 후보·실측/진동 도구
→ 그래프 비교 및 층간 애니메이션
→ 승강로 위치 시뮬레이션
→ 현재 main 브랜치

## 5. 이력 보존 원칙

이 저장소는 버전 숫자를 억지로 1부터 연속적으로 채우지 않습니다.
복구되지 않은 버전은 실제 파일이나 Git 객체가 발견될 때만 추가합니다.

과거 소스를 현재 main에 덮어써서 가짜 시간순 커밋을 만드는 대신, 기존 Git 커밋/태그는 그대로 보존하고 복구된 원본은 별도 archive로 관리하는 것을 원칙으로 합니다.
