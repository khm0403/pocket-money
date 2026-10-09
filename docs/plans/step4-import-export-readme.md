# 4단계 설계서: import / export + README.md

## 1. 목표

- 옵션 방식 명령 `import --from <csv>`, `export --out <csv> (--month | --from --to)` 를 기존 구조(업무 규칙 `services.py` 의 `LedgerService`, 파서·핸들러 `cli.py` + `@handle_errors`, 파일 입출력 `storage.py`) 위에 추가해 끝까지 동작시킨다.
- CSV 파일과 거래 파일은 모두 한 행(한 줄)씩 스트리밍한다. import 는 "기존 줄 + 새 줄"을 임시 파일에 쓴 뒤 `os.replace` 로 한 번에 바꿔, 도중에 실패하거나 강제 종료돼도 `transactions.jsonl` 이 반쯤 반영된 상태가 생기지 않게 한다. export 결과 파일도 같은 방식으로 쓴다.
- 프로젝트 루트에 `README.md` 를 만든다(PDF 2장 10번 필수 항목 + 문서에 고정하라고 한 결정 사항). 예시 출력은 실제 실행 결과로만 채운다.

## 2. 대상 요구사항

| REQUIREMENTS.md 항목 | 이번 단계 충족 범위 |
| --- | --- |
| 0장 모든 명령에 `--help`, 옵션은 `--` 형식 | `import`, `export` |
| 1장 입력 검증 (날짜 / 금액 / type / 미등록 category) | import 행 검증(잘못된 행은 건너뜀), export `--month/--from/--to` (오류 메시지) |
| 2장 저장 정책 (원자적 교체) | import 는 임시 파일 + `os.replace` 로 거래 파일 전체 교체 (1단계 `_atomic_rewrite` 재사용) |
| 3장 #9 import | 전체 |
| 3장 #10 export | 전체 |
| 3장 import/export CSV 스키마 (고정), "import 중 잘못된 행은 건너뛰고 skipped 로 집계" | 전체 |
| 4장 제너레이터 | CSV 읽기(`iter_csv_records`), 거래 파일 읽기, CSV 쓰기 모두 한 건씩. 전체 로드 없음 |
| 4장 데코레이터, 예외 처리, 종료 코드 | 새 핸들러 2개에 `@handle_errors`. 2단계 규칙(stdout/stderr, 0/1/2) 그대로 |
| 4장 타입 힌트, 모듈화 | 새 함수·클래스 전부. 계층 규칙은 2·3단계와 같음 |
| 4장 README.md | 실행 방법, 저장 파일 위치·형식, 주요 명령 예시, CSV 스키마 (+ 문서에 고정할 결정 사항) |

PDF 근거: 1장("작은 서비스 = 예외 상황에서도 데이터가 안전"), 2장 9번(`import --from <csv>`, `export --out <csv> --month ... 또는 --from/--to`, "처리 건수 출력 + CSV 파일 생성/반영 확인"), 2장 10번(README 필수 항목), 4장 1번(export, import 는 옵션 인자 방식 허용), 4장 3번·6번("문서에 명확히 고정"), 4장 11번("import/export는 아래 CSV **최소** 스키마를 고정", "export는 --month YYYY-MM 또는 --from YYYY-MM-DD --to YYYY-MM-DD 중 하나 이상 조건을 필수로"), CSV 스키마 표("공통: UTF-8, 헤더 포함"), 8장 예시(`[완료] export.csv (12 records)`, `[완료] imported=5, skipped=0`).

## 3. 파일/모듈 설계

### 3.0 공통 결정 (이번 단계에서 고정)

2단계 설계서 3.0 표와 3단계 3.0 표는 모두 그대로 적용한다: 새 파서는 `add_help=False` + `_with_help(...)`(`-h` 는 사용법 오류 2), `allow_abbrev=False`(`--fro`, `--ou`, `--mon` 은 오류 2), `--data-dir` 는 말단 명령(`import`, `export`) 뒤에만(부모 파서 `**leaf`), 옵션 값은 argparse `type` 없이 문자열로 받고 검증은 서비스가 `ValidationError`(종료 코드 1)로 한다, help 문구는 한국어 한 줄이고 `%` 를 쓰지 않는다.

| 항목 | 결정 | 근거 |
| --- | --- | --- |
| 입력 방식 | 두 명령 모두 옵션 방식. 대화형 입력 없음 | ← PDF 4장 1번(export, import 옵션 허용), 3장 #9·#10 |
| 필수 옵션 | `import --from`, `export --out` 은 `required=True`. 없으면 argparse 사용법 오류(2) | ← 3장 #9 `--from <csv>`, #10 `--out <csv>` |
| CSV 파일 입출력 위치 | **저장소 계층(`storage.py`)**. 이유는 3.2 | ← 4장 모듈화, REQUIREMENTS 6장 "storage.py: 파일 읽기/쓰기, 제너레이터, 원자적 교체", PDF 4장 3번 "저장소(파일 I/O)" |
| CSV 공통 형식 | 헤더 `date,type,category,amount,memo,tags`, UTF-8, 헤더 포함, id 컬럼 없음 | ← 3장 CSV 스키마 (고정) |
| import 인코딩 | `encoding="utf-8-sig"` 로 연다. BOM 이 없는 UTF-8 과 BOM 이 붙은 UTF-8 을 모두 읽는다(BOM 도 UTF-8 인코딩의 일부이고, 그대로 두면 첫 헤더가 `﻿date` 가 되어 "필수 컬럼 없음"이라는 엉뚱한 오류가 난다). UTF-8 이 아니면 파일 수준 오류 (총괄 확인 필요 #6) | ← CSV 스키마 "UTF-8" |
| import 헤더 | 첫 행이 헤더. 각 이름은 앞뒤 공백 제거 후 **정확히** 비교(대소문자 구분). 컬럼 순서는 자유. 필수 4개(date, type, category, amount) 중 하나라도 없거나, 스키마 컬럼 이름이 두 번 나오면 파일 수준 오류. memo, tags 컬럼은 없어도 된다(각각 `""`, `[]`) | ← CSV 스키마 required 열 |
| 스키마 밖 컬럼 | **무시**한다(`id` 컬럼 포함. id 는 항상 새로 발급). PDF 가 "**최소** 스키마"라고 했으므로 추가 컬럼이 있는 파일도 받는다 | ← PDF 4장 11번 "CSV 최소 스키마", 3장 "id 컬럼 없음 (import 시 새 id 발급)" |
| import 행 검증 | 행마다 date → `validate_date`, type → `validate_type`, category → 앞뒤 공백 제거 후 등록된 이름과 정확히 같아야 함(대소문자 구분), amount → `parse_amount`(1 이상 정수, `"1,000"`·`"1.5"` 거부), memo → 앞뒤 공백 제거, tags → `parse_tags`(쉼표 구분). 하나라도 틀리면 그 행은 **건너뛰고 skipped 로 센다** | ← 3장 "import 중 잘못된 행은 건너뛰고 skipped 로 집계", 1장 입력 검증 4종, add 와 같은 정리 규칙(2단계 3.0 메모·태그) |
| 행 모양 오류 | 필드 수가 헤더 컬럼 수와 다른 행은 건너뛰고 skipped 로 센다(쉼표가 든 값을 따옴표로 감싸지 않으면 칸이 밀려 다른 값이 저장될 수 있으므로). 완전히 빈 줄은 **무시**하고 세지 않는다(JSONL 빈 줄 처리와 같음) | ← 3장 "잘못된 행은 건너뛰고 skipped" |
| 건너뛴 행 알림 | **개수만 센다.** 출력은 `[완료] imported=N, skipped=M` 한 줄뿐이고 행 번호·이유는 출력하지 않는다(stderr 도 비어 있음) (총괄 확인 필요 #1) | ← PDF 8장 예시 `[완료] imported=5, skipped=0` (다른 출력 없음) |
| skipped 가 있을 때 종료 코드 | 0 (정상 완료). 올바른 행이 0개여도 0 | ← 3장 "건너뛰고 skipped 로 집계"(오류가 아니라 집계) |
| import 파일 수준 오류 | 파일 없음, 헤더 없음(빈 파일·첫 줄이 빈 줄), 필수 컬럼 누락, 스키마 컬럼 중복, UTF-8 아님, CSV 로 읽을 수 없는 줄(필드가 너무 큼 등) → `[오류]/[힌트]`, 종료 코드 1, **아무것도 저장하지 않음** | ← 4장 예외 처리·종료 코드, PDF 1장 데이터 안전 |
| import 데이터 안전 | 기존 거래 줄 + 새 거래 줄을 같은 폴더 임시 파일에 한 줄씩 쓰고 `os.replace` 로 한 번에 교체(1단계 `_atomic_rewrite` 재사용). 3.4 참고 | ← 2장 원자적 교체, PDF 1장 |
| import 중복 | 같은 내용의 거래가 이미 있어도 새 거래로 추가한다(중복 검사 없음) | ← PDF·REQUIREMENTS 에 중복 규칙 없음(추가 기능 금지) |
| import id | 올바른 행에만 CSV 순서대로 `issue_id()` 로 발급(현재 최대 번호 + 1 부터). 건너뛴 행은 번호를 쓰지 않는다 | ← 1장 id 유일, 3장 "import 시 새 id 발급" |
| export 조건 필수 | `--month`, `--from`, `--to` 가 모두 없으면 `ValidationError`(종료 코드 1) | ← 3장 #10 "**필수**", PDF 4장 11번 |
| `--from`/`--to` 한쪽만 | **오류(1).** PDF 가 `--from YYYY-MM-DD --to YYYY-MM-DD` 를 한 묶음의 조건으로 적었기 때문 (총괄 확인 필요 #2) | ← PDF 4장 11번, 2장 9번 "`--month ...` 또는 `--from/--to`" |
| `--month` 와 `--from/--to` 함께 | **허용하고 둘 다 만족(AND)** 하는 거래만. "중 하나 이상" 은 둘 다 주는 것도 허용하는 문구이고, 조건 결합은 search 와 같은 AND (총괄 확인 필요 #2) | ← PDF 4장 11번 "중 하나 이상", 3단계 search 조건 결합 |
| 기간 규칙 | `--from/--to` 는 `validate_date`, **양 끝 포함**. `--from` > `--to` 는 오류가 아니라 0건(3단계 search 와 같음). `--month` 는 `validate_month`, date 가 `"{month}-"` 로 시작하는 거래 | ← 3장 #10, 3단계 3.0 `--from/--to`, summary 대상 거래 |
| export 출력 행 순서 | **거래 파일에 저장된 순서 그대로**(정렬하지 않음). 한 건씩 읽어 바로 쓰므로 메모리가 거래 수와 무관하다 (총괄 확인 필요 #3) | ← 4장 제너레이터(PDF 에 export 순서 규칙 없음) |
| export 행 형식 | `csv.writer(..., lineterminator="\n")`, 기본 따옴표 규칙(쉼표·따옴표·줄바꿈이 든 값만 `"` 로 감쌈, 안의 `"` 는 `""`). 컬럼 순서 고정 `date,type,category,amount,memo,tags`. amount 는 정수 문자열, tags 는 `",".join(tags)`(태그 여러 개면 `"meal,friend"` 처럼 따옴표로 감싸짐). 인코딩 `utf-8`(BOM 없음). 줄 끝 `\n`(저장 파일 JSONL 과 같음) | ← CSV 스키마 "UTF-8, 헤더 포함", "tags 쉼표(,) 구분 문자열" |
| 왕복 | export 결과 파일은 그대로 import 할 수 있다. export → import(빈 폴더, 같은 카테고리) → 같은 조건으로 export 하면 두 CSV 가 **바이트 단위로 같다** | ← 3장 스키마를 import/export 가 공유 |
| `--out` 이 이미 있음 | **오류(1), 덮어쓰지 않음**(파일·폴더 모두). 삭제 확인 질문·`--force` 같은 옵션은 추가 금지이므로, 가장 데이터에 안전한 쪽(오타로 `--out data/transactions.jsonl` 을 줘도 거래 파일이 지워지지 않음)을 택한다 (총괄 확인 필요 #4) | ← PDF 1장 데이터 안전, 추가 기능 금지 규칙 |
| `--out` 의 폴더가 없음 | **오류(1)**, 폴더를 자동으로 만들지 않는다(`--data-dir` 의 자동 생성은 저장 파일 3개에 대한 요구사항이고, 출력 경로 오타로 폴더가 생기지 않게) (총괄 확인 필요 #4) | ← 2장 자동 생성은 data 폴더에 한정 |
| export 쓰기 안전 | 같은 폴더 임시 파일에 끝까지 쓴 뒤 `os.replace`. 도중 실패(Ctrl+C, 거래 파일 손상 줄, 쓰기 오류) 시 임시 파일을 지우고 `--out` 파일은 생기지 않는다 | ← PDF 1장, 2장 원자적 교체 방식 재사용 |
| export 0건 | 헤더 한 줄만 있는 파일을 만들고 `[완료] <경로> (0 records)`, 종료 코드 0. 0건 파일도 import 가능한 올바른 CSV 이고 출력 형식이 한 가지로 유지된다 (총괄 확인 필요 #3) | ← PDF 8장 출력 형식 |
| 출력 문구 | import: `[완료] imported={N}, skipped={M}`. export: `[완료] {경로} ({N} records)` — 경로는 사용자가 준 `--out` 값(앞뒤 공백 제거)을 그대로, 1건이어도 `records` | ← PDF 8장 예시 그대로 |
| `--from`/`--out` 빈 값 | `"   "`, `""` 는 `ValidationError`(`--from 값이 비어 있습니다`, `--out 값이 비어 있습니다`), 종료 코드 1. 경로는 앞뒤 공백을 제거해 쓴다(3단계 `_required_text` 재사용) | ← 4장 예외 처리 |
| 명령 등록 순서 | 최상위 `add, list, search, summary, budget, update, delete, category, import, export`, `metavar="{add,list,search,summary,budget,update,delete,category,import,export}"` | ← PDF 2장 기능 순서(9번 import/export) |

### 3.1 변경하지 않는 파일

`models.py`, `__main__.py`, `__init__.py` 는 **수정하지 않는다**(6.2 S0 에서 SHA-256 확인). 필요한 재료는 이미 있다: `Transaction`, `ValidationError`, `BudgetAppError`, `validate_date`, `validate_month`, `validate_type`, `parse_amount`, `tx_id_seq`.

변경 파일: `storage.py`(CSV 입출력 + `_atomic_write` 추출 + `append_many`), `services.py`, `cli.py`, `decorators.py`(문구 1개). 새 파일: `README.md`(프로젝트 루트).

### 3.2 CSV 파일 입출력을 저장소 계층에 두는 이유

- CSV 를 여는 것, 헤더를 읽는 것, 한 행씩 넘기는 것, 임시 파일에 써서 `os.replace` 로 바꾸는 것은 모두 **파일 형식과 파일 입출력**이다. 계층 표(REQUIREMENTS 6장, PDF 4장 3번 "저장소(파일 I/O)")에서 이것은 저장소 책임이다. JSONL 의 줄 읽기(`_iter_lines`)와 원자적 교체(`_atomic_rewrite`)도 이미 `storage.py` 에 있어 재사용할 수 있다.
- 행 **값**의 검증(날짜·금액·type·등록된 카테고리)은 업무 규칙이므로 **서비스**가 한다. 저장소는 행을 `{컬럼: 문자열}` 로만 넘기고 값의 의미는 판단하지 않는다(1단계 4장 책임 분담과 같음: 저장소는 파일 형식 무결성, 업무 규칙은 서비스).
- export 방향은 이미 검증된 `Transaction` 을 CSV 한 행으로 바꾸는 직렬화이므로 저장소가 한다(JSONL 직렬화 `to_json_line` 을 저장소가 쓰는 것과 같은 위치).
- 그래서 `csv` 모듈과 `open(` 은 `storage.py` 에만 있다(6.2 S9 에서 확인). CLI 는 여전히 `storage` 를 import 하지 않는다.

### 3.3 `budget_app/storage.py` — [저장소] (추가·변경)

import 추가: `csv`, `collections.abc` 에서 `Callable`, `typing` 에서 `TextIO`. (`budget_app.models` 에서 새로 가져올 것은 없다.) `print`/`input` 은 쓰지 않는다.

#### 모듈 상수

| 시그니처 | 책임 | 근거 |
| --- | --- | --- |
| `CSV_COLUMNS: tuple[str, ...] = ("date", "type", "category", "amount", "memo", "tags")` | CSV 스키마 컬럼과 export 헤더 순서 | ← 3장 CSV 스키마 |
| `CSV_REQUIRED_COLUMNS: tuple[str, ...] = ("date", "type", "category", "amount")` | import 헤더 필수 컬럼 | ← 3장 CSV 스키마 required |
| `_CSV_HEADER_HINT: str = "첫 줄에 헤더 date,type,category,amount,memo,tags 를 넣으세요 (memo, tags 는 생략 가능)"` | 헤더 오류 공통 힌트 | ← 4장 예외 처리 |

#### 원자적 쓰기 (변경: 공통 부분 추출)

| 시그니처 | 책임 | 근거 |
| --- | --- | --- |
| `def _atomic_write(path: Path, write: Callable[[TextIO], int], newline: str \| None = None) -> int` | **기존 `_atomic_rewrite` 본문을 그대로 옮긴 것.** `tempfile.mkstemp(dir=path.parent, prefix=path.name + ".", suffix=".tmp")` → `os.fdopen(fd, "w", encoding="utf-8", newline=newline)` 안에서 `count = write(f)` → 파일을 닫은 **뒤** `os.replace(tmp, path)`. `except BaseException:` 에서 임시 파일을 `os.unlink`(없으면 무시)하고 다시 던진다. `count` 반환. `os.replace` 와 `mkstemp` 는 저장소 전체에서 **여기 한 곳에만** 있다 | ← 2장 원자적 교체, PDF 1장 |
| `def _atomic_rewrite(path: Path, lines: Iterable[str]) -> None` (변경) | 동작은 1단계와 **완전히 같다.** 내부 `def _write(f: TextIO) -> int:` 가 `lines` 의 각 항목 뒤에 `"\n"` 을 붙여 쓰고 줄 수를 돌려주며, `_atomic_write(path, _write)` 를 호출한다(`newline=None` = 1단계와 같은 기본값) | ← 2장 원자적 교체 (update/delete/budget set/카테고리 기본값 쓰기가 계속 사용) |

- 기존 주석(왜 같은 폴더에 임시 파일을 만드는지, `os.replace` 가 "옛 파일 아니면 새 파일"만 보이게 하는 이유)은 `_atomic_write` 로 옮긴다.
- 1단계 검증 스크립트는 `os.replace` 를 전역으로 감시하므로 `os.replace(...)` 형태로 호출해야 한다(`from os import replace` 금지).

#### CSV 읽기 (import)

| 시그니처 | 책임 | 근거 |
| --- | --- | --- |
| `def _csv_header_index(path: Path, header: list[str]) -> dict[str, int]` | `names = [h.strip() for h in header]`. `names` 가 비었거나 모두 빈 문자열이면 `BudgetAppError(cause=f"CSV 파일에 헤더가 없습니다: {path}", hint=_CSV_HEADER_HINT)`. `CSV_COLUMNS` 중 두 번 이상 나온 이름이 있으면 `BudgetAppError(cause=f"CSV 헤더에 같은 컬럼이 여러 번 있습니다: {', '.join(중복)}", hint="컬럼 이름이 한 번씩만 나오도록 헤더를 고치세요")`. `CSV_REQUIRED_COLUMNS` 중 없는 것이 있으면 `BudgetAppError(cause=f"CSV 헤더에 필수 컬럼이 없습니다: {', '.join(누락)}", hint=_CSV_HEADER_HINT)`. 통과하면 `{컬럼: 위치}` (스키마 컬럼 중 헤더에 있는 것만) 반환. 스키마 밖 이름은 무시 | ← 3장 CSV 스키마, PDF "최소 스키마" |
| `def iter_csv_records(path: str \| os.PathLike[str]) -> Iterator[dict[str, str] \| None]` | **제너레이터.** 아래 "iter_csv_records 처리 순서" | ← 3장 #9, 4장 제너레이터 |
| `def check_csv_header(path: str \| os.PathLike[str]) -> None` | `for _ in iter_csv_records(path): break` — 제너레이터를 한 번만 움직여 파일 열기와 헤더 검사(와 첫 행 읽기)만 먼저 끝낸다. 파일 수준 오류는 **임시 파일을 만들기 전에** 여기서 난다(1단계 `CategoryStore.__init__` 의 `for ... break` 와 같은 관용구) | ← 3장 #9, PDF 1장 데이터 안전 |

**iter_csv_records 처리 순서**

1. `p = Path(path)`. `open(p, encoding="utf-8-sig", newline="")` 를 `try` 로 연다. `FileNotFoundError` 면 `BudgetAppError(cause=f"가져올 CSV 파일이 없습니다: {p}", hint="--from 에 있는 CSV 파일 경로를 입력하세요") from None`. 그 밖의 `OSError`(폴더, 권한 없음)는 잡지 않는다(데코레이터가 경로와 원인을 출력, 3.7).
2. `with f:` 안에서 `reader = csv.reader(f)`. 다음을 `try` 로 감싼다:
   - `header = next(reader, [])`, `index = _csv_header_index(p, header)`, `width = len(header)`.
   - `for row in reader:` — `row` 가 빈 리스트(빈 줄)면 `continue`(세지 않음). `len(row) != width` 면 `yield None`(행 모양 오류, 서비스가 skipped 로 셈) 후 `continue`. 아니면 `yield {c: (row[index[c]] if c in index else "") for c in CSV_COLUMNS}` (6개 키가 항상 있음, 값은 원문 그대로).
3. `except UnicodeDecodeError:` → `BudgetAppError(cause=f"CSV 파일을 UTF-8 로 읽을 수 없습니다: {p}", hint="CSV 파일을 UTF-8 인코딩으로 저장한 뒤 다시 가져오세요") from None`.
4. `except csv.Error as e:` → `BudgetAppError(cause=f"{p} 파일 {reader.line_num}번째 줄을 CSV 로 읽을 수 없습니다 ({e})", hint="해당 줄의 따옴표(\")와 쉼표를 확인하세요") from None`. (예: 한 칸이 131072자를 넘는 줄)

- `list(reader)`, `readlines()`, `read()` 는 쓰지 않는다. 메모리에는 지금 처리 중인 한 행만 있다.
- UTF-8 오류와 CSV 오류는 파일 **중간**에서도 날 수 있다(텍스트 파일은 8KB 단위로 디코딩된다). 그때는 import 가 이미 임시 파일에 쓰는 중이므로 3.4 의 원자적 교체가 원본을 지킨다.

#### CSV 쓰기 (export)

| 시그니처 | 책임 | 근거 |
| --- | --- | --- |
| `def write_transactions_csv(path: str \| os.PathLike[str], txs: Iterable[Transaction]) -> int` | 아래 순서. 쓴 거래 수(헤더 제외) 반환 | ← 3장 #10, 2장 원자적 교체 방식, 4장 제너레이터 |

1. `p = Path(path)`. `p.exists()` 면 `BudgetAppError(cause=f"이미 있는 경로입니다: {p}", hint="덮어쓰지 않습니다. 다른 --out 경로를 지정하거나 기존 파일을 옮긴 뒤 다시 실행하세요")`.
2. `not p.parent.is_dir()` 면 `BudgetAppError(cause=f"출력 폴더가 없습니다: {p.parent}", hint="이미 있는 폴더 안의 경로를 --out 에 지정하세요 (폴더는 자동으로 만들지 않습니다)")`.
3. 내부 `def _write(f: TextIO) -> int:` — `writer = csv.writer(f, lineterminator="\n")`, `writer.writerow(CSV_COLUMNS)`, `for tx in txs:` 마다 `writer.writerow([tx.date, tx.type, tx.category, str(tx.amount), tx.memo, ",".join(tx.tags)])` 하고 센다. 센 값 반환.
4. `return _atomic_write(p, _write, newline="")` (`csv` 모듈 규칙상 `newline=""` 로 연다).

- `txs` 는 서비스의 제너레이터다. `for tx in txs` 로 한 건씩 받아 바로 쓰므로 거래를 모으지 않는다.
- 1·2의 검사는 거래 파일을 읽기 전에 끝난다(제너레이터는 3에서 처음 움직임).
- `mkstemp` 로 만든 파일이라 결과 파일 권한은 `0600`(본인만 읽기·쓰기)이다. 1단계부터 update/delete 후 거래 파일도 같다. 권한 조정은 하지 않는다.

#### `class TransactionRepository` (추가 메서드)

| 시그니처 | 책임 | 근거 |
| --- | --- | --- |
| `def append_many(self, txs: Iterable[Transaction]) -> None` | 내부 제너레이터 `def _lines() -> Iterator[str]:` 가 ① `for lineno, line in _iter_lines(self.path):` 에서 `self._parse_line(lineno, line)` 로 기존 줄을 검사한 뒤(손상 줄이면 `BudgetAppError` → 원본 보존) 원문 `line` 을 그대로 내보내고, ② `for tx in txs:` 에서 `tx.to_json_line()` 을 내보낸다. 이것을 `_atomic_rewrite(self.path, _lines())` 에 넘긴다 | ← 3장 #9, 2장 원자적 교체, PDF 1장 |

- `txs` 가 0건이어도 파일은 같은 내용으로 다시 쓰인다(내용은 바이트 단위로 같고, update/delete 와 같이 빈 줄만 사라짐). 올바른 행이 있는지는 CSV 를 끝까지 읽어야 알 수 있기 때문이다.
- `issue_id()` 는 서비스가 `txs` 를 만들 때 부른다. 첫 호출은 기존 파일을 한 번 훑는데, 이 시점에는 아직 `os.replace` 전이라 원본을 읽는다(1단계 설계대로 이후 호출은 파일을 다시 읽지 않음).

### 3.4 데이터 안전 설계 (import / export)

**import 흐름**

```
check_csv_header(path)                  # ① 파일 없음·헤더 문제·UTF-8 아님(앞부분) → 오류, 임시 파일도 만들지 않음
categories = set(list_names())          # ② 카테고리 목록은 한 번만 읽는다 (행마다 파일을 다시 읽지 않음)
append_many(_iter_imported(...))        # ③ 아래
  _atomic_rewrite(transactions.jsonl, _lines())
    mkstemp → transactions.jsonl.XXXX.tmp (같은 폴더)
    기존 줄을 한 줄씩 검사하며 그대로 복사
    CSV 를 한 행씩: 검증 → 통과하면 새 id 발급 → JSON 한 줄 쓰기 / 실패하면 skipped += 1
    파일 닫기 → os.replace(tmp, transactions.jsonl)   # 여기서 한 번에 "옛 파일 → 새 파일"
  (① 이후 어디서든 예외·Ctrl+C → tmp 삭제, 원본 그대로, 종료 코드 1)
```

| 실패 상황 | 결과 |
| --- | --- |
| 헤더 문제·파일 없음 | ①에서 오류. 임시 파일 생성 전 |
| 파일 중간의 UTF-8 오류·CSV 형식 오류 | ③ 도중 `BudgetAppError` → `_atomic_write` 가 임시 파일 삭제 → 원본 그대로, 종료 코드 1. 오류 앞의 올바른 행도 저장되지 않는다 |
| 기존 거래 파일에 손상 줄 | ③에서 `_parse_line` 이 `BudgetAppError` → 같음 |
| Ctrl+C (SIGINT) | `KeyboardInterrupt` 도 `except BaseException` 에서 임시 파일 삭제 후 다시 던짐 → 데코레이터가 `[오류] 사용자가 입력을 중단했습니다 (Ctrl+C)` + `[힌트] 저장되지 않았습니다…`, 종료 코드 1 |
| 쓰기 오류(디스크 가득 참 등, `os.replace` 실패 포함) | 임시 파일 삭제, 원본 그대로, 데코레이터의 `OSError` 메시지, 종료 코드 1 |
| 강제 종료(SIGKILL, 전원 차단) | 정리 코드가 돌 기회가 없어 `transactions.jsonl.XXXX.tmp` 가 남을 수 있지만 **`transactions.jsonl` 은 옛 내용 그대로**(교체 전) 또는 새 내용 전체(교체 후) 중 하나다. 앱은 고정된 파일 이름만 읽으므로 남은 임시 파일은 동작에 영향이 없다. `os.fsync` 는 하지 않는다(보너스 "저장 원자성 강화"는 범위 밖, 1단계와 같음) |

**검토한 다른 방법 (채택하지 않음)**

| 방법 | 채택하지 않은 이유 |
| --- | --- |
| 거래 파일 끝에 `open(..., "a")` 로 한 줄씩 추가 | 중간에 멈추면 일부 행만 반영된 상태가 남는다(PDF 1장 위반) |
| 추가 모드로 쓰고 실패 시 원래 크기로 `truncate` | Ctrl+C·쓰기 오류는 되돌릴 수 있지만 강제 종료·전원 차단 때는 되돌리는 코드가 실행되지 않는다 |
| CSV 전체를 먼저 검증해 메모리에 모은 뒤 한 번에 추가 | 행 수에 비례해 메모리가 늘어난다(4장 제너레이터 위반) |
| **채택: 기존 줄 + 새 줄을 임시 파일에 쓰고 `os.replace`** | 어떤 시점에 멈춰도 원본은 교체 전까지 손대지 않는다. 메모리는 한 행 분량. 대가: import 할 때마다 거래 파일 전체를 다시 쓴다(시간 O(기존 거래 수 + CSV 행 수)). update/delete 와 같은 방식이라 설명할 것이 하나다 |

**export 흐름**: 조건 검증 → `--out` 존재·폴더 검사 → `_atomic_write(out, ...)` 가 같은 폴더 임시 파일에 헤더와 행을 한 건씩 쓰고 `os.replace`. 도중 실패(거래 파일 손상 줄, Ctrl+C, 쓰기 오류) 시 임시 파일을 지우므로 `--out` 파일은 생기지 않는다. 거래 파일은 읽기만 한다.

### 3.5 `budget_app/services.py` — [서비스] (추가)

import 추가: storage 에서 `check_csv_header`, `iter_csv_records`, `write_transactions_csv`. (`dataclasses`, `Iterator`, `Any`, `ValidationError`, 검증 함수들은 이미 import 되어 있다.) `print`/`input`/`open`/`csv` 는 쓰지 않는다.

#### `@dataclasses.dataclass class ImportResult`

import 결과 개수. `_iter_imported` 가 한 행씩 처리하며 값을 올리므로 **frozen 이 아니다**. ← 3장 #9 `imported=N, skipped=M`

```python
imported: int = 0
skipped: int = 0
```

#### 모듈 함수

| 시그니처 | 책임 | 근거 |
| --- | --- | --- |
| `def _import_fields(record: dict[str, str], categories: set[str]) -> dict[str, Any]` | CSV 한 행을 검증·정리해 `Transaction` 생성 인자(`id` 제외)로 바꾼다. `category = record["category"].strip()` 가 `categories` 에 없으면 `ValidationError(cause=f"등록되지 않은 카테고리입니다: {category!r}", hint="category add 로 먼저 추가하세요")`. 반환: `{"date": validate_date(record["date"]), "type": validate_type(record["type"]), "category": category, "amount": parse_amount(record["amount"]), "memo": record["memo"].strip(), "tags": parse_tags(record["tags"])}`. 틀린 값은 해당 `ValidationError` 가 그대로 나간다 | ← 3장 #9, 1장 입력 검증 4종, 3장 CSV 스키마 |

#### `class LedgerService` (추가 메서드)

| 시그니처 | 책임 | 근거 |
| --- | --- | --- |
| `def import_csv(self, src: str) -> ImportResult` | ① `path = _required_text(src, "--from", "가져올 CSV 파일 경로를 입력하세요 (예: --from import.csv)")` ② `check_csv_header(path)` ③ `categories = set(self.categories.list_names())` ④ `result = ImportResult()` ⑤ `self.transactions.append_many(self._iter_imported(path, categories, result))` ⑥ `result` 반환. ⑤가 예외 없이 끝났을 때(= `os.replace` 완료)만 결과가 나간다 | ← 3장 #9, 3.4 |
| `def _iter_imported(self, path: str, categories: set[str], result: ImportResult) -> Iterator[Transaction]` | **제너레이터.** `for record in iter_csv_records(path):` — `record is None` 이면 `result.skipped += 1`; `_import_fields` 가 `ValidationError` 면 `result.skipped += 1`; 통과하면 `tx = Transaction(id=self.transactions.issue_id(), **fields)`, `result.imported += 1`, `yield tx`. 거래를 모으지 않는다. `ValidationError` 만 잡는다(`BudgetAppError` 파일 오류, `KeyboardInterrupt` 는 그대로 올라가 import 전체를 취소) | ← 3장 "건너뛰고 skipped 로 집계", 4장 제너레이터 |
| `def export_csv(self, out: str, *, month: str \| None, date_from: str \| None, date_to: str \| None) -> tuple[str, int]` | 아래 "export 처리 순서" | ← 3장 #10 |
| `def _iter_export(self, month: str \| None, flt: SearchFilter) -> Iterator[Transaction]` | **제너레이터.** `prefix = None if month is None else month + "-"`; `for tx in self.transactions.iter_transactions():` 에서 (`prefix` 가 있으면 `tx.date.startswith(prefix)`) 이고 `flt.matches(tx)` 인 것만 `yield`. 파일 순서 그대로, 모으지 않는다 | ← 3장 #10, 4장 제너레이터, 3단계 `SearchFilter` 재사용 |

**export 처리 순서** ← 3장 #10

1. `month`, `date_from`, `date_to` 가 모두 `None` 이면 `ValidationError(cause="내보낼 조건이 없습니다", hint="--month YYYY-MM 또는 --from YYYY-MM-DD --to YYYY-MM-DD 를 지정하세요")`.
2. `date_from` 과 `date_to` 중 하나만 `None` 이면 `ValidationError(cause="--from 과 --to 는 함께 지정해야 합니다", hint="기간은 --from YYYY-MM-DD --to YYYY-MM-DD 로, 한 달 전체는 --month YYYY-MM 으로 지정하세요")`.
3. `m = None if month is None else validate_month(month)`, `flt = SearchFilter(date_from=…validate_date…, date_to=…validate_date…)`.
4. `path = _required_text(out, "--out", "저장할 CSV 파일 경로를 입력하세요 (예: --out export.csv)")`.
5. `count = write_transactions_csv(path, self._iter_export(m, flt))` → `(path, count)` 반환.

1~4 는 거래 파일을 읽거나 `--out` 을 만들기 전에 끝난다. `sorted`/`list`/`.sort` 는 쓰지 않는다(3단계 S8: `sorted` 는 search 의 1회만).

### 3.6 `budget_app/cli.py` — [CLI] (추가·변경)

import 추가: 없음(`LedgerService` 로 충분). **`storage` 와 `csv` 는 import 하지 않는다.**

| 시그니처 | 책임 | 근거 |
| --- | --- | --- |
| `@handle_errors def _cmd_import(args: argparse.Namespace) -> int` | `service = LedgerService(args.data_dir)` → `result = service.import_csv(args.csv_path)` → `print(f"[완료] imported={result.imported}, skipped={result.skipped}")` → `EXIT_OK` | ← 3장 #9, PDF 8장 |
| `@handle_errors def _cmd_export(args: argparse.Namespace) -> int` | `path, count = service.export_csv(args.out, month=args.month, date_from=args.date_from, date_to=args.date_to)` → `print(f"[완료] {path} ({count} records)")` → `EXIT_OK` | ← 3장 #10, PDF 8장 |

- `LedgerService(...)` 는 반드시 데코레이터가 적용된 핸들러 안에서 만든다(2·3단계와 같음).

#### 명령 구성 (추가분)

```
python -m budget_app {add,list,search,summary,budget,update,delete,category,import,export} ...
  import --from CSV [--data-dir DATA_DIR]                                   CSV 파일의 거래를 한 번에 추가 (잘못된 행은 건너뜀)
  export --out CSV [--month YYYY-MM] [--from YYYY-MM-DD] [--to YYYY-MM-DD] [--data-dir DATA_DIR]
                                                                            조건에 맞는 거래를 CSV 파일로 저장
```

| 파서 | 인자 (모두 문자열, 값 검증은 서비스) |
| --- | --- |
| 최상위 `sub` | `metavar="{add,list,search,summary,budget,update,delete,category,import,export}"` 로 변경 |
| `import` (`**leaf`) | `add_argument("--from", dest="csv_path", required=True, metavar="CSV", help="가져올 CSV 파일 경로 (UTF-8, 헤더 포함)")`. 다른 옵션 없음 |
| `export` (`**leaf`) | `add_argument("--out", required=True, metavar="CSV", help="저장할 CSV 파일 경로 (이미 있으면 오류)")`, `add_argument("--month", default=None, metavar="YYYY-MM", help="내보낼 월")`, `add_argument("--from", dest="date_from", default=None, metavar="YYYY-MM-DD", help="시작 날짜 (이 날짜 포함, --to 와 함께)")`, `add_argument("--to", dest="date_to", default=None, metavar="YYYY-MM-DD", help="끝 날짜 (이 날짜 포함, --from 과 함께)")`. 다른 옵션 없음 |

- 각 말단 파서에 `set_defaults(handler=_cmd_import | _cmd_export)`. `import` 의 `dest` 를 `csv_path` 로 둔 이유: `from` 은 파이썬 예약어라 `args.from` 으로 쓸 수 없다.
- 등록 위치는 `category` 파서 다음(명령 등록 순서).

### 3.7 `budget_app/decorators.py` (문구 1개만 변경)

`OSError` 분기의 hint 를 `"--data-dir 경로가 올바른지, 해당 파일·폴더에 읽기/쓰기 권한이 있는지 확인하세요"` → `"경로(--data-dir, --from, --out)가 올바른지, 해당 파일·폴더에 읽기/쓰기 권한이 있는지 확인하세요"` 로 바꾼다. 이제 `--from` 에 폴더를 주거나 `--out` 폴더에 쓰기 권한이 없을 때도 같은 분기로 오므로, 힌트가 `--data-dir` 만 가리키면 잘못된 해결 방법을 안내하게 된다. cause 는 그대로(`e.filename` 과 `e.strerror` 로 실제 경로가 나옴). 다른 코드는 바꾸지 않는다. ← 4장 예외 처리 "원인 + 해결 힌트"

### 3.8 `README.md` — 목차와 절별 내용

**원칙**: 구현된 동작만 적는다(보너스 과제·없는 옵션·계획 금지). 모든 옵션 이름은 실제 `--help` 에 있는 것만 쓴다(6.2 N 에서 검사, 예외는 `python3 --version` 의 `--version` 하나). **예시 출력은 에이전트 2가 아래 형식 규칙대로 실제 실행 결과를 붙여 넣어 채운다**(손으로 쓰지 않는다). 문장은 비전공자가 읽을 수 있게 짧게 쓴다.

**형식 규칙 (6.2 N 이 README 를 그대로 다시 실행해 비교한다)**

1. ` ```console ` 블록은 **실제 실행 기록**이다. README 전체의 console 블록을 문서 순서대로, 빈 작업 폴더 하나(기본 `./data` 사용, `--data-dir` 없이)에서 이어서 실행했을 때 화면과 글자 하나까지 같아야 한다. console 블록에는 `$ python -m budget_app ...` 줄과 `$ cat <파일>` 줄만 쓴다. 명령 줄 다음 줄부터 다음 `$ ` 줄 전까지가 그 명령의 화면(stdout 과 stderr 가 터미널에 보이는 순서대로)이다.
2. 대화형 입력은 터미널처럼 프롬프트 뒤에 입력값을 같은 줄에 적는다(예: `날짜(YYYY-MM-DD): 2024-01-15`). 빈 입력은 프롬프트만 적는다.
3. 명령만 보여 주는 안내(설치·실행 방법, `--data-dir` 예)는 ` ```bash ` 블록에 쓰고 출력은 적지 않는다(재생하지 않음).
4. 가져오기용 예시 CSV 는 정보 문자열에 파일 이름을 붙인 ` ```csv import.csv ` 블록으로 쓴다. 재생 전에 이 내용이 작업 폴더의 `import.csv` 로 만들어진다.

**목차와 각 절의 내용** (절 제목은 아래 글자 그대로. 6.2 N 이 확인한다)

| 절 (제목 그대로) | 들어갈 내용 | 근거 |
| --- | --- | --- |
| `# 용돈 기입장 (budget_app)` | 한두 줄 소개: 콘솔 가계부, 파일(JSONL)에 영구 저장, Python 3.10 이상, 표준 라이브러리만 사용 | ← 0장 |
| `## 실행 방법` | Python 3.10 이상 필요, 설치할 패키지 없음. 프로젝트 루트(README.md 가 있는 폴더)에서 `python -m budget_app <command> [options]`. **`python` 명령이 없는 환경(예: 이 Mac)에서는 `python3 -m budget_app ...`**. 도움말 `python -m budget_app --help`, 명령별 `python -m budget_app search --help`, `python -m budget_app category add --help`. 옵션은 `--` 로 시작하는 전체 이름만(`-h`·줄임말 `--lim` 은 사용법 오류). `--data-dir <경로>` 는 **명령 뒤**에 쓴다(예: `python -m budget_app list --data-dir ./mydata`, 명령 앞에 쓰면 사용법 오류). bash 블록 사용 | ← 0장, 2장 `--data-dir`, 4장 README "실행 방법" |
| `## 저장 파일 위치와 형식` | 기본 폴더 `./data`(명령을 실행한 현재 폴더 기준), `--data-dir` 로 변경. 처음 실행하면 폴더와 파일 3개를 자동 생성(`--help`, 사용법 오류 때는 만들지 않음). 표: `data/transactions.jsonl`(거래), `data/categories.jsonl`(카테고리), `data/budgets.jsonl`(월 예산) — 각 파일의 **실제 한 줄 예**(에이전트 2가 실제 파일에서 복사). 형식: JSONL(한 줄에 JSON 객체 하나), UTF-8. 거래 id 는 `TX-000001` 형식, 새 id 는 현재 가장 큰 번호 + 1. **카테고리 파일이 비었을 때(안 A)**: 기본 카테고리 `food, transport, rent, etc` 를 자동으로 만든다(카테고리를 모두 지워 파일이 비면 다음 실행 때 다시 생긴다). 안전: update, delete, budget set, import 는 임시 파일에 전체를 쓴 뒤 `os.replace` 로 한 번에 바꾸므로 도중에 멈춰도 원래 파일이 남는다(export 결과 파일도 같은 방식). 손상된 줄이 있으면 파일 경로·줄 번호와 함께 오류로 알린다 | ← 2장 전체, 4장 README "저장 파일 위치/형식", PDF 4장 3번 "동작을 명확히" |
| `## 명령 요약` | 표: 명령 / 입력 방식 / 옵션 / 하는 일. `add`(대화형), `list`(`--limit N`, 기본 20), `search`(`--from --to --category --type --q --tag`, 1개 이상), `summary`(`--month` 필수, `--top N` 기본 3), `budget set`(`--month --amount`), `category add`·`category remove`(대화형, 이름 입력), `category list`, `update`(**옵션 방식(안 A)**: `--id` 필수 + `--date --type --category --amount --memo --tags` 중 1개 이상), `delete`(`--id`), `import`(`--from CSV`), `export`(`--out CSV` + `--month` 또는 `--from/--to`). 모든 명령에 `--help`, `--data-dir` | ← 3장 표, 4장 README "주요 명령" |
| `## 주요 명령 예시` | console 블록. **아래 "예시 시나리오" 순서 그대로** | ← 4장 README "주요 명령 예시", PDF 8장 |
| `## import/export CSV 스키마` | ① CSV 스키마 표(REQUIREMENTS 3장 표와 같은 6행: `\| date \| Y \| YYYY-MM-DD \|` …) + 공통: UTF-8, 헤더 포함, id 컬럼 없음(import 때 새 id). 헤더 줄 `date,type,category,amount,memo,tags`. ② import 규칙: 컬럼 순서 자유, 스키마 밖 컬럼(id 포함) 무시, memo·tags 컬럼 생략 가능, UTF-8 BOM 허용, 값 앞뒤 공백 제거, tags 는 쉼표 구분(여러 개면 `"meal,friend"` 처럼 따옴표로 감쌈). 건너뛰는 행(skipped): 날짜·type·amount 가 틀린 행, 등록되지 않은 category(대소문자 구분), 필수 값이 빈 행, 칸 수가 헤더와 다른 행. 빈 줄은 무시(세지 않음). 건너뛴 행의 위치는 따로 출력하지 않음(개수만). 파일 오류(파일 없음, 헤더 없음·필수 컬럼 누락·컬럼 중복, UTF-8 아님, CSV 형식이 깨진 줄)는 오류로 끝나고 아무것도 저장하지 않음. 도중에 실패하거나 Ctrl+C 로 멈춰도 거래 파일은 그대로. 같은 내용의 거래가 있어도 새로 추가(중복 검사 없음). ③ export 규칙: `--month` 또는 `--from`+`--to` 중 하나 이상 필수, `--from`/`--to` 는 함께, 둘 다 주면 둘 다 만족하는 거래, 날짜는 양 끝 포함, 행 순서는 저장된 순서(추가한 순서), 컬럼 순서 고정, UTF-8(BOM 없음), `--out` 이 이미 있으면 오류(덮어쓰지 않음), 폴더가 없으면 오류, 0건이면 헤더만 있는 파일과 `(0 records)`. export 한 파일은 그대로 import 할 수 있다. ④ 예시 파일: ` ```csv import.csv ` 블록(아래 내용 그대로) | ← 3장 CSV 스키마, 4장 README "import/export CSV 스키마", PDF 4장 11번 |
| `## 동작 규칙` | 간결한 목록: **update 는 옵션 방식(안 A)으로 고정** — 준 항목만 바뀜, 1개 이상 필요, `--memo ""`/`--tags ""` 는 비우기, 없는 id 는 "없는 데이터" 오류. delete 도 없는 id 는 오류. **카테고리**: 빈 파일이면 기본 4개(안 A), 이름 규칙(빈 이름 거부 후 다시 입력, 앞뒤 공백 제거, 이미 있는 이름 거부 후 다시 입력, 대소문자 구분 `Food` ≠ `food`), **사용 중인 카테고리는 삭제할 수 없음**(거래를 update/delete 한 뒤 삭제), 거래에는 등록된 카테고리만. 입력 검증: 날짜 `YYYY-MM-DD` 실제 날짜, 금액 1 이상 정수(쉼표 불가), type `income`/`expense`. add 는 틀린 항목만 다시 묻고, 옵션 명령은 오류로 끝남. 태그는 쉼표 구분. **최신순** = 날짜 내림차순, 같은 날짜면 id 번호가 큰 것 먼저(list 기본 20건). **search**: 조건 1개 이상 필수(없으면 오류), 모든 조건을 만족(AND), `--from`/`--to` 는 그 날짜 포함·하나만 줘도 됨·`--from` 이 `--to` 보다 늦으면 결과 없음, `--category` 는 등록된 이름만(없으면 오류), `--q` 메모 부분 일치(대소문자 구분), `--tag` 태그 하나와 정확히 일치. **summary**: `--top` 기본 3, 거래가 없는 달은 `YYYY-MM 데이터 없음`, 예산이 있으면 사용률(소수 첫째 자리 반올림), 지출이 예산보다 크면 `[경고] 예산을 초과했습니다`, TOP 금액이 같으면 이름순. **budget set**: 같은 월은 덮어씀 | ← PDF 4장 3번·6번 "문서에 명확히 고정", REQUIREMENTS 2장·3장 [결정] |
| `## 오류와 종료 코드` | 오류는 `[오류] 원인` + `[힌트] 해결 방법` 두 줄을 표준 오류(stderr)로 출력, 스택트레이스 없음. 종료 코드 표: `0` 정상(결과 없음, import skipped 가 있어도 0), `1` 실행 오류(입력값 오류, 없는 id, 사용 중 카테고리 삭제, 파일 문제, Ctrl+C, 입력 끝(EOF)), `2` 사용법 오류(없는 명령·옵션, 필수 옵션 누락, `-h`, 옵션 줄임말, `--data-dir` 를 명령 앞에 둠). `[경고]` 줄은 stdout 이고 종료 코드 0 | ← 4장 예외 처리·종료 코드, 2단계 3.0 |

**예시 시나리오 (`## 주요 명령 예시`, 이 순서로 실행해 출력 붙여 넣기)** ← PDF 8장 화면 예시를 재현(summary 숫자가 PDF 와 같게 나오도록 구성)

| # | 명령 (console 블록의 `$` 줄) | 입력 / 기대 결과 |
| --- | --- | --- |
| 1 | `python -m budget_app category list` | 기본 4개 |
| 2 | `python -m budget_app category add` | `카테고리명: salary` |
| 3 | `python -m budget_app add` | 날짜 `2024-13-40` 입력 → `[오류]/[힌트]` 후 다시 `2024-01-15`, `expense`, `food`, `15000`, `점심`, `meal` → `TX-000001` |
| 4 | `python -m budget_app import --from import.csv` | `[완료] imported=4, skipped=1` (hobby 미등록 행 건너뜀) |
| 5 | `python -m budget_app list --limit 3` | TX-000005, TX-000001, TX-000002 |
| 6 | `python -m budget_app search --category food` / `python -m budget_app search --from 2024-01-12 --to 2024-01-14` | 두 명령 |
| 7 | `python -m budget_app budget set --month 2024-01 --amount 500000` / `python -m budget_app summary --month 2024-01 --top 3` | PDF 8장과 같은 숫자(총 지출 215000원, 사용률 43.0%, rent/food/transport) |
| 8 | `python -m budget_app update --id TX-000003 --amount 25000 --memo "버스 왕복"` | `[수정 완료] id=TX-000003` |
| 9 | `python -m budget_app delete --id TX-000005` / `python -m budget_app delete --id TX-999999` | 삭제 완료 / 없는 데이터 오류 예 |
| 10 | `python -m budget_app category remove` | `카테고리명: food` → 사용 중이라 삭제 차단 오류 예 |
| 11 | `python -m budget_app export --out export.csv --month 2024-01` / `cat export.csv` | `[완료] export.csv (4 records)` 와 파일 내용 |

`import.csv` 예시 블록 내용(스키마 절에 ` ```csv import.csv ` 로):

```
date,type,category,amount,memo,tags
2024-01-14,income,salary,3000000,월급,
2024-01-12,expense,transport,20000,버스,commute
2024-01-05,expense,rent,150000,1월 월세,"house,fixed"
2024-01-15,expense,food,30000,저녁,"meal,friend"
2024-01-20,expense,hobby,12000,영화,
```

- 각 명령 앞뒤에 한 줄 설명을 붙여도 된다(console 블록 밖에). 시나리오를 바꿔야 하면 6.2 N 의 필수 명령 목록(`add, list, search, summary, budget set, category add, category list, category remove, update, delete, import, export`)과 `[오류]` 예시 1개 이상은 유지한다.

## 4. 계층 규칙

2·3단계와 같다. 새 import 도 이 표 안에서만 한다.

```
__main__.py → cli.py → services.py → storage.py → models.py
                 └──→ decorators.py ──→ models.py
```

| 모듈 | import 가능한 `budget_app` 모듈 |
| --- | --- |
| `models.py` | 없음 |
| `storage.py` | `models` |
| `services.py` | `storage`, `models` |
| `decorators.py` | `models` (`BudgetAppError` 만) |
| `cli.py` | `services`, `decorators`, `models` — **`storage` 금지** |
| `__main__.py` | `cli` |

- `csv` 모듈과 파일 열기(`open(`)는 `storage.py` 에만 둔다(3.2).
- `print`/`input` 은 `cli.py`, `decorators.py` 에만 둔다. 행 검증·건수 계산은 서비스, 문구 조립은 CLI.
- 상대 import 금지(`from budget_app.xxx import ...`).

## 5. 예외/경계 상황

| 상황 | 처리 | 종료 코드 |
| --- | --- | --- |
| import `--from` 누락, export `--out` 누락 | argparse 사용법 오류 | 2 |
| `import -h`, `--fro`/`--ou`/`--mon` 같은 줄임말, import 에 `--month` 등 없는 옵션, export 에 `--limit`, `--data-dir` 를 명령 앞에 | argparse 사용법 오류 | 2 |
| import `--from "  "` / export `--out ""` | `[오류] --from 값이 비어 있습니다` 등 | 1 |
| import 파일 없음 | `[오류] 가져올 CSV 파일이 없습니다: <경로>` | 1 |
| import `--from` 이 폴더·읽기 권한 없음 | 데코레이터 `OSError`: `[오류] 파일을 읽거나 쓸 수 없습니다: <경로> (<원인>)` | 1 |
| import 빈 파일(0바이트), 첫 줄이 빈 줄 | `[오류] CSV 파일에 헤더가 없습니다` | 1 |
| import 필수 컬럼 누락 / 헤더 없이 데이터부터 시작 | `[오류] CSV 헤더에 필수 컬럼이 없습니다: amount` 등 | 1 |
| import 헤더에 `date` 가 두 번 | `[오류] CSV 헤더에 같은 컬럼이 여러 번 있습니다: date` | 1 |
| import 파일이 CP949 등 UTF-8 아님 (앞부분 / 중간) | `[오류] CSV 파일을 UTF-8 로 읽을 수 없습니다` — 앞부분이면 임시 파일도 만들지 않고, 중간이면 임시 파일을 지우고 원본 유지 | 1 |
| import 한 칸이 너무 긴 줄(131072자 초과) | `[오류] … 번째 줄을 CSV 로 읽을 수 없습니다 (…)`, 원본 유지 | 1 |
| import 중 Ctrl+C / 쓰기 오류 / 기존 거래 파일 손상 줄 | 원본 유지, 임시 파일 삭제 | 1 |
| import 중 강제 종료(SIGKILL) | 원본 유지(임시 파일은 남을 수 있음, 앱은 무시) | (-9) |
| import 헤더만 있음 | `[완료] imported=0, skipped=0`, 거래 파일 내용 그대로 | 0 |
| import BOM 있는 UTF-8, 줄 끝 `\r\n` | 정상 처리 | 0 |
| import 컬럼 순서가 다름, `id`·`note` 등 추가 컬럼, memo/tags 컬럼 없음 | 정상 처리(추가 컬럼 무시, memo `""`, tags `[]`) | 0 |
| import 행: 날짜 `2024-13-01`/`2024-3-1`, type `refund`/`Expense`/빈 값, amount `0`/`-5`/`1.5`/`"1,000"`/`abc`, category `nope`/`Food`/빈 값, 칸 수 다름 | 건너뛰고 skipped 로 셈(출력은 한 줄) | 0 |
| import 행 값 앞뒤 공백, memo 안의 쉼표·따옴표, tags `" a , ,b "` | 공백 제거, 따옴표 규칙대로 읽음, tags `["a", "b"]` | 0 |
| import 빈 줄 | 무시(세지 않음) | 0 |
| import 가 categories.jsonl, budgets.jsonl 에 주는 영향 | 없음(읽기만) | — |
| export 조건 없음 | `[오류] 내보낼 조건이 없습니다` | 1 |
| export `--from` 만 / `--to` 만 (`--month` 와 함께여도) | `[오류] --from 과 --to 는 함께 지정해야 합니다` | 1 |
| export `--month 2024-13`/`2024-1`/`2024-01-01`, `--from 2024-02-30`, `--to 2024-1-5` | 검증 함수의 `[오류]/[힌트]`, 파일 생성 없음 | 1 |
| export `--month` + `--from/--to` | 둘 다 만족하는 거래 | 0 |
| export `--from` > `--to`, 해당 월 거래 없음 | 헤더만 있는 파일, `(0 records)` | 0 |
| export `--out` 이 이미 있는 파일/폴더 | `[오류] 이미 있는 경로입니다: <경로>`, 기존 파일 그대로 | 1 |
| export `--out` 의 폴더 없음 | `[오류] 출력 폴더가 없습니다: <폴더>`, 폴더를 만들지 않음 | 1 |
| export `--out` 폴더에 쓰기 권한 없음 | 데코레이터 `OSError` 메시지 | 1 |
| export 중 거래 파일 손상 줄 / Ctrl+C / 쓰기 오류 | `--out` 파일 생기지 않음, 임시 파일 삭제 | 1 |
| export 상대 경로 `--out export.csv` | 현재 폴더에 생성, 출력 `[완료] export.csv (N records)` | 0 |
| 어떤 경우에도 | `Traceback` 없음. `[오류]/[힌트]` 는 stderr, `[완료]` 는 stdout | — |

### Python 3.10 호환 주의

1~3단계 금지 목록을 그대로 적용한다(`fromisoformat`, `typing.Self`, `datetime.UTC`, `except*`, `ExceptionGroup`, `tomllib`, PEP 695, argparse `color`/`suggest_on_error`). `csv`, `typing.TextIO`, `encoding="utf-8-sig"`, `next(reader, [])`, `@dataclasses.dataclass` 는 3.10 에서 사용 가능하다. 참고: NUL 문자(`\0`)가 든 CSV 는 3.10 에서는 `csv.Error`(파일 오류), 3.11+ 에서는 일반 값으로 읽힌다. 버전마다 결과가 달라 검사하지 않는다.

## 6. 완료 기준 (에이전트 3 검증 절차)

아래 스크립트 하나에 정적 검사, import/export 동작·경계 검사, 왕복 검사, 데이터 안전(도중 실패) 검사, 스트리밍 메모리 검사, README 검사, 1·2·3단계 회귀 검사를 모두 넣었다.

- **실행 방법**: 6.2 코드 블록 내용을 스크래치패드에 파일로 저장한 뒤 `bash <파일>` 로 실행한다(macOS 기본 bash 3.2 에서 동작). **백그라운드(`&`)로 실행하지 않는다**(G 절이 Ctrl+C 신호를 보낸다). 저장한 스크립트 파일은 실행 후 지운다.
- 이 Mac 에는 `python` 이 없어 스크립트 첫머리에서 임시 폴더에 `python → python3` 링크를 만들고 PATH 앞에 둔다.
- 모든 임시 파일은 `W="$(mktemp -d)"` 아래에만 만들고 끝나면(실패해도) `trap` 으로 지운다. 3단계 회귀 스크립트의 `mktemp -d` 도 `$W` 아래로 바꿔 실행한다(3단계 스크립트가 1·2단계를 다시 실행한다).
- `PYTHONDONTWRITEBYTECODE=1` 로 `__pycache__` 를 남기지 않는다. 프로젝트 루트에 `./data`, `export.csv` 등 예상 밖 파일이 생기면 실패다.
- 성공 기준: `FAIL` 로 시작하는 줄이 하나도 없고, `SAFETY_OK`, `SIGNAL_OK`, `IO_MEMORY_OK`, `README_OK` 와 마지막 줄 `STEP4_ALL_OK` 가 나온다. 전체 실행 시간은 1분 안팎(10만 행 메모리 측정 + 3단계 회귀).

### 6.1 정적 검사 항목 (스크립트 S0~S11)

| # | 검사 | 기대 |
| --- | --- | --- |
| S0 | 변경 금지 파일 3개(`models`, `__main__`, `__init__`)의 SHA-256 이 3단계 완료 시점과 같음 | 일치 |
| S1 | 파일 7개 + `README.md` 존재 | 존재 |
| S2 | 3.10 문법 (`ast.parse(feature_version=(3, 10))`) | 통과 |
| S3 | 3.11+ 전용 API grep | 없음 |
| S4 | `.read()`/`readlines(` (전체 로드) grep | 없음 |
| S5 | 계층 규칙 (4장 표) | 위반 없음 |
| S6 | 모든 함수(중첩 함수 포함)의 매개변수·반환 타입 힌트 | 누락 없음 |
| S7 | `def handle_errors` 1개, `@handle_errors` **12개**, `_cmd_*` 12개(3단계 10개 + `import`, `export`) 전부 데코레이터 적용 | 일치 |
| S8 | CSV·거래 스트리밍: storage/services 에서 `list/tuple/set/sorted` 의 첫 인자나 컴프리헨션의 반복 대상이 `iter_csv_records`/`_iter_imported`/`_iter_export`/`iter_transactions`/`reader` 이면 실패. `iter_csv_records` 는 `reader` 를 `for` 로 도는 제너레이터, `check_csv_header` 는 `iter_csv_records` 를 `for` 로 돎, `write_transactions_csv` 는 `_atomic_write` 호출 + `txs` 를 `for` 로 돎, `append_many` 는 `_atomic_rewrite` 호출, `_atomic_rewrite` 는 `_atomic_write` 호출, `_iter_imported`/`_iter_export` 는 각각 `iter_csv_records()`/`iter_transactions()` 를 `for` 로 도는 제너레이터, `import_csv` 는 `check_csv_header`·`append_many`·`_iter_imported` 호출, `export_csv` 는 `write_transactions_csv`·`_iter_export` 호출. storage 의 `os.replace` 와 `mkstemp` 는 각 1회. storage 의 모든 `open`/`fdopen` 에 `encoding=`, `utf-8-sig` 로 여는 곳에는 `newline=` | 위반 없음 |
| S9 | `csv` import 와 `open(` 은 storage.py 에만 | 일치 |
| S10 | `print(`/`input(` 이 models/storage/services 에 없음 | 없음 |
| S11 | cli.py 에 최상위 metavar `{add,list,search,summary,budget,update,delete,category,import,export}` | 있음 |

3단계 S8(search/summary/list 스트리밍 규칙, `sorted` 는 search 1회)은 R 절의 3단계 회귀 스크립트가 그대로 검사한다.

### 6.2 검증 스크립트

```bash
# 4단계 검증 스크립트. 실행: bash <이 파일>   (백그라운드 & 로 실행하지 말 것)
cd "/Users/khm04/codessey/pocket money" || exit 1
export PYTHONDONTWRITEBYTECODE=1
W="$(mktemp -d)"; export W                      # 이 스크립트의 임시 파일은 전부 여기 아래
cleanup() { chmod -R u+rwx "$W" 2>/dev/null; rm -rf "$W"; }
trap cleanup EXIT
mkdir "$W/bin" && ln -s "$(command -v python3)" "$W/bin/python" || exit 1   # python 이 없어서 python3 로 연결
export PATH="$W/bin:$PATH"
python --version || exit 1
ROOT="$(pwd)"; export ROOT
D="$W/run"; mkdir "$D"; DD="$D/data"; O="$D/csv"; mkdir "$O"; FAIL=0     # $D/out, $D/err 는 t() 의 출력 파일
TXF="$DD/transactions.jsonl"; CTF="$DD/categories.jsonl"; BGF="$DD/budgets.jsonl"

fail()      { echo "FAIL $*"; FAIL=1; }
# t <기대 종료코드> <표준입력(printf %b 형식)> <인자...>
t() {
  local want=$1 input=$2; shift 2
  printf '%b' "$input" | python -m budget_app "$@" >"$D/out" 2>"$D/err"
  local rc=$?
  [ "$rc" = "$want" ] || { echo "FAIL rc=$rc want=$want :: $*"; cat "$D/err"; FAIL=1; }
  if grep -q "Traceback" "$D/out" "$D/err"; then echo "FAIL traceback :: $*"; FAIL=1; fi
}
out_has()   { grep -qF -- "$1" "$D/out" || fail "stdout에 없음: $1"; }
err_has()   { grep -qF -- "$1" "$D/err" || fail "stderr에 없음: $1"; }
out_eq()    { [ "$(cat "$D/out")" = "$1" ] || { echo "FAIL stdout 불일치"; echo "--- got"; cat "$D/out"; echo "--- want"; printf '%s\n' "$1"; FAIL=1; }; }
out_empty() { [ ! -s "$D/out" ] || { echo "FAIL stdout 이 비어 있어야 함"; cat "$D/out"; FAIL=1; }; }
err_empty() { [ ! -s "$D/err" ] || { echo "FAIL stderr 가 비어 있어야 함"; cat "$D/err"; FAIL=1; }; }
cnt()       { grep -oF -- "$2" "$D/$1" | wc -l | tr -d ' '; }
err_cnt()   { [ "$(cnt err '[오류]')" = "$1" ] && [ "$(cnt err '[힌트]')" = "$1" ] || { echo "FAIL [오류]/[힌트] 개수 != $1"; cat "$D/err"; FAIL=1; }; }
file_eq()   { [ "$(cat "$1")" = "$2" ] || { echo "FAIL 파일 내용 불일치: $1"; echo "--- got"; cat "$1"; echo "--- want"; printf '%s\n' "$2"; FAIL=1; }; }
no_tmp()    { if find "$1" -name '*.tmp' | grep -q .; then fail "임시 파일 남음: $1"; fi; }

# ======================= S. 정적 검사 =======================
# S0 변경 금지 파일
shasum -a 256 -c - >/dev/null <<'SUMS' || fail "S0 변경 금지 파일이 바뀜 (models/__main__/__init__)"
08b6a94954a6ca8d6619a69a026ac2fd2d028844e17a8c55cb8d6f02faca513f  budget_app/models.py
6958ee4078ab3cdd31564e022cd9fccc673a5f2f8509c241b4771646a4e72753  budget_app/__main__.py
0cb00a1323d1945aa0e71486ffebaf612fde2efe434f13182806c00515b3605c  budget_app/__init__.py
SUMS
# S1 파일 존재
for f in __init__ __main__ models storage services decorators cli; do [ -f "budget_app/$f.py" ] || fail "S1 budget_app/$f.py 없음"; done
[ -f README.md ] || fail "S1 README.md 없음"
# S2 3.10 문법
python3 - budget_app/*.py <<'PY' || fail "S2 3.10 문법"
import ast, sys
for f in sys.argv[1:]:
    ast.parse(open(f, encoding="utf-8").read(), feature_version=(3, 10))
PY
# S3 3.11+ 전용 API
if grep -nE "fromisoformat|typing\.Self|from typing import .*Self|datetime\.UTC|except\*|ExceptionGroup|tomllib|suggest_on_error|color=" budget_app/*.py; then fail "S3 3.11+ API"; fi
# S4 전체 로드
if grep -nE "\.read\(\)|readlines\(" budget_app/*.py; then fail "S4 전체 로드"; fi
# S5 계층 규칙
python3 - <<'PY' || fail "S5 계층 규칙"
import ast, sys
allowed = {"models": set(), "storage": {"models"}, "services": {"storage", "models"},
           "decorators": {"models"}, "cli": {"services", "decorators", "models"},
           "__main__": {"cli"}, "__init__": set()}
bad = []
for m, ok in allowed.items():
    for n in ast.walk(ast.parse(open(f"budget_app/{m}.py", encoding="utf-8").read())):
        if isinstance(n, ast.ImportFrom):
            if n.level: bad.append((m, "relative import"))
            mods = [n.module or ""]
        elif isinstance(n, ast.Import):
            mods = [a.name for a in n.names]
        else:
            continue
        for mod in mods:
            if mod == "budget_app" or mod.startswith("budget_app."):
                tgt = mod.split(".")[1] if "." in mod else "?"
                if tgt not in ok: bad.append((m, mod))
print(bad) if bad else None
sys.exit(1 if bad else 0)
PY
# S6 타입 힌트
python3 - budget_app/*.py <<'PY' || fail "S6 타입 힌트"
import ast, sys
bad = []
for f in sys.argv[1:]:
    for n in ast.walk(ast.parse(open(f, encoding="utf-8").read())):
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
            a = n.args
            args = a.posonlyargs + a.args + a.kwonlyargs + [x for x in (a.vararg, a.kwarg) if x]
            miss = [x.arg for x in args if x.annotation is None and x.arg not in ("self", "cls")]
            if n.returns is None or miss: bad.append((f, n.name, miss))
print(bad) if bad else None
sys.exit(1 if bad else 0)
PY
# S7 데코레이터
[ "$(grep -c "def handle_errors" budget_app/decorators.py)" = 1 ] || fail "S7 handle_errors 정의"
[ "$(grep -c "@handle_errors" budget_app/cli.py)" = 12 ] || fail "S7 @handle_errors 개수 != 12"
python3 - <<'PY' || fail "S7 _cmd_* 데코레이터 적용"
import ast, sys
tree = ast.parse(open("budget_app/cli.py", encoding="utf-8").read())
cmds = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name.startswith("_cmd_")]
want = {"_cmd_add", "_cmd_list", "_cmd_update", "_cmd_delete", "_cmd_category_add", "_cmd_category_list",
        "_cmd_category_remove", "_cmd_search", "_cmd_summary", "_cmd_budget_set", "_cmd_import", "_cmd_export"}
names = {n.name for n in cmds}
undecorated = [n.name for n in cmds if not any(isinstance(d, ast.Name) and d.id == "handle_errors" for d in n.decorator_list)]
if names != want or undecorated:
    print("names:", sorted(names ^ want), "undecorated:", undecorated); sys.exit(1)
PY
# S8 CSV·거래 스트리밍, 원자적 쓰기 한 곳
python3 - <<'PY' || fail "S8 스트리밍/원자적 쓰기 규칙"
import ast, sys
def callname(c):
    f = c.func
    return f.id if isinstance(f, ast.Name) else f.attr if isinstance(f, ast.Attribute) else None
def target(x):
    return callname(x) if isinstance(x, ast.Call) else x.id if isinstance(x, ast.Name) else None
def load(m):
    tree = ast.parse(open(f"budget_app/{m}.py", encoding="utf-8").read())
    return tree, {n.name: n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)}
def is_gen(fn): return any(isinstance(n, (ast.Yield, ast.YieldFrom)) for n in ast.walk(fn))
def for_over(fn, name): return any(isinstance(n, ast.For) and target(n.iter) == name for n in ast.walk(fn))
def calls(fn, name): return any(isinstance(n, ast.Call) and callname(n) == name for n in ast.walk(fn))
st, sf = load("storage")
sv, vf = load("services")
STREAMS = {"iter_csv_records", "_iter_imported", "_iter_export", "iter_transactions", "reader"}
bad = []
for tree, mod in ((st, "storage"), (sv, "services")):
    for n in ast.walk(tree):
        if isinstance(n, ast.Call) and callname(n) in ("list", "tuple", "set", "sorted") and n.args and target(n.args[0]) in STREAMS:
            bad.append(f"{mod} {n.lineno}행: {callname(n)}({target(n.args[0])}) 전체 로드")
        if isinstance(n, (ast.ListComp, ast.SetComp, ast.DictComp, ast.GeneratorExp)):
            if isinstance(n, ast.GeneratorExp):
                continue
            for g in n.generators:
                if target(g.iter) in STREAMS:
                    bad.append(f"{mod} {n.lineno}행: 컴프리헨션으로 {target(g.iter)} 전체 로드")
need = [
    (sf, "iter_csv_records", lambda f: is_gen(f) and for_over(f, "reader")),
    (sf, "check_csv_header", lambda f: for_over(f, "iter_csv_records")),
    (sf, "write_transactions_csv", lambda f: calls(f, "_atomic_write") and for_over(f, "txs")),
    (sf, "append_many", lambda f: calls(f, "_atomic_rewrite")),
    (sf, "_atomic_rewrite", lambda f: calls(f, "_atomic_write")),
    (vf, "_iter_imported", lambda f: is_gen(f) and for_over(f, "iter_csv_records")),
    (vf, "_iter_export", lambda f: is_gen(f) and for_over(f, "iter_transactions")),
    (vf, "import_csv", lambda f: calls(f, "check_csv_header") and calls(f, "append_many") and calls(f, "_iter_imported")),
    (vf, "export_csv", lambda f: calls(f, "write_transactions_csv") and calls(f, "_iter_export")),
]
for funcs, name, ok in need:
    if name not in funcs or not ok(funcs[name]):
        bad.append(f"{name}: 설계서 3.3/3.5 의 스트리밍·원자적 쓰기 구조가 아님")
nrep = sum(1 for n in ast.walk(st) if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
           and n.func.attr == "replace" and isinstance(n.func.value, ast.Name) and n.func.value.id == "os")
nmk = sum(1 for n in ast.walk(st) if isinstance(n, ast.Call) and callname(n) == "mkstemp")
if (nrep, nmk) != (1, 1):
    bad.append(f"storage 의 os.replace {nrep}회, mkstemp {nmk}회 (각 1회, _atomic_write 에만)")
for n in ast.walk(st):
    if isinstance(n, ast.Call) and callname(n) in ("open", "fdopen"):
        kw = {k.arg: k.value for k in n.keywords}
        if "encoding" not in kw:
            bad.append(f"storage {n.lineno}행: {callname(n)} 에 encoding 없음")
        elif isinstance(kw["encoding"], ast.Constant) and kw["encoding"].value == "utf-8-sig" and "newline" not in kw:
            bad.append(f"storage {n.lineno}행: CSV 읽기에 newline 없음")
print(*bad, sep="\n") if bad else None
sys.exit(1 if bad else 0)
PY
# S9 csv 모듈과 파일 열기는 storage.py 에만
if grep -nE "^(import csv|from csv )" budget_app/models.py budget_app/services.py budget_app/cli.py budget_app/decorators.py; then fail "S9 csv 는 storage.py 에서만"; fi
grep -q "^import csv" budget_app/storage.py || fail "S9 storage.py 가 csv 모듈을 쓰지 않음"
if grep -nE "(^|[^A-Za-z0-9_.])open\(" budget_app/models.py budget_app/services.py budget_app/cli.py budget_app/decorators.py; then fail "S9 open( 은 storage.py 에서만"; fi
# S10 print/input 위치
if grep -nE "(^|[^A-Za-z0-9_.])(print|input)\(" budget_app/models.py budget_app/storage.py budget_app/services.py; then fail "S10 print/input 위치"; fi
# S11 최상위 metavar
grep -qF '{add,list,search,summary,budget,update,delete,category,import,export}' budget_app/cli.py || fail "S11 최상위 metavar"

# ======================= A. --help =======================
t 0 '' --help;          out_has "{add,list,search,summary,budget,update,delete,category,import,export}"
t 0 '' import --help;   out_has "usage:"; for o in --from --data-dir CSV; do out_has "$o"; done
t 0 '' export --help;   out_has "usage:"; for o in --out --month --from --to --data-dir CSV YYYY-MM-DD; do out_has "$o"; done
[ ! -e data ] || fail "--help 가 ./data 를 만듦"

# ======================= B. 사용법 오류 (2) =======================
t 2 '' import -h;                                                      err_cnt 1
t 2 '' export -h;                                                      err_cnt 1
t 2 '' import --data-dir "$DD";                                        err_cnt 1; err_has "--from"
t 2 '' export --month 2024-01 --data-dir "$DD";                        err_cnt 1; err_has "--out"
t 2 '' import --fro x.csv --data-dir "$DD";                            err_cnt 1   # 줄임말 금지
t 2 '' export --ou x.csv --month 2024-01 --data-dir "$DD";             err_cnt 1
t 2 '' export --out x.csv --mon 2024-01 --data-dir "$DD";              err_cnt 1
t 2 '' import --from x.csv --month 2024-01 --data-dir "$DD";           err_cnt 1   # import 에 없는 옵션
t 2 '' export --out x.csv --month 2024-01 --limit 3 --data-dir "$DD";  err_cnt 1   # PDF 에 없는 옵션
t 2 '' --data-dir "$DD" import --from x.csv;                           err_cnt 1   # --data-dir 는 명령 뒤에만
t 2 '' --data-dir "$DD" export --out x.csv --month 2024-01;            err_cnt 1
[ ! -e "$DD" ] || fail "사용법 오류에서 data 폴더가 생김"
[ ! -e x.csv ] || fail "사용법 오류에서 x.csv 가 생김"

# ======================= C. 데이터 준비 (대화형 add) =======================
t 0 'salary\n' category add --data-dir "$DD"; out_has "[저장 완료] category=salary"
addtx() { t 0 "$1" add --data-dir "$DD"; out_has "[저장 완료] id=$2"; }
addtx '2024-01-15\nexpense\nfood\n15000\n점심\nmeal\n'                          TX-000001
addtx '2024-01-14\nincome\nsalary\n3000000\n월급\n\n'                           TX-000002
addtx '2024-01-12\nexpense\ntransport\n20000\n버스\ncommute\n'                  TX-000003
addtx '2024-01-05\nexpense\nrent\n150000\n1월 월세\nhouse,fixed\n'              TX-000004
addtx '2024-01-15\nexpense\nfood\n30000\n저녁 Pizza, "특식"\nmeal, friend\n'    TX-000005
addtx '2024-02-03\nexpense\nfood\n12000\n점심\nmeal\n'                          TX-000006
addtx '2023-12-31\nincome\netc\n50000\n용돈\n\n'                                TX-000007
SUMT="$(cksum < "$TXF")"; SUMC="$(cksum < "$CTF")"; SUMB="$(cksum < "$BGF")"
H='date,type,category,amount,memo,tags'
R1='2024-01-15,expense,food,15000,점심,meal'
R2='2024-01-14,income,salary,3000000,월급,'
R3='2024-01-12,expense,transport,20000,버스,commute'
R4='2024-01-05,expense,rent,150000,1월 월세,"house,fixed"'
R5='2024-01-15,expense,food,30000,"저녁 Pizza, ""특식""","meal,friend"'
R6='2024-02-03,expense,food,12000,점심,meal'
R7='2023-12-31,income,etc,50000,용돈,'

# ======================= D. export =======================
t 0 '' export --out "$O/jan.csv" --month 2024-01 --data-dir "$DD";   err_empty; out_eq "[완료] $O/jan.csv (5 records)"
file_eq "$O/jan.csv" "$(printf '%s\n' "$H" "$R1" "$R2" "$R3" "$R4" "$R5")"           # 저장 순서 그대로, 따옴표 규칙
[ "$(head -c 5 "$O/jan.csv")" = "date," ] || fail "export 파일 앞에 BOM 등 다른 바이트"
[ "$(tail -c 1 "$O/jan.csv" | od -An -tx1 | tr -d ' ')" = "0a" ] || fail "export 마지막 줄 개행 없음"
if LC_ALL=C grep -q "$(printf '\r')" "$O/jan.csv"; then fail "export 줄 끝에 CR"; fi
t 0 '' export --out "$O/range.csv" --from 2024-01-14 --to 2024-02-03 --data-dir "$DD";  out_eq "[완료] $O/range.csv (4 records)"
file_eq "$O/range.csv" "$(printf '%s\n' "$H" "$R1" "$R2" "$R5" "$R6")"                 # 양 끝 포함
t 0 '' export --out "$O/both.csv" --month 2024-01 --from 2024-01-13 --to 2024-12-31 --data-dir "$DD"; out_eq "[완료] $O/both.csv (3 records)"
file_eq "$O/both.csv" "$(printf '%s\n' "$H" "$R1" "$R2" "$R5")"                        # --month 와 기간 AND
t 0 '' export --out "$O/all.csv" --from 2000-01-01 --to 2099-12-31 --data-dir "$DD";   out_eq "[완료] $O/all.csv (7 records)"
file_eq "$O/all.csv" "$(printf '%s\n' "$H" "$R1" "$R2" "$R3" "$R4" "$R5" "$R6" "$R7")"
t 0 '' export --out "$O/rev.csv" --from 2024-02-01 --to 2024-01-01 --data-dir "$DD";   out_eq "[완료] $O/rev.csv (0 records)"; file_eq "$O/rev.csv" "$H"
t 0 '' export --out "$O/may.csv" --month 2024-05 --data-dir "$DD";                     out_eq "[완료] $O/may.csv (0 records)"; file_eq "$O/may.csv" "$H"
( cd "$O" && PYTHONPATH="$ROOT" python -m budget_app export --out rel.csv --month 2023-12 --data-dir "$DD" ) >"$D/out" 2>"$D/err" || fail "상대 경로 export 실패"
out_eq "[완료] rel.csv (1 records)"; file_eq "$O/rel.csv" "$(printf '%s\n' "$H" "$R7")"
t 1 '' export --out "$O/e1.csv" --data-dir "$DD";                                   err_cnt 1; out_empty; err_has "--month"
t 1 '' export --out "$O/e2.csv" --from 2024-01-01 --data-dir "$DD";                 err_cnt 1; err_has "--to"
t 1 '' export --out "$O/e3.csv" --to 2024-01-31 --data-dir "$DD";                   err_cnt 1; err_has "--from"
t 1 '' export --out "$O/e4.csv" --month 2024-01 --from 2024-01-01 --data-dir "$DD"; err_cnt 1
for v in 2024-13 2024-1 2024-01-01 abc; do t 1 '' export --out "$O/e5.csv" --month "$v" --data-dir "$DD"; err_cnt 1; out_empty; done
t 1 '' export --out "$O/e6.csv" --from 2024-02-30 --to 2024-03-01 --data-dir "$DD"; err_cnt 1
t 1 '' export --out "$O/e7.csv" --from 2024-01-01 --to 2024-1-5 --data-dir "$DD";   err_cnt 1
t 1 '' export --out "   " --month 2024-01 --data-dir "$DD";                         err_cnt 1; err_has "--out"
for n in 1 2 3 4 5 6 7; do [ ! -e "$O/e$n.csv" ] || fail "실패한 export 가 e$n.csv 를 만듦"; done
SUMJ="$(cksum < "$O/jan.csv")"
t 1 '' export --out "$O/jan.csv" --month 2024-02 --data-dir "$DD";      err_cnt 1; out_empty; err_has "$O/jan.csv"
[ "$(cksum < "$O/jan.csv")" = "$SUMJ" ] || fail "이미 있는 --out 파일을 덮어씀"
t 1 '' export --out "$O" --month 2024-01 --data-dir "$DD";              err_cnt 1          # 폴더
t 1 '' export --out "$O/nodir/x.csv" --month 2024-01 --data-dir "$DD";  err_cnt 1; err_has "$O/nodir"
[ ! -e "$O/nodir" ] || fail "export 가 출력 폴더를 만듦"
mkdir "$O/ro"; chmod 555 "$O/ro"
t 1 '' export --out "$O/ro/x.csv" --month 2024-01 --data-dir "$DD";     err_cnt 1; err_has "--out"   # 쓰기 권한 없음
chmod 755 "$O/ro"; [ -z "$(ls -A "$O/ro")" ] || fail "읽기 전용 폴더에 파일이 생김"
DC="$D/badt"; t 0 '' list --data-dir "$DC"; cp "$TXF" "$DC/transactions.jsonl"; echo 'not json' >> "$DC/transactions.jsonl"
t 1 '' export --out "$O/bad.csv" --from 2000-01-01 --to 2099-12-31 --data-dir "$DC"; err_cnt 1; err_has "transactions.jsonl"
[ ! -e "$O/bad.csv" ] || fail "도중에 실패한 export 가 --out 파일을 남김"
no_tmp "$O"
[ "$(cksum < "$TXF")" = "$SUMT" ] || fail "export 가 거래 파일을 바꿈"

# ======================= E. import =======================
# E1 왕복: export → 빈 폴더로 import → 같은 조건 export → 바이트 단위로 같음
RT="$D/rt"; t 0 'salary\n' category add --data-dir "$RT"
t 0 '' import --from "$O/all.csv" --data-dir "$RT";   err_empty; out_eq "[완료] imported=7, skipped=0"
t 0 '' export --out "$O/all2.csv" --from 2000-01-01 --to 2099-12-31 --data-dir "$RT"; out_eq "[완료] $O/all2.csv (7 records)"
cmp -s "$O/all.csv" "$O/all2.csv" || fail "export→import→export 결과가 다름"
python3 - "$TXF" "$RT/transactions.jsonl" <<'PY' || fail "왕복 후 거래 내용이 다름"
import json, sys
a, b = ([json.loads(l) for l in open(p, encoding="utf-8") if l.strip()] for p in sys.argv[1:3])
drop = lambda d: {k: v for k, v in d.items() if k != "id"}
assert [drop(x) for x in a] == [drop(x) for x in b], (a, b)
assert [x["id"] for x in b] == [f"TX-{i:06d}" for i in range(1, 8)], [x["id"] for x in b]
PY
# E2 기존 데이터에 추가: id 는 이어서 발급, 기존 줄은 그대로, 카테고리·예산 파일 불변
DUP="$D/dup"; cp -R "$DD" "$DUP"
t 0 '' import --from "$O/jan.csv" --data-dir "$DUP";  out_eq "[완료] imported=5, skipped=0"
[ "$(head -7 "$DUP/transactions.jsonl")" = "$(cat "$TXF")" ] || fail "import 가 기존 거래 줄을 바꿈"
[ "$(tail -5 "$DUP/transactions.jsonl" | python3 -c 'import json,sys; print(" ".join(json.loads(l)["id"] for l in sys.stdin))')" = "TX-000008 TX-000009 TX-000010 TX-000011 TX-000012" ] || fail "import id 이어서 발급 안 됨"
[ "$(cksum < "$DUP/categories.jsonl")" = "$SUMC" ] && [ "$(cksum < "$DUP/budgets.jsonl")" = "$SUMB" ] || fail "import 가 카테고리·예산 파일을 바꿈"
# E3 행 단위 검증: 컬럼 순서 자유, 추가 컬럼(note, id) 무시, 잘못된 행은 skipped, 빈 줄 무시
MX="$D/mx"; cp -R "$DD" "$MX"
cat > "$D/mixed.csv" <<'CSV'
type,date,amount,category,note,memo,tags,id
expense,2024-03-01,1000,food,x,  점심  ," a , ,b ",TX-999999
 income , 2024-03-02 , 500000 , salary ,, 월급 ,,
expense,2024-13-01,1000,food,,,,
expense,2024-3-1,1000,food,,,,
refund,2024-03-03,1000,food,,,,
Expense,2024-03-03,1000,food,,,,
expense,2024-03-04,0,food,,,,
expense,2024-03-04,-5,food,,,,
expense,2024-03-04,1.5,food,,,,
expense,2024-03-04,"1,000",food,,,,
expense,2024-03-04,abc,food,,,,
expense,2024-03-05,1000,nope,,,,
expense,2024-03-05,1000,Food,,,,
,2024-03-06,1000,food,,,,
expense,2024-03-06,1000,,,,,
expense,2024-03-07,1000,food
expense,2024-03-08,1000,food,,,,,extra

expense,2024-03-09,2000,transport,,"메모, ""따옴표""",commute,
CSV
t 0 '' import --from "$D/mixed.csv" --data-dir "$MX";  err_empty; out_eq "[완료] imported=3, skipped=15"
python3 - "$MX/transactions.jsonl" "$TXF" <<'PY' || fail "import 행 정리 결과가 다름"
import json, sys
lines = [l for l in open(sys.argv[1], encoding="utf-8") if l.strip()]
orig = [l for l in open(sys.argv[2], encoding="utf-8") if l.strip()]
assert lines[:7] == orig, "기존 줄이 바뀜"
got = [json.loads(l) for l in lines[7:]]
want = [
    {"id": "TX-000008", "type": "expense", "date": "2024-03-01", "amount": 1000, "category": "food", "memo": "점심", "tags": ["a", "b"]},
    {"id": "TX-000009", "type": "income", "date": "2024-03-02", "amount": 500000, "category": "salary", "memo": "월급", "tags": []},
    {"id": "TX-000010", "type": "expense", "date": "2024-03-09", "amount": 2000, "category": "transport", "memo": '메모, "따옴표"', "tags": ["commute"]},
]
assert got == want, got
PY
# E4 BOM, CRLF, memo/tags 컬럼 없음
BM="$D/bom"
printf '\xef\xbb\xbfdate,type,category,amount\r\n2024-04-01,expense,food,700\r\n2024-04-02,income,etc,800\r\n' > "$D/bom.csv"
t 0 '' import --from "$D/bom.csv" --data-dir "$BM";  out_eq "[완료] imported=2, skipped=0"
t 0 '' list --data-dir "$BM"; out_eq "$(printf '%s\n' 'TX-000002 | 2024-04-02 | income | etc | 800 |' 'TX-000001 | 2024-04-01 | expense | food | 700 |')"
# E5 헤더만 있는 파일: 0건, 거래 파일 내용 그대로
printf '%s\n' "$H" > "$D/h.csv"
t 0 '' import --from "$D/h.csv" --data-dir "$DD";  err_empty; out_eq "[완료] imported=0, skipped=0"
[ "$(cksum < "$TXF")" = "$SUMT" ] || fail "0건 import 가 거래 내용을 바꿈"
# E6 파일 수준 오류: 종료 코드 1, 아무것도 저장하지 않음
: > "$D/empty.csv"
printf '\ndate,type,category,amount\n2024-01-01,expense,food,1000\n' > "$D/blank1.csv"
printf 'date,type,category,memo\n2024-01-01,expense,food,x\n' > "$D/noamt.csv"
printf 'date,type,category,amount,date\n2024-01-01,expense,food,1000,2024-01-02\n' > "$D/dupcol.csv"
printf '2024-01-01,expense,food,1000\n' > "$D/nohdr.csv"
python3 -c 'import sys; open(sys.argv[1], "wb").write("date,type,category,amount,memo\n2024-01-01,expense,food,1000,점심\n".encode("cp949"))' "$D/cp949.csv"
python3 - "$D" <<'PY'
import sys
d = sys.argv[1]
good = "".join(f"2024-06-{i % 28 + 1:02d},expense,food,{i % 900 + 1},메모 {i},t{i % 5}\n" for i in range(20000))
with open(f"{d}/mid_utf8.csv", "wb") as f:      # 앞 20000행은 올바르고 중간에 UTF-8 이 아닌 바이트
    f.write(("date,type,category,amount,memo,tags\n" + good).encode() + b"2024-06-01,expense,food,1,\xff\xfe,\n" + good[:500].encode())
with open(f"{d}/mid_big.csv", "w", encoding="utf-8") as f:   # 중간에 131072자를 넘는 칸
    f.write("date,type,category,amount,memo,tags\n" + good + "2024-06-01,expense,food,1," + "x" * 200000 + ",\n")
PY
t 1 '' import --from "$D/none.csv" --data-dir "$DD";   err_cnt 1; out_empty; err_has "$D/none.csv"
t 1 '' import --from "$D" --data-dir "$DD";            err_cnt 1; out_empty; err_has "--from"      # 폴더
t 1 '' import --from "$D/empty.csv" --data-dir "$DD";  err_cnt 1; err_has "헤더"
t 1 '' import --from "$D/blank1.csv" --data-dir "$DD"; err_cnt 1; err_has "헤더"
t 1 '' import --from "$D/noamt.csv" --data-dir "$DD";  err_cnt 1; err_has "amount"
t 1 '' import --from "$D/dupcol.csv" --data-dir "$DD"; err_cnt 1; err_has "date"
t 1 '' import --from "$D/nohdr.csv" --data-dir "$DD";  err_cnt 1
t 1 '' import --from "$D/cp949.csv" --data-dir "$DD";  err_cnt 1; err_has "UTF-8"
t 1 '' import --from "$D/mid_utf8.csv" --data-dir "$DD"; err_cnt 1; err_has "UTF-8"
t 1 '' import --from "$D/mid_big.csv" --data-dir "$DD";  err_cnt 1
t 1 '' import --from "   " --data-dir "$DD";           err_cnt 1; err_has "--from"
[ "$(cksum < "$TXF")" = "$SUMT" ] || fail "실패한 import 가 거래 파일을 바꿈"
no_tmp "$DD"
# E7 기존 거래 파일에 손상 줄: import 취소, 원본 그대로
DC2="$D/badt2"; cp -R "$DD" "$DC2"; echo 'not json' >> "$DC2/transactions.jsonl"; SUMX="$(cksum < "$DC2/transactions.jsonl")"
t 1 '' import --from "$O/jan.csv" --data-dir "$DC2";   err_cnt 1; err_has "transactions.jsonl"
[ "$(cksum < "$DC2/transactions.jsonl")" = "$SUMX" ] || fail "손상 파일에 import 가 반영됨"; no_tmp "$DC2"
[ "$(cksum < "$CTF")" = "$SUMC" ] && [ "$(cksum < "$BGF")" = "$SUMB" ] || fail "import/export 가 카테고리·예산 파일을 바꿈"

# ======================= F. 도중 실패 주입 (같은 프로세스) =======================
python - <<'PY' || FAIL=1
import contextlib, errno, glob, io, json, os, sys, tempfile
import budget_app.models as models
from budget_app.cli import main
base = os.path.join(os.environ["W"], "inj"); os.makedirs(base)
d = os.path.join(base, "data"); tx = os.path.join(d, "transactions.jsonl")
ok = True
def need(cond, msg):
    global ok
    if not cond:
        print("FAIL", msg); ok = False
def run(argv):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        rc = main(argv)
    return rc, out.getvalue(), err.getvalue()
def snap():
    return {n: open(os.path.join(d, n), "rb").read() for n in sorted(os.listdir(d))}
def tmps(folder):
    return glob.glob(os.path.join(folder, "*.tmp"))
def csvfile(name, data):
    p = os.path.join(base, name)
    with open(p, "wb") as f:
        f.write(data)
    return p
H = "date,type,category,amount,memo,tags\n"
def rows(n):
    return "".join(f"2024-05-{i % 28 + 1:02d},expense,food,{i % 900 + 1},메모 {i},t{i % 5}\n" for i in range(n))
run(["list", "--data-dir", d])
with open(tx, "w", encoding="utf-8") as f:
    for i in range(1, 4):
        f.write(json.dumps({"id": f"TX-{i:06d}", "type": "expense", "date": f"2024-01-0{i}", "amount": i * 100,
                            "category": "food", "memo": "", "tags": []}) + "\n")
before = snap()
# 1) 파일 수준 오류는 임시 파일을 만들기 전에 멈춘다
mk_calls = []
_mk = tempfile.mkstemp
def mk_spy(*a, **k):
    mk_calls.append(1)
    return _mk(*a, **k)
tempfile.mkstemp = mk_spy
early = {"none": os.path.join(base, "none.csv"), "empty": csvfile("empty.csv", b""),
         "noamt": csvfile("noamt.csv", b"date,type,category\n2024-01-01,expense,food\n"),
         "cp949": csvfile("cp949.csv", (H + "2024-01-01,expense,food,1000,점심,\n").encode("cp949"))}
for k, p in early.items():
    mk_calls.clear()
    rc, out, err = run(["import", "--from", p, "--data-dir", d])
    need(rc == 1 and "[오류]" in err and out == "", f"{k}: rc={rc} err={err!r}")
    need(mk_calls == [], f"{k}: 헤더 검사 전에 임시 파일을 만듦")
    need(snap() == before, f"{k}: 데이터 파일이 바뀜")
# 2) 쓰기 도중 실패(파일 중간의 UTF-8 오류·CSV 오류): 임시 파일은 만들어졌다가 지워지고 원본은 그대로
mid = {"utf8": csvfile("mid_utf8.csv", (H + rows(20000)).encode() + b"2024-01-01,expense,food,1,\xff\xfe,\n" + rows(10).encode()),
       "field": csvfile("mid_field.csv", (H + rows(20000) + "2024-01-01,expense,food,1," + "x" * 200000 + ",\n").encode())}
for k, p in mid.items():
    mk_calls.clear()
    rc, out, err = run(["import", "--from", p, "--data-dir", d])
    need(rc == 1 and "[오류]" in err and out == "", f"{k}: rc={rc} err={err!r}")
    need(len(mk_calls) == 1, f"{k}: 쓰기 도중 실패를 재현하지 못함 (mkstemp {len(mk_calls)}회)")
    need(snap() == before and not tmps(d), f"{k}: 원본이 바뀌었거나 임시 파일이 남음")
tempfile.mkstemp = _mk
good = csvfile("good.csv", (H + rows(5000)).encode())
# 3) os.replace 실패 (디스크 가득 참 흉내)
_rep = os.replace
def rep_fail(a, b):
    raise OSError(errno.ENOSPC, "No space left on device")
os.replace = rep_fail
rc, out, err = run(["import", "--from", good, "--data-dir", d])
os.replace = _rep
need(rc == 1 and "[오류]" in err and out == "" and snap() == before and not tmps(d), f"import os.replace 실패: rc={rc} {err!r}")
# 4) 새 거래 1000건째를 쓰는 중 Ctrl+C
TJ = models.Transaction.__dict__["to_json_line"]
n = [0]
def boom(self):
    n[0] += 1
    if n[0] == 1000:
        raise KeyboardInterrupt
    return TJ(self)
models.Transaction.to_json_line = boom
rc, out, err = run(["import", "--from", good, "--data-dir", d])
models.Transaction.to_json_line = TJ
need(rc == 1 and "Ctrl+C" in err and snap() == before and not tmps(d), f"import 중 Ctrl+C: rc={rc} {err!r}")
# 5) 성공: os.replace 1회, 같은 폴더 임시 파일 → transactions.jsonl, 기존 줄이 앞에 그대로
calls = []
def rep_spy(a, b):
    calls.append((str(a), str(b)))
    return _rep(a, b)
os.replace = rep_spy
rc, out, err = run(["import", "--from", good, "--data-dir", d])
os.replace = _rep
need(rc == 0 and out == "[완료] imported=5000, skipped=0\n" and err == "", f"import 성공: {rc} {out!r} {err!r}")
need(len(calls) == 1 and os.path.samefile(calls[0][1], tx)
     and os.path.dirname(os.path.abspath(calls[0][0])) == os.path.abspath(d), f"import 원자적 교체: {calls}")
need(open(tx, "rb").read().startswith(before["transactions.jsonl"]), "기존 거래 줄이 앞에 그대로 남지 않음")
need(sum(1 for l in open(tx, encoding="utf-8") if l.strip()) == 5003, "import 후 거래 수가 5003 이 아님")
after = snap()
# 6) export 도중 실패 → --out 파일이 생기지 않음
outd = os.path.join(base, "out"); os.makedirs(outd)
FJ = models.Transaction.__dict__["from_json_line"]
n[0] = 0
def boom2(cls, line):
    n[0] += 1
    if n[0] == 3000:
        raise KeyboardInterrupt
    return FJ.__func__(cls, line)
models.Transaction.from_json_line = classmethod(boom2)
rc, out, err = run(["export", "--out", os.path.join(outd, "a.csv"), "--month", "2024-05", "--data-dir", d])
models.Transaction.from_json_line = FJ
need(rc == 1 and "Ctrl+C" in err and os.listdir(outd) == [], f"export 중 Ctrl+C: rc={rc} {os.listdir(outd)}")
os.replace = rep_fail
rc, out, err = run(["export", "--out", os.path.join(outd, "b.csv"), "--month", "2024-05", "--data-dir", d])
os.replace = _rep
need(rc == 1 and "[오류]" in err and os.listdir(outd) == [], f"export os.replace 실패: rc={rc} {os.listdir(outd)}")
calls.clear()
os.replace = rep_spy
c = os.path.join(outd, "c.csv")
rc, out, err = run(["export", "--out", c, "--month", "2024-05", "--data-dir", d])
os.replace = _rep
need(rc == 0 and out == f"[완료] {c} (5000 records)\n", f"export 성공: {out!r} {err!r}")
need(len(calls) == 1 and os.path.dirname(os.path.abspath(calls[0][0])) == os.path.abspath(outd), f"export 원자적 교체: {calls}")
need(snap() == after, "export 가 데이터 파일을 바꿈")
print("SAFETY_OK" if ok else "SAFETY_FAIL")
sys.exit(0 if ok else 1)
PY

# ======================= G. 실제 신호로 중단 (별도 프로세스) =======================
python - <<'PY' || FAIL=1
import glob, json, os, signal, subprocess, sys, time
base = os.path.join(os.environ["W"], "sig"); os.makedirs(base)
d = os.path.join(base, "data"); tx = os.path.join(d, "transactions.jsonl")
ok = True
def need(cond, msg):
    global ok
    if not cond:
        print("FAIL", msg); ok = False
subprocess.run([sys.executable, "-m", "budget_app", "list", "--data-dir", d], capture_output=True, check=True)
with open(tx, "w", encoding="utf-8") as f:
    for i in range(1, 4):
        f.write(json.dumps({"id": f"TX-{i:06d}", "type": "expense", "date": f"2024-01-0{i}", "amount": i,
                            "category": "food", "memo": "", "tags": []}) + "\n")
before = open(tx, "rb").read()
big = os.path.join(base, "big.csv")
with open(big, "w", encoding="utf-8") as f:
    f.write("date,type,category,amount,memo,tags\n")
    for i in range(200_000):
        f.write(f"2024-06-{i % 28 + 1:02d},expense,food,{i % 900 + 1},메모 {i},t{i % 5}\n")
def interrupt(sig):
    # 셸이 SIGINT 를 무시하도록 물려준 경우에도 파이썬이 KeyboardInterrupt 를 쓰도록 기본 동작으로 되돌린다
    p = subprocess.Popen([sys.executable, "-m", "budget_app", "import", "--from", big, "--data-dir", d],
                         stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                         preexec_fn=lambda: signal.signal(signal.SIGINT, signal.SIG_DFL))
    t0 = time.time()
    while not glob.glob(os.path.join(d, "*.tmp")):          # 임시 파일에 쓰기 시작할 때까지 기다림
        if p.poll() is not None or time.time() - t0 > 30:
            p.kill(); p.communicate()
            return None, "임시 파일이 생기기 전에 끝남"
        time.sleep(0.005)
    time.sleep(0.1)                                         # 몇천 행을 쓴 뒤에 중단
    p.send_signal(sig)
    out, err = p.communicate(timeout=60)
    return p.returncode, err
rc, err = interrupt(signal.SIGINT)
need(rc == 1 and "Ctrl+C" in err and "Traceback" not in err, f"SIGINT: rc={rc} err={err!r}")
need(open(tx, "rb").read() == before, "Ctrl+C 로 멈춘 import 가 거래 파일을 바꿈")
need(not glob.glob(os.path.join(d, "*.tmp")), "Ctrl+C 후 임시 파일이 남음")
rc, err = interrupt(signal.SIGKILL)
need(rc == -signal.SIGKILL, f"SIGKILL: rc={rc} {err!r}")
need(open(tx, "rb").read() == before, "강제 종료된 import 가 거래 파일을 바꿈")
print(f"  SIGKILL 뒤 남은 임시 파일 {len(glob.glob(os.path.join(d, '*.tmp')))}개 (정리할 기회가 없으므로 남을 수 있음, 앱은 읽지 않음)")
r = subprocess.run([sys.executable, "-m", "budget_app", "list", "--data-dir", d], capture_output=True, text=True)
need(r.returncode == 0 and len(r.stdout.splitlines()) == 3, f"강제 종료 뒤 list: {r.returncode} {r.stdout!r}")
print("SIGNAL_OK" if ok else "SIGNAL_FAIL")
sys.exit(0 if ok else 1)
PY

# ======================= M. 스트리밍 메모리 (1만 행 vs 10만 행) =======================
# 같은 프로세스에서 cli.main 을 tracemalloc 으로 감싸 최대 메모리를 잰다. 첫 호출의 1회성 할당은 워밍업으로 뺀다.
python - <<'PY' || FAIL=1
import contextlib, csv, filecmp, io, os, sys, tracemalloc
from budget_app.cli import main
M = os.path.join(os.environ["W"], "mem"); os.makedirs(M)
ok = True
def need(cond, msg):
    global ok
    if not cond:
        print("FAIL", msg); ok = False
def gen(path, n):
    cats = ("food", "transport", "rent", "etc")
    with open(path, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(["date", "type", "category", "amount", "memo", "tags"])
        for i in range(1, n + 1):
            w.writerow([f"2024-{i % 12 + 1:02d}-{i % 28 + 1:02d}", "income" if i % 4 == 0 else "expense", cats[i % 4],
                        str(i % 997 + 1), f"메모 {i}, 끝" if i % 7 == 0 else f"메모 {i}", f"t{i % 50},x" if i % 3 else ""])
def peak(argv):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        tracemalloc.start()
        rc = main(argv)
        p = tracemalloc.get_traced_memory()[1]
        tracemalloc.stop()
    need(rc == 0, f"{argv} 종료 코드 {rc}")
    return p, buf.getvalue()
def control(path):                                   # 대조군: CSV 를 list 로 한 번에 읽으면 행 수에 비례해 는다
    tracemalloc.start()
    with open(path, encoding="utf-8", newline="") as f:
        rows = list(csv.reader(f))
    p = tracemalloc.get_traced_memory()[1]
    tracemalloc.stop()
    del rows
    return p
csvs = {}
for k, n in (("tiny", 100), ("small", 10_000), ("big", 100_000)):
    csvs[k] = os.path.join(M, f"{k}.csv"); gen(csvs[k], n)
peak(["import", "--from", csvs["tiny"], "--data-dir", os.path.join(M, "warm")])                       # 워밍업
peak(["export", "--out", os.path.join(M, "warm.csv"), "--month", "2024-01", "--data-dir", os.path.join(M, "warm")])
r = {}
for k, n in (("small", 10_000), ("big", 100_000)):
    d = os.path.join(M, k); o = os.path.join(M, f"{k}_out.csv")
    r["import", k], out = peak(["import", "--from", csvs[k], "--data-dir", d])
    need(out == f"[완료] imported={n}, skipped=0\n", f"{k} import 출력: {out!r}")
    r["export", k], out = peak(["export", "--out", o, "--from", "2024-01-01", "--to", "2024-12-31", "--data-dir", d])
    need(out == f"[완료] {o} ({n} records)\n", f"{k} export 출력: {out!r}")
    need(filecmp.cmp(csvs[k], o, shallow=False), f"{k}: export(import(CSV)) 가 원본 CSV 와 바이트 단위로 다름")
r["control", "small"], r["control", "big"] = control(csvs["small"]), control(csvs["big"])
for k, v in r.items():
    print(f"  {k[0]:8s} {k[1]:5s} peak={v:,} bytes")
for op in ("import", "export"):
    need(r[op, "big"] < 2 * r[op, "small"] and r[op, "big"] < 3_000_000,
         f"{op} 최대 메모리가 행 수(1만→10만)에 비례해 늘어남 (전체 로드 의심)")
need(r["control", "big"] > 5 * r["control", "small"], "대조군(전체 로드)의 메모리가 늘지 않음: 측정 방법 확인 필요")
print("IO_MEMORY_OK" if ok else "IO_MEMORY_FAIL")
sys.exit(0 if ok else 1)
PY

# ======================= N. README =======================
python - <<'PY' || FAIL=1
import difflib, os, re, shlex, subprocess, sys
ROOT, W = os.environ["ROOT"], os.environ["W"]
FENCE = "`" * 3                                  # 이 설계서 코드 블록이 끊기지 않도록 백틱 3개를 직접 쓰지 않는다
text = open("README.md", encoding="utf-8").read()
ok = True
def need(cond, msg):
    global ok
    if not cond:
        print("FAIL", msg); ok = False
# N1 필수 절 (설계서 3.8 목차)
for h in ("## 실행 방법", "## 저장 파일 위치와 형식", "## 명령 요약", "## 주요 명령 예시",
          "## import/export CSV 스키마", "## 동작 규칙", "## 오류와 종료 코드"):
    need(re.search(r"^" + re.escape(h) + r"\s*$", text, re.M), f"README 절 없음: {h}")
# N2 필수 내용 (PDF 2장 10번 + 문서에 고정할 결정 사항)
for s in ("python -m budget_app", "python3 -m budget_app", "--help", "--data-dir", "./data", "transactions.jsonl",
          "categories.jsonl", "budgets.jsonl", "JSONL", "UTF-8", "3.10", "date,type,category,amount,memo,tags",
          "food, transport, rent, etc", "안 A", "옵션 방식", "update --id", "사용 중", "대소문자", "최신순", "os.replace",
          "종료 코드", "[오류]", "[힌트]", "imported=", "skipped=", "records)"):
    need(s in text, f"README 에 없음: {s}")
for col in ("date", "type", "category", "amount", "memo", "tags"):
    need(re.search(r"^\|\s*" + col + r"\s*\|", text, re.M), f"CSV 스키마 표에 {col} 행 없음")
# N3 구현하지 않은 기능·옵션을 적지 않음 (옵션 이름은 실제 --help 에 있는 것만)
for s in ("backup", "백업", "반복 내역"):
    need(s not in text, f"README 에 범위 밖 기능: {s}")
known = {"--version"}                              # python3 --version 안내만 허용
for c in ([], ["add"], ["list"], ["search"], ["summary"], ["budget"], ["budget", "set"], ["update"], ["delete"],
          ["category"], ["category", "add"], ["category", "list"], ["category", "remove"], ["import"], ["export"]):
    r = subprocess.run([sys.executable, "-m", "budget_app", *c, "--help"], capture_output=True, text=True)
    known |= set(re.findall(r"--[a-z][a-z-]*", r.stdout))
unknown = set(re.findall(r"--[a-z][a-z-]*", text)) - known
need(not unknown, f"README 에 --help 에 없는 옵션: {sorted(unknown)}")
# N4 console 블록을 빈 폴더에서 그대로 다시 실행해 출력 비교 (설계서 3.8 형식 규칙)
blocks, cur = [], None
for line in text.split("\n"):
    if cur is None:
        if line.startswith(FENCE):
            cur = (line[3:].strip(), [])
    elif line.strip() == FENCE:
        blocks.append(cur); cur = None
    else:
        cur[1].append(line)
need(cur is None, "README 코드 블록이 닫히지 않음")
work = os.path.join(W, "readme"); os.makedirs(work)
csv_files = [(info.split()[1], lines) for info, lines in blocks if info.split()[:1] == ["csv"] and len(info.split()) == 2]
need(csv_files, "README 에 가져오기용 예시 CSV 블록(정보 문자열 'csv <파일명>')이 없음")
for name, lines in csv_files:
    with open(os.path.join(work, name), "w", encoding="utf-8", newline="") as f:
        f.write("\n".join(lines) + "\n")
PROMPTS = ("날짜(YYYY-MM-DD): ", "타입(income/expense): ", "카테고리명: ", "카테고리: ", "금액(양수): ",
           "메모(선택): ", "태그(쉼표로 구분, 없으면 엔터): ")
env = {**os.environ, "PYTHONPATH": ROOT, "PYTHONUNBUFFERED": "1"}
seen, has_error, nrun = set(), False, 0
for info, lines in blocks:
    if info != "console":
        continue
    sessions = []
    for line in lines:
        if line.startswith("$ "):
            sessions.append((line[2:], []))
        elif sessions:
            sessions[-1][1].append(line)
        elif line.strip():
            need(False, f"console 블록이 '$ ' 명령 줄로 시작하지 않음: {line!r}")
    for cmd, out_lines in sessions:
        argv = shlex.split(cmd)
        if argv[:3] == ["python", "-m", "budget_app"]:
            stdin, want = [], ""
            for ln in out_lines:
                p = next((p for p in PROMPTS if ln.startswith(p) or ln == p.rstrip()), None)
                if p is None:
                    want += ln + "\n"
                else:
                    want += p; stdin.append(ln[len(p):])
            r = subprocess.run([sys.executable, "-m", "budget_app", *argv[3:]], cwd=work, env=env, timeout=60,
                               input="".join(s + "\n" for s in stdin), stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
            got = r.stdout
            words = [a for a in argv[3:] if not a.startswith("-")]
            if words:
                seen.add(" ".join(words[:2]) if words[0] in ("budget", "category") else words[0])
            has_error |= "[오류]" in got
        elif len(argv) == 2 and argv[0] == "cat":
            want = "".join(ln + "\n" for ln in out_lines)
            p = os.path.join(work, argv[1])
            got = open(p, encoding="utf-8").read() if os.path.isfile(p) else f"(파일 없음: {argv[1]})\n"
        else:
            need(False, f"README console 블록에 재생할 수 없는 명령: {cmd}")
            continue
        nrun += 1
        if got != want or "Traceback" in got:
            ok = False
            print(f"FAIL README 예시 출력이 실제와 다름: $ {cmd}")
            sys.stdout.writelines(difflib.unified_diff(want.splitlines(True), got.splitlines(True), "README", "실제"))
must = {"add", "list", "search", "summary", "budget set", "category add", "category list", "category remove",
        "update", "delete", "import", "export"}
need(must <= seen, f"README 예시에 빠진 명령: {sorted(must - seen)}")
need(has_error, "README 예시에 [오류] 출력 예가 없음")
print(f"  README 예시 {nrun}개 재생")
print("README_OK" if ok else "README_FAIL")
sys.exit(0 if ok else 1)
PY

# ======================= R. 3단계 회귀 (3단계 스크립트가 1·2단계도 다시 실행) =======================
# 3단계 설계서 6.2 스크립트를 꺼내 4단계에서 바뀐 부분만 고친다: 임시 폴더 위치, 이번에 바뀐 파일의 해시,
# @handle_errors 개수(10→12)와 _cmd_* 목록, import/export 미등록 검사, 최상위 명령 목록.
python3 - <<'PY' || FAIL=1
import os
W = os.environ["W"]
FENCE = "`" * 3
sec = open("docs/plans/step3-search-summary-budget.md", encoding="utf-8").read().split("### 6.2", 1)[1]
s3 = sec.split(FENCE + "bash\n", 1)[1].split(FENCE, 1)[0]
reps = [
    ('cd "/Users/khm04/codessey/pocket money" || exit 1', 'cd "$ROOT" || exit 1'),
    ('W="$(mktemp -d)"; export W', 'W="$(mktemp -d "$W/s3.XXXXXX")"; export W'),
    ("63a3d4493da74f683b4673050497238b7a1f59fce598673383e48d59816a77a5  budget_app/storage.py\n", ""),
    ("775389d5609a7243ab96a9c0b0365ea93546c61055b5c6b254894a49a3b3a096  budget_app/decorators.py\n", ""),
    ('= 10 ] || fail "S7 @handle_errors 개수 != 10"', '= 12 ] || fail "S7 @handle_errors 개수 != 12"'),
    ('"_cmd_summary", "_cmd_budget_set"}', '"_cmd_summary", "_cmd_budget_set", "_cmd_import", "_cmd_export"}'),
    ('out_has "{add,list,search,summary,budget,update,delete,category}"',
     'out_has "{add,list,search,summary,budget,update,delete,category,import,export}"'),
]
for old, new in reps:
    assert s3.count(old) == 1, f"3단계 스크립트에서 찾지 못함: {old!r}"
    s3 = s3.replace(old, new)
lines = s3.split("\n")
idx = [i for i, l in enumerate(lines) if 'fail "S9 import/export 등록됨"' in l]
assert len(idx) == 1, "3단계 S9 줄을 찾지 못함"
lines[idx[0]] = ": # S9: 4단계부터 import/export 가 등록되므로 검사하지 않음"
open(os.path.join(W, "step3.sh"), "w", encoding="utf-8").write("\n".join(lines))
PY
bash "$W/step3.sh" >"$W/r3" 2>&1
if grep -qx "STEP3_ALL_OK" "$W/r3" && ! grep -q "^FAIL" "$W/r3"; then :; else echo "FAIL 3단계 회귀 (1·2단계 포함)"; cat "$W/r3"; FAIL=1; fi

# ======================= 마무리 =======================
[ ! -e data ] || fail "프로젝트 루트에 ./data 가 생김"
if find budget_app -name __pycache__ | grep -q .; then fail "__pycache__ 생김"; fi
python3 - <<'PY' || FAIL=1
import os
allowed = {".claude", ".DS_Store", ".git", ".gitignore", "README.md", "REQUIREMENTS.md", "budget_app", "docs"}
extra = sorted(n for n in os.listdir(".") if n not in allowed and not n.endswith(".pdf"))
if extra:
    print("FAIL 프로젝트 루트에 예상 밖 파일:", extra)
raise SystemExit(1 if extra else 0)
PY
[ "$FAIL" = 0 ] && echo "STEP4_ALL_OK"
```

기대 출력: `FAIL` 로 시작하는 줄 없음, `SAFETY_OK`, `SIGNAL_OK`(앞에 SIGKILL 뒤 남은 임시 파일 개수 안내 1줄), 메모리 측정값 6줄과 `IO_MEMORY_OK`, `README 예시 N개 재생`과 `README_OK`, 마지막 줄 `STEP4_ALL_OK`. 스크립트가 끝나면 `$W` 가 지워져 있어야 한다(`trap`).

참고(설계 시 실측, Python 3.14): 이 설계대로 만든 시험 구현(임시 폴더에서만 만들고 지움)으로 이 스크립트 전체가 `STEP4_ALL_OK` 로 끝나는 것(약 50초, 3단계 회귀 포함)과, 결함을 일부러 넣으면(CSV 를 `list(reader)` 로 읽기, import 를 추가 모드로 바로 쓰기, README 출력 한 글자 바꾸기) S8·F·G·M·N 이 각각 `FAIL` 을 내는 것을 확인했다. tracemalloc 최대 메모리는 import·export 모두 1만 행·10만 행에서 약 0.51MB 로 같았고, 대조군(`list(csv.reader)`)은 약 4.3MB → 42MB 로 행 수에 비례해 늘었다. 10만 행 import 는 tracemalloc 없이 약 1.3초, 켠 상태에서 약 9초 걸린다.

## 7. 총괄 확인 필요

1. **건너뛴 행 알림**: PDF 8장 출력(`[완료] imported=5, skipped=0`)만 근거로 삼아 **개수만** 세고 행 번호·이유는 출력하지 않기로 했다. 사용자가 어느 행이 왜 빠졌는지 알 수 없다는 단점이 있다. 대안은 건너뛴 행마다 stderr 에 `[건너뜀] 5번째 줄: 등록되지 않은 카테고리 'hobby'` 를 출력하는 것이다(출력 형식이 PDF 예시보다 늘어남).
2. **export 조건 조합**: `--from`/`--to` 는 PDF 가 한 묶음(`--from YYYY-MM-DD --to YYYY-MM-DD`)으로 적어 **둘 다 있어야** 하도록 했다(한쪽만 주면 오류 1). search 는 한쪽만 허용하므로 두 명령의 규칙이 다르다. `--month` 와 `--from/--to` 를 함께 주면 "중 하나 이상" 문구에 따라 허용하고 **둘 다 만족(AND)** 하는 거래만 내보낸다. 한쪽만 허용하거나, 함께 주는 것을 오류로 막기를 원하면 알려 달라.
3. **export 행 순서와 0건 동작**: PDF 에 순서 규칙이 없어 거래 파일에 저장된 순서(추가한 순서) 그대로 쓴다(스트리밍 유지, 메모리 일정). 최신순·날짜순으로 원하면 search 처럼 매칭 결과를 모아 정렬해야 해 메모리가 매칭 건수에 비례하게 된다. 0건이면 헤더만 있는 파일을 만들고 `(0 records)` 를 출력한다(파일을 만들지 않는 방법도 가능).
4. **`--out` 경로 처리**: 이미 있는 파일은 **덮어쓰지 않고 오류**, 출력 폴더가 없으면 **만들지 않고 오류**로 정했다(데이터 안전 우선, `--force` 같은 옵션은 추가 금지). 같은 파일 이름으로 다시 내보내려면 사용자가 기존 파일을 먼저 옮기거나 지워야 한다. 덮어쓰기를 원하면 알려 달라(그래도 임시 파일 + `os.replace` 라 쓰기 도중 실패 시 기존 파일은 남는다).
5. **import 행 모양 규칙**: 칸 수가 헤더와 다른 행은 모두 건너뛴다(칸이 모자란 행도). 끝 쪽 선택 컬럼을 생략한 행(`2024-01-01,expense,food,1000` 을 6칸 헤더 아래에 둠)도 skipped 가 된다. 빈 줄은 세지 않는다. 스키마 밖 컬럼은 PDF "최소 스키마" 문구에 따라 무시한다.
6. **import 인코딩**: UTF-8 BOM 이 붙은 파일(엑셀의 "CSV UTF-8" 저장)도 받는다(`utf-8-sig`). export 는 BOM 없는 UTF-8 이라, 윈도 엑셀에서 바로 열면 한글이 깨져 보일 수 있다(스키마가 "UTF-8" 만 정하므로 BOM 을 붙이지 않았다).
7. **decorators.py 문구 변경**: `OSError` 힌트가 `--data-dir` 만 가리켜 import/export 경로 오류에 맞지 않아 `경로(--data-dir, --from, --out)…` 로 바꾸기로 했다(3.7). 1~3단계 회귀 검사는 문구를 비교하지 않아 영향이 없다.
