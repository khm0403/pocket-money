# 1단계 설계서: 데이터 모델(models.py) + 파일 저장소(storage.py)

## 1. 목표

- `budget_app/` 패키지를 만들고, 거래 데이터 모델(`Transaction`)과 입력 검증 함수, 원인과 힌트를 함께 담는 예외 클래스를 `models.py`에 둔다.
- `storage.py`에 거래·카테고리·예산 JSONL 파일 3개를 다루는 저장소 클래스 3개를 만든다. 거래는 제너레이터로 읽고, 수정·삭제는 임시 파일에 다시 쓴 뒤 `os.replace`로 교체한다.
- CLI, 서비스, 데코레이터는 이번 단계에서 만들지 않는다. 이번 단계 결과는 `python3` 검증 스크립트로만 확인한다.

## 2. 대상 요구사항

| REQUIREMENTS.md 항목 | 이번 단계에서 충족하는 범위 |
| --- | --- |
| 0장 Python 3.10+, 표준 라이브러리만 | 전체 (3.10 문법·API만 사용) |
| 1장 Transaction 필드/규칙, `@dataclass` | 전체 |
| 1장 클래스 2개 이상 | `Transaction`, `TransactionRepository`, `CategoryStore`, `BudgetStore` |
| 1장 입력 검증 (날짜 / 금액 / type) | 전체 |
| 1장 입력 검증 (등록되지 않은 category) | 판단 재료만 제공 (`CategoryStore.exists`). 검증 호출은 2단계 서비스 계층 |
| 2장 JSONL, 파일 3개, 자동 생성, 빈 카테고리 파일이면 기본값 생성, 원자적 교체 | 전체 |
| 2장 `--data-dir` | 저장소가 경로를 인자로 받는 구조까지만. 옵션 연결은 CLI 단계 |
| 3장 #6 카테고리 삭제 차단 | 판단 재료만 제공 (`TransactionRepository.is_category_used`). 차단 정책은 2단계 서비스 계층 |
| 3장 #7 update, #8 delete (없는 id) | 저장소 메서드와 반환값(찾았는지 여부)까지 |
| 3장 #5 budget set (같은 월 덮어쓰기) | 저장소 메서드까지 |
| 4장 제너레이터 | 거래 파일 읽기 전부 |
| 4장 예외 처리 (원인 + 힌트) | 예외 클래스 설계와, 저장소가 원인과 힌트를 담아 예외를 던지는 부분까지 |
| 4장 타입 힌트 | 전체 (내부 함수와 중첩 함수 포함) |

## 3. 파일/모듈 설계

### 3.1 `budget_app/__init__.py`

- 모듈 docstring 한 줄만 둔다 (`"""용돈 기입장 패키지."""`). 다른 코드는 넣지 않는다. ← 4장 모듈화 / 6장 폴더 구조

### 3.2 `budget_app/models.py` — [모델]

import 허용: 표준 라이브러리(`dataclasses`, `datetime`, `json`, `re`, `typing`)만 쓴다. `budget_app`의 다른 모듈은 import하지 않는다.

#### 상수

| 이름 | 값 | 근거 |
| --- | --- | --- |
| `TRANSACTION_TYPES: tuple[str, ...]` | `("income", "expense")` | ← 1장 type |
| `DEFAULT_CATEGORIES: tuple[str, ...]` | `("food", "transport", "rent", "etc")` (이 순서) | ← 2장 빈 카테고리 파일 [결정 안 A] |
| `_DATE_RE` | `re.compile(r"\d{4}-\d{2}-\d{2}")` (`fullmatch` 용) | ← 1장 date 형식 |
| `_MONTH_RE` | `re.compile(r"\d{4}-\d{2}")` (`fullmatch` 용) | ← 3장 #4, #5 `--month YYYY-MM` |
| `_AMOUNT_RE` | `re.compile(r"[0-9]+")` (`fullmatch` 용, ASCII 숫자만) | ← 1장 amount |
| `_TX_ID_RE` | `re.compile(r"TX-(\d{6,})")` (`fullmatch` 용) | ← 1장 id 예시 `TX-000012` |

#### 예외 클래스 ← 4장 예외 처리 ("원인 + 해결 힌트")

```python
class BudgetAppError(Exception):
    def __init__(self, cause: str, hint: str) -> None: ...
```
- 원인(`self.cause: str`)과 해결 힌트(`self.hint: str`)를 속성으로 저장하고, `super().__init__(cause)`를 호출한다.
- 앱에서 예상한 모든 오류의 기반 클래스다. 다음 단계 데코레이터가 이 예외를 잡아 `[오류] {cause}` / `[힌트] {hint}`로 출력한다.
- 저장소 파일 문제(손상된 줄, data 경로 오류)는 이 클래스로 직접 던진다.

```python
class ValidationError(BudgetAppError): ...
```
- 입력값 검증 실패 전용 예외다. 본문 추가 없이 상속만 한다. ← 1장 입력 검증
- 따로 두는 이유: 3장 #9 import가 잘못된 행을 건너뛰고 skipped로 셀 때 이 예외만 골라서 잡기 위해서다. ← 3장 #9

#### 검증 함수 ← 1장 입력 검증

모두 올바르면 정규화한 값을 돌려주고, 틀리면 `ValidationError(cause, hint)`를 던진다. 입력 문자열은 `strip()` 후 검사한다.

| 시그니처 | 책임 | 근거 |
| --- | --- | --- |
| `def validate_date(value: str) -> str` | `_DATE_RE.fullmatch`로 형식을 확인한 뒤 `datetime.strptime(value, "%Y-%m-%d")`로 실제 날짜인지 확인한다. `"2024-13-40"`, `"2024-02-30"`, `"2024-2-5"`는 거부한다. 힌트 예: `"YYYY-MM-DD 형식의 실제 날짜를 입력하세요 (예: 2024-05-01)"` | ← 1장 date, 입력 검증 #1 |
| `def validate_month(value: str) -> str` | `_MONTH_RE.fullmatch` 후 `strptime(value, "%Y-%m")`로 확인한다. `"2024-13"`, `"2024-5"`는 거부한다. | ← 3장 #4, #5 `--month YYYY-MM`, 2장 budgets.jsonl |
| `def parse_amount(value: str \| int) -> int` | 값이 `int`이면 그대로 쓰고(`bool`은 거부), `str`이면 `strip` 후 `_AMOUNT_RE.fullmatch`를 통과해야 `int()`로 바꾼다. 결과가 0 이하이면 거부한다. `"0"`, `"-5"`, `"abc"`, `"1.5"`, `""`, `"1,000"`은 모두 거부한다. 힌트 예: `"1 이상의 정수를 입력하세요 (예: 15000)"` | ← 1장 amount, 입력 검증 #2, 3장 #5 `--amount` |
| `def validate_type(value: str) -> str` | `strip` 후 `TRANSACTION_TYPES` 안에 있는지 확인한다(대소문자 구분). 힌트: `"income 또는 expense 중 하나를 입력하세요"` | ← 1장 type, 입력 검증 #3 |
| `def format_tx_id(seq: int) -> str` | `f"TX-{seq:06d}"`를 돌려준다. | ← 1장 id |
| `def tx_id_seq(tx_id: str) -> int` | `_TX_ID_RE.fullmatch`로 숫자 부분을 `int`로 돌려주고, 형식이 틀리면 `ValidationError`를 던진다. 저장소의 새 id 발급과 다음 단계의 "같은 날짜면 id 내림차순" 정렬에 쓴다. 문자열 비교는 `TX-1000000`부터 틀린다. | ← 1장 id 유일, 3장 "최신순" 정의 |

- 카테고리 존재 여부 검증은 models.py에 두지 않는다. 판단하려면 저장소 데이터가 필요하다. 2단계 서비스가 `CategoryStore.exists()` 결과로 판단하고, 등록되지 않았으면 `ValidationError`를 던진다. (4장 참고) ← 1장 입력 검증 #4

#### `Transaction` ← 1장 Transaction, `@dataclass`

```python
@dataclass
class Transaction:
    id: str
    type: str
    date: str
    amount: int
    category: str
    memo: str = ""
    tags: list[str] = field(default_factory=list)
```

| 시그니처 | 책임 | 근거 |
| --- | --- | --- |
| `def __post_init__(self) -> None` | 생성할 때마다 불변식을 검사한다. `tx_id_seq(self.id)`, `validate_date(self.date)`, `validate_type(self.type)`를 호출하고, 금액은 `isinstance(amount, int)`이면서 `bool`이 아니고 0보다 커야 한다(문자열 변환은 하지 않는다). `category`는 공백이 아닌 `str`, `memo`는 `str`, `tags`는 원소가 모두 `str`인 `list`여야 한다. 하나라도 어기면 `ValidationError`를 던진다. 값을 바꾸지 않는다(정규화는 호출하는 쪽 책임). 따라서 검증 함수의 반환값이 원래 값과 다르면(예: `" income"`, `"2024-05-01 "`) 정규화되지 않은 값으로 보고 거부한다. `category`도 앞뒤 공백이 있으면(`category != category.strip()`) 거부한다. (검토 반영) | ← 1장 필드 규칙, 입력 검증 |
| `def to_dict(self) -> dict[str, Any]` | `dataclasses.asdict(self)`를 돌려준다(키 순서는 필드 순서). | ← 2장 JSONL |
| `def to_json_line(self) -> str` | `json.dumps(self.to_dict(), ensure_ascii=False)`를 돌려준다. 줄바꿈 문자는 포함하지 않는다. 한글 메모를 사람이 읽을 수 있게 `ensure_ascii=False`를 쓴다. | ← 2장 JSONL |
| `@classmethod def from_dict(cls, data: dict[str, Any]) -> "Transaction"` | 7개 키가 모두 있는지 확인하고(누락 시 `ValidationError`), `cls(**...)`로 만든다. 나머지 검증은 `__post_init__`이 맡는다. 알 수 없는 추가 키는 무시한다. | ← 2장 JSONL, 1장 |
| `@classmethod def from_json_line(cls, line: str) -> "Transaction"` | `json.loads`가 실패하거나(`json.JSONDecodeError`) 결과가 `dict`가 아니면 `ValidationError`를 던지고, 성공하면 `from_dict`로 넘긴다. | ← 2장 JSONL |

- 반환 타입에 `typing.Self`는 쓰지 않는다(3.11+ 전용). 문자열 전방 참조 `"Transaction"`을 쓴다.
- 이번 단계에서는 태그 문자열 파싱(쉼표 구분)을 만들지 않는다. add/update/import 입력 처리와 함께 다음 단계에서 설계한다.

### 3.3 `budget_app/storage.py` — [저장소]

import 허용: 표준 라이브러리(`json`, `os`, `tempfile`, `pathlib`, `typing`/`collections.abc`)와 `budget_app.models`만 쓴다.

#### 모듈 상수 / 내부 함수

| 시그니처 | 책임 | 근거 |
| --- | --- | --- |
| `DEFAULT_DATA_DIR: str = "data"` | 기본 data 폴더 이름. 다음 단계 CLI의 `--data-dir` 기본값으로 쓴다. | ← 2장 기본 폴더 `./data` |
| `TRANSACTIONS_FILE = "transactions.jsonl"`, `CATEGORIES_FILE = "categories.jsonl"`, `BUDGETS_FILE = "budgets.jsonl"` | 파일 이름 상수 | ← 2장 파일 3개 |
| `def _ensure_file(path: Path) -> None` | `path.parent.mkdir(parents=True, exist_ok=True)`와 `path.touch(exist_ok=True)`로 폴더와 파일을 없으면 만든다. `OSError`(data 경로가 이미 파일로 있음, 권한 없음 등)가 나면 `BudgetAppError(cause=f"데이터 폴더를 준비할 수 없습니다: {path.parent}", hint="--data-dir 로 쓰기 가능한 폴더 경로를 지정하세요")`로 바꿔 던진다. | ← 2장 파일 자동 생성, 4장 예외 처리 |
| `def _iter_lines(path: Path) -> Iterator[tuple[int, str]]` | **제너레이터.** `with open(path, encoding="utf-8")` 안에서 `for` 루프로 한 줄씩 읽는다. 빈 줄(공백만 있는 줄 포함)은 건너뛰고, `(줄번호(1부터), 줄 끝 개행을 제거한 문자열)`을 `yield`한다. `read()`와 `readlines()`는 쓰지 않는다. | ← 4장 제너레이터 |
| `def _corrupt_line_error(path: Path, lineno: int, detail: str) -> BudgetAppError` | 손상된 줄 오류 객체를 만든다. cause: `f"{path} 파일 {lineno}번째 줄을 읽을 수 없습니다 ({detail})"`, hint: `"해당 줄을 올바른 JSON 형식으로 고치거나 삭제한 뒤 다시 실행하세요"` | ← 4장 예외 처리 |
| `def _atomic_rewrite(path: Path, lines: Iterable[str]) -> None` | `tempfile.mkstemp(dir=path.parent, prefix=path.name + ".", suffix=".tmp")`로 **같은 폴더**에 임시 파일을 만든다. `os.fdopen(fd, "w", encoding="utf-8")`로 `lines`의 각 항목 뒤에 `"\n"`을 붙여 쓰고, 파일을 닫은 **뒤에** `os.replace(tmp, path)`를 호출한다. 도중에 예외가 나면 임시 파일을 `os.unlink`로 지우고 예외를 다시 던진다. `lines`는 원본 파일을 한 줄씩 읽는 제너레이터로 받으므로 원본을 한 번에 메모리에 올리지 않는다. 제너레이터를 끝까지 소비하면 원본 파일 핸들이 `os.replace` 전에 닫힌다. | ← 2장 원자적 교체, 4장 제너레이터 |

- `os.fsync`와 백업 파일 생성은 하지 않는다. 5장 보너스 "저장 원자성 강화"는 범위 밖이다.

#### `class TransactionRepository` ← 1장 클래스, 2장, 3장 #1·#7·#8, 4장 제너레이터

| 시그니처 | 책임 | 근거 |
| --- | --- | --- |
| `def __init__(self, data_dir: str \| os.PathLike[str]) -> None` | `self.path = Path(data_dir) / TRANSACTIONS_FILE`로 경로를 정하고, `_ensure_file(self.path)`를 호출하고, `self._last_seq: int \| None = None`으로 초기화한다. | ← 2장 자동 생성, `--data-dir` 구조 |
| `def iter_transactions(self) -> Iterator[Transaction]` | **제너레이터.** `_iter_lines`로 받은 줄마다 `Transaction.from_json_line`을 호출해 `yield`한다. `ValidationError`가 나면 `_corrupt_line_error(path, lineno, str(e))`로 바꿔 던진다(`raise ... from e`). 순서는 파일에 저장된 순서 그대로이며, 정렬은 서비스 책임이다. | ← 4장 제너레이터, 3장 #2·#3 스트리밍 |
| `def issue_id(self) -> str` | 새 유일 id를 발급한다. 첫 호출 때 `iter_transactions()`를 한 번 훑어 `tx_id_seq`의 최댓값을 `_last_seq`에 저장한다(파일이 비어 있으면 0). 이후에는 `_last_seq += 1` 후 `format_tx_id(_last_seq)`를 돌려준다. 같은 인스턴스에서 여러 번 호출해도 파일을 한 번만 훑는다(다음 단계 import 대비). 첫 id는 `TX-000001`이다. | ← 1장 id 유일, 3장 #1 `[저장 완료] id=TX-…`, #9 새 id 발급 |
| `def append(self, tx: Transaction) -> None` | `open(self.path, "a", encoding="utf-8")`로 `tx.to_json_line() + "\n"`을 한 줄 추가한다. id 중복 검사는 하지 않는다(id는 `issue_id`로만 발급받는 것이 계약). | ← 3장 #1 add, #9 import |
| `def get(self, tx_id: str) -> Transaction \| None` | `iter_transactions()`를 돌다가 id가 같은 거래를 찾으면 바로 반환하고, 없으면 `None`을 반환한다. 다음 단계 update가 기존 값에 바꿀 필드만 덮어쓸 때 쓴다. | ← 3장 #7 update (옵션식), 없는 id 처리 |
| `def update(self, tx: Transaction) -> bool` | `self.get(tx.id)`가 `None`이면 **파일을 건드리지 않고** `False`를 반환한다. 있으면 `_iter_lines`를 도는 내부 제너레이터로 id가 같은 줄은 `tx.to_json_line()`으로 바꾸고 나머지 줄은 원문 그대로 내보내, `_atomic_rewrite`에 넘긴 뒤 `True`를 반환한다. 각 줄의 id는 `Transaction.from_json_line`으로 파싱해 비교하고, 파싱이 실패하면 `_corrupt_line_error`를 던진다(이때 원본 파일은 그대로 남는다). | ← 3장 #7, 2장 원자적 교체 |
| `def delete(self, tx_id: str) -> bool` | `update`와 같은 구조다. 없는 id면 `False`를 반환하고 파일을 건드리지 않는다. 있으면 해당 줄만 빼고 `_atomic_rewrite`로 다시 쓴 뒤 `True`를 반환한다. | ← 3장 #8, 2장 원자적 교체 |
| `def is_category_used(self, name: str) -> bool` | `iter_transactions()`를 돌며 `category == name`인 거래가 하나라도 나오면 바로 `True`를 반환한다. | ← 3장 #6 사용 중 삭제 차단 [결정] |

- 내부 제너레이터(예: `def _lines() -> Iterator[str]:`)에도 타입 힌트를 단다. ← 4장 타입 힌트
- `update`와 `delete`는 파일을 두 번 훑는다(존재 확인 1회 + 재작성 1회). 없는 id일 때 파일을 다시 쓰지 않으려고 의도한 것이다.

#### `class CategoryStore` ← 1장 category, 2장, 3장 #6

줄 형식: `{"name": "food"}`

| 시그니처 | 책임 | 근거 |
| --- | --- | --- |
| `def __init__(self, data_dir: str \| os.PathLike[str]) -> None` | `self.path = Path(data_dir) / CATEGORIES_FILE`로 경로를 정하고 `_ensure_file`을 호출한다. 이어서 `_iter_lines(self.path)`에서 한 줄도 나오지 않으면(빈 파일이거나 공백 줄만 있는 파일) `_atomic_rewrite`로 `DEFAULT_CATEGORIES`를 순서대로 기록한다. | ← 2장 빈 카테고리 파일 [결정 안 A], 자동 생성 |
| `def list_names(self) -> list[str]` | 파일 순서대로 이름 목록을 반환한다. 줄이 `dict`가 아니거나 `name`이 비어 있지 않은 `str`이 아니면 `_corrupt_line_error`를 던진다. 카테고리 파일은 작으므로 리스트로 반환한다(제너레이터 요구는 4장에서 거래 파일에 한정). | ← 3장 #6 category list |
| `def exists(self, name: str) -> bool` | `name in self.list_names()`를 반환한다(대소문자 구분, 정확히 같은 문자열). | ← 1장 입력 검증 #4, 3장 #6 |
| `def add(self, name: str) -> None` | `{"name": name}` 한 줄을 append한다. 중복 여부와 이름 형식은 검사하지 않는다(서비스 책임). | ← 3장 #6 category add |
| `def remove(self, name: str) -> bool` | 이름이 없으면 파일을 건드리지 않고 `False`를 반환한다. 있으면 그 줄을 빼고 `_atomic_rewrite`한 뒤 `True`를 반환한다. **사용 중인지는 검사하지 않는다.** | ← 3장 #6 category remove, 2장 |

#### `class BudgetStore` ← 2장 budgets.jsonl, 3장 #5

줄 형식: `{"month": "2024-05", "amount": 300000}`

| 시그니처 | 책임 | 근거 |
| --- | --- | --- |
| `def __init__(self, data_dir: str \| os.PathLike[str]) -> None` | `self.path = Path(data_dir) / BUDGETS_FILE`로 경로를 정하고 `_ensure_file`을 호출한다. | ← 2장 자동 생성 |
| `def get(self, month: str) -> int \| None` | `_iter_lines`로 읽다가 `month`가 같은 줄의 `amount`를 반환하고, 없으면 `None`을 반환한다. 손상된 줄(dict 아님, `month`가 str 아니거나 `validate_month`를 통과한 값과 다름, `amount`가 bool이 아닌 int가 아니거나 0 이하)은 `_corrupt_line_error`로 던진다. (검토 반영) | ← 3장 #4 summary 사용률, #5 |
| `def set(self, month: str, amount: int) -> None` | 내부 제너레이터가 기존 줄을 그대로 내보내다가 같은 month 줄은 새 금액 줄로 바꾸고, 끝까지 없었으면 마지막에 새 줄을 하나 추가한다. 이 제너레이터를 `_atomic_rewrite`에 넘긴다. 결과적으로 월마다 한 줄만 남는다(같은 월 재설정은 덮어쓰기). `month`와 `amount` 검증은 호출하는 쪽(서비스)에서 `validate_month`와 `parse_amount`로 끝낸 값이라고 가정한다. | ← 3장 #5 budget set, 2장 원자적 교체 |

- 같은 월 재설정도 "수정"이므로 `update`와 같은 원자적 교체 방식을 쓴다. 예산 파일은 작지만 `_iter_lines`를 재사용하면 구현이 하나로 통일된다.

## 4. 계층 규칙

```
cli.py (다음 단계) → services.py (다음 단계) → storage.py → models.py
```

- `models.py`: `budget_app` 안의 어떤 모듈도 import하지 않는다.
- `storage.py`: `budget_app.models`만 import한다(`Transaction`, `BudgetAppError`, `ValidationError`, `DEFAULT_CATEGORIES`, `format_tx_id`, `tx_id_seq`, `validate_month`(검토 반영)).
- 역방향 import(예: models → storage)는 금지한다.
- 저장소는 파일 입출력과 파일 형식 무결성만 책임진다. **업무 규칙은 서비스 계층(2단계) 책임이다.** 이번 단계에서 정한 책임 분담은 다음과 같다.

| 규칙 | 담당 계층 | 저장소가 주는 재료 |
| --- | --- | --- |
| 등록되지 않은 category 거부 (1장 입력 검증 #4) | 서비스: 등록되지 않았으면 `ValidationError`를 던진다. 힌트 예: `"category list 로 확인하거나 category add 로 먼저 추가하세요"` | `CategoryStore.exists` |
| 사용 중인 카테고리 삭제 차단 (3장 #6 [결정]) | 서비스: 사용 중이면 `BudgetAppError`를 던지고 `remove`를 호출하지 않는다. | `TransactionRepository.is_category_used` |
| 카테고리 중복 추가 방지 (3장 #6) | 서비스 | `CategoryStore.exists` |
| 없는 id 처리 (3장 #7·#8) | 서비스: `False`/`None`이면 원인·힌트를 담은 오류로 바꾼다. | `get`, `update`, `delete` 반환값 |
| 월·금액 형식 검증 (3장 #5) | 서비스가 models 검증 함수를 호출한다. | 없음 |

## 5. 예외/경계 상황 (이번 단계 처리 범위)

| 상황 | 처리 |
| --- | --- |
| data 폴더나 파일이 없음 | 저장소 생성자가 자동으로 만든다(중간 폴더 포함). |
| data 경로가 파일이거나 쓰기 권한이 없음 | `BudgetAppError`(원인: 경로, 힌트: `--data-dir`로 다른 경로 지정) |
| categories.jsonl이 0바이트이거나 공백 줄만 있음 | 기본 카테고리 4개를 기록한다. |
| 파일 안의 빈 줄 | 읽을 때 건너뛴다. 원자적 재작성을 거치면 빈 줄은 사라진다. |
| JSON이 아닌 줄 / 필드 누락 / 규칙 위반 값(예: amount 0) | `BudgetAppError`(파일 경로와 줄 번호를 원인에 적고, 고치거나 삭제하라는 힌트). `json.JSONDecodeError`, `KeyError`, `TypeError`가 그대로 밖으로 나가면 안 된다. |
| 재작성 도중 예외 | 임시 파일을 지우고 원본은 그대로 둔다. |
| 없는 id로 update/delete | `False`를 반환하고 파일은 바이트 단위로 그대로 둔다. |
| 없는 카테고리 remove | `False`를 반환하고 파일은 그대로 둔다. |
| 거래 파일이 비었을 때 id 발급 | `TX-000001` |
| 최대 id의 거래가 삭제된 뒤 새로 발급 | 현재 최댓값 + 1이 되므로, 지워진 최대 id가 다시 쓰일 수 있다. 현재 파일 안에서의 유일성(1장)은 지켜진다. |
| 날짜 `2024-2-5`(자릿수 부족), `2024-02-30`, `2024-13-40` | `ValidationError` |
| 금액 `"0"`, `"-5"`, `"abc"`, `"1.5"`, `""`, `"1,000"`, `True`, `0` | `ValidationError` |
| type `"Income"`, `"refund"` | `ValidationError` |

### Python 3.10 호환 주의 (로컬은 3.14)

- `date.fromisoformat`/`datetime.fromisoformat`은 쓰지 않는다. 3.11부터 `"20240105"` 같은 형식도 받아들여 3.10과 결과가 달라진다. 정규식과 `strptime`을 함께 쓴다.
- `typing.Self`, `datetime.UTC`, `except*`, `ExceptionGroup`, `tomllib`, PEP 695 제네릭 문법(`def f[T]()`, `type X = ...`)은 금지한다.
- `X | None` 표기와 내장 제네릭(`list[str]`)은 3.10에서 사용 가능하다.

## 6. 완료 기준 (에이전트 3 검증 절차)

모든 명령은 프로젝트 루트에서 실행한다. data 폴더는 `mktemp -d`로 만든 스크래치 폴더를 쓰며, 프로젝트의 `./data`는 만들지 않는다.

### 6.1 정적 검사

```bash
cd "/Users/khm04/codessey/pocket money"

# (a) 파일 존재
ls budget_app/__init__.py budget_app/models.py budget_app/storage.py

# (b) 3.10 문법 호환
python3 -c "
import ast
for f in ['budget_app/__init__.py','budget_app/models.py','budget_app/storage.py']:
    ast.parse(open(f, encoding='utf-8').read(), feature_version=(3, 10))
print('SYNTAX_310_OK')
"
# 기대 출력: SYNTAX_310_OK

# (c) 3.11+ 전용 API 사용 금지 → 출력이 없어야 함
grep -nE "fromisoformat|typing\.Self|from typing import .*Self|datetime\.UTC|except\*|ExceptionGroup|tomllib" budget_app/*.py

# (d) 거래 파일 전체 로드 금지 → 출력이 없어야 함
grep -nE "\.read\(\)|readlines\(" budget_app/storage.py

# (e) 계층 규칙: models 는 budget_app 을 import 하지 않음 → 출력이 없어야 함
grep -nE "^(from|import) +(budget_app|\.)" budget_app/models.py
# storage 는 models 만 import → 출력된 줄이 모두 models 만 가리켜야 함
grep -nE "^(from|import) +(budget_app|\.)" budget_app/storage.py

# (f) 원자적 교체 사용 확인 → 1줄 이상 출력
grep -n "os.replace" budget_app/storage.py

# (g) 타입 힌트 누락 검사 → 기대 출력: TYPE_HINTS_OK
python3 -c "
import ast
bad=[]
for f in ['budget_app/models.py','budget_app/storage.py']:
    for n in ast.walk(ast.parse(open(f, encoding='utf-8').read())):
        if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef)):
            args=n.args.posonlyargs+n.args.args+n.args.kwonlyargs
            miss=[a.arg for a in args if a.annotation is None and a.arg not in ('self','cls')]
            if n.returns is None or miss: bad.append((f,n.name,miss))
print(bad or 'TYPE_HINTS_OK')
"
```

### 6.2 동작 검증 스크립트

아래를 그대로 실행한다. 마지막 줄에 `ALL_OK`가 나와야 하며, 중간에 `AssertionError`나 트레이스백이 나오면 실패다.

```bash
cd "/Users/khm04/codessey/pocket money"
D="$(mktemp -d)"
python3 - "$D/data" <<'PY'
import sys, os, inspect, glob
from pathlib import Path
from dataclasses import is_dataclass
from budget_app.models import (Transaction, BudgetAppError, ValidationError,
    validate_date, validate_month, parse_amount, validate_type,
    format_tx_id, tx_id_seq, DEFAULT_CATEGORIES)
from budget_app.storage import TransactionRepository, CategoryStore, BudgetStore

d = sys.argv[1]  # 아직 존재하지 않는 폴더

def rejects(fn, *a):
    try:
        fn(*a)
    except ValidationError as e:
        assert e.cause and e.hint, "원인/힌트가 비어 있음"
        return True
    return False

# 1) 검증 함수
assert validate_date("2024-02-29") == "2024-02-29"
for v in ["2024-13-40", "2024-02-30", "2024-2-5", "abc", ""]:
    assert rejects(validate_date, v), v
assert validate_month("2024-05") == "2024-05"
for v in ["2024-13", "2024-5", "2024-05-01"]:
    assert rejects(validate_month, v), v
assert parse_amount("15000") == 15000 and parse_amount(" 7 ") == 7 and parse_amount(3) == 3
for v in ["0", "-5", "abc", "1.5", "", "1,000", 0, -1, True]:
    assert rejects(parse_amount, v), repr(v)
assert validate_type("income") == "income" and validate_type("expense") == "expense"
for v in ["Income", "refund", ""]:
    assert rejects(validate_type, v), v
assert format_tx_id(12) == "TX-000012" and tx_id_seq("TX-000012") == 12
assert tx_id_seq("TX-1000000") == 1000000
assert rejects(tx_id_seq, "TX-12")
assert issubclass(ValidationError, BudgetAppError)
print("1 VALIDATION_OK")

# 2) Transaction dataclass + JSONL 변환
assert is_dataclass(Transaction)
t = Transaction(id="TX-000001", type="expense", date="2024-05-01", amount=12000,
                category="food", memo="점심", tags=["회사", "평일"])
line = t.to_json_line()
assert "\n" not in line and "점심" in line
assert Transaction.from_json_line(line) == t
assert Transaction(id="TX-000009", type="income", date="2024-05-02", amount=1,
                   category="etc").memo == "" 
assert rejects(Transaction, "TX-000002", "expense", "2024-05-01", 0, "food")
assert rejects(Transaction, "TX-000002", "expense", "2024-05-01", "100", "food")
assert rejects(Transaction.from_json_line, "not json")
assert rejects(Transaction.from_json_line, '{"id": "TX-000001"}')
print("2 MODEL_OK")

# 3) 저장소 초기화: 폴더/파일 3개 자동 생성, 기본 카테고리
repo, cats, buds = TransactionRepository(d), CategoryStore(d), BudgetStore(d)
for f in ["transactions.jsonl", "categories.jsonl", "budgets.jsonl"]:
    assert os.path.isfile(os.path.join(d, f)), f
assert cats.list_names() == ["food", "transport", "rent", "etc"] == list(DEFAULT_CATEGORIES)
print("3 INIT_OK")

# 4) 제너레이터 + id 발급 + append
assert inspect.isgenerator(repo.iter_transactions())
id1 = repo.issue_id(); assert id1 == "TX-000001"
repo.append(Transaction(id1, "expense", "2024-05-01", 12000, "food", "점심", ["회사"]))
id2 = repo.issue_id(); assert id2 == "TX-000002"
repo.append(Transaction(id2, "income", "2024-05-03", 50000, "etc"))
assert TransactionRepository(d).issue_id() == "TX-000003"   # 새 인스턴스도 이어서 발급
assert [x.id for x in repo.iter_transactions()] == ["TX-000001", "TX-000002"]
print("4 APPEND_OK")

# 5) get / update / delete + 원자적 교체
calls = []
_orig = os.replace
def spy(a, b, *k, **kw):
    calls.append((str(a), str(b))); return _orig(a, b, *k, **kw)
os.replace = spy
tx_path = os.path.join(d, "transactions.jsonl")

assert repo.get("TX-000001").amount == 12000 and repo.get("TX-999999") is None
before = Path(tx_path).read_bytes()
assert repo.update(Transaction("TX-999999", "expense", "2024-05-01", 1, "food")) is False
assert repo.delete("TX-999999") is False
assert Path(tx_path).read_bytes() == before and calls == []      # 없는 id: 파일 불변, 교체 없음

u = Transaction("TX-000001", "expense", "2024-05-01", 13000, "food", "점심(수정)", ["회사"])
assert repo.update(u) is True
assert repo.get("TX-000001") == u
assert len(calls) == 1 and os.path.samefile(calls[0][1], tx_path)
assert os.path.dirname(os.path.abspath(calls[0][0])) == os.path.abspath(d)  # 임시 파일은 같은 폴더

assert repo.delete("TX-000002") is True
assert [x.id for x in repo.iter_transactions()] == ["TX-000001"]
assert len(calls) == 2
assert glob.glob(os.path.join(d, "*.tmp")) == []                  # 임시 파일 잔존 없음
os.replace = _orig
print("5 UPDATE_DELETE_OK")

# 6) 카테고리 사용 여부 / 추가 / 삭제
assert repo.is_category_used("food") is True
assert repo.is_category_used("rent") is False
cats.add("hobby"); assert cats.exists("hobby") and cats.list_names()[-1] == "hobby"
assert cats.remove("hobby") is True and not cats.exists("hobby")
assert cats.remove("nope") is False
print("6 CATEGORY_OK")

# 7) 예산: 저장/조회/덮어쓰기
assert buds.get("2024-05") is None
buds.set("2024-05", 300000); buds.set("2024-06", 100000); buds.set("2024-05", 350000)
assert buds.get("2024-05") == 350000 and buds.get("2024-06") == 100000
assert BudgetStore(d).get("2024-05") == 350000
lines = [l for l in Path(d, "budgets.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
assert len(lines) == 2                                            # 같은 월은 한 줄만
print("7 BUDGET_OK")

# 8) 빈(또는 공백 줄만 있는) 카테고리 파일 → 기본값 재생성
Path(d, "categories.jsonl").write_text("\n  \n", encoding="utf-8")
assert CategoryStore(d).list_names() == ["food", "transport", "rent", "etc"]
print("8 DEFAULT_CATEGORIES_OK")

# 9) 손상된 줄 → BudgetAppError(원인+힌트), 원시 예외 누출 없음
with open(tx_path, "a", encoding="utf-8") as f:
    f.write("\n")          # 빈 줄은 무시되어야 함
assert [x.id for x in repo.iter_transactions()] == ["TX-000001"]
with open(tx_path, "a", encoding="utf-8") as f:
    f.write("not json\n")
try:
    list(repo.iter_transactions()); raise SystemExit("손상 줄이 통과됨")
except BudgetAppError as e:
    assert "transactions.jsonl" in e.cause and e.hint, (e.cause, e.hint)
before = Path(tx_path).read_bytes()
try:
    repo.delete("TX-000001"); raise SystemExit("손상 파일 재작성이 통과됨")
except BudgetAppError:
    pass
assert Path(tx_path).read_bytes() == before                       # 원본 보존
assert glob.glob(os.path.join(d, "*.tmp")) == []
print("9 CORRUPT_LINE_OK")

# 10) data 경로가 파일인 경우
bad = os.path.join(d, "transactions.jsonl")  # 파일을 폴더로 지정
try:
    TransactionRepository(bad); raise SystemExit("잘못된 data 경로가 통과됨")
except BudgetAppError as e:
    assert e.hint
print("10 BAD_DATA_DIR_OK")
print("ALL_OK")
PY
ls "$D/data"
```

기대 출력:

```
1 VALIDATION_OK
2 MODEL_OK
3 INIT_OK
4 APPEND_OK
5 UPDATE_DELETE_OK
6 CATEGORY_OK
7 BUDGET_OK
8 DEFAULT_CATEGORIES_OK
9 CORRUPT_LINE_OK
10 BAD_DATA_DIR_OK
ALL_OK
budgets.jsonl  categories.jsonl  transactions.jsonl
```

그리고 프로젝트 루트에 `data/` 폴더가 생기지 않았는지 확인한다(`ls "/Users/khm04/codessey/pocket money"`).

> 참고: 스크립트 5번의 `os.replace` 감시는 `storage.py`가 `os.replace(...)` 형태로 호출한다고 가정한다(`from os import replace` 금지). 3.3의 `_atomic_rewrite` 설명대로 구현하면 이 형태가 된다.

## 7. 총괄 확인 필요

1. **카테고리 이름 형식 검증**: REQUIREMENTS에는 `category add`의 이름 규칙(빈 문자열·공백 거부, 대소문자 처리 등)이 없다. 이번 설계는 저장소가 받은 값을 그대로 저장하고, 존재 여부는 정확히 같은 문자열로 비교한다. 빈 이름을 거부할지는 3장 #6을 설계하는 다음 단계 전에 정해 달라.
2. **모든 카테고리를 지운 뒤의 동작**: [결정 안 A]를 그대로 적용하면, 사용자가 카테고리를 전부 삭제해 파일이 비는 경우 다음 실행 때 기본 4개가 다시 생긴다. 이 동작을 받아들일지 확인이 필요하다.
3. **삭제된 최대 id 재사용**: 새 id는 "현재 파일의 최대 번호 + 1"로 발급한다. 가장 큰 번호의 거래를 삭제하면 그 번호가 다시 발급될 수 있다(현재 데이터 안에서는 유일). 한 번 쓴 번호를 영구히 재사용하지 않게 하려면 카운터를 따로 저장해야 하는데, REQUIREMENTS에 근거가 없어 넣지 않았다.
4. **태그 입력 형식**: 대화형 add와 update `--tags`의 태그 입력을 CSV와 같은 쉼표 구분으로 받을지는 다음 단계(CLI/서비스)에서 정한다. 이번 단계의 `Transaction.tags`는 `list[str]`만 받는다.
