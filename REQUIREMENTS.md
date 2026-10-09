# 용돈 기입장(budget_app) 요구사항 정의서

> 원본: `미션 - AI 도구 학습.pdf` 를 구현 가능한 체크리스트로 정리한 문서.
> `[결정]` 표시는 과제가 선택을 맡긴 항목이며, 괄호 안이 확정안이다.
>
> **범위 원칙: 이 문서(= PDF)에 없는 기능·명령·옵션·편의 기능은 만들지 않는다.**
> 애매한 부분은 임의로 채우지 않고 사용자에게 확인한다.

## 0. 개발 환경 / 제약

- [ ] Python 3.10 이상
- [ ] 표준 라이브러리만 사용 (`pip install` 금지) → `argparse`, `json`, `csv`, `dataclasses`, `datetime`, `os`, `tempfile`, `functools`, `heapq`, `typing` 등
- [ ] 실행 방식: `python -m budget_app <command> [options]`
- [ ] 모든 명령에 `--help` 동작
- [ ] 옵션은 모두 `--` 두 개짜리로 통일 (`--limit`, `--from`, `--to`, `--month` …)

## 1. 데이터 모델

### Transaction (거래)
| 필드 | 타입 | 규칙 |
| --- | --- | --- |
| id | str | 유일. 예: `TX-000012` |
| type | str | `income` 또는 `expense` 만 허용 |
| date | str | `YYYY-MM-DD`, 실제 존재하는 날짜 |
| amount | int | 양의 정수 (0, 음수 불가) |
| category | str | 등록된 카테고리만 허용 |
| memo | str | 선택 (빈 문자열 가능) |
| tags | list[str] | 선택 (빈 리스트 가능) |

- [ ] `@dataclass` 로 정의
- [ ] 클래스 2개 이상 사용 (예: `Transaction`, `TransactionRepository`, `CategoryStore`, `BudgetStore`, `BudgetService`)

### 입력 검증 (어긋나면 재입력 요구 또는 오류 메시지)
- [ ] 날짜 형식/존재 여부 (`2024-13-40` 거부)
- [ ] 금액 0·음수·숫자 아님 거부
- [ ] type 이 income/expense 아님 거부
- [ ] 등록되지 않은 category 거부

## 2. 저장 정책

- [ ] 포맷 1개 선택 `[결정] (JSONL)`
- [ ] 파일 3개 이상 분리
  - `data/transactions.jsonl`
  - `data/categories.jsonl`
  - `data/budgets.jsonl`
- [ ] 기본 폴더 `./data`, `--data-dir <경로>` 옵션으로 변경 가능
- [ ] 파일이 없으면 자동 생성 (또는 초기화 안내 메시지)
- [ ] 카테고리 파일이 비었을 때 동작 `[결정] (안 A: PDF 예시 그대로 기본 카테고리 food, transport, rent, etc 자동 생성)`
- [ ] update/delete 는 임시 파일에 전체 재작성 → `os.replace` 로 원자적 교체

## 3. 명령어별 요구사항

| # | 명령 | 입력 | 출력 | 체크 |
| --- | --- | --- | --- | --- |
| 1 | `add` | 대화형 `input()`: 날짜, 타입, 카테고리, 금액, 메모, 태그 | `[저장 완료] id=TX-…` | [ ] |
| 2 | `list` | `--limit N` (기본값 있음, 예: 20) | 최신순 목록, 제너레이터 스트리밍 | [ ] |
| 3 | `search` | `--from --to --category --type --q --tag` (조합 가능) | 조건 일치 목록, 최신순, 스트리밍 | [ ] |
| 4 | `summary` | `--month YYYY-MM --top N` | 총수입/총지출/잔액 + 카테고리별 지출 TOP N, 없으면 "데이터 없음" | [ ] |
| 5 | `budget set` | `--month YYYY-MM --amount 금액` | 저장 완료 메시지. summary 에 사용률(%) + 초과 경고 | [ ] |
| 6 | `category add/list/remove` | add 는 이름 입력 | 목록/추가/삭제 결과. 사용 중이면 삭제 차단 `[결정] (차단)` | [ ] |
| 7 | `update` | `[결정] (안 A 옵션식)` `--id` + `--date --type --category --amount --memo --tags` 중 원하는 것 | 성공/실패, 없는 id 처리 | [ ] |
| 8 | `delete` | `--id <id>` | 성공/실패, 없는 id 처리 | [ ] |
| 9 | `import` | `--from <csv>` | `imported=N, skipped=M` | [ ] |
| 10 | `export` | `--out <csv>` + (`--month` 또는 `--from/--to`) **필수** | `[완료] export.csv (N records)` | [ ] |

- "최신순" 정의: date 내림차순, 같은 날짜면 id 내림차순
- `category add` 는 대화형 (`카테고리명:` 입력, PDF 8장 예시 / 4장 1번 옵션 허용 목록에 category 없음)
- 카테고리 이름 입력 검증 `[결정] (최소 검증)`: 빈 이름 거부 후 재입력, 앞뒤 공백 제거 후 저장, 이미 있는 이름 거부, 대소문자는 구분(그대로 비교) — 근거: 4장 2번 입력 검증
- 태그 입력: 쉼표(,) 구분 (PDF 8장 add 예시, CSV 스키마)
- search / summary 세부 규칙 (PDF 재확인 후 확정)
  - 미등록 `--category` 검색 → 오류 (근거: 4장 2번 "존재하지 않는 category … 오류 메시지")
  - `--q` 메모 부분 일치 (근거: 4장 7번 "메모 키워드")
  - 예산 경고는 지출 > 예산일 때만 (근거: 4장 9번 "초과 시 경고")
  - search 최신순 정렬은 외부 정렬(1000건 조각 + heapq.merge, fan-in 64)로 메모리를 매칭 수와 무관하게 유지 (근거: 4장 7번 "스트리밍 처리 유지" 엄격 해석, 5단계)
  - 사용법 오류(argparse)의 원인 문장도 한국어로 출력 (근거: 사용자 결정 — 다른 오류와 일관성, 7단계). 알 수 없는 형식은 원문 유지
  - 출력 받는 쪽이 먼저 닫히면(`| head`) 추가 출력 없이 종료 코드 1 (근거: 4장 "스택트레이스 대신 원인+힌트" 엄격 해석, 6단계)
  - `[결정]` 조건 없는 search → 오류 / `--from` > `--to` → 결과 없음 / `--tag` 정확 일치·대소문자 구분 / `--top` 기본값 3 — PDF 에 규칙 없음, 가장 단순한 해석

### import/export CSV 스키마 (고정)
UTF-8, 헤더 포함, id 컬럼 없음 (import 시 새 id 발급)

| column | required | 설명 |
| --- | --- | --- |
| date | Y | YYYY-MM-DD |
| type | Y | income / expense |
| category | Y | 등록된 카테고리 |
| amount | Y | 양수 정수 |
| memo | N | 문자열 |
| tags | N | 쉼표(,) 구분 문자열 |

- import 중 잘못된 행은 건너뛰고 skipped 로 집계

## 4. 비기능 요구사항 (구조·품질)

- [ ] **제너레이터**: 거래 파일은 `yield` 로 한 줄씩 읽음 (한 번에 전체 로드 금지)
- [ ] **데코레이터**: 공통 관심사 1개 이상 구현·적용 (예: 예외 → `[오류]`+`[힌트]` 변환, 실행 시간 측정)
- [ ] **예외 처리**: 스택트레이스 출력 금지, "원인 + 해결 힌트" 출력
- [ ] **종료 코드**: 정상 0, 오류 0 아닌 값
- [ ] **타입 힌트**: 모든 함수의 매개변수·반환값에 적용
- [ ] **모듈화**: 3개 이상 모듈, 권장 4계층 (모델 / 저장소 / 서비스 / CLI)
- [ ] **README.md**: 실행 방법, 저장 파일 위치·형식, 주요 명령 예시, CSV 스키마

## 5. 범위 제외

- PDF의 "5. 보너스 과제(선택)" 4개 항목(backup, 반복 내역, 테이블 정렬, 저장 원자성 강화)은 구현하지 않는다.
- 단, update/delete 의 원자적 교체는 본 요구사항(2. 저장 정책)에 권장으로 포함되어 있으므로 유지한다.

## 6. 제안 폴더 구조

```
pocket money/
├── README.md
├── REQUIREMENTS.md
├── data/                      # 실행 시 자동 생성
└── budget_app/
    ├── __init__.py
    ├── __main__.py            # python -m budget_app 진입점
    ├── models.py              # [모델] Transaction dataclass, 검증 함수
    ├── storage.py             # [저장소] 파일 읽기/쓰기, 제너레이터, 원자적 교체
    ├── services.py            # [서비스] 검색 조건, 요약 계산, 예산 사용률
    ├── decorators.py          # [공통] 예외 처리/시간 측정 데코레이터
    └── cli.py                 # [CLI] argparse 명령 정의, 입력/출력
```
