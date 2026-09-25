# 공개 버전과 로컬 작업 이력

현재 작업 트리 빌드 `2026.09.25.81`은 아래 공개 태그와 별개의 후속 변경입니다. 저장 시뮬레이션 곡선의 겹침·세로 비교와 출발/도착 층별 승강로 이동을 추가했습니다. 이번 변경의 게시 여부는 새 Git 커밋과 원격 상태로 확인해야 합니다.

| 공개 버전 | 공개 `main` 커밋 | 보존된 로컬 작업 브랜치 | 관계 |
| --- | --- | --- | --- |
| `v66.0.0` | `8c96040` | `v66-local-history` (`ceb57d1`) | 내용 트리 동일, 커밋 작성 이력은 별도 |
| `v68.0.0` | `b8c86c4` | `v68-local-history` (`44a0fd0`) | 내용 트리 동일, 커밋 작성 이력은 별도 |
| `v69.0.0` | `5c52d6c` | `v69-local-history` (`ee9a4cf`), `v69-local-ci-history` (`01c1348`) | 전자는 공개 기능 커밋 `6092d59`와 내용 트리 동일, 후자는 공개 `5c52d6c`와 내용 트리 동일 |

내용 비교 명령: `git rev-parse <브랜치명>^{tree}`. 브랜치는 이전 작업의 커밋 단위를 보관하려고 로컬에 남겼습니다. 동일한 소스 트리를 다시 `main`에 병합하면 중복 커밋만 생기므로 병합하지 않습니다. 로컬 백업 브랜치의 삭제는 이력 확인 후 별도 결정합니다.

태그 `v66.0.0`, `v68.0.0`, `v69.0.0`은 위의 공개 커밋을 가리킵니다. 태그를 원격으로 게시했는지는 `git ls-remote --tags origin`으로 확인합니다. `v69.0.0` 태그는 CI가 통과한 소스에 고정되며 이후 훅과 개발 문서 변경은 별도 커밋으로 남습니다.

## 실제 소스 본문

- [`main.py`](../main.py): 여섯 화면, 입력·저장 연결. 아직 큰 단일 GUI 파일입니다.
- [`src/core/calculators.py`](../src/core/calculators.py): 전동기·트랙션·브레이크·교통량 수식.
- [`src/core/motor_dynamics.py`](../src/core/motor_dynamics.py): 관성·가속 토크·운전율·전기 제동 저항 계산.
- [`src/core/energy_model.py`](../src/core/energy_model.py): 운행별 전력 적분 및 실측 CSV 비교.
- [`src/core/elevator_review_engine.py`](../src/core/elevator_review_engine.py): KC 개별 조항 및 S-Curve 모델.
- [`tests/test_motor_dynamics.py`](../tests/test_motor_dynamics.py): 산술 기준·예외 검증.

GitHub에서 파일을 누르면 Git 객체 바이너리나 로그 메타데이터 대신 Python 소스 본문을 볼 수 있습니다. `[source]` 탭의 `src/core/`가 독립 계산 엔진입니다.

## 기여 흐름

현 단계는 단일 기여자의 `main`과 필요할 때 만드는 `feature/<주제>` 브랜치로 충분합니다. 협업이 늘어 배포용 `main`과 통합 시험용 브랜치를 실제로 분리해야 할 때 `develop`을 추가할 수 있습니다. 브랜치 이름만 바꿔서는 품질이 올라가지 않으며, PR 검증·리뷰·태그·되돌리기 절차를 함께 운영해야 합니다.
