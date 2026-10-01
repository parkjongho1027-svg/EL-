# Archived pre-Git builds

Git 저장소가 본격적으로 사용되기 전에 보관된 실제 소스 파일을 추적하기 위한 인덱스입니다.

현재 확인된 원본은 아래 5개입니다. 파일명 숫자보다 소스 내부의 APP_BUILD를 우선합니다.

| Build | 원본 파일 | 크기(bytes) | SHA-256 |
|---|---|---:|---|
| 2026.09.13.7 | elevator_calc.py | 99,895 | ae59e32dd262557401be265da9548b45c2edc0efe9c81ccd419f300482eb1dc6 |
| 2026.09.13.30 | elevator_calc_38(1).py | 176,168 | a126b89c0852d7da974877941dcf9c77e3d32f40ce6e46e717def56a0c430451 |
| 2026.09.16.39 | elevator_calc_39.py | 739,869 | d6ea515b649a8fe92a86e74437df2adb533913074834aed017f6773551fa8350 |
| 2026.09.16.41 | elevator_calc_41.py | 738,940 | 83d69efa946d23f34c3e8009cfe64d344b61f3d5199489a7bffe39cf65c5e561 |
| 2026.09.18.48 | elevator_calc_52.py | 743,329 | 5dbe25775df1e6cfcbe31147a2ce9192308a22e5a908f3429197087e7cc92aa9 |

SHA-256은 복구된 원본 바이트를 기준으로 계산했습니다. 이후 archive에 소스가 추가될 때 이 값으로 동일 파일인지 확인할 수 있습니다.

## 원칙

- 없는 v1~v65를 임의 생성하지 않습니다.
- 과거 파일을 현재 코드처럼 수정하지 않습니다.
- 원본은 read-only 성격의 archive로 취급합니다.
- 실제 Git 이력은 v66.0.0 이후의 기존 태그/커밋을 그대로 사용합니다.
- 상세 변화는 ../docs/DEVELOPMENT_HISTORY.md와 ../CHANGELOG.md에 기록합니다.
