# 5단계 설계서 (보강): search 외부 정렬(external merge sort)

> 개정 1: 총괄 결정 반영. ① 한 번에 합치는 조각 수 제한(`SEARCH_MERGE_FAN_IN`)과 다단계 병합 추가. ② TMPDIR 표준 폴백 허용. ③ 병합 중 부분 출력 허용. ④ Ctrl+C 힌트 유지. ⑤ 메모리 기준값은 실측값을 보고하고, 기준과 맞지 않아도 코드를 기준에 맞추지 않음(6장).

## 1. 목표

- `search` 의 최신순 정렬을 "매칭 결과 전체를 `sorted` 로 모으기"에서 **외부 병합 정렬**로 바꾼다. 조건에 맞은 거래를 1,000건(`SEARCH_CHUNK_SIZE`)씩만 메모리에서 정렬해 시스템 임시 폴더의 조각 파일에 쓰고, 마지막에 `heapq.merge` 로 합쳐 한 건씩 출력한다.
- 조각이 `SEARCH_MERGE_FAN_IN`(64)개보다 많으면 64개씩 묶어 먼저 합치는 **다단계 병합**을 한다. 그래서 매칭 수가 아무리 많아도 동시에 여는 파일 수와 메모리가 일정 한도를 넘지 않는다.
- 출력 순서는 기존과 **완전히 같다**. 명령·옵션·출력 문구·종료 코드는 하나도 바뀌지 않는다.
- 임시 파일은 정상 종료·오류·Ctrl+C 에서 모두 지워진다. data 폴더가 읽기 전용이어도 search 는 동작한다.

## 2. 대상 요구사항

| REQUIREMENTS.md 항목 | 이번 단계 충족 범위 |
| --- | --- |
| 3장 #3 search "조건 일치 목록, **최신순, 스트리밍**" (PDF 4장 7번 "검색 결과는 최신순으로 출력", "스트리밍 처리(제너레이터 기반)를 유지") | 최신순을 유지하면서 결과를 모으지 않고 제너레이터로 한 건씩 출력. 메모리와 동시에 연 파일 수는 상수(조각 크기, FAN_IN)에 묶임 |
| 3장 "최신순" 정의 (date 내림차순, 같은 날짜면 id 내림차순) | 기존 `_recency_key` 를 조각 정렬과 모든 병합에 그대로 사용 |
| 4장 제너레이터 "한 번에 전체 로드 금지" (PDF 4장 5번 "파일 전체를 한 번에 로드하지 않고") | 거래 파일·조각 파일 모두 한 줄씩 읽음. 매칭 결과 전체도 메모리에 모으지 않음 |
| 0장 표준 라이브러리만 (`tempfile`, `heapq` 를 명시) | `tempfile.TemporaryDirectory`, `heapq.merge`, `contextlib.closing`, `pathlib.Path` |
| 2장 저장 정책 (저장 파일 3개, 기본 `./data`) | 조각 파일은 저장 파일이 아니므로 data 폴더에 만들지 않는다 |
| 4장 예외 처리 "원인 + 해결 힌트", 종료 코드 | 임시 파일 실패를 `[오류]/[힌트]`, 종료 코드 1로 변환 |
| 4장 모듈화 (모델/저장소/서비스/CLI) | 조각 파일 I/O 는 storage, 나누기·정렬·병합 흐름은 services, 출력은 cli |
| 4장 타입 힌트 | 새 함수와 바뀐 함수 모두 |
| 4장 README | search 동작 규칙에 임시 파일 설명 1줄 추가 |

## 3. 파일/모듈 설계

### 3.0 공통 결정 (이번 단계에서 고정)

| 항목 | 결정 | 근거 |
| --- | --- | --- |
| 정렬 방식 | 외부 병합 정렬. ① 매칭 거래를 한 건씩 받아 조각 리스트에 넣는다. ② 조각이 `SEARCH_CHUNK_SIZE`(1000)건으로 꽉 찬 상태에서 **한 건이 더 오면**, 조각을 최신순으로 정렬해 조각 파일 하나로 쓰고 리스트를 비운다. ③ 끝까지 읽었는데 조각 파일이 하나도 없으면(매칭 ≤ 1000) 파일 없이 메모리에서 정렬해 출력한다. ④ 조각 파일이 있으면 남은 조각도 파일로 쓴다. ⑤ 조각 수가 `SEARCH_MERGE_FAN_IN` 이하가 될 때까지 다단계 병합을 한다(아래). ⑥ 남은 조각들을 `heapq.merge(..., key=_recency_key, reverse=True)` 로 합쳐 한 건씩 내보낸다 | ← 3장 #3 최신순·스트리밍, 4장 제너레이터, 사용자 확정 조건 (b) |
| 조각 크기 | `SEARCH_CHUNK_SIZE: int = 1000` (services.py 모듈 상수) | ← 총괄 지시 "CHUNK(1000건, 상수로 명시)" |
| 한 번에 합치는 조각 수 | `SEARCH_MERGE_FAN_IN: int = 64` (services.py 모듈 상수). macOS 기본 열린 파일 한도 256 의 1/4 이다. 병합 중에는 읽는 조각 64개 + 쓰는 조각 1개 + 표준 입출력 3개 + 파이썬 자체 파일 몇 개만 열리므로 한도에 충분히 여유가 있다 | ← 총괄 결정 1, 3장 #3 스트리밍 |
| 다단계 병합 | 조각 목록(만든 순서 = 파일 순서)을 앞에서부터 `SEARCH_MERGE_FAN_IN` 개씩 묶는다. 묶음마다 `heapq.merge` 로 합쳐 같은 임시 폴더의 새 조각 파일 하나로 쓰고, 다 쓰면 그 묶음의 조각 파일들을 **즉시 지운다**. 묶음이 1개짜리면 다시 쓰지 않고 그대로 둔다. 새 조각들은 묶음 순서대로 다음 단계의 목록이 된다. 목록 길이가 `SEARCH_MERGE_FAN_IN` 이하가 될 때까지 반복한다. 예: 조각 250개, FAN_IN 64 → 1단계에서 64·64·64·58 개씩 합쳐 4개 → 마지막 병합 | ← 총괄 결정 1 |
| 조각 파일 수 | 1차 조각은 매칭 M 건(M > 1000)이면 ⌈M/1000⌉개. 예: 1001 → 2개(1000+1), 2500 → 3개(1000+1000+500), 2000 → 2개. 다단계 병합 뒤에는 최대 `SEARCH_MERGE_FAN_IN` 개 | ← 위 알고리즘 |
| 동시에 여는 파일 / 메모리 상한 | 동시에 여는 조각 파일은 최대 `SEARCH_MERGE_FAN_IN + 1`(읽기 64 + 쓰기 1)개다. 메모리는 조각 단계에서 최대 1000건, 병합 단계에서 조각마다 한 건 + 읽기 버퍼 하나(최대 64개)뿐이다. 거래 데이터는 둘 다 매칭 수와 무관하다. 단, 1차 조각 파일 경로 목록(매칭 1000건당 경로 1개, 약 1.1KB)은 매칭 수에 비례한다 — 100만 매칭에서 약 1.1MB로, 매칭 결과를 모으는 구 방식(1건당 약 700B)의 약 1/600 (검토 반영: 문구 정정) | ← 3장 #3 스트리밍, 4장 제너레이터 |
| 디스크 사용 | 임시 폴더에는 매칭 거래의 JSONL 크기만큼 쓰인다. 다단계 병합 중에는 "새 조각을 다 쓴 뒤 묶음 삭제"이므로, 잠시 최대 "전체 + 묶음 하나" 분량까지 쓰인다(3.3만 건이면 약 6MB) | ← 위 알고리즘 |
| 조각 파일 형식 | JSONL, 한 줄에 거래 하나. 기존 `Transaction.to_json_line()` / `Transaction.from_json_line()` 재사용 | ← 2장 JSONL, 총괄 지시 |
| 조각 파일 위치 | **시스템 임시 폴더**에 `tempfile.TemporaryDirectory(prefix="budget_app_search_", ignore_cleanup_errors=True)` 로 만든 개인 폴더(권한 0700) 안. 중간 병합 조각도 같은 폴더에 둔다. `dir=` 는 주지 않는다. data 폴더에는 아무것도 쓰지 않는다 | ← 사용자 확정 조건 (a), 2장 저장 파일은 data 폴더의 3개 |
| TMPDIR 를 쓸 수 없을 때 | 파이썬 `tempfile` 표준 동작을 따른다. `TMPDIR` 를 쓸 수 없으면 다음 후보(`/tmp` 등)를 쓴다(총괄 결정 2) | ← 총괄 결정 2 |
| 임시 폴더를 만드는 시점 | 첫 조각 파일을 써야 할 때(매칭 1001건째). 매칭이 1000건 이하면 만들지 않는다. 그래서 임시 폴더를 쓸 수 없어도 매칭이 1000건 이하인 search 는 성공한다 | ← 사용자 확정 조건 (b), (c) |
| 정리 | ① 서비스 제너레이터의 `try/finally` 에서 `SortRunStore.close()` 가 임시 폴더를 통째로 지운다(조각을 쓰거나, 중간 병합 중이거나, 읽는 도중의 오류·Ctrl+C). ② CLI 가 결과 제너레이터를 `contextlib.closing` 으로 감싼다. 그래서 출력(`print`) 도중 Ctrl+C 가 나도 제너레이터가 즉시 닫히고 ①의 `finally` 가 실행된다. ③ 그래도 남으면 `TemporaryDirectory` 자체의 정리 장치가 프로세스 종료 때 지운다. SIGKILL 은 정리 기회가 없어 예외 | ← 사용자 확정 조건 (a) |
| 임시 파일 오류 변환 위치 | **storage.py**(`SortRunStore`, `_iter_run`)에서 `OSError` → `BudgetAppError`. 이유: 이 오류가 "검색 정렬용 임시 파일" 오류라는 것은 그 파일을 다루는 저장소만 안다. 그대로 올리면 decorators 의 `OSError` 분기가 "경로(--data-dir, --from, --out)…" 힌트를 내 엉뚱한 안내가 된다. 1단계 `_ensure_file` 도 저장소에서 `OSError` 를 `BudgetAppError` 로 바꾼다. decorators.py 는 바꾸지 않는다 | ← 4장 예외 처리 "원인 + 해결 힌트", 사용자 확정 조건 (c) |
| 오류 문구 | cause: `검색 결과를 정렬할 임시 파일을 만들거나 읽을 수 없습니다: {상세}` (`상세` = `e.filename` 이 있으면 `"{e.filename} ({e.strerror})"`, 없으면 `str(e)`). hint: `시스템 임시 폴더(환경 변수 TMPDIR 가 가리키는 폴더, 없으면 /tmp)에 쓰기 권한과 디스크 여유 공간이 있는지 확인하세요`. 종료 코드 1 | ← 4장 예외 처리, 종료 코드 |
| 순서 동일성 | 조각 정렬은 `sorted(chunk, key=_recency_key, reverse=True)` 이고, 모든 병합은 같은 키의 `heapq.merge(reverse=True)` 다. 각 입력이 키 내림차순이면 병합 결과도 키 내림차순이다. 정상 데이터에서는 id 가 유일해 키가 모두 다르므로 기존 `sorted(전체)` 와 같은 순서가 하나뿐이다. 키가 같은 줄(손으로 고친 파일의 중복 id)이 있어도 같다. `sorted` 는 `reverse=True` 에서도 원래 순서를 유지한다(안정 정렬). `heapq.merge` 는 키가 같으면 **앞쪽 입력**을 먼저 내보낸다. 다단계 병합은 **이웃한 조각을 순서대로** 묶고, 결과를 묶음 순서대로 다음 단계에 넘긴다. 그래서 어느 단계에서도 "앞쪽 조각 = 파일의 앞쪽 줄"이 유지되고, 결국 파일 순서가 유지된다. 6.2 A절에서 중복 id 와 다단계 병합으로 확인한다 | ← 3장 "최신순" 정의, 총괄 지시 "완전히 같은 순서" |
| 조각 파일 읽기 버퍼 | 조각 파일은 동시에 최대 64개 열리므로 파일당 읽기 버퍼를 `_RUN_READ_BUFFER = 8192` 바이트로 고정한다(`open(..., buffering=_RUN_READ_BUFFER)`). 파이썬 버전마다 기본 버퍼 크기가 달라질 수 있어도 메모리를 예측할 수 있게 하려는 것이다 | ← 4장 제너레이터(메모리 제한), 3장 #3 스트리밍 |
| 바뀌지 않는 것 | 명령·옵션(`--from --to --category --type --q --tag --data-dir --help`), 검증 순서와 문구, 출력 형식(`_format_tx`), `조건에 맞는 거래가 없습니다.`, 종료 코드 0/1/2, `list`·`summary`·`export` 등 다른 명령 | ← 총괄 지시 4 (기능 추가 금지) |

### 3.1 변경 파일 / 변경 금지 파일

- 변경: `budget_app/storage.py`(추가만), `budget_app/services.py`, `budget_app/cli.py`(`_cmd_search` 와 import 1줄), `README.md`(1줄 추가).
- **변경 금지**: `budget_app/models.py`, `budget_app/decorators.py`, `budget_app/__main__.py`, `budget_app/__init__.py`. 6.2 S0 에서 해시와 문구로 확인한다.
- 다른 명령의 코드는 건드리지 않는다.

### 3.2 `budget_app/storage.py` — [저장소] (추가)

import 추가는 없다(`tempfile`, `Iterable`, `Iterator`, `Path`, `Transaction`, `BudgetAppError` 를 이미 import 하고 있다). 다음 호출 형태를 지킨다.
- `tempfile` 은 반드시 `tempfile.TemporaryDirectory(...)` 형태로 부른다(`from tempfile import ...` 금지).
- 파일은 내장 `open(...)` 으로 연다(`io.open` 금지).

6.2 A·C절이 `tempfile` 모듈 속성과 내장 `open` 을 바꿔 끼워 검사하므로 이 형태가 필요하다. `mkstemp`·`os.replace` 도 새로 쓰지 않는다(4단계 S8: 각 1회는 `_atomic_write` 에만).

#### 모듈 상수 / 함수

| 시그니처 | 책임 | 근거 |
| --- | --- | --- |
| `_SORT_DIR_PREFIX: str = "budget_app_search_"` | 임시 폴더 이름 앞부분. SIGKILL 뒤 남은 폴더를 사람이 알아볼 수 있게 하고, 검사 스크립트가 잔존 여부를 찾을 때 쓴다 | ← 3장 #3 search (조각 파일 위치), 사용자 확정 조건 (a) |
| `_RUN_READ_BUFFER: int = 8192` | 조각 파일 하나의 읽기 버퍼 크기(3.0) | ← 4장 제너레이터, 3장 #3 스트리밍 |
| `_TEMP_HINT: str = "시스템 임시 폴더(환경 변수 TMPDIR 가 가리키는 폴더, 없으면 /tmp)에 쓰기 권한과 디스크 여유 공간이 있는지 확인하세요"` | 임시 파일 오류 공통 힌트 | ← 4장 예외 처리, 사용자 확정 조건 (c) |
| `def _temp_file_error(e: OSError) -> BudgetAppError` | `detail = str(e) if e.filename is None else f"{e.filename} ({e.strerror})"` → `BudgetAppError(cause=f"검색 결과를 정렬할 임시 파일을 만들거나 읽을 수 없습니다: {detail}", hint=_TEMP_HINT)` | ← 4장 예외 처리, 사용자 확정 조건 (c) |
| `def _iter_run(path: Path) -> Iterator[Transaction]` | **제너레이터.** `try:` 안에서 `with open(path, encoding="utf-8", buffering=_RUN_READ_BUFFER) as f:` → `for line in f: yield Transaction.from_json_line(line)`. `except OSError as e: raise _temp_file_error(e) from None`. 조각 파일 전체를 읽지 않고 한 줄씩 넘긴다. 끝까지 읽으면 `with` 가 끝나 파일이 바로 닫힌다 | ← 4장 제너레이터, 3장 #3 스트리밍, 사용자 확정 조건 (c) |

#### `class SortRunStore`

search 외부 정렬용 **임시 조각 파일 저장소**. 시스템 임시 폴더에 개인 폴더 하나를 만들고, 그 안에서 조각 파일(`run-000001.jsonl`, `run-000002.jsonl`, … 중간 병합 조각 포함)을 쓰고, 읽고, 지운다. 어느 조각을 언제 합칠지는 서비스가 정한다. ← 3장 #3, 4장 모듈화(파일 I/O 는 저장소)

| 시그니처 | 책임 | 근거 |
| --- | --- | --- |
| `def __init__(self) -> None` | `try: self._dir = tempfile.TemporaryDirectory(prefix=_SORT_DIR_PREFIX, ignore_cleanup_errors=True)` / `except OSError as e: raise _temp_file_error(e) from None`. `self._count = 0` (지금까지 만든 조각 파일 수. 파일 이름 번호용) | ← 사용자 확정 조건 (a)(c) |
| `def write_run(self, txs: Iterable[Transaction]) -> Path` | `self._count += 1`, `path = Path(self._dir.name) / f"run-{self._count:06d}.jsonl"`. `try:` 안에서 `with open(path, "w", encoding="utf-8") as f:` → `for tx in txs: f.write(tx.to_json_line() + "\n")`. `except OSError as e: raise _temp_file_error(e) from None`. `path` 반환. `txs` 는 정렬된 조각 리스트일 수도 있고, 중간 병합의 `heapq.merge` 결과(한 건씩 나오는 반복자)일 수도 있다 | ← 3장 #3, 2장 JSONL, 사용자 확정 조건 (c), 총괄 결정 1 |
| `def read_run(self, path: Path) -> Iterator[Transaction]` | `return _iter_run(path)`. 조각 파일 하나를 한 줄씩 읽는 제너레이터(파일은 처음 `next` 할 때 열린다) | ← 3장 #3, 4장 제너레이터 |
| `def remove_run(self, path: Path) -> None` | `try: path.unlink()` / `except OSError as e: raise _temp_file_error(e) from None`. 다 합친 조각을 바로 지워 디스크를 아낀다 | ← 총괄 결정 1 "다 쓴 조각은 즉시 지운다" |
| `def close(self) -> None` | `self._dir.cleanup()` — 임시 폴더와 남은 조각 파일을 모두 지운다. `ignore_cleanup_errors=True` 라 지우기 실패가 원래 오류를 가리지 않는다 | ← 사용자 확정 조건 (a) |

- `print`/`input` 은 쓰지 않는다.
- `KeyboardInterrupt` 는 `OSError` 가 아니므로 바꾸지 않고 그대로 올린다(데코레이터가 기존 Ctrl+C 메시지를 낸다).
- 중간 병합에서 `write_run` 이 읽는 쪽(`_iter_run`)의 오류는 이미 `BudgetAppError` 로 바뀌어 올라온다. `write_run` 의 `except OSError` 에 다시 잡히지 않는다.

### 3.3 `budget_app/services.py` — [서비스] (추가·변경)

import 변경: `collections.abc` 에서 `Generator` 추가, `from pathlib import Path` 추가(조각 파일 경로 목록의 타입), storage 에서 `SortRunStore` 추가. **`tempfile` 은 import 하지 않고 `open(` 도 쓰지 않는다**(파일 I/O 는 저장소).

#### 모듈 상수 / 함수

| 시그니처 | 책임 | 근거 |
| --- | --- | --- |
| `SEARCH_CHUNK_SIZE: int = 1000` | 메모리에서 한 번에 정렬하는 최대 거래 수(조각 크기) | ← 3장 #3 스트리밍, 총괄 지시 |
| `SEARCH_MERGE_FAN_IN: int = 64` | 한 번에 합치는(= 동시에 여는) 최대 조각 파일 수 | ← 3장 #3 스트리밍, 총괄 결정 1 |
| `def _sort_chunk(chunk: list[Transaction]) -> list[Transaction]` | `return sorted(chunk, key=_recency_key, reverse=True)`. **services.py 의 유일한 `sorted` 호출.** 조각(최대 `SEARCH_CHUNK_SIZE` 건)만 정렬한다. 모듈 함수로 둔다(검사 스크립트가 조각 크기를 기록하려고 바꿔 끼운다) | ← 3장 "최신순" 정의 |
| `def _merge_runs(runs: SortRunStore, paths: list[Path]) -> Iterator[Transaction]` | `return heapq.merge(*(runs.read_run(p) for p in paths), key=_recency_key, reverse=True)`. **services.py 의 유일한 `heapq.merge` 호출.** 중간 병합과 마지막 병합이 함께 쓴다. `paths` 의 순서가 곧 같은 키일 때의 우선순위다 | ← 3장 #3 최신순·스트리밍 |
| `def _merge_down(runs: SortRunStore, paths: list[Path]) -> list[Path]` | 다단계 병합. 아래 골격 그대로. 조각 목록 길이가 `SEARCH_MERGE_FAN_IN` 이하가 될 때까지 앞에서부터 묶어 합치고, 합친 조각은 즉시 지운다. 남은 조각 목록(파일 순서 유지)을 돌려준다 | ← 총괄 결정 1, 3장 #3 |

**`_merge_down` 골격** (`# [주석 X]` 는 3.6 의 한국어 "왜" 주석을 넣을 자리)

```python
def _merge_down(runs: SortRunStore, paths: list[Path]) -> list[Path]:
    # [주석 H]
    while len(paths) > SEARCH_MERGE_FAN_IN:
        merged: list[Path] = []
        for start in range(0, len(paths), SEARCH_MERGE_FAN_IN):
            group = paths[start:start + SEARCH_MERGE_FAN_IN]
            if len(group) == 1:
                merged.append(group[0])
                continue
            merged.append(runs.write_run(_merge_runs(runs, group)))
            # [주석 I]
            for p in group:
                runs.remove_run(p)
        paths = merged
    return paths
```

#### `class LedgerService` (변경·추가)

| 시그니처 | 책임 | 근거 |
| --- | --- | --- |
| `def search_transactions(self, *, date_from: str \| None, date_to: str \| None, category: str \| None, type_: str \| None, q: str \| None, tag: str \| None) -> Generator[Transaction, None, None]` (변경) | 1~2단계(조건 없음 오류, `SearchFilter` 생성·검증)는 **기존 코드 그대로**, 함수 안에서 즉시 실행한다. 이 함수 자체는 제너레이터가 아니다(`yield` 없음). 그래서 입력 오류는 거래 파일을 읽기 전에, CLI 가 출력을 시작하기 전에 난다. 마지막 줄만 `return self._iter_recent_matches(flt)` 로 바꾼다. 기존 282~285행 주석("매칭 결과만 모아 정렬…")은 지운다 | ← 3장 #3 |
| `def _iter_recent_matches(self, flt: SearchFilter) -> Generator[Transaction, None, None]` | **제너레이터.** 외부 정렬 본체. 아래 골격 그대로 | ← 3장 #3 최신순·스트리밍, 4장 제너레이터, 사용자 확정 조건 (a)(b) |
| `def _iter_matches(self, flt: SearchFilter) -> Iterator[Transaction]` | 변경 없음 | — |

**`_iter_recent_matches` 골격**

```python
def _iter_recent_matches(self, flt: SearchFilter) -> Generator[Transaction, None, None]:
    # [주석 A]
    chunk: list[Transaction] = []
    paths: list[Path] = []
    runs: SortRunStore | None = None
    try:
        for tx in self._iter_matches(flt):
            if len(chunk) == SEARCH_CHUNK_SIZE:
                # [주석 B]
                if runs is None:
                    runs = SortRunStore()  # [주석 C]
                paths.append(runs.write_run(_sort_chunk(chunk)))
                chunk = []
            chunk.append(tx)
        if runs is None:
            # [주석 D]
            yield from _sort_chunk(chunk)
            return
        paths.append(runs.write_run(_sort_chunk(chunk)))
        chunk = []
        paths = _merge_down(runs, paths)
        # [주석 E]
        yield from _merge_runs(runs, paths)
    finally:
        # [주석 F]
        if runs is not None:
            runs.close()
```

- `SEARCH_CHUNK_SIZE`, `SEARCH_MERGE_FAN_IN`, `_sort_chunk` 는 실행할 때 모듈 전역에서 찾는다(지역 변수나 기본 인자로 복사하지 않는다). 6.2 A·C절이 이것들을 바꿔 끼워 조각 경계와 다단계 병합을 검사한다.
- 메모리: 조각 단계에서는 최대 `SEARCH_CHUNK_SIZE` 건이다. 병합 단계(중간·마지막)에서는 읽는 조각마다 한 건 + 읽기 버퍼 하나(최대 `SEARCH_MERGE_FAN_IN` 개)다. 조각 단계가 끝나면 마지막 조각까지 파일로 쓰고 리스트를 비우므로 두 단계가 겹치지 않는다. 거래 파일은 조각 단계가 끝날 때 닫힌다.

### 3.4 `budget_app/cli.py` — [CLI] (최소 변경)

import 추가: `from contextlib import closing`. `storage` 는 여전히 import 하지 않는다.

| 시그니처 | 책임 | 근거 |
| --- | --- | --- |
| `@handle_errors def _cmd_search(args: argparse.Namespace) -> int` (변경) | 아래 골격. 결과를 리스트로 모으지 않고(`list`/`len`/`if not txs` 없음) 한 줄씩 출력한다. 결과가 없었는지는 `found` 플래그로 판단한다. 출력 문구와 종료 코드는 그대로다 | ← 3장 #3 스트리밍, 사용자 확정 조건 (a) |

```python
@handle_errors
def _cmd_search(args: argparse.Namespace) -> int:
    service = LedgerService(args.data_dir)
    found = False
    # [주석 G]
    with closing(
        service.search_transactions(
            date_from=args.date_from,
            date_to=args.date_to,
            category=args.category,
            type_=args.type,
            q=args.q,
            tag=args.tag,
        )
    ) as txs:
        for tx in txs:
            print(_format_tx(tx))
            found = True
    if not found:
        print("조건에 맞는 거래가 없습니다.")
    return EXIT_OK
```

- 파서·help 문구·다른 핸들러는 바꾸지 않는다. `@handle_errors` 개수는 12개 그대로다.

### 3.5 `README.md` (1줄 추가)

**판단: 추가한다.** 사용자가 시스템 임시 폴더에 생기는 `budget_app_search_…` 폴더를 볼 수 있고, 임시 폴더나 디스크 오류 때 힌트가 임시 폴더를 가리키므로, 파일 위치를 문서에 적어 둔다. 근거: 4장 README "저장 파일 위치/형식", PDF 4장 3·6번 "문서에 명확히".

위치는 `## 동작 규칙` 의 `- **search**:` 하위 목록 마지막(현재 `--q` 줄 다음)이다. 아래 한 줄을 그대로 넣는다.

```
  - 맞는 거래가 1000건을 넘으면 메모리를 아끼려고 1000건씩 최신순으로 정렬해 시스템 임시 폴더(환경 변수 TMPDIR 가 가리키는 폴더, 없으면 /tmp)에 임시 파일로 나눠 쓴 뒤, 그 파일들을 합치면서 한 줄씩 출력합니다. 임시 파일은 검색이 끝나면(오류나 Ctrl+C 로 멈춰도) 지워지고, data 폴더에는 아무것도 쓰지 않습니다.
```

- console 예시 블록은 하나도 바꾸지 않는다(4단계 N절 재생 검사 유지).
- `--` 로 시작하는 단어를 새로 쓰지 않는다(4단계 N3 "help 에 없는 옵션" 검사 유지). 이 줄에는 `--` 로 시작하는 단어가 없다.

### 3.6 학습자(비전공자)용 "왜" 주석 위치

짧은 한국어 주석 1~3줄. 아래 내용을 담는다(문장은 자유).

| 위치 | 담을 내용 |
| --- | --- |
| [주석 A] `_iter_recent_matches` 첫머리 | 결과는 최신순이어야 하는데 파일은 입력 순서라서, 맞는 거래를 다 보기 전에는 첫 줄을 정할 수 없다. 전부 모아 정렬하면 메모리가 매칭 수만큼 커지므로, 1000건씩 정렬해 파일로 내려놓았다가 나중에 합치는 "외부 정렬"을 쓴다 |
| [주석 B] 조각이 꽉 찼을 때 | 1000건이 찼는데 한 건이 더 왔으므로 지금 조각을 정렬해 파일로 쓰고 리스트를 비운다. 그래서 메모리에는 항상 1000건 이하만 남는다. "한 건 더 왔을 때" 쓰는 이유: 딱 1000건으로 끝나면 파일을 만들 필요가 없기 때문 |
| [주석 C] `SortRunStore()` | 임시 폴더는 처음 필요해진 순간에만 만든다. 결과가 적으면 디스크를 전혀 쓰지 않는다 |
| [주석 D] `runs is None` 분기 | 맞는 거래가 1000건 이하라 이미 전부 메모리에 있으므로, 파일 없이 바로 정렬해 내보낸다 |
| [주석 E] 마지막 `_merge_runs` (와 `_merge_runs` 함수 위) | 조각 파일은 각각 이미 최신순이다. 그래서 각 조각의 "맨 앞 한 건"끼리만 비교해 가장 최신인 것을 내보내고, 그 조각에서 다음 한 건을 읽는다(줄을 합쳐 서는 원리). 메모리에는 조각마다 한 건만 있다 |
| [주석 F] `finally` | 정상 종료든 오류든 Ctrl+C 든, 이 제너레이터가 끝나거나 닫힐 때 반드시 임시 폴더를 지운다 |
| [주석 G] `closing` | 결과를 모으지 않고 한 줄씩 받는다. `closing` 은 출력 도중 Ctrl+C 로 반복이 끊겨도 제너레이터를 즉시 닫아, 서비스의 `finally`(임시 파일 삭제)가 바로 실행되게 한다 |
| [주석 H] `_merge_down` 첫머리 | 조각을 한꺼번에 합치려면 조각 파일을 모두 동시에 열어야 한다. 그런데 운영체제는 한 프로그램이 동시에 열 수 있는 파일 수를 제한한다(macOS 기본 256개). 그래서 64개씩 먼저 합쳐 조각 수를 줄이는 일을 반복한다. 이웃한 조각을 순서대로 묶으므로 최신순과 같은 날짜·같은 id 의 순서도 그대로 유지된다 |
| [주석 I] `remove_run` 반복 | 합친 내용은 새 조각에 모두 들어갔으므로 원래 조각들은 바로 지워 디스크를 아낀다 |
| `SEARCH_MERGE_FAN_IN` 위 | 왜 64인가: 동시에 여는 파일이 "64(읽기) + 1(쓰기) + 표준 입출력"이 되어 macOS 기본 한도 256 보다 충분히 작고, 메모리도 조각 64개분 버퍼로 묶인다 |
| `SortRunStore` 클래스 설명 | 조각 파일을 data 폴더가 아니라 시스템 임시 폴더에 두는 이유: 조각 파일은 저장 데이터가 아니라 검색 중에만 쓰는 작업 파일이다. data 폴더가 읽기 전용이어도 검색은 되어야 한다. 원자적 교체용 임시 파일과 달리 같은 폴더에 둘 필요가 없다. `TemporaryDirectory` 는 본인만 읽을 수 있는 폴더(권한 0700)를 만들어 메모 내용이 다른 사용자에게 보이지 않는다 |
| `_temp_file_error` 위 | `OSError` 를 그대로 올리면 공통 데코레이터가 data 폴더(`--data-dir`) 확인을 안내하게 된다. 이 오류는 임시 폴더·디스크 문제이므로 여기서 맞는 힌트로 바꾼다 |
| `_RUN_READ_BUFFER` 위 | 조각 파일이 동시에 여러 개(최대 64개) 열리므로 파일 하나당 버퍼를 작게 고정해 메모리를 예측할 수 있게 한다 |

## 4. 계층 규칙

1~4단계와 같다. 새 import 도 이 표 안에서만 한다.

```
__main__.py → cli.py → services.py → storage.py → models.py
                 └──→ decorators.py ──→ models.py
```

| 모듈 | import 가능한 `budget_app` 모듈 | 이번 단계 추가 import |
| --- | --- | --- |
| `models.py` | 없음 | 없음 (변경 금지) |
| `storage.py` | `models` | 없음 (`tempfile`, `Path` 는 이미 있음) |
| `services.py` | `storage`, `models` | `SortRunStore`(storage), `Generator`(collections.abc), `Path`(pathlib). **`tempfile` 금지** |
| `decorators.py` | `models` | 없음 (변경 금지) |
| `cli.py` | `services`, `decorators`, `models` — **`storage` 금지** | `contextlib.closing` (표준 라이브러리) |
| `__main__.py` | `cli` | 없음 (변경 금지) |

- 파일 열기(`open(`)·삭제와 `tempfile` 은 `storage.py` 에만 둔다. services 는 `Path` 를 조각을 가리키는 값으로 주고받기만 한다(열거나 지우지 않는다).
- `print`/`input` 은 `cli.py`, `decorators.py` 에만 둔다.
- 상대 import 금지. 표준 라이브러리 밖의 모듈 금지.

## 5. 예외/경계 상황

| 상황 | 처리 | 종료 코드 |
| --- | --- | --- |
| 조건 없음 / 날짜·type·카테고리·`--q`·`--tag` 값 오류 | 기존과 같다. `search_transactions` 가 즉시 검증하므로 거래 파일을 읽기 전에 오류가 나고, 임시 폴더도 만들지 않는다 | 1 |
| 매칭 0건 (빈 파일 포함) | `조건에 맞는 거래가 없습니다.` 출력. 임시 폴더 없음 | 0 |
| 매칭 1 ~ 1000건 (경계 999, 1000) | 메모리에서 정렬해 출력. 임시 폴더를 만들지 않음 | 0 |
| 매칭 1001 ~ 64,000건 (경계 1001, 2500) | 임시 폴더 1개, 조각 ⌈M/1000⌉개(1001 → 1000+1, 2500 → 1000+1000+500)를 한 번에 병합. 끝나면 삭제 | 0 |
| 매칭 64,001건 이상 (조각 > 64) | 다단계 병합. 동시에 여는 조각 파일은 최대 65개. 합친 조각은 즉시 삭제. 끝나면 임시 폴더 삭제 | 0 |
| 열린 파일 한도가 낮은 환경 (예: 한도 100) | 64 + 1 + 표준 입출력·파이썬 자체 파일로 한도 안에서 동작 (6.2 B7) | 0 |
| 키가 같은 줄(중복 id 이고 날짜도 같음) | 파일 순서를 유지한다(구 방식 `sorted` 와 같음, 3.0). 다단계 병합에서도 같음 | 0 |
| data 폴더·저장 파일이 읽기 전용 | 정상 동작(거래 파일은 읽기만 하고 조각은 시스템 임시 폴더에 쓴다). data 폴더에 파일이 생기지 않음 | 0 |
| 거래 파일 손상 줄 (조각을 쓰는 도중 발견) | 기존 `[오류] … transactions.jsonl 파일 N번째 줄…`. 출력이 시작되기 전이라 stdout 은 비어 있고, 임시 폴더는 `finally` 에서 삭제된다 | 1 |
| 파이썬이 고른 시스템 임시 폴더에 쓸 수 없음 / 쓸 수 있는 임시 폴더가 하나도 없음 | 매칭 1001건째에서 `[오류] 검색 결과를 정렬할 임시 파일을 만들거나 읽을 수 없습니다: …` + `[힌트] 시스템 임시 폴더(… TMPDIR …)에 쓰기 권한과 디스크 여유 공간…`. stdout 은 비어 있음. **매칭이 1000건 이하면 성공** | 1 (≤1000건이면 0) |
| `TMPDIR` 만 쓸 수 없고 `/tmp` 는 쓸 수 있음 | 파이썬 `tempfile` 표준 동작으로 다음 후보 폴더(`/tmp` 등)를 써서 **성공**한다(총괄 결정 2). 모든 후보가 불가하면 마지막 후보인 현재 폴더가 쓰일 수 있다(실행 중에만 있고 끝나면 지워짐) | 0 |
| 조각 파일 쓰기 실패 (디스크 부족 ENOSPC 등, 1차 조각·중간 병합 조각 모두) | 위와 같은 `[오류]/[힌트]`. 임시 폴더 삭제, stdout 비어 있음 | 1 |
| 조각 파일 읽기·삭제 실패: 중간 병합 중 또는 마지막 병합 시작 시 | 위와 같은 `[오류]/[힌트]`. `heapq.merge` 는 모든 입력의 첫 줄을 읽은 뒤에야 첫 결과를 내므로 stdout 은 비어 있다. 임시 폴더 삭제 | 1 |
| 조각 파일 읽기 실패: 마지막 병합 도중(출력 중) | 이미 출력한 줄은 남고 `[오류]/[힌트]` 로 끝난다(스트리밍 출력의 성질, 총괄 결정 3으로 허용). 임시 폴더 삭제 | 1 |
| Ctrl+C: 조각을 쓰는 중 / 중간 병합 중 / 출력하는 중 | 기존 `[오류] 사용자가 입력을 중단했습니다 (Ctrl+C)` + 힌트(문구는 그대로, 총괄 결정 4). 모든 경우 임시 폴더 삭제(3.0 정리 ①②) | 1 |
| SIGKILL·전원 차단 | 정리 기회가 없어 시스템 임시 폴더에 `budget_app_search_…` 폴더가 남을 수 있다(사용자 확정: 예외). 데이터 파일은 읽기만 했으므로 영향 없음 | (-9) |
| 출력이 파이프로 이어지다 끊김 (`… \| head`) | 기존과 같은 데코레이터 `OSError` 메시지. 단, `closing` 덕분에 임시 폴더는 지워진다 | 1 |
| 어떤 경우에도 | `Traceback` 없음. `[오류]/[힌트]` 는 stderr | — |

### Python 3.10 호환 주의

1~4단계 금지 목록을 그대로 적용한다. 이번 단계에서 쓰는 것 중 다음은 모두 3.10 에서 동작한다.
- `TemporaryDirectory(ignore_cleanup_errors=...)`: 3.10 에 추가되었다.
- `heapq.merge(key=, reverse=)`: 3.5+.
- `collections.abc.Generator`, `contextlib.closing`, `Path.unlink()`, `X | None`.

검사 스크립트의 `sys.stdlib_module_names` 도 3.10+ 이다. `resource` 모듈은 macOS·리눅스에 있다. 둘 다 검사 코드에서만 쓴다.

## 6. 완료 기준 (에이전트 3 검증 절차)

### 6.1 이전 단계 검사에 주는 영향과 이번 단계 검사 항목

**이전 단계 검사 영향 분석**

| 이전 검사 | 이번 변경 후 | 5단계 스크립트의 처리 |
| --- | --- | --- |
| 4단계 S0 (models, `__main__`, `__init__` SHA-256) | 세 파일을 바꾸지 않으므로 그대로 통과 | 회귀로 그대로 실행 + 5단계 S0 에서도 확인 |
| 3단계 S0 (4단계 R 이 storage·decorators 해시 줄을 지운 뒤 남은 3개) | 위와 같음 | 그대로 |
| 4단계 S8 (storage 의 `os.replace`·`mkstemp` 각 1회, 모든 `open` 에 `encoding=`, 스트림을 `list`/`sorted` 로 모으기 금지) | 조각 파일은 `TemporaryDirectory` + `open(encoding=…)` 이고, `sorted` 의 첫 인자는 이름(`chunk`)이라 통과 | 그대로 |
| 4단계 S9 (`open(` 은 storage 에만) | services·cli 에 `open(` 없음(`closing(` 은 걸리지 않음) | 그대로 |
| 4단계 N (README 재생·옵션·필수 문구) | console 블록은 그대로이고 추가 줄에 `--` 옵션이 없어 통과 | 그대로 |
| **3단계 S8** `sorted_args != ["_iter_matches"]` | `sorted(chunk, …)` 라 `[None]` → **깨짐** | 5단계 기준으로 치환: `sorted_args != [None]` |
| **3단계 S8** `search_transactions` 에 `sorted` 호출 | `sorted` 는 `_sort_chunk` 에 있음 → **깨짐** | 치환: `_sort_chunk` 에 `sorted` 가 있어야 함 |
| **3단계 M** `searchN big > 5 × small` (매칭 수에 비례해야 함) | 외부 정렬이라 비례하지 않음 → **깨짐** | 치환: `searchN big < 2 × small` (반대 방향) |
| 3단계 D·H 등 search 출력·오류 검사 | 출력이 같으므로 통과 | 그대로 |
| 1·2단계 6.2 | search 의 정렬을 검사하지 않음(2단계 (h) 는 6.1 에만 있고 회귀 대상이 아님) | 그대로 |

**회귀 실행 방식**: 4단계 6.2 스크립트를 꺼내 두 군데를 고쳐 실행한다.
1. 임시 폴더(`W`) 줄을 이 스크립트의 `$W` 아래로 바꾼다. R 절 안의 같은 문자열은 그대로 둔다.
2. 4단계 R 절이 3단계 스크립트를 고치는 자리(`lines = s3.split("\n")` 바로 앞)에 위 치환 3개를 끼워 넣는다.

이렇게 하면 4단계 스크립트 → 3단계 스크립트(4단계 치환 + 5단계 치환) → 1·2단계 스크립트가 차례로 모두 다시 실행된다.

**5단계 검사 항목**

| # | 검사 | 기대 |
| --- | --- | --- |
| S0 | models, `__main__`, `__init__` SHA-256 이 4단계와 같음. decorators.py 에 4단계 `OSError` 힌트 문구가 그대로 있고 `TMPDIR`·`tempfile`·`임시` 가 없음(오류 변환은 storage 에서 한다) | 일치 |
| S1 | 파일 7개 존재 | 존재 |
| S2 | 3.10 문법 | 통과 |
| S3 | 3.11+ 전용 API grep | 없음 |
| S4 | 계층 규칙 + **표준 라이브러리만** (`sys.stdlib_module_names`) | 위반 없음 |
| S5 | 모든 함수(중첩 포함)의 타입 힌트 | 누락 없음 |
| S6 | services/cli 구조. 아래 항목을 모두 만족 | 위반 없음 |
| S7 | storage 구조. 아래 항목을 모두 만족 | 위반 없음 |
| S8 | `print/input` 위치, `open(` 은 storage 에만, `.read()`/`readlines(` 없음 | 위반 없음 |
| S9 | README 에 search 임시 파일 설명(`TMPDIR`) | 있음 |
| A | 순서 동일성 + 경계 + 다단계 병합 (아래) | `ORDER_OK` |
| B | 임시 파일 정리·위치, 별도 프로세스 (아래) | `CLEANUP_OK` |
| C | 임시 파일 실패 → `[오류]/[힌트]`, 같은 프로세스에서 주입 (아래) | `TEMP_ERROR_OK` |
| M | 메모리, tracemalloc (아래) | `SEARCH_MEMORY_OK` |
| R | 1~4단계 회귀 (위 방식) | `STEP4_ALL_OK` 포함, `FAIL` 없음 |
| 마무리 | 이 스크립트 전체(회귀 포함)가 쓴 시스템 임시 폴더(`$W/systmp`)에 `budget_app_search_*` 잔존 없음. `./data`·`__pycache__`·루트의 예상 밖 파일 없음 | `STEP5_ALL_OK` |

**S6 services/cli 구조 세부 항목**
- 상수: `SEARCH_CHUNK_SIZE: int = 1000`, `SEARCH_MERGE_FAN_IN: int`(2 이상 128 이하 정수 상수).
- `sorted` 는 services 전체에서 1회, `_sort_chunk` 안에서 그 매개변수만 `key=_recency_key, reverse=True` 로 정렬한다. `.sort()` 는 없다.
- `heapq.merge` 는 services 전체에서 1회, `_merge_runs` 안에서 `key=_recency_key, reverse=True` 로 부른다.
- `_merge_down` 은 `SEARCH_MERGE_FAN_IN` 을 쓰는 `while` 반복이 있고, `_merge_runs`·`write_run`·`remove_run` 을 부른다.
- 스트림(`iter_transactions`, `_iter_matches`, `_iter_recent_matches`, `search_transactions`)을 `list/tuple/set/sorted/len`·컴프리헨션으로 모으지 않는다.
- `_iter_recent_matches` 는 제너레이터다. `_iter_matches()` 를 `for` 로 돌고, `SEARCH_CHUNK_SIZE`·`_sort_chunk`·`SortRunStore`·`write_run`·`_merge_down`·`_merge_runs` 를 쓰며, `finally` 에서 `close()` 를 부른다.
- `search_transactions` 는 제너레이터가 아니고 `_iter_recent_matches` 를 부른다.
- services 에 `tempfile` import 가 없다.
- `_cmd_search` 는 `closing` 을 쓰고 `for` 로 출력하며 `list/tuple/len/sorted` 를 쓰지 않는다. cli 에 `sorted/nlargest/nsmallest` 가 없다.

**S7 storage 구조 세부 항목**
- `SortRunStore` 에 `__init__/write_run/read_run/remove_run/close` 가 있고, `write_run` 은 `-> Path` 를 돌려준다.
- `tempfile.TemporaryDirectory(…)` 는 storage 전체에서 1회, `SortRunStore.__init__` 안에서 부른다. `dir=` 는 없고, `prefix=` 와 `ignore_cleanup_errors=True` 가 있다.
- `from tempfile import` 가 없다.
- `_iter_run` 은 제너레이터이고 `open(…, encoding=, buffering=)` 을 쓴다.
- `__init__`·`write_run`·`remove_run`·`_iter_run` 은 `except OSError` 에서 `_temp_file_error(…)` 로 바꾼다.
- `close` 는 `cleanup()` 을 부른다.
- `os.replace`·`mkstemp` 는 각 1회다(4단계 그대로).

**A. 순서 동일성 + 경계 + 다단계 병합** (같은 프로세스)
- 데이터: 6,000건. 날짜를 84개로 몰아 같은 날짜가 많다.
- 매칭 **999 / 1000 / 1001 / 2500** 건 태그, `--category`, `--type`, `--from/--to`, `--q`, 조합 조건, 0건마다 CLI 출력이 "구 방식 = 매칭 전체를 (날짜, id 숫자) 내림차순 `sorted`" 결과와 글자 하나까지 같다.
- 조각 크기 기록이 기대와 같다: `[999]`, `[1000]`, `[1000, 1]`, `[1000, 1000, 500]` 등.
- 임시 폴더는 매칭 > 조각 크기일 때만 1개 생기고, 시스템 임시 폴더 바로 아래에 있다.
- **조각 파일을 쓴 횟수**가 "1차 조각 수 + 중간 병합 수"와 같다. 정리 직전에 남은 조각 파일 수가 "마지막 단계 조각 수(≤ FAN_IN)"와 같다(다 쓴 조각은 즉시 지워졌다는 증거). 끝나면 임시 폴더가 사라진다.
- **동시에 열린 조각 파일 수가 `FAN_IN + 1` 이하**다(내장 `open` 을 감시).
- data 폴더에 파일이 생기지 않는다.
- 조각 크기와 FAN_IN 을 작게 바꿔 다단계 병합이 일어나게 한 경우에도 같은 검사를 모두 통과한다. 경우: (조각 10건, FAN_IN 기본 64, 매칭 2500 → 1차 250개 → 4개), (조각 4, FAN_IN 3), (조각 7, FAN_IN 2), (조각 4·7·10·1000, FAN_IN 64). 이 중 일부는 **중복 id(같은 키)** 가 조각 경계를 넘는 데이터다.

**B. 임시 파일 정리·위치** (별도 프로세스, 실행마다 빈 TMPDIR)
- 정상 종료(2500건), 오류 종료(2500건 뒤 손상 줄), Ctrl+C(조각을 쓰는 중 / 출력하는 중, 12만 건 = 1차 조각 120개라 다단계 병합 포함) 뒤 TMPDIR 이 비어 있다. Ctrl+C 시점에 조각 파일이 TMPDIR 에 실제로 있었다.
- **data 폴더 읽기 전용**(폴더 555, 파일 444)에서 2500건 search 가 성공하고, 출력이 쓰기 가능 폴더일 때와 같다.
- TMPDIR 이 쓰기 불가인 폴더면 파이썬 표준 동작대로 성공하고, 그 폴더에는 아무것도 남지 않는다.
- **열린 파일 한도를 100 으로 낮춘 프로세스**에서 12만 건 search 가 성공한다. 1차 조각이 120개라 다단계 병합이 없으면 실패하는 조건이다. 끝난 뒤 TMPDIR 이 비어 있다.

**C. 임시 파일 실패 → `[오류]/[힌트]`** (같은 프로세스에서 주입)
- 공통 검사: 종료 코드 1, stdout 비어 있음, `[오류]`·`[힌트]` 각 1줄, 힌트에 `TMPDIR`·`디스크` 가 있고 `--data-dir` 는 없음, 예외가 `main` 밖으로 새지 않음, 임시 폴더 잔존 없음.
- ① 파이썬이 고른 임시 폴더(`tempfile.tempdir`)를 쓰기 불가 폴더로 지정 → 2500건 search 가 공통 검사를 통과한다. 같은 상태에서 1000건 search 는 성공한다.
- ② 조각 쓰기 중 ENOSPC → 공통 검사.
- ③ 조각 읽기 중 EIO → 공통 검사.
- ④ 다단계 병합(조각 10, FAN_IN 4) **중간 병합 중** EIO → 공통 검사.
- ⑤ 중간 병합 중 Ctrl+C → 종료 코드 1, `Ctrl+C` 안내, 임시 폴더 잔존 없음.

**M. 메모리** (tracemalloc)
- 매칭 약 3,300건(1만 건 파일) vs 약 33,000건(10만 건 파일)에서 search 최대 메모리가 `big < 2 × small` 이고 `big < 3MB`.
- 매칭 10건 search 도 파일 크기에 따라 늘지 않는다.
- 대조군(구 방식: 매칭 전체 `sorted`)은 `big > 5 × small` 이다. 측정이 매칭 결과를 잡는다는 증거다.
- 출력 줄 수가 매칭 수와 같다.

**실행 방법**
- 6.2 코드 블록 내용을 스크래치패드에 파일로 저장한 뒤 `bash <파일>` 로 실행한다(macOS 기본 bash 3.2 에서 동작). 저장한 스크립트 파일은 실행 후 지운다.
- **백그라운드(`&`)로 실행하지 않는다.** B절과 4단계 회귀가 Ctrl+C 신호를 보낸다.
- `python` 이 없는 환경이라 첫머리에서 `python → python3` 링크를 만들어 PATH 앞에 둔다.
- 모든 임시 파일은 `W="$(mktemp -d)"` 아래에 만들고 `trap` 으로 지운다.
- **`TMPDIR` 를 `$W/systmp` 로 바꿔 export 한다.** 그래서 회귀를 포함한 모든 search 의 "시스템 임시 폴더"가 이곳이 되고, 마지막에 잔존 여부를 한 번에 확인할 수 있다.

**성공 기준**: `FAIL` 로 시작하는 줄이 하나도 없어야 한다. `ORDER_OK`, `CLEANUP_OK`, `TEMP_ERROR_OK`, `SEARCH_MEMORY_OK`, 그리고 마지막 줄 `STEP5_ALL_OK` 가 나와야 한다. 예상 실행 시간은 2~3분이다(4단계 회귀 약 50초 + 10만 건 메모리 측정 + 12만 건 시험 3회).

**메모리 기준값 처리 규칙 (총괄 결정 5)**
- M절의 기준값(`2배`, `3MB`)과 3단계 M 치환의 `2배` 는 실측이 아닌 추정치다. 근거는 다음과 같다.
  - 3단계 실측에서 매칭 1건이 약 0.7KB 였다. 그래서 조각 1,000건은 약 0.7MB, 기본 메모리 약 0.18MB 를 더하면 약 1MB 다.
  - 병합 단계는 조각당 버퍼 8KB 와 디코딩 버퍼를 합쳐 약 30KB 다. 이번 시험은 조각 34개이므로 약 1MB 다.
- **에이전트 2·3 은 M절 측정값 6줄(그리고 3단계 회귀의 측정값)을 그대로 보고한다.**
- 기준과 맞지 않으면 **코드를 기준에 맞추려고 고치지 않는다**(버퍼 크기·조각 크기·FAN_IN 조정, 측정 회피 등 금지). 실패한 기준, 실측값, 추정 원인을 총괄에게 보고한다. 기준을 바꿀지는 총괄이 정한다.

### 6.2 검증 스크립트

```bash
# 5단계 검증 스크립트. 실행: bash <이 파일>   (백그라운드 & 로 실행하지 말 것)
cd "/Users/khm04/codessey/pocket money" || exit 1
export PYTHONDONTWRITEBYTECODE=1
W="$(mktemp -d)"; export W                      # 이 스크립트의 임시 파일은 전부 여기 아래
cleanup() { chmod -R u+rwx "$W" 2>/dev/null; rm -rf "$W"; }
trap cleanup EXIT
mkdir "$W/bin" && ln -s "$(command -v python3)" "$W/bin/python" || exit 1   # python 이 없어서 python3 로 연결
export PATH="$W/bin:$PATH"
python --version || exit 1
mkdir "$W/systmp" && export TMPDIR="$W/systmp" || exit 1   # 이 스크립트(회귀 포함)의 "시스템 임시 폴더"
FAIL=0
fail() { echo "FAIL $*"; FAIL=1; }

# ======================= S. 정적 검사 =======================
# S0 변경 금지 파일
shasum -a 256 -c - >/dev/null <<'SUMS' || fail "S0 변경 금지 파일이 바뀜 (models/__main__/__init__)"
08b6a94954a6ca8d6619a69a026ac2fd2d028844e17a8c55cb8d6f02faca513f  budget_app/models.py
6958ee4078ab3cdd31564e022cd9fccc673a5f2f8509c241b4771646a4e72753  budget_app/__main__.py
0cb00a1323d1945aa0e71486ffebaf612fde2efe434f13182806c00515b3605c  budget_app/__init__.py
SUMS
grep -qF '경로(--data-dir, --from, --out)가 올바른지, 해당 파일·폴더에 읽기/쓰기 권한이 있는지 확인하세요' budget_app/decorators.py || fail "S0 decorators.py 의 OSError 힌트가 4단계와 다름 (decorators.py 변경 금지)"
if grep -nE "TMPDIR|tempfile|임시" budget_app/decorators.py; then fail "S0 임시 파일 오류 변환은 storage.py 에서 한다 (decorators.py 변경 금지)"; fi
# S1 파일 존재
for f in __init__ __main__ models storage services decorators cli; do [ -f "budget_app/$f.py" ] || fail "S1 budget_app/$f.py 없음"; done
# S2 3.10 문법
python3 - budget_app/*.py <<'PY' || fail "S2 3.10 문법"
import ast, sys
for f in sys.argv[1:]:
    ast.parse(open(f, encoding="utf-8").read(), feature_version=(3, 10))
PY
# S3 3.11+ 전용 API
if grep -nE "fromisoformat|typing\.Self|from typing import .*Self|datetime\.UTC|except\*|ExceptionGroup|tomllib|suggest_on_error|color=" budget_app/*.py; then fail "S3 3.11+ API"; fi
# S4 계층 규칙 + 표준 라이브러리만
python3 - <<'PY' || fail "S4 계층 규칙 / 표준 라이브러리만"
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
            top = mod.split(".")[0]
            if top == "budget_app":
                if (mod.split(".")[1] if "." in mod else "?") not in ok: bad.append((m, mod))
            elif top not in sys.stdlib_module_names:
                bad.append((m, "표준 라이브러리 아님: " + mod))
print(bad) if bad else None
sys.exit(1 if bad else 0)
PY
# S5 타입 힌트
python3 - budget_app/*.py <<'PY' || fail "S5 타입 힌트"
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
# S6 services/cli: 외부 정렬 + 다단계 병합 구조
python3 - <<'PY' || fail "S6 search 외부 정렬 구조 (services.py / cli.py)"
import ast, sys
def callname(c):
    f = c.func
    return f.id if isinstance(f, ast.Name) else f.attr if isinstance(f, ast.Attribute) else None
def calls(fn, name): return any(isinstance(n, ast.Call) and callname(n) == name for n in ast.walk(fn))
def is_gen(fn): return any(isinstance(n, (ast.Yield, ast.YieldFrom)) for n in ast.walk(fn))
def kwargs(c): return {k.arg: k.value for k in c.keywords}
def is_name(x, name): return isinstance(x, ast.Name) and x.id == name
def is_true(x): return isinstance(x, ast.Constant) and x.value is True
def inside(node, fn): return fn is not None and any(n is node for n in ast.walk(fn))
sv = ast.parse(open("budget_app/services.py", encoding="utf-8").read())
cl = ast.parse(open("budget_app/cli.py", encoding="utf-8").read())
fs = {n.name: n for n in ast.walk(sv) if isinstance(n, ast.FunctionDef)}
fc = {n.name: n for n in ast.walk(cl) if isinstance(n, ast.FunctionDef)}
bad = []
def const(name):
    c = [n for n in sv.body if isinstance(n, ast.AnnAssign) and is_name(n.target, name)]
    return c[0].value.value if len(c) == 1 and isinstance(c[0].value, ast.Constant) else None
if const("SEARCH_CHUNK_SIZE") != 1000:
    bad.append("SEARCH_CHUNK_SIZE: int = 1000 이 모듈 최상위에 없음")
fan = const("SEARCH_MERGE_FAN_IN")
if not (isinstance(fan, int) and 2 <= fan <= 128):
    bad.append(f"SEARCH_MERGE_FAN_IN: int 상수(2~128)가 모듈 최상위에 없음: {fan!r}")
sorts = [n for n in ast.walk(sv) if isinstance(n, ast.Call) and callname(n) == "sorted"]
sc = fs.get("_sort_chunk")
if len(sorts) != 1 or not inside(sorts[0], sc):
    bad.append(f"sorted 는 _sort_chunk 안에서 정확히 1회여야 함 (services 전체 {len(sorts)}회)")
else:
    s, kw = sorts[0], kwargs(sorts[0])
    if not (s.args and isinstance(s.args[0], ast.Name) and s.args[0].id in [a.arg for a in sc.args.args]):
        bad.append("_sort_chunk 의 sorted 첫 인자가 매개변수(조각 리스트)가 아님")
    if not (is_name(kw.get("key"), "_recency_key") and is_true(kw.get("reverse"))):
        bad.append("_sort_chunk 의 sorted 가 key=_recency_key, reverse=True 가 아님")
merges = [n for n in ast.walk(sv) if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
          and n.func.attr == "merge" and is_name(n.func.value, "heapq")]
if len(merges) != 1 or not inside(merges[0], fs.get("_merge_runs")):
    bad.append(f"heapq.merge 는 _merge_runs 안에서 정확히 1회여야 함 (services 전체 {len(merges)}회)")
elif not (is_name(kwargs(merges[0]).get("key"), "_recency_key") and is_true(kwargs(merges[0]).get("reverse"))):
    bad.append("heapq.merge 가 key=_recency_key, reverse=True 가 아님")
md = fs.get("_merge_down")
if md is None:
    bad.append("_merge_down 없음")
else:
    if not any(isinstance(n, ast.While) and any(is_name(x, "SEARCH_MERGE_FAN_IN") for x in ast.walk(n.test)) for n in ast.walk(md)):
        bad.append("_merge_down 에 SEARCH_MERGE_FAN_IN 을 조건으로 하는 while 반복이 없음")
    for name in ("_merge_runs", "write_run", "remove_run"):
        if not calls(md, name): bad.append(f"_merge_down 에서 {name} 호출 없음")
STREAMS = {"iter_transactions", "_iter_matches", "_iter_recent_matches", "search_transactions"}
for tree, mod in ((sv, "services"), (cl, "cli")):
    for n in ast.walk(tree):
        if isinstance(n, ast.Call):
            name = callname(n)
            inner = callname(n.args[0]) if n.args and isinstance(n.args[0], ast.Call) else None
            if name == "sort": bad.append(f"{mod} {n.lineno}행: .sort() 사용")
            if name in ("list", "tuple", "set", "sorted", "len") and inner in STREAMS:
                bad.append(f"{mod} {n.lineno}행: {name}({inner}()) 로 결과를 모음")
            if mod == "cli" and name in ("sorted", "nlargest", "nsmallest"): bad.append(f"cli {n.lineno}행: {name}")
        if isinstance(n, (ast.ListComp, ast.SetComp, ast.DictComp)):
            for g in n.generators:
                if isinstance(g.iter, ast.Call) and callname(g.iter) in STREAMS:
                    bad.append(f"{mod} {n.lineno}행: 컴프리헨션으로 {callname(g.iter)} 결과를 모음")
rm = fs.get("_iter_recent_matches")
if rm is None or not is_gen(rm):
    bad.append("_iter_recent_matches 제너레이터가 없음")
else:
    if not any(isinstance(n, ast.For) and isinstance(n.iter, ast.Call) and callname(n.iter) == "_iter_matches" for n in ast.walk(rm)):
        bad.append("_iter_recent_matches 가 _iter_matches() 를 for 로 한 건씩 받지 않음")
    for name in ("_sort_chunk", "SortRunStore", "write_run", "_merge_down", "_merge_runs"):
        if not calls(rm, name): bad.append(f"_iter_recent_matches 에서 {name} 호출 없음")
    if not any(is_name(n, "SEARCH_CHUNK_SIZE") for n in ast.walk(rm)):
        bad.append("_iter_recent_matches 가 SEARCH_CHUNK_SIZE 를 쓰지 않음")
    if not any(isinstance(n, ast.Try) and any(isinstance(x, ast.Call) and callname(x) == "close" for s in n.finalbody for x in ast.walk(s))
               for n in ast.walk(rm)):
        bad.append("_iter_recent_matches 의 finally 에서 close() 를 부르지 않음 (임시 파일 정리)")
st = fs.get("search_transactions")
if st is None or is_gen(st) or not calls(st, "_iter_recent_matches"):
    bad.append("search_transactions 는 검증을 먼저 끝내는 일반 함수(yield 없음)로 _iter_recent_matches(...) 를 돌려줘야 함")
if "_iter_matches" not in fs or not is_gen(fs["_iter_matches"]):
    bad.append("_iter_matches 제너레이터가 없음")
for n in ast.walk(sv):
    if isinstance(n, ast.Import) and any(a.name == "tempfile" for a in n.names) or isinstance(n, ast.ImportFrom) and n.module == "tempfile":
        bad.append("services.py 가 tempfile 을 import 함 (임시 파일 입출력은 storage.py)")
cs = fc.get("_cmd_search")
if cs is None or not calls(cs, "closing") or not calls(cs, "search_transactions") or not any(isinstance(n, ast.For) for n in ast.walk(cs)):
    bad.append("_cmd_search 가 closing(...) 으로 감싼 결과를 for 로 한 줄씩 출력하지 않음")
elif any(isinstance(n, ast.Call) and callname(n) in ("list", "tuple", "len", "sorted") for n in ast.walk(cs)):
    bad.append("_cmd_search 가 결과를 모음 (list/tuple/len/sorted)")
print(*bad, sep="\n") if bad else None
sys.exit(1 if bad else 0)
PY
# S7 storage: 임시 조각 파일 저장소
python3 - <<'PY' || fail "S7 임시 조각 파일 저장소 (storage.py)"
import ast, sys
def callname(c):
    f = c.func
    return f.id if isinstance(f, ast.Name) else f.attr if isinstance(f, ast.Attribute) else None
def kwargs(c): return {k.arg: k.value for k in c.keywords}
st = ast.parse(open("budget_app/storage.py", encoding="utf-8").read())
bad = []
cls = [n for n in st.body if isinstance(n, ast.ClassDef) and n.name == "SortRunStore"]
meth = {m.name: m for m in cls[0].body if isinstance(m, ast.FunctionDef)} if cls else {}
for name in ("__init__", "write_run", "read_run", "remove_run", "close"):
    if name not in meth: bad.append(f"SortRunStore.{name} 없음")
if "write_run" in meth and not (isinstance(meth["write_run"].returns, ast.Name) and meth["write_run"].returns.id == "Path"):
    bad.append("SortRunStore.write_run 이 -> Path 를 돌려주지 않음")
tds = [n for n in ast.walk(st) if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
       and n.func.attr == "TemporaryDirectory" and isinstance(n.func.value, ast.Name) and n.func.value.id == "tempfile"]
if len(tds) != 1 or "__init__" not in meth or not any(x is tds[0] for x in ast.walk(meth["__init__"])):
    bad.append("tempfile.TemporaryDirectory(...) 는 SortRunStore.__init__ 에서 1회만")
else:
    kw = kwargs(tds[0])
    if "dir" in kw: bad.append("TemporaryDirectory 에 dir= 를 주면 안 됨 (시스템 임시 폴더 사용)")
    if "prefix" not in kw: bad.append("TemporaryDirectory 에 prefix= 없음")
    if not (isinstance(kw.get("ignore_cleanup_errors"), ast.Constant) and kw["ignore_cleanup_errors"].value is True):
        bad.append("TemporaryDirectory 에 ignore_cleanup_errors=True 없음")
if any(isinstance(n, ast.ImportFrom) and n.module == "tempfile" for n in ast.walk(st)):
    bad.append("from tempfile import ... 금지 (tempfile.TemporaryDirectory 로 호출)")
ir = next((n for n in st.body if isinstance(n, ast.FunctionDef) and n.name == "_iter_run"), None)
if ir is None or not any(isinstance(n, (ast.Yield, ast.YieldFrom)) for n in ast.walk(ir)):
    bad.append("_iter_run 제너레이터 없음")
else:
    opens = [n for n in ast.walk(ir) if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == "open"]
    if len(opens) != 1 or not {"encoding", "buffering"} <= set(kwargs(opens[0])):
        bad.append("_iter_run 이 내장 open(..., encoding=, buffering=) 으로 열지 않음")
def converts(fn):
    has_except = any(isinstance(n, ast.ExceptHandler) and isinstance(n.type, ast.Name) and n.type.id == "OSError" for n in ast.walk(fn))
    return has_except and any(isinstance(n, ast.Call) and callname(n) == "_temp_file_error" for n in ast.walk(fn))
for name, fn in (("SortRunStore.__init__", meth.get("__init__")), ("SortRunStore.write_run", meth.get("write_run")),
                 ("SortRunStore.remove_run", meth.get("remove_run")), ("_iter_run", ir)):
    if fn is None or not converts(fn):
        bad.append(f"{name}: except OSError 에서 _temp_file_error(...) 로 바꾸지 않음")
if "close" in meth and not any(isinstance(n, ast.Call) and callname(n) == "cleanup" for n in ast.walk(meth["close"])):
    bad.append("SortRunStore.close 가 cleanup() 을 부르지 않음")
nrep = sum(1 for n in ast.walk(st) if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
           and n.func.attr == "replace" and isinstance(n.func.value, ast.Name) and n.func.value.id == "os")
nmk = sum(1 for n in ast.walk(st) if isinstance(n, ast.Call) and callname(n) == "mkstemp")
if (nrep, nmk) != (1, 1): bad.append(f"storage 의 os.replace {nrep}회, mkstemp {nmk}회 (4단계 그대로 각 1회)")
print(*bad, sep="\n") if bad else None
sys.exit(1 if bad else 0)
PY
# S8 입출력 위치, 전체 로드
if grep -nE "(^|[^A-Za-z0-9_.])(print|input)\(" budget_app/models.py budget_app/storage.py budget_app/services.py; then fail "S8 print/input 위치"; fi
if grep -nE "(^|[^A-Za-z0-9_.])open\(" budget_app/models.py budget_app/services.py budget_app/cli.py budget_app/decorators.py; then fail "S8 open( 은 storage.py 에서만"; fi
if grep -nE "\.read\(\)|readlines\(" budget_app/*.py; then fail "S8 전체 로드"; fi
# S9 README
grep -q "TMPDIR" README.md || fail "S9 README 에 search 임시 파일 설명이 없음"

# ======================= A. 순서 동일성 + CHUNK 경계 + 다단계 병합 (같은 프로세스) =======================
python - <<'PY' || FAIL=1
import builtins, contextlib, io, json, os, random, sys, tempfile
import budget_app.services as services
from budget_app.cli import main
base = os.path.join(os.environ["W"], "order"); os.makedirs(base)
SYS = tempfile.gettempdir()
ok = True
def need(cond, msg):
    global ok
    if not cond:
        print("FAIL", msg); ok = False
def run(argv):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        try:
            rc = main(argv)
        except BaseException as e:                  # main 밖으로 새면 실제 실행에서는 스택트레이스가 나온다
            rc = f"예외 누출 {type(e).__name__}: {e}"
    return rc, out.getvalue(), err.getvalue()
# 임시 폴더 감시: 만들어진 폴더와, 지우기 직전에 남아 있던 조각 파일 수를 기록한다
made = []
_TD = tempfile.TemporaryDirectory
class SpyTD(_TD):
    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        made.append([self.name, None])
    def cleanup(self):
        for m in made:
            if m[0] == self.name and m[1] is None:
                m[1] = len(os.listdir(self.name))
        super().cleanup()
tempfile.TemporaryDirectory = SpyTD
# 조각 크기 감시
sizes = []
_SC = services._sort_chunk
def spy_sort(chunk):
    sizes.append(len(chunk))
    return _SC(chunk)
services._sort_chunk = spy_sort
# 내장 open 감시: 시스템 임시 폴더 안 파일의 쓰기 횟수와 "동시에 열려 있던 최대 개수"
_open = builtins.open
live, stat = [], {"max_open": 0, "writes": 0}
def spy_open(file, *a, **k):
    f = _open(file, *a, **k)
    if isinstance(file, (str, os.PathLike)) and os.fspath(file).startswith(SYS + os.sep):
        mode = a[0] if a else k.get("mode", "r")
        if "w" in mode:
            stat["writes"] += 1
        live.append(f)
        live[:] = [x for x in live if not x.closed]
        stat["max_open"] = max(stat["max_open"], len(live))
    return f
builtins.open = spy_open
def want_sizes(n, size):
    if n <= size:
        return [n]
    full, rest = divmod(n, size)
    return [size] * full + ([rest] if rest else [])
def merge_plan(n_runs, fan):
    # 설계서 3.3 _merge_down 과 같은 규칙: (마지막 단계 조각 수, 중간 병합으로 새로 쓴 조각 수)
    merges = 0
    while n_runs > fan:
        groups = -(-n_runs // fan)
        merges += groups - (1 if n_runs % fan == 1 else 0)   # 1개짜리 묶음은 다시 쓰지 않음
        n_runs = groups
    return n_runs, merges
def fmt(r):
    return f'{r["id"]} | {r["date"]} | {r["type"]} | {r["category"]} | {r["amount"]} | {r["memo"]}'.rstrip()
def old_way(rows, pred):
    # 구 방식(3단계): 맞는 거래를 전부 모아 sorted 한 번. 최신순 = (날짜, id 숫자) 내림차순
    m = sorted((r for r in rows if pred(r)), key=lambda r: (r["date"], int(r["id"][3:])), reverse=True)
    return "".join(fmt(r) + "\n" for r in m), len(m)
def check(label, d, args, rows, pred):
    size, fan = services.SEARCH_CHUNK_SIZE, services.SEARCH_MERGE_FAN_IN
    made.clear(); sizes.clear(); live.clear(); stat["max_open"] = 0; stat["writes"] = 0
    before = sorted(os.listdir(d))
    want, n = old_way(rows, pred)
    rc, out, err = run(["search", *args, "--data-dir", d])
    tag = f"{label} [조각 {size}, FAN_IN {fan}]"
    need(rc == 0 and err == "", f"{tag}: rc={rc!r} err={err!r}")
    need(out == (want if n else "조건에 맞는 거래가 없습니다.\n"), f"{tag}: 출력이 구 방식(매칭 전체 sorted)과 다름")
    need(sizes == want_sizes(n, size), f"{tag}: 조각 크기 {sizes[:5]}... != {want_sizes(n, size)[:5]}...")
    if n > size:
        first = len(want_sizes(n, size))
        final, merges = merge_plan(first, fan)
        need(len(made) == 1, f"{tag}: 임시 폴더 {len(made)}개")
        need(stat["writes"] == first + merges, f"{tag}: 조각 파일 쓰기 {stat['writes']}회 != 1차 {first} + 중간 병합 {merges}")
        need(made[:1] and made[0][1] == final, f"{tag}: 정리 직전 남은 조각 {made[0][1] if made else None}개 != 마지막 단계 {final}개 (다 쓴 조각을 바로 지우지 않음)")
    else:
        need(made == [] and stat["writes"] == 0, f"{tag}: 매칭 {n}건(조각 크기 이하)인데 임시 파일을 만듦")
    need(stat["max_open"] <= fan + 1, f"{tag}: 동시에 열린 조각 파일 {stat['max_open']}개 > FAN_IN + 1")
    need(all(not os.path.exists(m[0]) for m in made), f"{tag}: 임시 폴더가 남음")
    need(all(os.path.dirname(m[0]) == SYS for m in made), f"{tag}: 임시 폴더가 시스템 임시 폴더 바로 아래가 아님 {made}")
    need(sorted(os.listdir(d)) == before, f"{tag}: data 폴더 파일 목록이 바뀜")
    return n
CHUNK0, FAN0 = services.SEARCH_CHUNK_SIZE, services.SEARCH_MERGE_FAN_IN
# 데이터 1: 6,000건, 날짜를 84개로 몰아 같은 날짜가 많음(id 비교가 자주 쓰임)
rng = random.Random(20241005)
N = 6000
pick = {k: set(rng.sample(range(1, N + 1), k)) for k in (999, 1000, 1001, 2500)}
d = os.path.join(base, "data")
run(["list", "--data-dir", d])
cats = ("food", "transport", "rent", "etc")
rows = []
with _open(os.path.join(d, "transactions.jsonl"), "w", encoding="utf-8") as f:
    for i in range(1, N + 1):
        r = {"id": f"TX-{i:06d}", "type": "income" if i % 4 == 0 else "expense",
             "date": f"2024-{rng.randint(1, 3):02d}-{rng.randint(1, 28):02d}", "amount": rng.randint(1, 99999),
             "category": cats[i % 4], "memo": rng.choice(["점심", "저녁 Pizza", "버스", "월세", ""]) + f" {i}",
             "tags": [f"c{k}" for k in (999, 1000, 1001, 2500) if i in pick[k]] + [f"t{i % 3}"]}
        rows.append(r)
        f.write(json.dumps(r, ensure_ascii=False) + "\n")
for k in (999, 1000, 1001, 2500):
    n = check(f"--tag c{k}", d, ["--tag", f"c{k}"], rows, lambda r, k=k: f"c{k}" in r["tags"])
    need(n == k, f"--tag c{k}: 매칭 {n}건 (데이터 생성 오류)")
check("--category food", d, ["--category", "food"], rows, lambda r: r["category"] == "food")
check("--type expense", d, ["--type", "expense"], rows, lambda r: r["type"] == "expense")
check("--from/--to", d, ["--from", "2024-02-01", "--to", "2024-02-28"], rows, lambda r: "2024-02-01" <= r["date"] <= "2024-02-28")
check("--q Pizza", d, ["--q", "Pizza"], rows, lambda r: "Pizza" in r["memo"])
check("조합", d, ["--type", "expense", "--from", "2024-01-10", "--q", "점심", "--tag", "t1"], rows,
      lambda r: r["type"] == "expense" and r["date"] >= "2024-01-10" and "점심" in r["memo"] and "t1" in r["tags"])
check("0건", d, ["--tag", "없는태그"], rows, lambda r: False)
# 다단계 병합 (실제 FAN_IN): 조각 10건 × 매칭 2500건 = 1차 조각 250개 > FAN_IN
services.SEARCH_CHUNK_SIZE = 10
need(len(want_sizes(2500, 10)) > services.SEARCH_MERGE_FAN_IN, "1차 조각 수가 FAN_IN 이하라 다단계 병합이 일어나지 않음")
check("다단계 --tag c2500", d, ["--tag", "c2500"], rows, lambda r: "c2500" in r["tags"])
check("다단계 --type expense", d, ["--type", "expense"], rows, lambda r: r["type"] == "expense")
services.SEARCH_CHUNK_SIZE = CHUNK0
# 데이터 2: 같은 키(날짜·id 가 같은 중복 줄)가 조각 경계·병합 묶음 경계를 넘어도 구 방식과 같은 순서인지
d2 = os.path.join(base, "dup")
run(["list", "--data-dir", d2])
rows2, prev = [], None
for i in range(1, 301):
    if i % 10 == 0:
        r = dict(prev, memo=f"같은 키 {i}")       # 바로 앞 줄과 날짜·id 가 같음
    else:
        r = {"id": f"TX-{i:06d}", "type": "expense", "date": f"2024-05-0{rng.randint(1, 5)}", "amount": i,
             "category": "food", "memo": f"m{i}", "tags": []}
    rows2.append(r); prev = r
with _open(os.path.join(d2, "transactions.jsonl"), "w", encoding="utf-8") as f:
    for r in rows2:
        f.write(json.dumps(r, ensure_ascii=False) + "\n")
for size, fan in ((4, FAN0), (7, FAN0), (10, FAN0), (1000, FAN0), (4, 3), (7, 2), (10, 4)):
    services.SEARCH_CHUNK_SIZE, services.SEARCH_MERGE_FAN_IN = size, fan
    check("중복 키", d2, ["--category", "food"], rows2, lambda r: True)
services.SEARCH_CHUNK_SIZE, services.SEARCH_MERGE_FAN_IN = CHUNK0, FAN0
builtins.open = _open
services._sort_chunk = _SC
tempfile.TemporaryDirectory = _TD
print("ORDER_OK" if ok else "ORDER_FAIL")
sys.exit(0 if ok else 1)
PY

# ======================= B. 임시 파일 정리·위치 (별도 프로세스) =======================
python - <<'PY' || FAIL=1
import glob, json, os, resource, signal, subprocess, sys, time
base = os.path.join(os.environ["W"], "clean"); os.makedirs(base)
ok = True
def need(cond, msg):
    global ok
    if not cond:
        print("FAIL", msg); ok = False
CMD = [sys.executable, "-m", "budget_app", "search", "--category", "food", "--data-dir"]
def prepare(name, n, bad_tail=False):
    d = os.path.join(base, name, "data")
    subprocess.run([sys.executable, "-m", "budget_app", "list", "--data-dir", d], capture_output=True, check=True)
    with open(os.path.join(d, "transactions.jsonl"), "w", encoding="utf-8") as f:
        for i in range(1, n + 1):
            f.write(json.dumps({"id": f"TX-{i:06d}", "type": "expense", "date": f"2024-{i % 12 + 1:02d}-{i % 28 + 1:02d}",
                                "amount": i % 997 + 1, "category": "food", "memo": f"메모 {i}", "tags": []},
                               ensure_ascii=False) + "\n")
        if bad_tail:
            f.write("not json\n")
    return d
def scratch(name):                                  # 실행마다 비어 있는 "시스템 임시 폴더"(TMPDIR)
    p = os.path.join(base, name, "tmp"); os.makedirs(p)
    return p
def search(d, tmp, **kw):
    return subprocess.run(CMD + [d], env={**os.environ, "TMPDIR": tmp}, capture_output=True, text=True, timeout=300, **kw)
# B1 정상 종료
d1 = prepare("normal", 2500); t1 = scratch("normal")
r = search(d1, t1); normal_out = r.stdout
need(r.returncode == 0 and r.stderr == "" and len(r.stdout.splitlines()) == 2500, f"정상: rc={r.returncode} err={r.stderr!r}")
need(os.listdir(t1) == [], f"정상 종료 뒤 TMPDIR 에 남음: {os.listdir(t1)}")
# B2 오류 종료 (조각 2개를 쓴 뒤 손상 줄 발견)
d2 = prepare("error", 2500, bad_tail=True); t2 = scratch("error")
r = search(d2, t2)
need(r.returncode == 1 and r.stdout == "" and "transactions.jsonl" in r.stderr and "Traceback" not in r.stderr,
     f"오류: rc={r.returncode} err={r.stderr!r}")
need(os.listdir(t2) == [], f"오류 종료 뒤 TMPDIR 에 남음: {os.listdir(t2)}")
# B3 data 폴더 읽기 전용
d3 = prepare("readonly", 2500); t3 = scratch("readonly")
files = sorted(os.listdir(d3))
for n in files:
    os.chmod(os.path.join(d3, n), 0o444)
os.chmod(d3, 0o555)
r = search(d3, t3)
os.chmod(d3, 0o755)
for n in files:
    os.chmod(os.path.join(d3, n), 0o644)
need(r.returncode == 0 and r.stdout == normal_out and r.stderr == "", f"읽기 전용 data 폴더: rc={r.returncode} err={r.stderr!r}")
need(sorted(os.listdir(d3)) == files and os.listdir(t3) == [], "읽기 전용 data 폴더: 파일이 생겼거나 TMPDIR 에 남음")
# B4/B5 Ctrl+C: 조각을 쓰는 중 / 출력하는 중 (12만 건 → 1차 조각 120개, 다단계 병합 포함)
d4 = prepare("big", 120_000)
def interrupt(tmp, wait_output):
    # 셸이 SIGINT 를 무시하도록 물려준 경우에도 KeyboardInterrupt 가 나도록 기본 동작으로 되돌린다
    p = subprocess.Popen(CMD + [d4], env={**os.environ, "TMPDIR": tmp}, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                         text=True, preexec_fn=lambda: signal.signal(signal.SIGINT, signal.SIG_DFL))
    t0 = time.time()
    while not glob.glob(os.path.join(tmp, "*", "*")):          # 조각 파일이 생길 때까지 기다림
        if p.poll() is not None or time.time() - t0 > 60:
            p.kill(); p.communicate()
            return None, "", "조각 파일이 생기기 전에 끝남", False
        time.sleep(0.005)
    line = p.stdout.readline() if wait_output else ""          # 출력이 시작될 때(마지막 병합 단계)까지 기다림
    had_runs = bool(glob.glob(os.path.join(tmp, "*", "*")))
    p.send_signal(signal.SIGINT)
    out, err = p.communicate(timeout=120)
    return p.returncode, line, err, had_runs
for label, wait_output, name in (("조각을 쓰는 중", False, "sig1"), ("출력하는 중", True, "sig2")):
    tmp = scratch(name)
    rc, line, err, had = interrupt(tmp, wait_output)
    need(rc == 1 and "Ctrl+C" in err and "Traceback" not in err, f"{label} Ctrl+C: rc={rc} err={err!r}")
    need(had, f"{label}: 중단 시점에 TMPDIR 에 조각 파일이 없음 (검사가 의미 없음)")
    if wait_output:
        need(line.startswith("TX-"), f"{label}: 첫 출력 줄 {line!r}")
    need(os.listdir(tmp) == [], f"{label} Ctrl+C 뒤 TMPDIR 에 남음: {os.listdir(tmp)}")
# B6 TMPDIR 가 쓰기 불가: 파이썬 tempfile 표준 동작으로 다음 후보(/tmp 등)를 써서 성공 (총괄 결정 2)
t6 = scratch("rotmp"); os.chmod(t6, 0o555)
r = search(d1, t6)
os.chmod(t6, 0o755)
need(r.returncode == 0 and r.stdout == normal_out and "Traceback" not in r.stderr, f"TMPDIR 쓰기 불가: rc={r.returncode} err={r.stderr!r}")
need(os.listdir(t6) == [], "쓰기 불가 TMPDIR 에 무언가 생김")
# B7 열린 파일 한도 100: 1차 조각 120개를 한꺼번에 열면 실패하지만, 다단계 병합이면 FAN_IN+1 개만 열어 성공
def low_fd_limit():
    soft, hard = resource.getrlimit(resource.RLIMIT_NOFILE)
    resource.setrlimit(resource.RLIMIT_NOFILE, (min(100, hard), hard))
t7 = scratch("fdlimit")
r = search(d4, t7, preexec_fn=low_fd_limit)
need(r.returncode == 0 and r.stderr == "" and len(r.stdout.splitlines()) == 120_000,
     f"열린 파일 한도 100 에서 12만 건 search: rc={r.returncode} err={r.stderr[-300:]!r}")
need(os.listdir(t7) == [], f"열린 파일 한도 시험 뒤 TMPDIR 에 남음: {os.listdir(t7)}")
print("CLEANUP_OK" if ok else "CLEANUP_FAIL")
sys.exit(0 if ok else 1)
PY

# ======================= C. 임시 파일 실패 → [오류]/[힌트] (같은 프로세스에서 주입) =======================
python - <<'PY' || FAIL=1
import contextlib, errno, glob, io, json, os, sys, tempfile
import budget_app.models as models
import budget_app.services as services
from budget_app.cli import main
base = os.path.join(os.environ["W"], "temperr"); os.makedirs(base)
d = os.path.join(base, "data")
ok = True
def need(cond, msg):
    global ok
    if not cond:
        print("FAIL", msg); ok = False
def run(argv):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        try:
            rc = main(argv)
        except BaseException as e:                  # main 밖으로 새면 실제 실행에서는 스택트레이스가 나온다
            rc = f"예외 누출 {type(e).__name__}: {e}"
    return rc, out.getvalue(), err.getvalue()
SYS = tempfile.gettempdir()
def leftovers():
    return glob.glob(os.path.join(SYS, "budget_app_search_*"))
run(["list", "--data-dir", d])
N = 3500
with open(os.path.join(d, "transactions.jsonl"), "w", encoding="utf-8") as f:
    for i in range(1, N + 1):
        f.write(json.dumps({"id": f"TX-{i:06d}", "type": "expense", "date": f"2024-03-{i % 28 + 1:02d}", "amount": i,
                            "category": "food" if i <= 2500 else "rent", "memo": f"메모 {i}", "tags": []},
                           ensure_ascii=False) + "\n")
BIG = ["search", "--category", "food", "--data-dir", d]      # 매칭 2500건 → 임시 파일 필요
SMALL = ["search", "--category", "rent", "--data-dir", d]    # 매칭 1000건 → 메모리에서만
def temp_error(label, rc, out, err):
    need(rc == 1, f"{label}: 종료 코드 {rc!r}")
    need(out == "", f"{label}: stdout 이 비어 있지 않음 {out[:80]!r}")
    need(err.count("[오류]") == 1 and err.count("[힌트]") == 1, f"{label}: [오류]/[힌트] 개수 {err!r}")
    need("TMPDIR" in err and "디스크" in err, f"{label}: 힌트가 임시 폴더·디스크를 안내하지 않음 {err!r}")
    need("--data-dir" not in err, f"{label}: 힌트가 --data-dir 를 가리킴 {err!r}")
    need(leftovers() == [], f"{label}: 시스템 임시 폴더에 남음 {leftovers()}")
FJ = models.Transaction.__dict__["from_json_line"]
def fail_reading_after(k, exc):
    # 거래 파일 N줄을 다 읽은 뒤, 조각 파일에서 k 번째 줄을 읽을 때 exc 를 낸다
    n = [0]
    def boom(cls, line):
        n[0] += 1
        if n[0] == N + k:
            raise exc
        return FJ.__func__(cls, line)
    models.Transaction.from_json_line = classmethod(boom)
    return n
# C1 파이썬이 고른 시스템 임시 폴더가 쓰기 불가
ro = os.path.join(base, "ro_tmp"); os.makedirs(ro); os.chmod(ro, 0o555)
tempfile.tempdir = ro
rc, out, err = run(BIG)
temp_error("임시 폴더 쓰기 불가", rc, out, err)
rc, out, err = run(SMALL)
need(rc == 0 and err == "" and len(out.splitlines()) == 1000, f"임시 폴더 쓰기 불가 + 매칭 1000건은 성공해야 함: rc={rc!r} {err!r}")
tempfile.tempdir = None
os.chmod(ro, 0o755)
need(os.listdir(ro) == [], "쓰기 불가 폴더에 무언가 생김")
# C2 조각 파일 쓰기 중 디스크 부족
TJ = models.Transaction.__dict__["to_json_line"]
def no_space(self):
    raise OSError(errno.ENOSPC, os.strerror(errno.ENOSPC))
models.Transaction.to_json_line = no_space
rc, out, err = run(BIG)
models.Transaction.to_json_line = TJ
temp_error("조각 쓰기 실패(디스크 부족)", rc, out, err)
# C3 조각 파일 읽기 실패 (마지막 병합 시작 = 조각의 첫 줄)
n = fail_reading_after(1, OSError(errno.EIO, os.strerror(errno.EIO)))
rc, out, err = run(BIG)
models.Transaction.from_json_line = FJ
need(n[0] >= N + 1, "조각 파일 읽기 단계까지 가지 못함 (주입이 의미 없음)")
temp_error("조각 읽기 실패", rc, out, err)
# C4/C5 다단계 병합(조각 10건 → 1차 250개, FAN_IN 4)의 중간 병합 도중 읽기 실패 / Ctrl+C
CHUNK0, FAN0 = services.SEARCH_CHUNK_SIZE, services.SEARCH_MERGE_FAN_IN
services.SEARCH_CHUNK_SIZE, services.SEARCH_MERGE_FAN_IN = 10, 4
n = fail_reading_after(30, OSError(errno.EIO, os.strerror(errno.EIO)))   # 첫 묶음(조각 4개 = 40줄)을 합치는 중
rc, out, err = run(BIG)
models.Transaction.from_json_line = FJ
need(n[0] >= N + 30, "중간 병합 단계까지 가지 못함 (주입이 의미 없음)")
temp_error("중간 병합 중 읽기 실패", rc, out, err)
n = fail_reading_after(30, KeyboardInterrupt())
rc, out, err = run(BIG)
models.Transaction.from_json_line = FJ
need(rc == 1 and out == "" and "Ctrl+C" in err and leftovers() == [], f"중간 병합 중 Ctrl+C: rc={rc!r} {err!r} 남음={leftovers()}")
services.SEARCH_CHUNK_SIZE, services.SEARCH_MERGE_FAN_IN = CHUNK0, FAN0
# C6 원래대로 되돌린 뒤 정상
rc, out, err = run(BIG)
need(rc == 0 and err == "" and len(out.splitlines()) == 2500 and leftovers() == [], f"복구 후 search: rc={rc!r} {err!r}")
print("TEMP_ERROR_OK" if ok else "TEMP_ERROR_FAIL")
sys.exit(0 if ok else 1)
PY

# ======================= M. 메모리 (매칭 약 3,300건 vs 약 33,000건) =======================
# 같은 프로세스에서 cli.main 을 tracemalloc 으로 감싸 최대 메모리를 잰다. 첫 호출의 1회성 할당은 워밍업으로 뺀다.
# 기준을 넘으면 코드를 기준에 맞추지 말고 측정값과 함께 총괄에게 보고한다 (설계서 6.1).
python - <<'PY' || FAIL=1
import contextlib, io, json, os, sys, tracemalloc
from budget_app.cli import main
from budget_app.storage import TransactionRepository
M = os.path.join(os.environ["W"], "mem5"); os.makedirs(M)
ok = True
def need(cond, msg):
    global ok
    if not cond:
        print("FAIL", msg); ok = False
class LineCounter(io.TextIOBase):
    # 출력을 메모리에 모으지 않고 줄 수만 센다 (StringIO 로 받으면 출력 자체가 측정에 잡힌다)
    def __init__(self):
        super().__init__()
        self.n = 0
    def write(self, s):
        self.n += s.count("\n")
        return len(s)
def gen(d, n):
    os.makedirs(d)
    cats = ("food", "transport", "etc")
    food = 0
    with open(os.path.join(d, "transactions.jsonl"), "w", encoding="utf-8") as f:
        for i in range(1, n + 1):
            needle = i % (n // 10) == 0        # rent 는 파일 크기와 관계없이 정확히 10건
            cat = "rent" if needle else cats[i % 3]
            food += cat == "food"
            f.write(json.dumps({"id": f"TX-{i:06d}", "type": "income" if i % 4 == 0 else "expense",
                                "date": f"2024-{i % 12 + 1:02d}-{i % 28 + 1:02d}", "amount": i % 997 + 1,
                                "category": cat, "memo": f"메모 {i}", "tags": [f"t{i % 50}"]}, ensure_ascii=False) + "\n")
    return food
def peak(argv):
    out = LineCounter()
    with contextlib.redirect_stdout(out):
        tracemalloc.start()
        rc = main(argv)
        p = tracemalloc.get_traced_memory()[1]
        tracemalloc.stop()
    need(rc == 0, f"{argv} 종료 코드 {rc}")
    return p, out.n
def control(d):
    # 대조군 = 구 방식: 맞는 거래를 전부 모아 sorted (매칭 수에 비례해 늘어야 정상)
    repo = TransactionRepository(d)
    tracemalloc.start()
    res = sorted((t for t in repo.iter_transactions() if t.category == "food"), key=lambda t: (t.date, int(t.id[3:])), reverse=True)
    p = tracemalloc.get_traced_memory()[1]
    tracemalloc.stop()
    del res
    return p
small, big = os.path.join(M, "small"), os.path.join(M, "big")
nfood = {"small": gen(small, 10_000), "big": gen(big, 100_000)}
cmds = {"searchN": ["search", "--category", "food"], "search10": ["search", "--category", "rent"]}
for a in cmds.values():
    peak(a + ["--data-dir", small])                            # 워밍업
r, lines = {}, {}
for k, a in cmds.items():
    for s, d in (("small", small), ("big", big)):
        r[k, s], lines[k, s] = peak(a + ["--data-dir", d])
r["control", "small"], r["control", "big"] = control(small), control(big)
for k, v in r.items():
    print(f"  {k[0]:9s} {k[1]:5s} peak={v:,} bytes")
for s in ("small", "big"):
    need(lines["searchN", s] == nfood[s], f"searchN {s}: 출력 {lines['searchN', s]}줄 != 매칭 {nfood[s]}건")
    need(lines["search10", s] == 10, f"search10 {s}: 출력 {lines['search10', s]}줄")
need(r["searchN", "big"] < 2 * r["searchN", "small"] and r["searchN", "big"] < 3_000_000,
     "매칭 약 3,300건→33,000건에서 search 최대 메모리가 매칭 수에 비례해 늘어남 (외부 정렬이 아님) — 측정값과 함께 총괄에게 보고")
need(r["search10", "big"] < 2 * r["search10", "small"] and r["search10", "big"] < 2_000_000,
     "매칭 10건 search 의 최대 메모리가 파일 크기에 따라 늘어남 (전체 로드 의심) — 측정값과 함께 총괄에게 보고")
need(r["control", "big"] > 5 * r["control", "small"], "대조군(구 방식)의 메모리가 늘지 않음: 측정 방법 확인 필요")
print("SEARCH_MEMORY_OK" if ok else "SEARCH_MEMORY_FAIL")
sys.exit(0 if ok else 1)
PY

# ======================= R. 1~4단계 회귀 (4단계 스크립트 → 3단계 → 1·2단계) =======================
# 4단계 설계서 6.2 스크립트를 꺼내 ① 임시 폴더를 $W 아래로 바꾸고 ② 4단계 R 절이 3단계 스크립트를 고칠 때
# 5단계에서 바뀐 기대값 3개(3단계 S8 의 sorted 규칙 2줄, 3단계 M 의 search 메모리 기대)도 함께 고치도록 끼워 넣는다.
python3 - <<'PY' || FAIL=1
import os
W = os.environ["W"]
FENCE = "`" * 3                                  # 설계서 코드 블록이 끊기지 않도록 백틱 3개를 직접 쓰지 않는다
sec = open("docs/plans/step4-import-export-readme.md", encoding="utf-8").read().split("### 6.2", 1)[1]
s4 = sec.split(FENCE + "bash\n", 1)[1].split(FENCE, 1)[0]
old_w = 'W="$(mktemp -d)"; export W'
assert s4.count(old_w) == 2 and s4.index(old_w) < s4.index("# ======================= S. 정적 검사"), "4단계 스크립트의 W 줄을 찾지 못함"
s4 = s4.replace(old_w, 'W="$(mktemp -d "$W/s4.XXXXXX")"; export W', 1)   # 첫 줄만 (R 절 안의 같은 문자열은 그대로)
REPS3 = [
    ('if sorted_args != ["_iter_matches"]: bad.append(f"sorted 는 _iter_matches 결과에만 1회 허용: {sorted_args}")',
     'if sorted_args != [None]: bad.append(f"5단계: sorted 는 _sort_chunk 의 조각 정렬 1회만 허용: {sorted_args}")'),
    ('if "search_transactions" not in funcs or not calls(funcs["search_transactions"], "sorted"): bad.append("search_transactions 에 sorted 없음")',
     'if "_sort_chunk" not in funcs or not calls(funcs["_sort_chunk"], "sorted"): bad.append("5단계: _sort_chunk 에 sorted 없음")'),
    ('need(r["searchN", "big"] > 5 * r["searchN", "small"],\n     "매칭 수가 10배일 때 search 메모리가 늘지 않음 (측정이 매칭 결과를 잡지 못함)")',
     'need(r["searchN", "big"] < 2 * r["searchN", "small"],\n     "5단계: 매칭 수가 10배일 때 search 메모리가 비례해 늘어남 (외부 정렬이 아님)")'),
]
ANCHOR = 'lines = s3.split("\\n")'
assert s4.count(ANCHOR) == 1, "4단계 스크립트의 R 절을 찾지 못함"
inject = ("STEP5_REPS = " + repr(REPS3) + "\n"
          "for old, new in STEP5_REPS:\n"
          "    assert s3.count(old) == 1, '5단계 치환 대상을 3단계 스크립트에서 찾지 못함: ' + old\n"
          "    s3 = s3.replace(old, new)\n")
s4 = s4.replace(ANCHOR, inject + ANCHOR)
open(os.path.join(W, "step4.sh"), "w", encoding="utf-8").write(s4)
PY
bash "$W/step4.sh" >"$W/r4" 2>&1
if grep -qx "STEP4_ALL_OK" "$W/r4" && ! grep -q "^FAIL" "$W/r4"; then :; else echo "FAIL 1~4단계 회귀"; cat "$W/r4"; FAIL=1; fi
grep -E "^  (summary|search10|searchN) " "$W/r4"     # 3단계 회귀의 메모리 측정값도 보고용으로 출력

# ======================= 마무리 =======================
left="$(find "$W/systmp" -maxdepth 1 -name 'budget_app_search_*' 2>/dev/null)"
[ -z "$left" ] || fail "시스템 임시 폴더에 search 임시 폴더가 남음: $left"
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
[ "$FAIL" = 0 ] && echo "STEP5_ALL_OK"
```

**기대 출력**
- `FAIL` 로 시작하는 줄이 없어야 한다.
- `ORDER_OK`, `CLEANUP_OK`, `TEMP_ERROR_OK`, M절 측정값 6줄과 `SEARCH_MEMORY_OK`, 3단계 회귀의 측정값 6줄, 마지막 줄 `STEP5_ALL_OK` 가 나와야 한다.
- 스크립트가 끝나면 `$W` 는 지워져 있어야 한다(`trap`).
- 에이전트 3 은 측정값 12줄을 보고서에 그대로 옮긴다(6.1 "메모리 기준값 처리 규칙").

## 7. 총괄 결정 기록 (개정 1에서 모두 확정)

1. **한 번에 합치는 조각 수 제한**: 반영했다. `SEARCH_MERGE_FAN_IN = 64` 와 다단계 병합(이웃 조각을 순서대로 묶어 합치고, 합친 조각은 즉시 삭제)을 3.0·3.3 에 추가했다. 검증은 다음과 같다.
   - 6.2 A: 조각 크기·FAN_IN 을 작게 바꾸고 순서 동일성, 쓰기 횟수, 남은 조각 수, 동시에 열린 파일 ≤ FAN_IN+1 을 확인한다.
   - 6.2 B7: 열린 파일 한도 100 에서 12만 건이 성공하는지 확인한다.
   - 6.2 C4·C5: 중간 병합 중 실패와 Ctrl+C 를 주입한다.
2. **TMPDIR 를 쓸 수 없을 때**: 파이썬 `tempfile` 의 표준 폴백(`/tmp` 등)을 허용한다. 오류 경로는 같은 프로세스 안에서 `tempfile.tempdir` 를 바꾸고 ENOSPC·EIO 를 주입해 검사한다(6.2 B6, C).
3. **병합 도중 읽기 오류**: 이미 출력한 줄이 남은 채 `[오류]` 로 끝나는 것을 허용한다(5장).
4. **Ctrl+C 힌트 문구**: 그대로 둔다(decorators.py 변경 금지 유지).
5. **메모리 기준값**: 에이전트 2·3 이 실측값을 보고한다. 기준과 맞지 않으면 코드를 기준에 맞추지 않고 총괄에게 보고한다(6.1 "메모리 기준값 처리 규칙").

## 부록: 검증 스크립트 알려진 문제 (총괄 기록)

- 6.2 R 절의 `grep -E "^  (summary|search10|searchN) " "$W/r4"` 는 아무것도 출력하지 않는다. 4단계 스크립트가 3단계 출력을 자기 안쪽 `$W/r3` 에만 쓰고 실패할 때만 보여 주기 때문이다. 통과/실패 판정에는 영향이 없다.
- 3단계 회귀 메모리 실측값(에이전트 2 진단 실행): summary 242,868 / 247,487 B, search10 253,133 / 254,268 B, searchN 946,888 / 997,692 B (small / big). 모두 기준 충족.
