"""[서비스] 거래·카테고리 업무 규칙. 입출력(print/input)은 하지 않는다."""

import dataclasses
import heapq
import os
import re
from collections.abc import Generator, Iterator
from pathlib import Path
from typing import Any

from budget_app.models import (
    BudgetAppError,
    Transaction,
    ValidationError,
    parse_amount,
    tx_id_seq,
    validate_date,
    validate_month,
    validate_type,
)
from budget_app.storage import (  # DEFAULT_DATA_DIR 는 CLI 가 쓰도록 재노출한다.
    DEFAULT_DATA_DIR,
    BudgetStore,
    CategoryStore,
    SortRunStore,
    TransactionRepository,
    check_csv_header,
    iter_csv_records,
    write_transactions_csv,
)

DEFAULT_LIST_LIMIT: int = 20
DEFAULT_SUMMARY_TOP: int = 3

# search 외부 정렬: 메모리에서 한 번에 정렬하는 최대 거래 수(조각 크기).
SEARCH_CHUNK_SIZE: int = 1000
# 왜 64인가: 동시에 여는 파일이 "64(읽기) + 1(쓰기) + 표준 입출력"이 되어 macOS 기본 한도 256 보다 충분히 작고,
# 메모리도 조각 64개분 버퍼로 묶인다.
SEARCH_MERGE_FAN_IN: int = 64

_POSITIVE_INT_RE = re.compile(r"[0-9]+")


def _parse_positive_option(value: str, option: str, example: str) -> int:
    """옵션 값을 1 이상의 정수로 바꿔 돌려준다."""
    text = value.strip()
    if _POSITIVE_INT_RE.fullmatch(text) and int(text) >= 1:
        return int(text)
    raise ValidationError(
        cause=f"{option} 값이 올바르지 않습니다: {value!r}",
        hint=f"{option} 에는 1 이상의 정수를 입력하세요 (예: {option} {example})",
    )


def parse_limit(value: str) -> int:
    """--limit 값을 1 이상의 정수로 바꿔 돌려준다."""
    return _parse_positive_option(value, "--limit", "20")


def parse_top(value: str) -> int:
    """--top 값을 1 이상의 정수로 바꿔 돌려준다."""
    return _parse_positive_option(value, "--top", "3")


def _required_text(value: str, option: str, hint: str) -> str:
    """앞뒤 공백을 제거한 값을 돌려준다. 비어 있으면 거부한다."""
    text = value.strip()
    if not text:
        raise ValidationError(cause=f"{option} 값이 비어 있습니다", hint=hint)
    return text


def parse_tags(value: str) -> list[str]:
    """쉼표로 구분한 태그 문자열을 목록으로 바꾼다. 빈 조각은 버린다."""
    return [t.strip() for t in value.split(",") if t.strip()]


def normalize_category_name(value: str) -> str:
    """카테고리 이름의 앞뒤 공백을 제거한다. 비어 있으면 거부한다."""
    name = value.strip()
    if not name:
        raise ValidationError(
            cause="카테고리 이름이 비어 있습니다",
            hint="한 글자 이상의 카테고리 이름을 입력하세요",
        )
    return name


def _recency_key(tx: Transaction) -> tuple[str, int]:
    # date 는 YYYY-MM-DD 라 문자열 비교가 곧 날짜 비교다.
    # id 는 숫자로 비교해야 TX-1000000 이 TX-999999 보다 최신이 된다.
    return (tx.date, tx_id_seq(tx.id))


def _sort_chunk(chunk: list[Transaction]) -> list[Transaction]:
    # 조각(최대 SEARCH_CHUNK_SIZE 건)만 메모리에서 최신순으로 정렬한다.
    return sorted(chunk, key=_recency_key, reverse=True)


# 조각 파일은 각각 이미 최신순이다. 그래서 각 조각의 "맨 앞 한 건"끼리만 비교해 가장 최신인 것을 내보내고,
# 그 조각에서 다음 한 건을 읽는다(여러 줄을 하나로 합쳐 세우는 원리). 메모리에는 조각마다 한 건만 있다.
# paths 의 순서가 곧 키가 같을 때의 우선순위다(heapq.merge 는 키가 같으면 앞쪽 입력을 먼저 내보낸다).
def _merge_runs(runs: SortRunStore, paths: list[Path]) -> Iterator[Transaction]:
    return heapq.merge(*(runs.read_run(p) for p in paths), key=_recency_key, reverse=True)


def _merge_down(runs: SortRunStore, paths: list[Path]) -> list[Path]:
    # 조각을 한꺼번에 합치려면 조각 파일을 모두 동시에 열어야 하는데, 운영체제는 한 프로그램이 동시에 여는
    # 파일 수를 제한한다(macOS 기본 256개). 그래서 64개씩 먼저 합쳐 조각 수를 줄이는 일을 반복한다.
    # 이웃한 조각을 순서대로 묶으므로 최신순과 같은 날짜·같은 id 의 순서도 그대로 유지된다.
    while len(paths) > SEARCH_MERGE_FAN_IN:
        merged: list[Path] = []
        for start in range(0, len(paths), SEARCH_MERGE_FAN_IN):
            group = paths[start:start + SEARCH_MERGE_FAN_IN]
            if len(group) == 1:
                merged.append(group[0])
                continue
            merged.append(runs.write_run(_merge_runs(runs, group)))
            # 합친 내용은 새 조각에 모두 들어갔으므로 원래 조각들은 바로 지워 디스크를 아낀다.
            for p in group:
                runs.remove_run(p)
        paths = merged
    return paths


def _top_key(item: tuple[str, int]) -> tuple[int, str]:
    # 금액은 음수로 바꿔 "작은 것 먼저" 규칙에서 큰 금액이 앞에 오게 하고, 동점이면 이름 오름차순.
    name, amount = item
    return (-amount, name)


def _usage_rate_text(expense: int, budget: int) -> str:
    """사용률(지출/예산×100)을 소수 첫째 자리까지 반올림한 문자열로 돌려준다."""
    # 사용률×10 을 정수로 구하고, 나누기 전에 예산의 절반을 더해 반올림한다.
    # 소수(float) 계산 오차를 피하려고 정수만 사용한다 (예: 6.25 → 6.3).
    tenths = (expense * 1000 + budget // 2) // budget
    return f"{tenths // 10}.{tenths % 10}"


@dataclasses.dataclass(frozen=True)
class SearchFilter:
    """search 조건 묶음. 검증을 마친 값만 담고, None 인 조건은 검사하지 않는다."""

    date_from: str | None = None
    date_to: str | None = None
    category: str | None = None
    tx_type: str | None = None
    q: str | None = None
    tag: str | None = None

    def matches(self, tx: Transaction) -> bool:
        # 주어진 조건을 모두 만족해야 한다(AND). YYYY-MM-DD 는 문자열 비교가 곧 날짜 비교다.
        if self.date_from is not None and tx.date < self.date_from:
            return False
        if self.date_to is not None and tx.date > self.date_to:
            return False
        if self.category is not None and tx.category != self.category:
            return False
        if self.tx_type is not None and tx.type != self.tx_type:
            return False
        if self.q is not None and self.q not in tx.memo:
            return False
        if self.tag is not None and self.tag not in tx.tags:
            return False
        return True


@dataclasses.dataclass(frozen=True)
class MonthlySummary:
    """summary 결과. 계산은 서비스가 하고, CLI 는 이 값을 글자로 바꾸기만 한다."""

    month: str
    top: int
    tx_count: int
    total_income: int
    total_expense: int
    balance: int
    budget: int | None
    usage_rate: str | None
    over_budget: bool
    top_expenses: list[tuple[str, int]]


# 행을 하나씩 처리하면서 개수를 올려야 하므로 frozen 이 아니다.
@dataclasses.dataclass
class ImportResult:
    """import 결과 개수."""

    imported: int = 0
    skipped: int = 0


def _import_fields(record: dict[str, str], categories: set[str]) -> dict[str, Any]:
    """CSV 한 행을 검증·정리해 Transaction 생성 인자(id 제외)로 바꾼다. 틀리면 ValidationError."""
    category = record["category"].strip()
    if category not in categories:
        raise ValidationError(
            cause=f"등록되지 않은 카테고리입니다: {category!r}",
            hint="category add 로 먼저 추가하세요",
        )
    return {
        "date": validate_date(record["date"]),
        "type": validate_type(record["type"]),
        "category": category,
        "amount": parse_amount(record["amount"]),
        "memo": record["memo"].strip(),
        "tags": parse_tags(record["tags"]),
    }


def _not_found(tx_id: str) -> BudgetAppError:
    return BudgetAppError(
        cause=f"없는 데이터입니다: id={tx_id.strip()}",
        hint="list 로 거래 id 를 확인한 뒤 다시 시도하세요",
    )


class LedgerService:
    """거래·카테고리·예산 저장소를 묶어 업무 규칙을 적용한다."""

    def __init__(self, data_dir: str | os.PathLike[str]) -> None:
        self.transactions = TransactionRepository(data_dir)
        self.categories = CategoryStore(data_dir)
        # budget set 과 summary 가 쓴다. 어떤 명령이든 저장 파일 3개가 자동 생성되도록 항상 만든다.
        self.budgets = BudgetStore(data_dir)

    def list_categories(self) -> list[str]:
        return self.categories.list_names()

    def validate_new_category(self, name: str) -> str:
        n = normalize_category_name(name)
        if self.categories.exists(n):
            raise ValidationError(
                cause=f"이미 있는 카테고리입니다: {n!r}",
                hint="category list 로 목록을 확인하고 다른 이름을 입력하세요",
            )
        return n

    def add_category(self, name: str) -> str:
        n = self.validate_new_category(name)
        self.categories.add(n)
        return n

    def validate_category(self, name: str) -> str:
        n = name.strip()
        names = self.categories.list_names()
        if n and n in names:
            return n
        raise ValidationError(
            cause=f"등록되지 않은 카테고리입니다: {n!r}",
            hint=f"등록된 카테고리: {', '.join(names)} (새 카테고리는 category add 로 먼저 추가하세요)",
        )

    def remove_category(self, name: str) -> str:
        n = normalize_category_name(name)
        if not self.categories.exists(n):
            raise BudgetAppError(
                cause=f"등록되지 않은 카테고리입니다: {n!r}",
                hint="category list 로 이름을 확인하세요 (대소문자 구분)",
            )
        if self.transactions.is_category_used(n):
            raise BudgetAppError(
                cause=f"사용 중인 카테고리는 삭제할 수 없습니다: {n!r}",
                hint="이 카테고리를 쓰는 거래를 update --category 로 바꾸거나 delete 로 삭제한 뒤 다시 시도하세요",
            )
        self.categories.remove(n)
        return n

    def add_transaction(
        self,
        date: str,
        type_: str,
        category: str,
        amount: int,
        memo: str,
        tags: list[str],
    ) -> Transaction:
        # 프롬프트에서 확인한 뒤 저장 직전까지 카테고리가 바뀌었을 수 있어 한 번 더 확인한다.
        cat = self.validate_category(category)
        tx = Transaction(
            id=self.transactions.issue_id(),
            type=type_,
            date=date,
            amount=amount,
            category=cat,
            memo=memo,
            tags=tags,
        )
        self.transactions.append(tx)
        return tx

    def recent_transactions(self, limit: int) -> list[Transaction]:
        # iter_transactions() 는 제너레이터라 거래를 한 건씩 넘겨준다.
        # heapq.nlargest 는 그중 가장 최신 limit 건만 힙에 유지하므로
        # 거래가 아무리 많아도 메모리에는 최대 limit 건만 남는다 (전체를 모아 정렬하지 않음).
        return heapq.nlargest(limit, self.transactions.iter_transactions(), key=_recency_key)

    def search_transactions(
        self,
        *,
        date_from: str | None,
        date_to: str | None,
        category: str | None,
        type_: str | None,
        q: str | None,
        tag: str | None,
    ) -> Generator[Transaction, None, None]:
        if all(v is None for v in (date_from, date_to, category, type_, q, tag)):
            raise ValidationError(
                cause="검색 조건이 없습니다",
                hint="--from, --to, --category, --type, --q, --tag 중 하나 이상을 지정하세요 (최근 거래는 list 로 확인하세요)",
            )
        flt = SearchFilter(
            date_from=None if date_from is None else validate_date(date_from),
            date_to=None if date_to is None else validate_date(date_to),
            category=None if category is None else self.validate_category(category),
            tx_type=None if type_ is None else validate_type(type_),
            q=None if q is None else _required_text(q, "--q", "메모에서 찾을 글자를 한 글자 이상 입력하세요 (예: --q 점심)"),
            tag=None if tag is None else _required_text(tag, "--tag", "찾을 태그 하나를 입력하세요 (예: --tag meal)"),
        )
        return self._iter_recent_matches(flt)

    def _iter_recent_matches(self, flt: SearchFilter) -> Generator[Transaction, None, None]:
        # 결과는 최신순이어야 하는데 파일은 입력 순서라서, 맞는 거래를 다 보기 전에는 첫 줄을 정할 수 없다.
        # 전부 모아 정렬하면 메모리가 매칭 수만큼 커지므로, 1000건씩 정렬해 파일로 내려놓았다가
        # 나중에 합치는 "외부 정렬"을 쓴다.
        chunk: list[Transaction] = []
        paths: list[Path] = []
        runs: SortRunStore | None = None
        try:
            for tx in self._iter_matches(flt):
                if len(chunk) == SEARCH_CHUNK_SIZE:
                    # 1000건이 찼는데 한 건이 더 왔으므로 지금 조각을 정렬해 파일로 쓰고 리스트를 비운다.
                    # 그래서 메모리에는 항상 1000건 이하만 남는다. "한 건 더 왔을 때" 쓰는 이유는
                    # 딱 1000건으로 끝나면 파일을 만들 필요가 없기 때문이다.
                    if runs is None:
                        runs = SortRunStore()  # 임시 폴더는 처음 필요해진 순간에만 만든다(결과가 적으면 디스크를 안 씀).
                    paths.append(runs.write_run(_sort_chunk(chunk)))
                    chunk = []
                chunk.append(tx)
            if runs is None:
                # 맞는 거래가 1000건 이하라 이미 전부 메모리에 있으므로, 파일 없이 바로 정렬해 내보낸다.
                yield from _sort_chunk(chunk)
                return
            paths.append(runs.write_run(_sort_chunk(chunk)))
            chunk = []
            paths = _merge_down(runs, paths)
            # 남은 조각(최대 64개)의 맨 앞 한 건끼리만 비교해 가장 최신인 것부터 한 건씩 내보낸다.
            yield from _merge_runs(runs, paths)
        finally:
            # 정상 종료든 오류든 Ctrl+C 든, 이 제너레이터가 끝나거나 닫힐 때 반드시 임시 폴더를 지운다.
            if runs is not None:
                runs.close()

    def _iter_matches(self, flt: SearchFilter) -> Iterator[Transaction]:
        # 제너레이터: 파일에서 한 건씩 받아 조건에 맞는 것만 넘겨준다. 여기서는 거래를 모으지 않는다.
        for tx in self.transactions.iter_transactions():
            if flt.matches(tx):
                yield tx

    def _iter_month(self, month: str) -> Iterator[Transaction]:
        # 제너레이터: 해당 월(date 가 "YYYY-MM-" 로 시작) 거래만 한 건씩 넘겨준다.
        prefix = month + "-"
        for tx in self.transactions.iter_transactions():
            if tx.date.startswith(prefix):
                yield tx

    def summarize_month(self, month: str, top: int) -> MonthlySummary:
        m = validate_month(month)
        budget = self.budgets.get(m)
        tx_count = income = expense = 0
        by_category: dict[str, int] = {}
        # 거래를 목록에 쌓지 않고 한 건씩 받아 합계만 더해 간다.
        # 그래서 메모리는 거래 수가 아니라 카테고리 수에만 비례한다.
        for tx in self._iter_month(m):
            tx_count += 1
            if tx.type == "income":
                income += tx.amount
            else:
                expense += tx.amount
                by_category[tx.category] = by_category.get(tx.category, 0) + tx.amount
        # 카테고리 합계(작은 dict)에서 상위 top 개만 고른다. 금액 내림차순, 동점이면 이름 오름차순.
        top_expenses = heapq.nsmallest(top, by_category.items(), key=_top_key)
        return MonthlySummary(
            month=m,
            top=top,
            tx_count=tx_count,
            total_income=income,
            total_expense=expense,
            balance=income - expense,
            budget=budget,
            usage_rate=None if budget is None else _usage_rate_text(expense, budget),
            over_budget=budget is not None and expense > budget,
            top_expenses=top_expenses,
        )

    def set_budget(self, month: str, amount: str) -> tuple[str, int]:
        m = validate_month(month)
        a = parse_amount(amount)
        # 같은 월이 있으면 덮어쓰며, 저장은 임시 파일 + os.replace 로 원자적으로 교체된다.
        self.budgets.set(m, a)
        return m, a

    def update_transaction(
        self,
        tx_id: str,
        *,
        date: str | None,
        type_: str | None,
        category: str | None,
        amount: str | None,
        memo: str | None,
        tags: str | None,
    ) -> Transaction:
        if all(v is None for v in (date, type_, category, amount, memo, tags)):
            raise ValidationError(
                cause="수정할 항목이 없습니다",
                hint="--date, --type, --category, --amount, --memo, --tags 중 하나 이상을 지정하세요",
            )
        changes: dict[str, Any] = {}
        if date is not None:
            changes["date"] = validate_date(date)
        if type_ is not None:
            changes["type"] = validate_type(type_)
        if category is not None:
            changes["category"] = self.validate_category(category)
        if amount is not None:
            changes["amount"] = parse_amount(amount)
        if memo is not None:
            changes["memo"] = memo.strip()
        if tags is not None:
            changes["tags"] = parse_tags(tags)

        existing = self.transactions.get(tx_id.strip())
        if existing is None:
            raise _not_found(tx_id)
        # dataclasses.replace 는 바뀐 필드만 갈아 끼운 새 거래를 만들며, __post_init__ 검증도 다시 거친다.
        new = dataclasses.replace(existing, **changes)
        if not self.transactions.update(new):
            raise _not_found(tx_id)
        return new

    def delete_transaction(self, tx_id: str) -> str:
        n = tx_id.strip()
        if not self.transactions.delete(n):
            raise _not_found(tx_id)
        return n

    def import_csv(self, src: str) -> ImportResult:
        path = _required_text(src, "--from", "가져올 CSV 파일 경로를 입력하세요 (예: --from import.csv)")
        # 파일 없음·헤더 문제는 임시 파일을 만들기 전에 먼저 걸러낸다.
        check_csv_header(path)
        # 카테고리 목록은 한 번만 읽어 둔다 (행마다 파일을 다시 읽지 않음).
        categories = set(self.categories.list_names())
        result = ImportResult()
        # append_many 가 예외 없이 끝났을 때(= 파일 교체 완료)만 결과를 돌려준다.
        self.transactions.append_many(self._iter_imported(path, categories, result))
        return result

    def _iter_imported(self, path: str, categories: set[str], result: ImportResult) -> Iterator[Transaction]:
        # 제너레이터: CSV 를 한 행씩 검증해 올바른 행만 거래로 만들어 넘긴다. 거래를 모으지 않는다.
        # ValidationError(행 값 오류)만 건너뛰고, 파일 오류·Ctrl+C 는 그대로 올라가 import 전체를 취소한다.
        for record in iter_csv_records(path):
            if record is None:
                result.skipped += 1
                continue
            try:
                fields = _import_fields(record, categories)
            except ValidationError:
                result.skipped += 1
                continue
            tx = Transaction(id=self.transactions.issue_id(), **fields)
            result.imported += 1
            yield tx

    def export_csv(
        self,
        out: str,
        *,
        month: str | None,
        date_from: str | None,
        date_to: str | None,
    ) -> tuple[str, int]:
        if month is None and date_from is None and date_to is None:
            raise ValidationError(
                cause="내보낼 조건이 없습니다",
                hint="--month YYYY-MM 또는 --from YYYY-MM-DD --to YYYY-MM-DD 를 지정하세요",
            )
        if (date_from is None) != (date_to is None):
            raise ValidationError(
                cause="--from 과 --to 는 함께 지정해야 합니다",
                hint="기간은 --from YYYY-MM-DD --to YYYY-MM-DD 로, 한 달 전체는 --month YYYY-MM 으로 지정하세요",
            )
        m = None if month is None else validate_month(month)
        flt = SearchFilter(
            date_from=None if date_from is None else validate_date(date_from),
            date_to=None if date_to is None else validate_date(date_to),
        )
        path = _required_text(out, "--out", "저장할 CSV 파일 경로를 입력하세요 (예: --out export.csv)")
        count = write_transactions_csv(path, self._iter_export(m, flt))
        return path, count

    def _iter_export(self, month: str | None, flt: SearchFilter) -> Iterator[Transaction]:
        # 제너레이터: 저장된 순서 그대로 한 건씩 읽어 조건(월 AND 기간)에 맞는 것만 넘긴다. 모으지 않는다.
        prefix = None if month is None else month + "-"
        for tx in self.transactions.iter_transactions():
            if (prefix is None or tx.date.startswith(prefix)) and flt.matches(tx):
                yield tx
