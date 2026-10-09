# 2단계 설계서: 데코레이터 + CLI 뼈대 + 서비스(일부) + category / add / list / update / delete

## 1. 목표

- `python -m budget_app <command> [options]`로 실행되는 argparse CLI 뼈대를 만들고, 명령 `category add/list/remove`, `add`, `list`, `update`, `delete`를 끝까지 동작시킨다.
- 업무 규칙(미등록 카테고리 거부, 카테고리 이름 규칙, 사용 중 카테고리 삭제 차단, 없는 id 처리, 최신순 상위 N개)은 `services.py`에 둔다. 공통 예외 처리는 `decorators.py`의 데코레이터 하나로 모든 명령 핸들러에 적용한다.
- search, summary, budget, import, export, README는 이번 단계에서 만들지 않고 서브커맨드로 등록하지도 않는다(3·4단계).

## 2. 대상 요구사항

| REQUIREMENTS.md 항목 | 이번 단계 충족 범위 |
| --- | --- |
| 0장 실행 방식 `python -m budget_app <command> [options]` | 전체 (`__main__.py`) |
| 0장 모든 명령에 `--help`, 옵션은 `--` 형식 | 이번 단계 명령 전부 (하위 명령 `category add/list/remove` 포함) |
| 1장 입력 검증 4종 (날짜/금액/type/미등록 category) | add(재입력), update(오류 메시지) |
| 2장 `--data-dir` 옵션, 기본 `./data`, 파일 자동 생성 | 전체 |
| 3장 #1 add | 전체 |
| 3장 #2 list | 전체 |
| 3장 #6 category add/list/remove, 사용 중 삭제 차단 | 전체 |
| 3장 #7 update (옵션식), #8 delete | 전체 |
| 3장 "최신순" 정의, 카테고리 이름 규칙, 태그 쉼표 구분 | 전체 |
| 4장 제너레이터 | list가 `iter_transactions()`를 스트리밍 소비 (전체 리스트화·전체 정렬 금지) |
| 4장 데코레이터 | `handle_errors` 1개 구현 + 모든 명령 핸들러에 적용 |
| 4장 예외 처리(스택트레이스 금지, 원인+힌트), 종료 코드 | 전체. 1단계 검토 이월 과제(원시 `OSError`, `UnicodeDecodeError`, Ctrl+C, EOF) 포함 |
| 4장 타입 힌트, 모듈화(4계층) | 새 파일 4개 전부 |

## 3. 파일/모듈 설계

### 3.0 공통 결정 (이번 단계에서 고정)

| 항목 | 결정 | 근거 |
| --- | --- | --- |
| `--data-dir` 위치 | **명령 뒤(마지막 하위 명령 뒤)** 에만 둔다. 예: `list --data-dir X`, `category add --data-dir X`. `--data-dir X list`(명령 앞)는 argparse 사용법 오류(종료 코드 2)가 된다. 구현: `--data-dir`만 가진 부모 파서(`add_help=False`)를 만들어 **말단 서브파서마다** `parents=[...]`로 붙인다. 최상위 파서와 중간 파서(`category`)에는 붙이지 않는다. | ← 0장 `python -m budget_app <command> [options]` (옵션은 명령 뒤), 2장 `--data-dir` |
| `--data-dir` 기본값 | `storage.DEFAULT_DATA_DIR` (`"data"`, 즉 현재 폴더 기준 `./data`). CLI는 storage를 직접 import하지 않으므로 `services.DEFAULT_DATA_DIR`로 재노출한 값을 쓴다. | ← 2장 기본 폴더 |
| `list --limit` 기본값 | `20` | ← 3장 #2 "기본값 있음, 예: 20" |
| 출력 스트림 | 정상 결과·프롬프트는 stdout, `[오류]`/`[힌트]` 두 줄은 **stderr** | ← 4장 예외 처리 (총괄 확인 필요 #2) |
| 종료 코드 | 정상 `0`. 앱 오류(검증 실패, 없는 id, 없는 카테고리, 사용 중 카테고리 삭제 차단, 파일 오류, Ctrl+C, EOF, 예상 못한 예외) `1`. argparse 사용법 오류(없는 명령, 필수 옵션 누락, 알 수 없는 옵션) `2`(argparse 관례 유지). | ← 4장 종료 코드 "정상 0, 오류 0 아닌 값" (총괄 확인 필요 #1) |
| 입력 방식 | `add`, `category add`, `category remove`는 대화형(`input()`). `list`, `update`, `delete`는 옵션식. | ← 3장 #1, #6, #7 [결정 안 A], #8, 3장 하단 "category add 는 대화형 (4장 1번 옵션 허용 목록에 category 없음)" |
| `category remove` 입력 방식 | **대화형** `카테고리명: ` 한 줄 입력. PDF 4장 1번은 입력 기본 방식을 "대화형"으로 정하고, 옵션 인자 방식 허용 목록을 `search, list, summary, export, import, delete`(+update 선택)로 한정한다. `category`는 이 목록에 없으므로 add와 같은 근거로 remove도 대화형이다. | ← PDF 4장 1번, 3장 #6 |
| 메모 입력 | 입력값의 앞뒤 공백만 제거해 저장. 빈 값 허용. | ← 1장 memo "선택 (빈 문자열 가능)" |
| 태그 입력 | 쉼표로 나누고 각 조각의 앞뒤 공백을 제거, 빈 조각은 버린다. 빈 입력은 `[]`. 중복 제거·순서 변경은 하지 않는다. | ← 3장 하단 "태그 입력: 쉼표(,) 구분", 1장 tags |
| 도움말 옵션 (검토 반영) | argparse 기본 `-h` 를 쓰지 않는다. 모든 파서를 `add_help=False` 로 만들고 `--help` 만 붙인다. `-h` 는 사용법 오류(2). | ← 0장 "옵션은 모두 `--` 형식", PDF 4장 1번 |
| 옵션 약어 (검토 반영) | 모든 파서에 `allow_abbrev=False`. `--cat`, `--lim` 같은 줄임 표기는 사용법 오류(2). 문서에 적힌 철자만 허용한다. | ← 0장 옵션 규칙 |
| 사용법 오류 문구 (검토 반영) | 서브파서에 metavar 를 지정해 `category_command` 같은 내부 변수 이름이 오류 메시지에 드러나지 않게 한다. | ← 4장 예외 처리 "원인 + 해결 힌트" |
| EOF 출력 (검토 반영) | Ctrl+C 와 같이 `[오류]` 앞에 빈 줄 하나를 출력해 프롬프트 줄과 분리한다. | ← 4장 예외 처리 |

### 3.1 `budget_app/__main__.py` — [진입점]

import 허용: `sys`는 쓰지 않아도 된다. `budget_app.cli`의 `main`만 import한다.

```python
from budget_app.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
```
- 다른 코드는 두지 않는다. ← 0장 실행 방식

### 3.2 `budget_app/decorators.py` — [공통 관심사]

import 허용: 표준 라이브러리(`functools`, `sys`, `collections.abc`, `typing`)와 `budget_app.models`(`BudgetAppError`만).

| 시그니처 | 책임 | 근거 |
| --- | --- | --- |
| `EXIT_OK: int = 0`, `EXIT_ERROR: int = 1` | 종료 코드 상수. 핸들러는 성공 시 `EXIT_OK`를 반환한다. | ← 4장 종료 코드 |
| `P = ParamSpec("P")` | 데코레이터가 감싼 함수의 매개변수 타입을 보존한다(`typing.ParamSpec`, 3.10+). | ← 4장 타입 힌트 |
| `def print_error(cause: str, hint: str) -> None` | stderr에 `[오류] {cause}`와 `[힌트] {hint}` 두 줄을 출력한다. 데코레이터와 CLI의 재입력 안내가 같은 형식을 쓰도록 한 곳에 둔다. | ← 4장 예외 처리 "원인 + 해결 힌트", PDF 8장 오류 출력 예시 |
| `def handle_errors(func: Callable[P, int]) -> Callable[P, int]` | 명령 핸들러를 감싸는 데코레이터. `functools.wraps`를 쓴다. 내부 `def wrapper(*args: P.args, **kwargs: P.kwargs) -> int:`가 `func`를 호출해 반환값을 그대로 돌려주고, 아래 표의 예외를 잡아 `print_error` 후 `EXIT_ERROR`를 반환한다. **추가 출력(실행 시간, 로그 등)은 하지 않는다.** | ← 4장 데코레이터, 예외 처리, 종료 코드 |

`handle_errors`가 잡는 예외 (위에서부터 순서대로 `except`):

| 예외 | cause | hint |
| --- | --- | --- |
| `KeyboardInterrupt` | 먼저 stderr에 빈 줄 하나를 출력한 뒤(프롬프트 줄을 끊기 위함) `"사용자가 입력을 중단했습니다 (Ctrl+C)"` | `"저장되지 않았습니다. 명령을 처음부터 다시 실행하세요"` |
| `EOFError` | `"입력이 끝나 더 읽을 값이 없습니다 (EOF)"` | `"모든 항목을 입력하세요. 표준입력으로 넣을 때는 항목마다 한 줄씩 넣으세요"` |
| `BudgetAppError` (`ValidationError` 포함) | `e.cause` | `e.hint` |
| `UnicodeDecodeError` | `f"UTF-8 로 읽을 수 없는 데이터가 있습니다 ({e.reason})"` | `"--data-dir 폴더의 .jsonl 파일과 입력이 UTF-8 인코딩인지 확인하세요"` |
| `OSError` (`PermissionError`, `IsADirectoryError`, `FileNotFoundError` 등 전부) | `f"파일을 읽거나 쓸 수 없습니다: {e.filename} ({e.strerror})"`. `e.filename`이 `None`이면 `f"파일을 읽거나 쓸 수 없습니다: {e}"` | `"--data-dir 경로가 올바른지, 해당 파일·폴더에 읽기/쓰기 권한이 있는지 확인하세요"` |
| `Exception` (최후 수단) | `f"예상하지 못한 오류가 발생했습니다: {type(e).__name__}: {e}"` | `"입력값과 --data-dir 폴더의 파일을 확인한 뒤 다시 실행하세요"` (총괄 확인 필요 #6) |

- `SystemExit`는 잡지 않는다(`Exception` 하위가 아님). 
- `KeyboardInterrupt`는 `Exception` 하위가 아니므로 반드시 별도 `except`로 잡는다.
- `UnicodeDecodeError`는 `ValueError` 하위, `OSError`와 겹치지 않는다. 둘 다 `Exception`보다 먼저 둔다.

### 3.3 `budget_app/services.py` — [서비스]

import 허용: 표준 라이브러리(`dataclasses`, `heapq`, `os`, `re`, `collections.abc`, `typing`), `budget_app.storage`, `budget_app.models`. `print`/`input`은 쓰지 않는다(입출력은 CLI 책임).

#### 모듈 상수 / 함수

| 시그니처 | 책임 | 근거 |
| --- | --- | --- |
| `DEFAULT_DATA_DIR` | `from budget_app.storage import DEFAULT_DATA_DIR`로 재노출. CLI의 `--data-dir` 기본값. | ← 2장 기본 폴더 `./data` |
| `DEFAULT_LIST_LIMIT: int = 20` | list 기본 개수 | ← 3장 #2 |
| `_LIMIT_RE = re.compile(r"[0-9]+")` | `--limit` 값 검사용(`fullmatch`, ASCII 숫자만) | ← 3장 #2 |
| `def parse_limit(value: str) -> int` | `strip` 후 `_LIMIT_RE.fullmatch`를 통과하고 1 이상이면 `int`를 반환. 아니면 `ValidationError(cause=f"--limit 값이 올바르지 않습니다: {value!r}", hint="--limit 에는 1 이상의 정수를 입력하세요 (예: --limit 20)")`. `"0"`, `"-1"`, `"abc"`, `"1.5"`, `""` 거부. | ← 3장 #2 `--limit N` |
| `def parse_tags(value: str) -> list[str]` | `[t.strip() for t in value.split(",") if t.strip()]`. 실패하지 않는다. `" a , ,b "` → `["a", "b"]`, `""` → `[]`. | ← 3장 하단 태그 쉼표 구분, 1장 tags |
| `def normalize_category_name(value: str) -> str` | `strip`한 값을 반환. 결과가 빈 문자열이면 `ValidationError(cause="카테고리 이름이 비어 있습니다", hint="한 글자 이상의 카테고리 이름을 입력하세요")`. 대소문자는 바꾸지 않는다. | ← 3장 하단 카테고리 이름 규칙(빈 이름 거부, 앞뒤 공백 제거, 대소문자 구분) |
| `def _recency_key(tx: Transaction) -> tuple[str, int]` | `(tx.date, tx_id_seq(tx.id))`. date는 `YYYY-MM-DD`라 문자열 비교가 날짜 순서와 같다. id는 문자열이 아닌 숫자로 비교한다(`TX-1000000` > `TX-999999`). | ← 3장 "최신순" 정의 |

#### `class LedgerService`

거래·카테고리·예산 저장소를 묶어 업무 규칙을 적용한다. ← 1장 클래스 2개 이상, 4장 모듈화(서비스 계층)

| 시그니처 | 책임 | 근거 |
| --- | --- | --- |
| `def __init__(self, data_dir: str \| os.PathLike[str]) -> None` | `self.transactions = TransactionRepository(data_dir)`, `self.categories = CategoryStore(data_dir)`, `self.budgets = BudgetStore(data_dir)`를 이 순서로 만든다. `BudgetStore`는 이번 단계 명령에서 쓰지 않지만, 어떤 명령을 실행해도 저장 파일 3개가 자동 생성되도록 여기서 만든다. | ← 2장 파일 3개, 자동 생성, `--data-dir` |
| `def list_categories(self) -> list[str]` | `self.categories.list_names()` 반환 | ← 3장 #6 category list |
| `def validate_new_category(self, name: str) -> str` | `normalize_category_name(name)` 후 이미 있으면(`exists`, 대소문자 구분) `ValidationError(cause=f"이미 있는 카테고리입니다: {n!r}", hint="category list 로 목록을 확인하고 다른 이름을 입력하세요")`. 통과하면 정리된 이름 반환. 저장하지 않는다. | ← 3장 #6, 이름 규칙(중복 거부) |
| `def add_category(self, name: str) -> str` | `validate_new_category(name)`로 다시 확인한 뒤 `self.categories.add(n)`, 저장한 이름 반환 | ← 3장 #6 category add |
| `def validate_category(self, name: str) -> str` | 거래에 쓸 카테고리 확인. `strip` 후 등록되어 있으면 그 값을 반환. 비었거나 미등록이면 `ValidationError(cause=f"등록되지 않은 카테고리입니다: {name.strip()!r}", hint=f"등록된 카테고리: {', '.join(names)} (새 카테고리는 category add 로 먼저 추가하세요)")`. | ← 1장 입력 검증 #4, PDF 4장 4번 "없으면 안내 후 재입력/등록 유도" |
| `def remove_category(self, name: str) -> str` | `normalize_category_name(name)` → 미등록이면 `BudgetAppError(cause=f"등록되지 않은 카테고리입니다: {n!r}", hint="category list 로 이름을 확인하세요 (대소문자 구분)")`. `self.transactions.is_category_used(n)`이 참이면 `BudgetAppError(cause=f"사용 중인 카테고리는 삭제할 수 없습니다: {n!r}", hint="이 카테고리를 쓰는 거래를 update --category 로 바꾸거나 delete 로 삭제한 뒤 다시 시도하세요")`를 던지고 **`remove`를 호출하지 않는다**. 통과하면 `self.categories.remove(n)` 후 이름 반환. | ← 3장 #6 remove, 사용 중 삭제 차단 [결정] |
| `def add_transaction(self, date: str, type_: str, category: str, amount: int, memo: str, tags: list[str]) -> Transaction` | `validate_category(category)`로 다시 확인(프롬프트와 저장 사이 변경 대비), `self.transactions.issue_id()`로 id 발급, `Transaction(...)` 생성(`__post_init__` 검증), `append` 후 반환. | ← 3장 #1 add, 1장 id 유일 |
| `def recent_transactions(self, limit: int) -> list[Transaction]` | `heapq.nlargest(limit, self.transactions.iter_transactions(), key=_recency_key)`를 반환. 제너레이터를 한 건씩 소비하면서 크기 `limit`의 힙만 유지하므로 메모리에는 최대 `limit`건만 남는다. 반환 리스트는 이미 최신순이다. **`list(iter_transactions())`, `sorted(...)`, `.sort()`로 전체를 모으지 않는다.** | ← 3장 #2 최신순·스트리밍, 3장 "최신순" 정의, 4장 제너레이터 |
| `def update_transaction(self, tx_id: str, *, date: str \| None, type_: str \| None, category: str \| None, amount: str \| None, memo: str \| None, tags: str \| None) -> Transaction` | 아래 "update 처리 순서"를 따른다. 성공 시 수정된 거래 반환. | ← 3장 #7 [결정 안 A], 1장 입력 검증 |
| `def delete_transaction(self, tx_id: str) -> str` | `tx_id.strip()`으로 `self.transactions.delete(...)`. `False`면 `_not_found(tx_id)`를 던진다. 성공 시 id 반환. | ← 3장 #8 delete, 없는 id |
| `def _not_found(tx_id: str) -> BudgetAppError` (모듈 함수) | `BudgetAppError(cause=f"없는 데이터입니다: id={tx_id.strip()}", hint="list 로 거래 id 를 확인한 뒤 다시 시도하세요")` 객체를 만든다. | ← PDF 4장 6번 "없는 id는 '없는 데이터'로 처리", 3장 #7·#8 |

**update 처리 순서** ← 3장 #7

1. 여섯 옵션이 모두 `None`이면 `ValidationError(cause="수정할 항목이 없습니다", hint="--date, --type, --category, --amount, --memo, --tags 중 하나 이상을 지정하세요")`. (id 조회 전에 검사)
2. 주어진 옵션만 검증·정리해 `changes: dict[str, Any]`에 담는다: `date`→`validate_date`, `type`→`validate_type`, `category`→`self.validate_category`, `amount`→`parse_amount`, `memo`→`memo.strip()`, `tags`→`parse_tags`. 하나라도 틀리면 해당 `ValidationError`가 그대로 나간다(파일 변경 없음). `--memo ""`는 메모 비우기, `--tags ""`는 태그 비우기다.
3. `self.transactions.get(tx_id.strip())`가 `None`이면 `_not_found`.
4. `dataclasses.replace(existing, **changes)`로 새 거래를 만들고(`__post_init__` 재검증) `self.transactions.update(new)`. `False`(그 사이 삭제됨)면 `_not_found`. `True`면 `new` 반환.

- id 형식 검사(`tx_id_seq`)는 하지 않는다. 형식이 틀린 id도 "없는 데이터"로 처리한다. ← PDF 4장 6번

### 3.4 `budget_app/cli.py` — [CLI]

import 허용: 표준 라이브러리(`argparse`, `collections.abc`, `typing`), `budget_app.services`, `budget_app.decorators`, `budget_app.models`(`ValidationError`, `Transaction`, `validate_date`, `validate_type`, `parse_amount`만). **`budget_app.storage`는 import하지 않는다.**

| 시그니처 | 책임 | 근거 |
| --- | --- | --- |
| `PROG: str = "python -m budget_app"` | 파서 `prog`. 3.10과 3.14의 기본 prog 표시가 달라 고정한다. | ← 0장 실행 방식, `--help` |
| `T = TypeVar("T")` | `_prompt` 반환 타입용 | ← 4장 타입 힌트 |
| `class _ArgumentParser(argparse.ArgumentParser)` + `def error(self, message: str) -> NoReturn` | argparse 사용법 오류를 `print_error(message, f"{self.prog} --help 로 사용법을 확인하세요")`로 출력하고 `self.exit(2)`. `add_subparsers`는 기본적으로 부모 파서 클래스를 쓰므로 하위 파서에도 적용된다. | ← 4장 예외 처리(원인+힌트), 종료 코드 |
| `def build_parser() -> argparse.ArgumentParser` | 아래 "명령 구성"대로 파서를 만든다. 각 말단 파서에 `set_defaults(handler=...)`. 서브파서는 `add_subparsers(dest=..., required=True)`(3.10에서 `required=True`는 `dest`가 있어야 안전). 3.11+ 전용 인자(`color`, `suggest_on_error`)는 쓰지 않는다. | ← 0장, 3장 |
| `def main(argv: list[str] \| None = None) -> int` | `args = build_parser().parse_args(argv)`, `return args.handler(args)`. | ← 0장 실행 방식, 4장 종료 코드 |
| `def _prompt(label: str, parse: Callable[[str], T]) -> T` | `raw = input(label)` → `parse(raw)` 반환. `ValidationError`만 잡아 `print_error(e.cause, e.hint)` 후 같은 항목을 다시 묻는다. 그 외 예외(`BudgetAppError` 파일 손상, `EOFError`, `KeyboardInterrupt`)는 그대로 올려 데코레이터가 처리한다. | ← 1장 입력 검증 "재입력 요구", PDF 4장 4번 |
| `def _format_tx(tx: Transaction) -> str` | `f"{tx.id} \| {tx.date} \| {tx.type} \| {tx.category} \| {tx.amount} \| {tx.memo}".rstrip()` (메모가 비면 `... \| 3000000 \|`로 끝남). 태그는 표시하지 않는다(총괄 확인 필요 #4). | ← 3장 #2, PDF 8장 list 예시 |
| `@handle_errors def _cmd_add(args: argparse.Namespace) -> int` | `service = LedgerService(args.data_dir)` 후 순서대로 입력: `_prompt("날짜(YYYY-MM-DD): ", validate_date)`, `_prompt("타입(income/expense): ", validate_type)`, `_prompt("카테고리: ", service.validate_category)`, `_prompt("금액(양수): ", parse_amount)`, `input("메모(선택): ").strip()`, `parse_tags(input("태그(쉼표로 구분, 없으면 엔터): "))`. `service.add_transaction(...)` 후 `[저장 완료] id={tx.id}` 출력, `EXIT_OK`. | ← 3장 #1, PDF 8장 add 예시 |
| `@handle_errors def _cmd_list(args: argparse.Namespace) -> int` | `limit = DEFAULT_LIST_LIMIT if args.limit is None else parse_limit(args.limit)`. `service.recent_transactions(limit)`의 각 거래를 `_format_tx`로 출력. 결과가 없으면 `거래 내역이 없습니다.` 출력. `EXIT_OK`. | ← 3장 #2 |
| `@handle_errors def _cmd_update(args: argparse.Namespace) -> int` | `service.update_transaction(args.id, date=args.date, type_=args.type, category=args.category, amount=args.amount, memo=args.memo, tags=args.tags)` 후 `[수정 완료] id={tx.id}`. | ← 3장 #7 |
| `@handle_errors def _cmd_delete(args: argparse.Namespace) -> int` | `service.delete_transaction(args.id)` 후 `[삭제 완료] id={id}`. | ← 3장 #8 |
| `@handle_errors def _cmd_category_add(args: argparse.Namespace) -> int` | `name = _prompt("카테고리명: ", service.validate_new_category)` → `service.add_category(name)` → `[저장 완료] category={name}`. 빈 이름·중복 이름은 `[오류]/[힌트]` 후 다시 묻는다. | ← 3장 #6, 이름 규칙, PDF 8장 category 예시 |
| `@handle_errors def _cmd_category_list(args: argparse.Namespace) -> int` | `service.list_categories()`를 한 줄에 하나씩 `- {name}`으로 출력. | ← 3장 #6, PDF 8장 category list 예시 |
| `@handle_errors def _cmd_category_remove(args: argparse.Namespace) -> int` | `name = _prompt("카테고리명: ", normalize_category_name)`(빈 이름만 재입력) → `service.remove_category(name)` → `[삭제 완료] category={name}`. 미등록·사용 중이면 예외가 데코레이터로 가서 종료 코드 1. | ← 3장 #6 remove, 사용 중 차단 |

- `LedgerService(...)` 생성은 반드시 **데코레이터가 적용된 핸들러 안**에서 한다(`--data-dir` 오류도 `[오류]/[힌트]`로 바뀌도록). `--help`와 argparse 오류는 핸들러 전에 끝나므로 data 폴더를 만들지 않는다.

#### 명령 구성 (help 문구는 한국어 한 줄)

```
python -m budget_app {add,list,update,delete,category} ...
  add                         [--data-dir DIR]                  거래 추가 (대화형)
  list    [--limit N]         [--data-dir DIR]                  최신순 거래 목록 (기본 20건)
  update  --id ID [--date D] [--type T] [--category C] [--amount A] [--memo M] [--tags T]
                              [--data-dir DIR]                  거래 수정 (옵션식)
  delete  --id ID             [--data-dir DIR]                  거래 삭제
  category {add,list,remove}                                    카테고리 관리
    category add              [--data-dir DIR]                  카테고리 추가 (대화형)
    category list             [--data-dir DIR]                  카테고리 목록
    category remove           [--data-dir DIR]                  카테고리 삭제 (대화형, 사용 중이면 차단)
```

- `--data-dir`: `default=DEFAULT_DATA_DIR`, help `"데이터 폴더 경로 (기본값: ./data)"`. 모든 말단 파서에 부모 파서로 붙인다.
- `--limit`, `update`의 값 옵션은 **`type`을 지정하지 않고 문자열로 받는다**(`default=None`). 값 검증은 서비스가 `ValidationError`로 하여 `[오류]/[힌트]` + 종료 코드 1로 통일한다. `--id`는 `required=True`.
- `update --tags` help: `"쉼표(,)로 구분한 태그. 빈 문자열이면 태그를 모두 지움"`. `--memo` help: `"메모. 빈 문자열이면 메모를 지움"`.
- search, summary, budget, import, export는 등록하지 않는다(입력 시 argparse `invalid choice` → 종료 코드 2).

## 4. 계층 규칙

```
__main__.py → cli.py → services.py → storage.py → models.py
                 └──→ decorators.py ──→ models.py
```

| 모듈 | import 가능한 `budget_app` 모듈 |
| --- | --- |
| `models.py` | 없음 |
| `storage.py` | `models` |
| `services.py` | `storage`, `models` |
| `decorators.py` | `models` (`BudgetAppError`만) |
| `cli.py` | `services`, `decorators`, `models` (예외·`Transaction`·검증 함수) — **`storage` 금지** |
| `__main__.py` | `cli` |

- 역방향(아래 계층이 위 계층을 import)과 `services`/`storage`/`models`의 `decorators` import는 금지한다.
- `print`와 `input`은 `cli.py`와 `decorators.py`에만 있다.
- 상대 import(`from . import`)는 쓰지 않고 `from budget_app.xxx import ...` 형태로 쓴다(검사 스크립트 기준).

## 5. 예외/경계 상황

| 상황 | 처리 | 종료 코드 |
| --- | --- | --- |
| add 중 잘못된 날짜/타입/금액, 미등록·빈 카테고리 | `[오류]/[힌트]`(stderr) 후 **그 항목만** 다시 묻는다 | (계속 진행) |
| category add 중 빈 이름·중복 이름 | `[오류]/[힌트]` 후 다시 묻는다. 앞뒤 공백은 제거해 저장, 대소문자 구분(`Food` ≠ `food`) | (계속 진행) |
| category remove 중 빈 이름 | `[오류]/[힌트]` 후 다시 묻는다 | (계속 진행) |
| category remove: 미등록 이름 / 사용 중 | `[오류]/[힌트]`, 파일 변경 없음 | 1 |
| 대화형 입력 중 EOF (입력 부족) | `[오류] 입력이 끝나 …(EOF)` + 힌트. 거래·카테고리 저장 안 됨 | 1 |
| 대화형 입력 중 Ctrl+C | 빈 줄 + `[오류] 사용자가 입력을 중단했습니다 (Ctrl+C)` + 힌트. 저장 안 됨 | 1 |
| list: 거래 없음 | `거래 내역이 없습니다.` | 0 |
| list: `--limit` 0/음수/숫자 아님 | `[오류]/[힌트]` | 1 |
| list: 같은 날짜 여러 건 | id 숫자 내림차순 (`TX-1000000`이 `TX-999999`보다 먼저) | 0 |
| update: 바꿀 옵션 없음 | `[오류] 수정할 항목이 없습니다` (id 존재 여부 확인 전) | 1 |
| update: 값 오류(날짜/타입/금액/미등록 카테고리) | `[오류]/[힌트]`, 파일 변경 없음 | 1 |
| update/delete: 없는 id(형식이 틀린 id 포함) | `[오류] 없는 데이터입니다: id=…`, 파일 변경 없음 | 1 |
| update/delete: `--id` 누락, 알 수 없는 옵션, 등록 안 된 명령, 명령 없음 | argparse 메시지를 `[오류]`로, 힌트 `… --help 로 사용법을 확인하세요` | 2 |
| `--data-dir`를 명령 앞에 둠 | argparse 오류(최상위 파서에 없는 옵션) | 2 |
| `--data-dir`가 파일 경로 | 1단계 `_ensure_file`의 `BudgetAppError` | 1 |
| 저장 파일이 폴더(`IsADirectoryError`), 권한 없음(`PermissionError`), 기타 `OSError` | `[오류] 파일을 읽거나 쓸 수 없습니다: …` + 힌트 | 1 |
| 저장 파일이 UTF-8 아님(`UnicodeDecodeError`) | `[오류] UTF-8 로 읽을 수 없는 데이터가 있습니다 …` + 힌트 | 1 |
| 저장 파일 손상 줄 | 1단계 `BudgetAppError`(파일 경로·줄 번호) | 1 |
| 어떤 경우에도 | `Traceback` 출력 없음 | — |

### Python 3.10 호환 주의 (로컬은 3.14)

- 1단계 금지 목록(`fromisoformat`, `typing.Self`, `datetime.UTC`, `except*`, `ExceptionGroup`, `tomllib`, PEP 695 문법)을 새 파일에도 적용한다.
- `argparse.ArgumentParser(color=..., suggest_on_error=...)`(3.14 전용)는 쓰지 않는다.
- `ParamSpec`는 `typing`에서 import한다(3.10+). `Callable[P, int]`는 `collections.abc.Callable`로 써도 된다. `NoReturn`은 `typing`에서 import한다.

## 6. 완료 기준 (에이전트 3 검증 절차)

모든 명령은 프로젝트 루트에서 실행하고, data는 `mktemp -d` 스크래치 폴더만 쓴다. `PYTHONDONTWRITEBYTECODE=1`을 켜서 `__pycache__`를 남기지 않는다.

### 6.1 정적 검사

```bash
cd "/Users/khm04/codessey/pocket money"
export PYTHONDONTWRITEBYTECODE=1
# (a) 파일 존재 (7개)
ls budget_app/__init__.py budget_app/__main__.py budget_app/models.py budget_app/storage.py \
   budget_app/services.py budget_app/decorators.py budget_app/cli.py

# (b) 3.10 문법 호환 → SYNTAX_310_OK
python3 -c "
import ast, sys
for f in sys.argv[1:]:
    ast.parse(open(f, encoding='utf-8').read(), feature_version=(3, 10))
print('SYNTAX_310_OK')
" budget_app/*.py

# (c) 3.11+ 전용 API → 출력 없어야 함
grep -nE "fromisoformat|typing\.Self|from typing import .*Self|datetime\.UTC|except\*|ExceptionGroup|tomllib|suggest_on_error|color=" budget_app/*.py

# (d) 전체 로드 금지 → 출력 없어야 함
grep -nE "\.read\(\)|readlines\(" budget_app/*.py

# (e) 계층 규칙 → IMPORTS_OK
python3 -c "
import ast
allowed = {'models': set(), 'storage': {'models'}, 'services': {'storage','models'},
           'decorators': {'models'}, 'cli': {'services','decorators','models'},
           '__main__': {'cli'}, '__init__': set()}
bad = []
for m, ok in allowed.items():
    tree = ast.parse(open(f'budget_app/{m}.py', encoding='utf-8').read())
    for n in ast.walk(tree):
        if isinstance(n, ast.ImportFrom):
            if n.level: bad.append((m, 'relative import'))
            mods = [n.module or '']
        elif isinstance(n, ast.Import):
            mods = [a.name for a in n.names]
        else:
            continue
        for mod in mods:
            if mod == 'budget_app' or mod.startswith('budget_app.'):
                tgt = mod.split('.')[1] if '.' in mod else '?'
                if tgt not in ok: bad.append((m, mod))
print(bad or 'IMPORTS_OK')
"

# (f) 타입 힌트 누락(가변 인자 포함) → TYPE_HINTS_OK
python3 -c "
import ast, sys
bad = []
for f in sys.argv[1:]:
    for n in ast.walk(ast.parse(open(f, encoding='utf-8').read())):
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
            a = n.args
            args = a.posonlyargs + a.args + a.kwonlyargs + [x for x in (a.vararg, a.kwarg) if x]
            miss = [x.arg for x in args if x.annotation is None and x.arg not in ('self', 'cls')]
            if n.returns is None or miss: bad.append((f, n.name, miss))
print(bad or 'TYPE_HINTS_OK')
" budget_app/*.py

# (g) 데코레이터 정의·적용 → handle_errors 정의 1줄, cli 적용 7줄
grep -n "def handle_errors" budget_app/decorators.py
grep -c "@handle_errors" budget_app/cli.py          # 기대: 7

# (h) list 스트리밍: 전체 정렬 없음 → 첫 줄 출력 없음, 둘째 줄 1줄 이상
grep -nE "sorted\(|\.sort\(|list\(self\.transactions\.iter_transactions" budget_app/services.py budget_app/cli.py
grep -n "nlargest" budget_app/services.py

# (i) 범위 밖 명령 미등록 → 출력 없어야 함
grep -nE "[\"'](search|summary|budget|import|export)[\"']" budget_app/cli.py

# (j) 입출력 위치: print/input 은 cli, decorators 에만 → 출력 없어야 함
grep -nE "(^|[^A-Za-z0-9_.])(print|input)\(" budget_app/models.py budget_app/storage.py budget_app/services.py

# (k) 1단계 설계서 6.2 동작 검증 스크립트를 다시 실행 → ALL_OK (회귀 없음)
```

### 6.2 동작 검증 스크립트

아래를 그대로 실행한다. 실패한 검사는 `FAIL ...`로 출력되고, 모두 통과하면 마지막에 `STEP2_ALL_OK`가 나온다.

```bash
cd "/Users/khm04/codessey/pocket money"
export PYTHONDONTWRITEBYTECODE=1
D="$(mktemp -d)"; DD="$D/data"; FAIL=0
TXF="$DD/transactions.jsonl"

# t <기대 종료코드> <표준입력(printf %b 형식)> <인자...>
t() {
  local want=$1 input=$2; shift 2
  printf '%b' "$input" | python -m budget_app "$@" >"$D/out" 2>"$D/err"
  local rc=$?
  [ "$rc" = "$want" ] || { echo "FAIL rc=$rc want=$want :: $*"; cat "$D/err"; FAIL=1; }
  if grep -q "Traceback" "$D/out" "$D/err"; then echo "FAIL traceback :: $*"; FAIL=1; fi
}
out_has() { grep -qF -- "$1" "$D/out" || { echo "FAIL stdout에 없음: $1"; FAIL=1; }; }
err_has() { grep -qF -- "$1" "$D/err" || { echo "FAIL stderr에 없음: $1"; FAIL=1; }; }
out_eq()  { [ "$(cat "$D/out")" = "$1" ] || { echo "FAIL stdout 불일치"; echo "--- got"; cat "$D/out"; echo "--- want"; printf '%s\n' "$1"; FAIL=1; }; }
cnt()     { grep -oF -- "$2" "$D/$1" | wc -l | tr -d ' '; }   # cnt out|err 문자열
err_cnt() { [ "$(cnt err '[오류]')" = "$1" ] && [ "$(cnt err '[힌트]')" = "$1" ] || { echo "FAIL [오류]/[힌트] 개수 != $1"; cat "$D/err"; FAIL=1; }; }
lines()   { grep -c . "$TXF"; }
tags()    { python3 -c "import json,sys; print({d['id']: d['tags'] for d in map(json.loads, (l for l in open(sys.argv[1], encoding='utf-8') if l.strip()))})" "$TXF"; }

# ---------- A. --help (프로젝트 루트에 ./data 가 생기지 않아야 함) ----------
# (zsh 는 따옴표 없는 변수를 단어로 나누지 않으므로 명령을 한 줄씩 적는다)
t 0 '' --help;                   out_has "usage:"; out_has "category"; out_has "update"
t 0 '' category --help;          out_has "usage:"; out_has "remove"
t 0 '' add --help;               out_has "usage:"; out_has "--data-dir"
t 0 '' list --help;              out_has "usage:"; out_has "--data-dir"; out_has "--limit"
t 0 '' delete --help;            out_has "usage:"; out_has "--data-dir"; out_has "--id"
t 0 '' category add --help;      out_has "usage:"; out_has "--data-dir"
t 0 '' category list --help;     out_has "usage:"; out_has "--data-dir"
t 0 '' category remove --help;   out_has "usage:"; out_has "--data-dir"
t 0 '' update --help;            out_has "usage:"; out_has "--data-dir"
for o in --id --date --type --category --amount --memo --tags; do out_has "$o"; done
[ ! -e data ] || { echo "FAIL ./data 가 생김"; FAIL=1; }

# ---------- B. 사용법 오류 (종료 코드 2, [오류]+[힌트]) ----------
for c in search summary budget import export; do t 2 '' $c --data-dir "$DD"; err_cnt 1; done
t 2 ''                                  # 명령 없음
t 2 '' --data-dir "$DD" list            # --data-dir 는 명령 뒤에만
t 2 '' category --data-dir "$DD"        # category 하위 명령 없음
[ ! -e "$DD" ] || { echo "FAIL 사용법 오류에서 data 폴더가 생김"; FAIL=1; }

# ---------- C. category ----------
t 0 '' category list --data-dir "$DD"
out_eq "$(printf '%s\n' '- food' '- transport' '- rent' '- etc')"
ls "$DD"   # 기대: budgets.jsonl  categories.jsonl  transactions.jsonl
t 0 'hobby\n' category add --data-dir "$DD";            out_has "카테고리명: "; out_has "[저장 완료] category=hobby"
t 0 '   \n  salary  \n' category add --data-dir "$DD";  err_cnt 1; out_has "[저장 완료] category=salary"
[ "$(cnt out '카테고리명: ')" = 2 ] || { echo "FAIL 빈 이름 재입력 안 됨"; FAIL=1; }
t 0 'food\nFood\n' category add --data-dir "$DD";       err_cnt 1; err_has "이미 있는 카테고리"; out_has "[저장 완료] category=Food"
t 1 '' category add --data-dir "$DD";                   err_cnt 1; err_has "EOF"
t 0 '' category list --data-dir "$DD"
out_eq "$(printf '%s\n' '- food' '- transport' '- rent' '- etc' '- hobby' '- salary' '- Food')"
t 0 'Food\n' category remove --data-dir "$DD";          out_has "[삭제 완료] category=Food"
t 1 'nope\n' category remove --data-dir "$DD";          err_cnt 1; err_has "등록되지 않은 카테고리"
t 0 '\nhobby\n' category remove --data-dir "$DD";       err_cnt 1; out_has "[삭제 완료] category=hobby"
t 0 '' category list --data-dir "$DD"
out_eq "$(printf '%s\n' '- food' '- transport' '- rent' '- etc' '- salary')"

# ---------- D. add ----------
t 0 '2024-01-15\nexpense\nfood\n15000\n점심\nmeal\n' add --data-dir "$DD"
for p in "날짜(YYYY-MM-DD): " "타입(income/expense): " "카테고리: " "금액(양수): " "메모(선택): " "태그(쉼표로 구분, 없으면 엔터): "; do out_has "$p"; done
out_has "[저장 완료] id=TX-000001"
# 날짜 1회, 타입 1회, 카테고리 1회, 금액 3회 오류 → 각각 재입력 후 저장
t 0 '2024-13-40\n2024-01-14\nrefund\nincome\nnope\nsalary\n0\n-5\nabc\n3000000\n\n\n' add --data-dir "$DD"
err_cnt 6; err_has "category add"; out_has "[저장 완료] id=TX-000002"
[ "$(cnt out '날짜(YYYY-MM-DD): ')" = 2 ] && [ "$(cnt out '금액(양수): ')" = 4 ] || { echo "FAIL 재입력 횟수"; FAIL=1; }
t 0 '2024-01-12\nexpense\ntransport\n20000\n\n a , ,b \n' add --data-dir "$DD"; out_has "[저장 완료] id=TX-000003"
t 0 '2024-01-15\nincome\nsalary\n500\n용돈\n\n' add --data-dir "$DD";         out_has "[저장 완료] id=TX-000004"
t 1 '2024-01-15\nexpense\n' add --data-dir "$DD"; err_cnt 1; err_has "EOF"
[ "$(lines)" = 4 ] || { echo "FAIL EOF 후 저장됨"; FAIL=1; }
[ "$(tags)" = "{'TX-000001': ['meal'], 'TX-000002': [], 'TX-000003': ['a', 'b'], 'TX-000004': []}" ] || { echo "FAIL tags: $(tags)"; FAIL=1; }

# Ctrl+C: 첫 프롬프트가 나온 뒤 SIGINT → 종료 코드 != 0, [오류]/[힌트], Traceback 없음, 저장 없음
python3 - "$DD" <<'PY' || FAIL=1
import signal, subprocess, sys
p = subprocess.Popen([sys.executable, "-m", "budget_app", "add", "--data-dir", sys.argv[1]],
                     stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
prompt = "날짜(YYYY-MM-DD): "
assert p.stdout.read(len(prompt)) == prompt
p.send_signal(signal.SIGINT)
out, err = p.communicate(timeout=10)
assert p.returncode not in (0, None), p.returncode
assert "[오류]" in err and "[힌트]" in err and "Traceback" not in err + out, err
print("CTRL_C_OK")
PY
[ "$(lines)" = 4 ] || { echo "FAIL Ctrl+C 후 저장됨"; FAIL=1; }

# ---------- E. list ----------
t 0 '' list --data-dir "$DD"
out_eq "$(printf '%s\n' \
 'TX-000004 | 2024-01-15 | income | salary | 500 | 용돈' \
 'TX-000001 | 2024-01-15 | expense | food | 15000 | 점심' \
 'TX-000002 | 2024-01-14 | income | salary | 3000000 |' \
 'TX-000003 | 2024-01-12 | expense | transport | 20000 |')"
t 0 '' list --limit 2 --data-dir "$DD"
out_eq "$(printf '%s\n' 'TX-000004 | 2024-01-15 | income | salary | 500 | 용돈' 'TX-000001 | 2024-01-15 | expense | food | 15000 | 점심')"
for v in 0 -1 abc 1.5; do t 1 '' list --limit "$v" --data-dir "$DD"; err_cnt 1; done
t 0 '' list --data-dir "$D/empty"; out_eq "거래 내역이 없습니다."
# 기본값 20건 + id 숫자 비교
python3 - "$D/big" <<'PY'
import json, os, sys
os.makedirs(sys.argv[1])
with open(os.path.join(sys.argv[1], "transactions.jsonl"), "w", encoding="utf-8") as f:
    rows = [(f"TX-{i:06d}", f"2024-03-{i:02d}") for i in range(1, 24)] + [("TX-999999", "2024-03-31"), ("TX-1000000", "2024-03-31")]
    for i, d in rows:
        f.write(json.dumps({"id": i, "type": "expense", "date": d, "amount": 1, "category": "food", "memo": "", "tags": []}) + "\n")
PY
t 0 '' list --data-dir "$D/big"
[ "$(grep -c . "$D/out")" = 20 ] || { echo "FAIL 기본 limit 20 아님"; FAIL=1; }
[ "$(head -2 "$D/out" | cut -d' ' -f1 | tr '\n' ' ')" = "TX-1000000 TX-999999 " ] || { echo "FAIL id 숫자 정렬"; FAIL=1; }
tail -1 "$D/out" | grep -q "^TX-000006 " || { echo "FAIL 20번째 줄"; FAIL=1; }

# ---------- F. update ----------
SUM="$(cksum < "$TXF")"
t 1 '' update --id TX-000001 --data-dir "$DD";                    err_cnt 1; err_has "수정할 항목이 없습니다"
t 1 '' update --id TX-999999 --amount 100 --data-dir "$DD";       err_cnt 1; err_has "없는 데이터"
t 1 '' update --id bad-id --memo x --data-dir "$DD";              err_has "없는 데이터"
t 1 '' update --id TX-000001 --date 2024-02-30 --data-dir "$DD";  err_cnt 1
t 1 '' update --id TX-000001 --type refund --data-dir "$DD";      err_cnt 1
t 1 '' update --id TX-000001 --amount 0 --data-dir "$DD";         err_cnt 1
t 1 '' update --id TX-000001 --category nope --data-dir "$DD";    err_cnt 1; err_has "등록되지 않은 카테고리"
t 2 '' update --amount 100 --data-dir "$DD";                      err_cnt 1
[ "$(cksum < "$TXF")" = "$SUM" ] || { echo "FAIL 실패한 update 가 파일을 바꿈"; FAIL=1; }
t 0 '' update --id TX-000003 --amount 25000 --memo 버스 --tags "x, y" --data-dir "$DD"; out_eq "[수정 완료] id=TX-000003"
t 0 '' update --id TX-000003 --date 2024-01-20 --data-dir "$DD";  out_eq "[수정 완료] id=TX-000003"
t 0 '' list --limit 1 --data-dir "$DD"; out_eq "TX-000003 | 2024-01-20 | expense | transport | 25000 | 버스"
t 0 '' update --id TX-000003 --tags "" --data-dir "$DD"
[ "$(tags)" = "{'TX-000001': ['meal'], 'TX-000002': [], 'TX-000003': [], 'TX-000004': []}" ] || { echo "FAIL tags 비우기: $(tags)"; FAIL=1; }

# ---------- G. delete + 사용 중 카테고리 차단 ----------
t 0 '' delete --id TX-000002 --data-dir "$DD"; out_eq "[삭제 완료] id=TX-000002"
t 1 '' delete --id TX-000002 --data-dir "$DD"; err_cnt 1; err_has "없는 데이터"
t 2 '' delete --data-dir "$DD"
t 0 '' list --data-dir "$DD"
out_eq "$(printf '%s\n' \
 'TX-000003 | 2024-01-20 | expense | transport | 25000 | 버스' \
 'TX-000004 | 2024-01-15 | income | salary | 500 | 용돈' \
 'TX-000001 | 2024-01-15 | expense | food | 15000 | 점심')"
t 1 'food\n' category remove --data-dir "$DD";   err_cnt 1; err_has "사용 중"
t 1 'salary\n' category remove --data-dir "$DD"; err_has "사용 중"
t 0 '' delete --id TX-000004 --data-dir "$DD"
t 0 'salary\n' category remove --data-dir "$DD"; out_has "[삭제 완료] category=salary"
t 0 '' category list --data-dir "$DD"; out_eq "$(printf '%s\n' '- food' '- transport' '- rent' '- etc')"
find "$DD" -name '*.tmp' | grep -q . && { echo "FAIL 임시 파일 남음"; FAIL=1; }

# ---------- H. 원시 예외 변환 (모두 종료 코드 1, [오류]+[힌트] 각 1줄, Traceback 없음) ----------
touch "$D/afile";                 t 1 '' list --data-dir "$D/afile"; err_cnt 1          # data-dir 가 파일
mkdir -p "$D/d2/transactions.jsonl"; t 1 '' list --data-dir "$D/d2"; err_cnt 1       # IsADirectoryError
t 0 '' list --data-dir "$D/d3"; chmod 000 "$D/d3/transactions.jsonl"
t 1 '' list --data-dir "$D/d3"; err_cnt 1; chmod 644 "$D/d3/transactions.jsonl"      # PermissionError(읽기)
t 0 '2024-01-01\nexpense\nfood\n1\n\n\n' add --data-dir "$D/d3"; chmod 555 "$D/d3"
t 1 '' delete --id TX-000001 --data-dir "$D/d3"; err_cnt 1; chmod 755 "$D/d3"        # PermissionError(임시 파일 생성)
t 0 '' list --data-dir "$D/d5"; printf '\xff\xfe\n' > "$D/d5/transactions.jsonl"
t 1 '' list --data-dir "$D/d5"; err_cnt 1; err_has "UTF-8"                            # UnicodeDecodeError
t 0 '' list --data-dir "$D/d6"; echo 'not json' > "$D/d6/transactions.jsonl"
t 1 '' list --data-dir "$D/d6"; err_cnt 1; err_has "transactions.jsonl"               # 손상 줄

[ ! -e data ] || { echo "FAIL 프로젝트 루트에 ./data 가 생김"; FAIL=1; }
find budget_app -name __pycache__ | grep -q . && { echo "FAIL __pycache__ 생김"; FAIL=1; }
[ "$FAIL" = 0 ] && echo "STEP2_ALL_OK"
```

기대 출력: `ls "$DD"` 결과 `budgets.jsonl  categories.jsonl  transactions.jsonl`, `CTRL_C_OK`, 마지막 줄 `STEP2_ALL_OK`. `FAIL`로 시작하는 줄이 하나도 없어야 한다.

참고(사람이 눈으로 확인할 때): 표준입력을 파이프로 넣으면 입력값이 화면에 되풀이되지 않아 프롬프트가 한 줄로 붙어 보인다. 예: `printf '2024-01-15\nexpense\nfood\n15000\n점심\nmeal\n' | python -m budget_app add --data-dir "$DD"`의 stdout은
`날짜(YYYY-MM-DD): 타입(income/expense): 카테고리: 금액(양수): 메모(선택): 태그(쉼표로 구분, 없으면 엔터): [저장 완료] id=TX-000001` 이다.

## 7. 총괄 확인 필요

1. **실패 시 종료 코드**: 없는 id(update/delete), 미등록 카테고리 remove, 사용 중 카테고리 삭제 차단, Ctrl+C, EOF를 모두 "오류 종료"로 보고 `1`로 정했다(argparse 사용법 오류만 `2`). REQUIREMENTS는 "오류 종료는 0이 아닌 값"만 정하므로 없는 id를 오류로 볼지, Ctrl+C에 관례값 `130`을 쓸지는 근거가 없다.
2. **`[오류]/[힌트]` 출력 스트림**: stderr로 정했다(정상 결과 stdout과 분리). PDF 8장 예시는 화면만 보여 주므로 어느 스트림인지 근거가 없다.
3. **대화형 category 명령의 세부 동작**: `category add`에서 중복 이름은 빈 이름과 같이 "재입력"으로 정했다(REQUIREMENTS는 "거부"만 명시). `category remove`는 PDF 4장 1번 근거로 대화형으로 정했고, 빈 이름만 재입력, 미등록 이름과 사용 중 이름은 즉시 종료(코드 1)로 정했다.
4. **list 출력에 태그 미표시**: PDF 8장 list 예시(`id | date | type | category | amount | memo`)를 따라 태그는 표시하지 않는다. 태그는 이번 단계에서 화면으로 확인할 방법이 없다(3단계 `search --tag`에서 사용).
5. **모든 카테고리 삭제 후 기본값 재생성 (1단계 총괄 확인 #2 미결)**: 이번 단계에서 `category remove`가 생기므로 실제로 발생한다. 쓰지 않는 카테고리를 전부 지우면 다음 실행 때 food/transport/rent/etc가 다시 생긴다.
6. **최후 수단 `except Exception`**: 4장 "스택트레이스 출력 금지"를 근거로 넣었다. 대신 예상하지 못한 버그도 한 줄 메시지로만 보이게 된다. 빼기를 원하면 알려 달라.
