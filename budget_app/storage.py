"""[저장소] JSONL·CSV 파일 읽기/쓰기, 제너레이터 읽기, 원자적 교체."""

import csv
import json
import os
import tempfile
from collections.abc import Callable, Iterable, Iterator
from pathlib import Path
from typing import Any, TextIO

from budget_app.models import (
    DEFAULT_CATEGORIES,
    BudgetAppError,
    Transaction,
    ValidationError,
    format_tx_id,
    tx_id_seq,
    validate_month,
)

DEFAULT_DATA_DIR: str = "data"
TRANSACTIONS_FILE = "transactions.jsonl"
CATEGORIES_FILE = "categories.jsonl"
BUDGETS_FILE = "budgets.jsonl"

CSV_COLUMNS: tuple[str, ...] = ("date", "type", "category", "amount", "memo", "tags")
CSV_REQUIRED_COLUMNS: tuple[str, ...] = ("date", "type", "category", "amount")
_CSV_HEADER_HINT: str = "첫 줄에 헤더 date,type,category,amount,memo,tags 를 넣으세요 (memo, tags 는 생략 가능)"


def _ensure_file(path: Path) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.touch(exist_ok=True)
    except OSError:
        raise BudgetAppError(
            cause=f"데이터 폴더를 준비할 수 없습니다: {path.parent}",
            hint="--data-dir 로 쓰기 가능한 폴더 경로를 지정하세요",
        ) from None


def _iter_lines(path: Path) -> Iterator[tuple[int, str]]:
    # 제너레이터: 파일 전체를 메모리에 올리지 않고, 호출하는 쪽이 요청할 때마다 한 줄씩 yield 한다.
    # 거래가 아무리 많아도 메모리에는 지금 처리 중인 한 줄만 있다.
    with open(path, encoding="utf-8") as f:
        for lineno, raw in enumerate(f, start=1):
            if not raw.strip():
                continue
            yield lineno, raw.rstrip("\n")


def _corrupt_line_error(path: Path, lineno: int, detail: str) -> BudgetAppError:
    return BudgetAppError(
        cause=f"{path} 파일 {lineno}번째 줄을 읽을 수 없습니다 ({detail})",
        hint="해당 줄을 올바른 JSON 형식으로 고치거나 삭제한 뒤 다시 실행하세요",
    )


def _parse_json_object(path: Path, lineno: int, line: str) -> dict[str, Any]:
    try:
        data = json.loads(line)
    except json.JSONDecodeError as e:
        raise _corrupt_line_error(path, lineno, f"JSON 형식이 아닙니다: {e.msg}") from None
    if not isinstance(data, dict):
        raise _corrupt_line_error(path, lineno, "JSON 객체가 아닙니다")
    return data


def _atomic_write(path: Path, write: Callable[[TextIO], int], newline: str | None = None) -> int:
    # 원자적 교체: 원본을 직접 고치다 중간에 멈추면 파일이 반쯤 깨진다.
    # 그래서 같은 폴더의 임시 파일에 새 내용을 끝까지 쓴 뒤, os.replace 로 한 번에 바꿔치기한다.
    # os.replace 는 같은 파일 시스템 안에서 "옛 파일 아니면 새 파일" 둘 중 하나만 보이게 보장한다.
    # (다른 폴더는 다른 디스크일 수 있어 원자성이 깨지므로 임시 파일은 반드시 같은 폴더에 만든다.)
    # JSONL 다시 쓰기와 CSV 내보내기가 이 함수 하나를 함께 쓰고, 무엇을 쓸지는 write 함수가 정한다.
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=path.name + ".", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline=newline) as f:
            count = write(f)
        # 파일을 다 쓰고 닫은 뒤에만 바꿔치기한다.
        os.replace(tmp, path)
    except BaseException:
        # 도중에 실패하면(Ctrl+C 포함) 임시 파일만 지우고 원본은 손대지 않은 채 예외를 다시 던진다.
        try:
            os.unlink(tmp)
        except FileNotFoundError:
            pass
        raise
    return count


def _atomic_rewrite(path: Path, lines: Iterable[str]) -> None:
    def _write(f: TextIO) -> int:
        n = 0
        for line in lines:
            f.write(line + "\n")
            n += 1
        return n

    _atomic_write(path, _write)


def _csv_header_index(path: Path, header: list[str]) -> dict[str, int]:
    """CSV 헤더를 검사하고 스키마 컬럼별 위치를 돌려준다. 스키마 밖 컬럼은 무시한다."""
    names = [h.strip() for h in header]
    if not any(names):
        raise BudgetAppError(cause=f"CSV 파일에 헤더가 없습니다: {path}", hint=_CSV_HEADER_HINT)
    duplicated = [c for c in CSV_COLUMNS if names.count(c) > 1]
    if duplicated:
        raise BudgetAppError(
            cause=f"CSV 헤더에 같은 컬럼이 여러 번 있습니다: {', '.join(duplicated)}",
            hint="컬럼 이름이 한 번씩만 나오도록 헤더를 고치세요",
        )
    missing = [c for c in CSV_REQUIRED_COLUMNS if c not in names]
    if missing:
        raise BudgetAppError(
            cause=f"CSV 헤더에 필수 컬럼이 없습니다: {', '.join(missing)}",
            hint=_CSV_HEADER_HINT,
        )
    return {c: names.index(c) for c in CSV_COLUMNS if c in names}


def iter_csv_records(path: str | os.PathLike[str]) -> Iterator[dict[str, str] | None]:
    """CSV 를 한 행씩 {컬럼: 원문 문자열} 로 넘긴다. 칸 수가 헤더와 다른 행은 None 으로 넘긴다."""
    # 제너레이터: CSV 가 수십만 행이어도 한 번에 읽지 않고, 호출하는 쪽이 요청할 때마다 한 행씩 yield 한다.
    # 그래서 메모리에는 지금 처리 중인 한 행만 있고, 파일 크기와 상관없이 메모리 사용량이 일정하다.
    p = Path(path)
    try:
        # utf-8-sig: 엑셀이 붙이는 BOM 이 있어도 없어도 읽는다. newline="" 은 csv 모듈이 요구하는 규칙이다.
        f = open(p, encoding="utf-8-sig", newline="")
    except FileNotFoundError:
        raise BudgetAppError(
            cause=f"가져올 CSV 파일이 없습니다: {p}",
            hint="--from 에 있는 CSV 파일 경로를 입력하세요",
        ) from None
    with f:
        reader = csv.reader(f)
        try:
            header = next(reader, [])
            index = _csv_header_index(p, header)
            width = len(header)
            for row in reader:
                if not row:
                    continue
                if len(row) != width:
                    yield None
                    continue
                yield {c: (row[index[c]] if c in index else "") for c in CSV_COLUMNS}
        except UnicodeDecodeError:
            raise BudgetAppError(
                cause=f"CSV 파일을 UTF-8 로 읽을 수 없습니다: {p}",
                hint="CSV 파일을 UTF-8 인코딩으로 저장한 뒤 다시 가져오세요",
            ) from None
        except csv.Error as e:
            raise BudgetAppError(
                cause=f"{p} 파일 {reader.line_num}번째 줄을 CSV 로 읽을 수 없습니다 ({e})",
                hint="해당 줄의 따옴표(\")와 쉼표를 확인하세요",
            ) from None


def check_csv_header(path: str | os.PathLike[str]) -> None:
    """파일 열기와 헤더 검사만 먼저 끝낸다. 파일 수준 오류는 임시 파일을 만들기 전에 여기서 난다."""
    for _ in iter_csv_records(path):
        break


def write_transactions_csv(path: str | os.PathLike[str], txs: Iterable[Transaction]) -> int:
    """거래를 CSV 로 저장하고 쓴 거래 수(헤더 제외)를 돌려준다. 이미 있는 경로는 덮어쓰지 않는다."""
    p = Path(path)
    if p.exists():
        raise BudgetAppError(
            cause=f"이미 있는 경로입니다: {p}",
            hint="덮어쓰지 않습니다. 다른 --out 경로를 지정하거나 기존 파일을 옮긴 뒤 다시 실행하세요",
        )
    if not p.parent.is_dir():
        raise BudgetAppError(
            cause=f"출력 폴더가 없습니다: {p.parent}",
            hint="이미 있는 폴더 안의 경로를 --out 에 지정하세요 (폴더는 자동으로 만들지 않습니다)",
        )

    def _write(f: TextIO) -> int:
        writer = csv.writer(f, lineterminator="\n")
        writer.writerow(CSV_COLUMNS)
        n = 0
        # txs 는 서비스의 제너레이터라 거래를 한 건 받을 때마다 바로 한 행을 쓴다(목록으로 모으지 않음).
        for tx in txs:
            writer.writerow([tx.date, tx.type, tx.category, str(tx.amount), tx.memo, ",".join(tx.tags)])
            n += 1
        return n

    # csv 모듈 규칙상 newline="" 으로 열어야 줄 끝이 lineterminator 그대로 저장된다.
    return _atomic_write(p, _write, newline="")


class TransactionRepository:
    """transactions.jsonl 을 다루는 저장소."""

    def __init__(self, data_dir: str | os.PathLike[str]) -> None:
        self.path = Path(data_dir) / TRANSACTIONS_FILE
        _ensure_file(self.path)
        self._last_seq: int | None = None

    def iter_transactions(self) -> Iterator[Transaction]:
        # 제너레이터: 거래를 한 건씩 만들어 넘겨주므로 list/search 가 전체를 불러오지 않고 스트리밍할 수 있다.
        for lineno, line in _iter_lines(self.path):
            yield self._parse_line(lineno, line)

    def issue_id(self) -> str:
        if self._last_seq is None:
            self._last_seq = max((tx_id_seq(tx.id) for tx in self.iter_transactions()), default=0)
        self._last_seq += 1
        return format_tx_id(self._last_seq)

    def append(self, tx: Transaction) -> None:
        with open(self.path, "a", encoding="utf-8") as f:
            f.write(tx.to_json_line() + "\n")

    def get(self, tx_id: str) -> Transaction | None:
        for tx in self.iter_transactions():
            if tx.id == tx_id:
                return tx
        return None

    def _parse_line(self, lineno: int, line: str) -> Transaction:
        try:
            return Transaction.from_json_line(line)
        except ValidationError as e:
            raise _corrupt_line_error(self.path, lineno, str(e)) from e

    def update(self, tx: Transaction) -> bool:
        if self.get(tx.id) is None:
            return False

        def _lines() -> Iterator[str]:
            for lineno, line in _iter_lines(self.path):
                if self._parse_line(lineno, line).id == tx.id:
                    yield tx.to_json_line()
                else:
                    yield line

        _atomic_rewrite(self.path, _lines())
        return True

    def delete(self, tx_id: str) -> bool:
        if self.get(tx_id) is None:
            return False

        def _lines() -> Iterator[str]:
            for lineno, line in _iter_lines(self.path):
                if self._parse_line(lineno, line).id != tx_id:
                    yield line

        _atomic_rewrite(self.path, _lines())
        return True

    def append_many(self, txs: Iterable[Transaction]) -> None:
        # import 는 파일 끝에 바로 덧붙이지 않고 "기존 줄 + 새 줄"을 임시 파일에 모두 쓴 뒤 한 번에 교체한다.
        # 덧붙이다 중간에 멈추면(Ctrl+C, CSV 중간 오류, 디스크 가득 참) 일부 행만 들어간 상태가 남지만,
        # 이렇게 하면 교체 전까지 원본을 건드리지 않으므로 "전부 반영" 아니면 "전혀 반영 안 됨" 둘 중 하나다.
        def _lines() -> Iterator[str]:
            for lineno, line in _iter_lines(self.path):
                self._parse_line(lineno, line)  # 손상된 줄이 있으면 여기서 멈춰 원본을 그대로 둔다.
                yield line
            for tx in txs:
                yield tx.to_json_line()

        _atomic_rewrite(self.path, _lines())

    def is_category_used(self, name: str) -> bool:
        for tx in self.iter_transactions():
            if tx.category == name:
                return True
        return False


class CategoryStore:
    """categories.jsonl 을 다루는 저장소. 줄 형식: {"name": "food"}"""

    def __init__(self, data_dir: str | os.PathLike[str]) -> None:
        self.path = Path(data_dir) / CATEGORIES_FILE
        _ensure_file(self.path)
        for _ in _iter_lines(self.path):
            break
        else:
            _atomic_rewrite(
                self.path,
                (json.dumps({"name": name}, ensure_ascii=False) for name in DEFAULT_CATEGORIES),
            )

    def _parse_name(self, lineno: int, line: str) -> str:
        data = _parse_json_object(self.path, lineno, line)
        name = data.get("name")
        if not isinstance(name, str) or not name:
            raise _corrupt_line_error(self.path, lineno, "name 이 비어 있지 않은 문자열이 아닙니다")
        return name

    def list_names(self) -> list[str]:
        return [self._parse_name(lineno, line) for lineno, line in _iter_lines(self.path)]

    def exists(self, name: str) -> bool:
        return name in self.list_names()

    def add(self, name: str) -> None:
        with open(self.path, "a", encoding="utf-8") as f:
            f.write(json.dumps({"name": name}, ensure_ascii=False) + "\n")

    def remove(self, name: str) -> bool:
        if not self.exists(name):
            return False

        def _lines() -> Iterator[str]:
            for lineno, line in _iter_lines(self.path):
                if self._parse_name(lineno, line) != name:
                    yield line

        _atomic_rewrite(self.path, _lines())
        return True


class BudgetStore:
    """budgets.jsonl 을 다루는 저장소. 줄 형식: {"month": "2024-05", "amount": 300000}"""

    def __init__(self, data_dir: str | os.PathLike[str]) -> None:
        self.path = Path(data_dir) / BUDGETS_FILE
        _ensure_file(self.path)

    def _parse_entry(self, lineno: int, line: str) -> tuple[str, int]:
        data = _parse_json_object(self.path, lineno, line)
        month = data.get("month")
        amount = data.get("amount")
        if not isinstance(month, str):
            raise _corrupt_line_error(self.path, lineno, "month 가 문자열이 아닙니다")
        try:
            valid_month = validate_month(month)
        except ValidationError:
            valid_month = None
        if valid_month != month:
            raise _corrupt_line_error(self.path, lineno, "month 가 YYYY-MM 형식이 아닙니다")
        if isinstance(amount, bool) or not isinstance(amount, int):
            raise _corrupt_line_error(self.path, lineno, "amount 가 정수가 아닙니다")
        if amount <= 0:
            raise _corrupt_line_error(self.path, lineno, "amount 가 0 이하입니다")
        return month, amount

    def get(self, month: str) -> int | None:
        for lineno, line in _iter_lines(self.path):
            entry_month, amount = self._parse_entry(lineno, line)
            if entry_month == month:
                return amount
        return None

    def set(self, month: str, amount: int) -> None:
        new_line = json.dumps({"month": month, "amount": amount}, ensure_ascii=False)

        def _lines() -> Iterator[str]:
            found = False
            for lineno, line in _iter_lines(self.path):
                entry_month, _ = self._parse_entry(lineno, line)
                if entry_month == month:
                    found = True
                    yield new_line
                else:
                    yield line
            if not found:
                yield new_line

        _atomic_rewrite(self.path, _lines())


# ---- search 외부 정렬용 임시 조각 파일 ----

_SORT_DIR_PREFIX: str = "budget_app_search_"
# 조각 파일이 동시에 여러 개(최대 64개) 열리므로 파일 하나당 읽기 버퍼를 작게 고정해 메모리를 예측할 수 있게 한다.
_RUN_READ_BUFFER: int = 8192
_TEMP_HINT: str = (
    "시스템 임시 폴더(환경 변수 TMPDIR 가 가리키는 폴더, 없으면 /tmp)에 쓰기 권한과 디스크 여유 공간이 있는지 확인하세요"
)


# OSError 를 그대로 올리면 공통 데코레이터가 data 폴더(--data-dir) 확인을 안내하게 된다.
# 이 오류는 임시 폴더·디스크 문제이므로 여기서 맞는 힌트로 바꾼다.
def _temp_file_error(e: OSError) -> BudgetAppError:
    detail = str(e) if e.filename is None else f"{e.filename} ({e.strerror})"
    return BudgetAppError(
        cause=f"검색 결과를 정렬할 임시 파일을 만들거나 읽을 수 없습니다: {detail}",
        hint=_TEMP_HINT,
    )


def _iter_run(path: Path) -> Iterator[Transaction]:
    # 제너레이터: 조각 파일 전체를 읽지 않고 한 줄씩 거래로 바꿔 넘긴다.
    # 끝까지 읽으면 with 가 끝나 파일이 바로 닫힌다.
    try:
        with open(path, encoding="utf-8", buffering=_RUN_READ_BUFFER) as f:
            for line in f:
                yield Transaction.from_json_line(line)
    except OSError as e:
        raise _temp_file_error(e) from None


class SortRunStore:
    """search 외부 정렬용 임시 조각 파일 저장소. 어느 조각을 언제 합칠지는 서비스가 정한다."""

    # 조각 파일을 data 폴더가 아니라 시스템 임시 폴더에 두는 이유:
    # 조각 파일은 저장 데이터가 아니라 검색 중에만 쓰는 작업 파일이고, data 폴더가 읽기 전용이어도 검색은 되어야 한다.
    # 원자적 교체용 임시 파일과 달리 같은 폴더에 둘 필요가 없다.
    # TemporaryDirectory 는 본인만 읽을 수 있는 폴더(권한 0700)를 만들어 메모 내용이 다른 사용자에게 보이지 않는다.

    def __init__(self) -> None:
        try:
            self._dir = tempfile.TemporaryDirectory(prefix=_SORT_DIR_PREFIX, ignore_cleanup_errors=True)
        except OSError as e:
            raise _temp_file_error(e) from None
        self._count = 0

    def write_run(self, txs: Iterable[Transaction]) -> Path:
        # txs 는 정렬된 조각 리스트일 수도, 중간 병합 결과(한 건씩 나오는 반복자)일 수도 있다.
        self._count += 1
        path = Path(self._dir.name) / f"run-{self._count:06d}.jsonl"
        try:
            with open(path, "w", encoding="utf-8") as f:
                for tx in txs:
                    f.write(tx.to_json_line() + "\n")
        except OSError as e:
            raise _temp_file_error(e) from None
        return path

    def read_run(self, path: Path) -> Iterator[Transaction]:
        return _iter_run(path)

    def remove_run(self, path: Path) -> None:
        try:
            path.unlink()
        except OSError as e:
            raise _temp_file_error(e) from None

    def close(self) -> None:
        # 임시 폴더와 남은 조각 파일을 모두 지운다. ignore_cleanup_errors=True 라 지우기 실패가 원래 오류를 가리지 않는다.
        self._dir.cleanup()
