# Changelog

승강기 설계 계산·검토 및 시뮬레이션 프로그램의 **검증 가능한** 개발 기록입니다.

## 2026-10-01
- MIT License 적용
- 과거 원본 파일과 Git 태그/커밋을 대조한 DEVELOPMENT_HISTORY 작성
- 파일명과 내부 APP_BUILD가 다른 과거 파일은 내부 빌드 번호 기준으로 정리

## v82.0.0 — 2026-09-25
- 승강로 UI 모듈 분리
- 층 표시 스크롤
- 현재 정지층 기준 목적층 이동 경로 처리
- 승강로 UI 테스트 추가

## v81.0.0 — 2026-09-25
- 시뮬레이션 차트 비교
- 층간 운행 애니메이션
- hoistway 운행 계산 추가

## v69.0.0 — 2026-09-24
- src/config · src/core · src/ui 구조 도입
- motor_dynamics · capacity · rope_traction 등 공학 계산 확장
- GitHub Actions 검증 워크플로와 VALIDATION_PLAN 추가
- 그래프/모터 동역학 테스트 확대
- Pillow 개발 의존성 추가

## v68.0.0 — 2026-09-24
- 기준검토 레이아웃 정렬 수정
- Enter 입력 후 다음 입력 위치 선택 동작 개선
- 키보드/레이아웃 회귀 테스트 보강

## v66.0.0 — 2026-09-24
- 계산기 소스, 기준검토 엔진, 에너지 모델, 그래프 모듈 공개
- 테스트 코드와 개발 의존성 포함
- 공개 Git 이력의 주요 기준점

## 복구된 이전 빌드
- Build 48 — elevator_calc_52.py
- Build 41 — elevator_calc_41.py
- Build 39 — elevator_calc_39.py
- Build 30 — elevator_calc_38(1).py
- Build 7 — elevator_calc.py

> 이전 파일은 파일명 숫자가 실제 APP_BUILD와 일치하지 않을 수 있습니다. 상세 근거는 docs/DEVELOPMENT_HISTORY.md를 참고하십시오.
