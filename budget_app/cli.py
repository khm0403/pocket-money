"""[CLI] argparse 명령 정의와 입력/출력."""

import argparse
import re
from collections.abc import Callable
from contextlib import closing
from typing import Any, NoReturn, TypeVar

from budget_app.decorators import EXIT_OK, handle_broken_pipe, handle_errors, print_error
from budget_app.models import Transaction, ValidationError, parse_amount, validate_date, validate_type
from budget_app.services import (
    DEFAULT_DATA_DIR,
    DEFAULT_LIST_LIMIT,
    DEFAULT_SUMMARY_TOP,
    LedgerService,
    MonthlySummary,
    normalize_category_name,
    parse_limit,
    parse_tags,
    parse_top,
)

PROG: str = "python -m budget_app"

T = TypeVar("T")


# argparse 는 사용법 오류(없는 명령, 빠진 옵션 등)의 원인 문장을 영어로 만든다. 다른 오류처럼 한국어로 보이도록,
# 다 만들어진 영어 문장을 정해 둔 모양(정규식)과 맞춰 보고 한국어 문장으로 바꾼다.
# argparse 내부 함수를 바꿔 끼우거나 번역 파일을 쓰는 방법은 버전마다 내부가 달라 깨지기 쉽고 준비할 것이 많아 쓰지 않는다.
def _usage_error_cause(message: str) -> str:
    """argparse 의 영어 사용법 오류 원인 문장을 한국어로 바꾼다. 모르는 모양이면 그대로 돌려준다."""
    m = re.fullmatch(r"the following arguments are required: \{(?P<choices>[^{}]*)\}", message)
    if m:
        choices = m["choices"].replace(",", ", ")
        return f"명령을 입력하세요 (사용 가능: {choices})"
    m = re.fullmatch(r"the following arguments are required: (?P<options>--[a-z-]+(?:, --[a-z-]+)*)", message)
    if m:
        return f"필수 옵션이 없습니다: {m['options']}"
    # 명령 목록은 끝의 (choose from ...) 가 아니라 앞쪽 {add,list,...} 에서 꺼낸다. 끝부분은 파이썬 버전·설정에 따라
    # 따옴표 표시가 다를 수 있어서('add' 또는 add) 앞쪽을 써야 어느 버전에서나 같은 문장이 나온다.
    # 3.15 부터 기본으로 붙는 ", maybe you meant 'list'?" 제안 꼬리는 있어도 맞추되, 한국어 문장에는 넣지 않는다.
    m = re.fullmatch(r"argument \{(?P<choices>[^{}]*)\}: invalid choice: (?P<value>'[^']*')(?:, maybe you meant '[^']*'\?)? \(choose from [^()]*\)", message)
    if m:
        choices = m["choices"].replace(",", ", ")
        return f"알 수 없는 명령입니다: {m['value']} (사용 가능: {choices})"
    m = re.fullmatch(r"argument (?P<option>--[a-z-]+): expected one argument", message)
    if m:
        return f"{m['option']} 옵션에 값이 필요합니다"
    m = re.fullmatch(r"argument (?P<option>--[a-z-]+): ignored explicit argument (?P<value>.*)", message)
    if m:
        return f"{m['option']} 옵션에는 값을 붙일 수 없습니다: {m['value']}"
    m = re.fullmatch(r"unrecognized arguments: (?P<args>.+)", message)
    if m:
        return f"알 수 없는 옵션 또는 값입니다: {m['args']}"
    # 모르는 모양의 문장(새 파이썬 버전에서 바뀐 문장 등)은 그대로 돌려준다. 최악의 경우에도
    # 영어 원인 문장이 그대로 나올 뿐, 오류 메시지가 사라지거나 프로그램이 멈추지 않는다.
    return message


class _ArgumentParser(argparse.ArgumentParser):
    """argparse 사용법 오류도 [오류]/[힌트] 형식으로 출력한다."""

    def error(self, message: str) -> NoReturn:
        # 바꾸는 것은 [오류] 줄의 원인 문장뿐이다. [힌트] 문장과 종료 코드 2 는 그대로다.
        print_error(_usage_error_cause(message), f"{self.prog} --help 로 사용법을 확인하세요")
        self.exit(2)


def _prompt(label: str, parse: Callable[[str], T]) -> T:
    """값을 입력받아 parse 로 검증한다. 검증에 실패하면 안내 후 같은 항목을 다시 묻는다."""
    while True:
        raw = input(label)
        try:
            return parse(raw)
        except ValidationError as e:
            print_error(e.cause, e.hint)


def _format_tx(tx: Transaction) -> str:
    return f"{tx.id} | {tx.date} | {tx.type} | {tx.category} | {tx.amount} | {tx.memo}".rstrip()


@handle_errors
def _cmd_add(args: argparse.Namespace) -> int:
    service = LedgerService(args.data_dir)
    date = _prompt("날짜(YYYY-MM-DD): ", validate_date)
    type_ = _prompt("타입(income/expense): ", validate_type)
    category = _prompt("카테고리: ", service.validate_category)
    amount = _prompt("금액(양수): ", parse_amount)
    memo = input("메모(선택): ").strip()
    tags = parse_tags(input("태그(쉼표로 구분, 없으면 엔터): "))
    tx = service.add_transaction(date, type_, category, amount, memo, tags)
    print(f"[저장 완료] id={tx.id}")
    return EXIT_OK


@handle_errors
def _cmd_list(args: argparse.Namespace) -> int:
    limit = DEFAULT_LIST_LIMIT if args.limit is None else parse_limit(args.limit)
    service = LedgerService(args.data_dir)
    txs = service.recent_transactions(limit)
    for tx in txs:
        print(_format_tx(tx))
    if not txs:
        print("거래 내역이 없습니다.")
    return EXIT_OK


@handle_errors
def _cmd_search(args: argparse.Namespace) -> int:
    service = LedgerService(args.data_dir)
    found = False
    # 결과를 모으지 않고 한 줄씩 받아 바로 출력한다. closing 은 출력 도중 Ctrl+C 로 반복이 끊겨도
    # 제너레이터를 즉시 닫아, 서비스의 finally(정렬용 임시 폴더 삭제)가 바로 실행되게 한다.
    # 출력 받는 쪽이 먼저 닫혀(BrokenPipeError) 반복이 끊길 때도 마찬가지로 정렬용 임시 폴더가 바로 지워진다.
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


def _summary_lines(s: MonthlySummary) -> list[str]:
    budget_line = None if s.budget is None else f"예산: {s.budget}원 (사용률 {s.usage_rate}%)"
    if s.tx_count == 0:
        lines = [f"{s.month} 데이터 없음"]
        if budget_line is not None:
            lines.append(budget_line)
        return lines
    lines = [
        f"총 수입: {s.total_income}원",
        f"총 지출: {s.total_expense}원",
        f"잔액: {s.balance}원",
    ]
    if budget_line is not None:
        lines.append(budget_line)
    if s.over_budget:
        lines.append("[경고] 예산을 초과했습니다")
    lines.append(f"지출 TOP {s.top}")
    if not s.top_expenses:
        lines.append("지출 내역 없음")
    for rank, (category, amount) in enumerate(s.top_expenses, start=1):
        lines.append(f"{rank}) {category} {amount}원")
    return lines


@handle_errors
def _cmd_summary(args: argparse.Namespace) -> int:
    top = DEFAULT_SUMMARY_TOP if args.top is None else parse_top(args.top)
    service = LedgerService(args.data_dir)
    for line in _summary_lines(service.summarize_month(args.month, top)):
        print(line)
    return EXIT_OK


@handle_errors
def _cmd_budget_set(args: argparse.Namespace) -> int:
    service = LedgerService(args.data_dir)
    month, amount = service.set_budget(args.month, args.amount)
    print(f"[저장 완료] {month} 예산 {amount}원")
    return EXIT_OK


@handle_errors
def _cmd_update(args: argparse.Namespace) -> int:
    service = LedgerService(args.data_dir)
    tx = service.update_transaction(
        args.id,
        date=args.date,
        type_=args.type,
        category=args.category,
        amount=args.amount,
        memo=args.memo,
        tags=args.tags,
    )
    print(f"[수정 완료] id={tx.id}")
    return EXIT_OK


@handle_errors
def _cmd_delete(args: argparse.Namespace) -> int:
    service = LedgerService(args.data_dir)
    tx_id = service.delete_transaction(args.id)
    print(f"[삭제 완료] id={tx_id}")
    return EXIT_OK


@handle_errors
def _cmd_category_add(args: argparse.Namespace) -> int:
    service = LedgerService(args.data_dir)
    name = _prompt("카테고리명: ", service.validate_new_category)
    name = service.add_category(name)
    print(f"[저장 완료] category={name}")
    return EXIT_OK


@handle_errors
def _cmd_category_list(args: argparse.Namespace) -> int:
    service = LedgerService(args.data_dir)
    for name in service.list_categories():
        print(f"- {name}")
    return EXIT_OK


@handle_errors
def _cmd_category_remove(args: argparse.Namespace) -> int:
    service = LedgerService(args.data_dir)
    name = _prompt("카테고리명: ", normalize_category_name)
    name = service.remove_category(name)
    print(f"[삭제 완료] category={name}")
    return EXIT_OK


@handle_errors
def _cmd_import(args: argparse.Namespace) -> int:
    service = LedgerService(args.data_dir)
    result = service.import_csv(args.csv_path)
    print(f"[완료] imported={result.imported}, skipped={result.skipped}")
    return EXIT_OK


@handle_errors
def _cmd_export(args: argparse.Namespace) -> int:
    service = LedgerService(args.data_dir)
    path, count = service.export_csv(
        args.out,
        month=args.month,
        date_from=args.date_from,
        date_to=args.date_to,
    )
    print(f"[완료] {path} ({count} records)")
    return EXIT_OK


def _with_help(parser: argparse.ArgumentParser) -> argparse.ArgumentParser:
    # 옵션은 모두 "--" 형식으로 통일하므로 argparse 기본 -h 대신 --help 만 붙인다.
    parser.add_argument("--help", action="help", help="show this help message and exit")
    return parser


def build_parser() -> argparse.ArgumentParser:
    # --data-dir 만 가진 부모 파서. 말단 명령마다 붙여 "명령 뒤"에서만 받도록 한다.
    data_dir_parent = argparse.ArgumentParser(add_help=False, allow_abbrev=False)
    data_dir_parent.add_argument(
        "--data-dir",
        default=DEFAULT_DATA_DIR,
        help="데이터 폴더 경로 (기본값: ./data)",
    )
    # 모든 하위 파서 공통: -h 없음, 옵션 약어(--lim 등) 금지.
    common: dict[str, Any] = {"add_help": False, "allow_abbrev": False}
    leaf: dict[str, Any] = {**common, "parents": [data_dir_parent]}

    parser = _with_help(_ArgumentParser(prog=PROG, add_help=False, allow_abbrev=False))
    sub = parser.add_subparsers(
        dest="command", required=True, metavar="{add,list,search,summary,budget,update,delete,category,import,export}"
    )

    p_add = _with_help(sub.add_parser("add", help="거래 추가 (대화형)", **leaf))
    p_add.set_defaults(handler=_cmd_add)

    p_list = _with_help(sub.add_parser("list", help="최신순 거래 목록 (기본 20건)", **leaf))
    p_list.add_argument("--limit", default=None, help="보여 줄 최대 건수 (기본값: 20)")
    p_list.set_defaults(handler=_cmd_list)

    p_search = _with_help(sub.add_parser("search", help="조건 검색 (최신순, 조건은 모두 만족)", **leaf))
    p_search.add_argument("--from", dest="date_from", metavar="YYYY-MM-DD", default=None, help="시작 날짜 (이 날짜 포함)")
    p_search.add_argument("--to", dest="date_to", metavar="YYYY-MM-DD", default=None, help="끝 날짜 (이 날짜 포함)")
    p_search.add_argument("--category", default=None, help="등록된 카테고리 (정확히 일치)")
    p_search.add_argument("--type", default=None, help="거래 종류 (income 또는 expense)")
    p_search.add_argument("--q", default=None, help="메모에 포함된 글자 (대소문자 구분)")
    p_search.add_argument("--tag", default=None, help="태그 하나 (정확히 일치)")
    p_search.set_defaults(handler=_cmd_search)

    p_summary = _with_help(
        sub.add_parser("summary", help="월별 요약 (총수입/총지출/잔액, 예산 사용률, 지출 TOP N)", **leaf)
    )
    p_summary.add_argument("--month", required=True, metavar="YYYY-MM", help="요약할 월 (필수)")
    p_summary.add_argument("--top", default=None, metavar="N", help="지출 TOP N 개수 (기본값: 3)")
    p_summary.set_defaults(handler=_cmd_summary)

    p_budget = _with_help(sub.add_parser("budget", help="월 예산 관리", **common))
    budget_sub = p_budget.add_subparsers(dest="budget_command", required=True, metavar="{set}")

    p_budget_set = _with_help(budget_sub.add_parser("set", help="월 예산 저장 (같은 월은 덮어씀)", **leaf))
    p_budget_set.add_argument("--month", required=True, metavar="YYYY-MM", help="예산을 정할 월")
    p_budget_set.add_argument("--amount", required=True, metavar="AMOUNT", help="예산 금액 (1 이상의 정수)")
    p_budget_set.set_defaults(handler=_cmd_budget_set)

    p_update = _with_help(sub.add_parser("update", help="거래 수정 (옵션식)", **leaf))
    p_update.add_argument("--id", required=True, help="수정할 거래 id (예: TX-000001)")
    p_update.add_argument("--date", default=None, help="날짜 (YYYY-MM-DD)")
    p_update.add_argument("--type", default=None, help="거래 종류 (income 또는 expense)")
    p_update.add_argument("--category", default=None, help="등록된 카테고리")
    p_update.add_argument("--amount", default=None, help="금액 (1 이상의 정수)")
    p_update.add_argument("--memo", default=None, help="메모. 빈 문자열이면 메모를 지움")
    p_update.add_argument("--tags", default=None, help="쉼표(,)로 구분한 태그. 빈 문자열이면 태그를 모두 지움")
    p_update.set_defaults(handler=_cmd_update)

    p_delete = _with_help(sub.add_parser("delete", help="거래 삭제", **leaf))
    p_delete.add_argument("--id", required=True, help="삭제할 거래 id (예: TX-000001)")
    p_delete.set_defaults(handler=_cmd_delete)

    p_category = _with_help(sub.add_parser("category", help="카테고리 관리", **common))
    cat_sub = p_category.add_subparsers(dest="category_command", required=True, metavar="{add,list,remove}")

    p_cat_add = _with_help(cat_sub.add_parser("add", help="카테고리 추가 (대화형)", **leaf))
    p_cat_add.set_defaults(handler=_cmd_category_add)

    p_cat_list = _with_help(cat_sub.add_parser("list", help="카테고리 목록", **leaf))
    p_cat_list.set_defaults(handler=_cmd_category_list)

    p_cat_remove = _with_help(cat_sub.add_parser("remove", help="카테고리 삭제 (대화형, 사용 중이면 차단)", **leaf))
    p_cat_remove.set_defaults(handler=_cmd_category_remove)

    p_import = _with_help(sub.add_parser("import", help="CSV 파일의 거래를 한 번에 추가 (잘못된 행은 건너뜀)", **leaf))
    p_import.add_argument(
        "--from", dest="csv_path", required=True, metavar="CSV", help="가져올 CSV 파일 경로 (UTF-8, 헤더 포함)"
    )
    p_import.set_defaults(handler=_cmd_import)

    p_export = _with_help(sub.add_parser("export", help="조건에 맞는 거래를 CSV 파일로 저장", **leaf))
    p_export.add_argument("--out", required=True, metavar="CSV", help="저장할 CSV 파일 경로 (이미 있으면 오류)")
    p_export.add_argument("--month", default=None, metavar="YYYY-MM", help="내보낼 월")
    p_export.add_argument(
        "--from", dest="date_from", default=None, metavar="YYYY-MM-DD", help="시작 날짜 (이 날짜 포함, --to 와 함께)"
    )
    p_export.add_argument(
        "--to", dest="date_to", default=None, metavar="YYYY-MM-DD", help="끝 날짜 (이 날짜 포함, --from 과 함께)"
    )
    p_export.set_defaults(handler=_cmd_export)

    return parser


# 명령이 끝난 뒤 남은 출력과 --help 출력이 끊기는 경우까지 조용히 끝내도록 main 전체를 감싼다.
# 명령 실행 중의 끊김은 handle_errors 가 처리한다.
@handle_broken_pipe
def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.handler(args)
