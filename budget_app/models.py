"""[모델] 거래 데이터 모델, 입력 검증 함수, 앱 예외 클래스."""

import json
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any

TRANSACTION_TYPES: tuple[str, ...] = ("income", "expense")
DEFAULT_CATEGORIES: tuple[str, ...] = ("food", "transport", "rent", "etc")

_DATE_RE = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}")
_MONTH_RE = re.compile(r"[0-9]{4}-[0-9]{2}")
_AMOUNT_RE = re.compile(r"[0-9]+")
_TX_ID_RE = re.compile(r"TX-([0-9]{6,})")

_TX_KEYS: tuple[str, ...] = ("id", "type", "date", "amount", "category", "memo", "tags")


class BudgetAppError(Exception):
    """앱에서 예상한 모든 오류의 기반 클래스. 원인과 해결 힌트를 함께 담는다."""

    def __init__(self, cause: str, hint: str) -> None:
        super().__init__(cause)
        self.cause = cause
        self.hint = hint


class ValidationError(BudgetAppError):
    """입력값 검증 실패. import 가 잘못된 행만 골라 건너뛸 수 있도록 따로 둔다."""


def validate_date(value: str) -> str:
    """YYYY-MM-DD 형식의 실제 날짜인지 확인하고 정리한 값을 돌려준다."""
    hint = "YYYY-MM-DD 형식의 실제 날짜를 입력하세요 (예: 2024-05-01)"
    if not isinstance(value, str):
        raise ValidationError(f"날짜가 문자열이 아닙니다: {value!r}", hint)
    text = value.strip()
    if not _DATE_RE.fullmatch(text):
        raise ValidationError(f"날짜 형식이 올바르지 않습니다: {value!r}", hint)
    try:
        datetime.strptime(text, "%Y-%m-%d")
    except ValueError:
        raise ValidationError(f"존재하지 않는 날짜입니다: {value!r}", hint) from None
    return text


def validate_month(value: str) -> str:
    """YYYY-MM 형식의 실제 월인지 확인하고 정리한 값을 돌려준다."""
    hint = "YYYY-MM 형식으로 입력하세요 (예: 2024-05)"
    if not isinstance(value, str):
        raise ValidationError(f"월이 문자열이 아닙니다: {value!r}", hint)
    text = value.strip()
    if not _MONTH_RE.fullmatch(text):
        raise ValidationError(f"월 형식이 올바르지 않습니다: {value!r}", hint)
    try:
        datetime.strptime(text, "%Y-%m")
    except ValueError:
        raise ValidationError(f"존재하지 않는 월입니다: {value!r}", hint) from None
    return text


def parse_amount(value: str | int) -> int:
    """1 이상의 정수 금액으로 바꿔 돌려준다."""
    hint = "1 이상의 정수를 입력하세요 (예: 15000)"
    # bool 은 int 의 하위 클래스라서 먼저 걸러낸다.
    if isinstance(value, bool):
        raise ValidationError(f"금액이 숫자가 아닙니다: {value!r}", hint)
    if isinstance(value, int):
        amount = value
    elif isinstance(value, str):
        text = value.strip()
        if not _AMOUNT_RE.fullmatch(text):
            raise ValidationError(f"금액이 정수가 아닙니다: {value!r}", hint)
        amount = int(text)
    else:
        raise ValidationError(f"금액이 숫자가 아닙니다: {value!r}", hint)
    if amount <= 0:
        raise ValidationError(f"금액은 0보다 커야 합니다: {value!r}", hint)
    return amount


def validate_type(value: str) -> str:
    """income 또는 expense 인지 확인하고 정리한 값을 돌려준다."""
    hint = "income 또는 expense 중 하나를 입력하세요"
    if not isinstance(value, str):
        raise ValidationError(f"거래 종류가 문자열이 아닙니다: {value!r}", hint)
    text = value.strip()
    if text not in TRANSACTION_TYPES:
        raise ValidationError(f"알 수 없는 거래 종류입니다: {value!r}", hint)
    return text


def format_tx_id(seq: int) -> str:
    """일련번호를 TX-000012 형태의 id 로 만든다."""
    return f"TX-{seq:06d}"


def tx_id_seq(tx_id: str) -> int:
    """id 의 숫자 부분을 정수로 돌려준다. 문자열 비교 대신 이 값으로 비교한다."""
    hint = "id 는 TX-000012 처럼 TX- 뒤에 6자리 이상 숫자여야 합니다"
    match = _TX_ID_RE.fullmatch(tx_id) if isinstance(tx_id, str) else None
    if match is None:
        raise ValidationError(f"id 형식이 올바르지 않습니다: {tx_id!r}", hint)
    return int(match.group(1))


# @dataclass 를 쓰면 __init__, __eq__, __repr__ 을 필드 선언만으로 자동 생성해 준다.
# 필드 목록이 곧 저장 형식(JSONL 한 줄의 키)이 되어 읽고 쓰기가 단순해진다.
@dataclass
class Transaction:
    id: str
    type: str
    date: str
    amount: int
    category: str
    memo: str = ""
    # 리스트 같은 가변 기본값은 인스턴스끼리 공유되지 않도록 default_factory 로 매번 새로 만든다.
    tags: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        # dataclass 가 만든 __init__ 직후 자동 호출되므로, 어떤 경로로 만들든 규칙을 어긴 거래는 생길 수 없다.
        # 값은 바꾸지 않으므로, 검증 함수가 정리(strip)한 값과 다르면 정규화되지 않은 값으로 보고 거부한다.
        tx_id_seq(self.id)  # fullmatch 로 검사하므로 앞뒤 공백이 있으면 여기서 이미 거부된다.
        if validate_date(self.date) != self.date:
            raise ValidationError(
                f"날짜 앞뒤에 공백이 있습니다: {self.date!r}",
                "YYYY-MM-DD 형식의 실제 날짜를 공백 없이 입력하세요 (예: 2024-05-01)",
            )
        if validate_type(self.type) != self.type:
            raise ValidationError(
                f"거래 종류 앞뒤에 공백이 있습니다: {self.type!r}",
                "income 또는 expense 중 하나를 공백 없이 입력하세요",
            )
        if isinstance(self.amount, bool) or not isinstance(self.amount, int) or self.amount <= 0:
            raise ValidationError(
                f"금액은 1 이상의 정수여야 합니다: {self.amount!r}",
                "1 이상의 정수를 입력하세요 (예: 15000)",
            )
        if not isinstance(self.category, str) or not self.category.strip():
            raise ValidationError(
                f"카테고리가 비어 있거나 문자열이 아닙니다: {self.category!r}",
                "등록된 카테고리 이름을 입력하세요",
            )
        if self.category != self.category.strip():
            raise ValidationError(
                f"카테고리 앞뒤에 공백이 있습니다: {self.category!r}",
                "등록된 카테고리 이름을 공백 없이 입력하세요",
            )
        if not isinstance(self.memo, str):
            raise ValidationError(
                f"메모가 문자열이 아닙니다: {self.memo!r}",
                "메모는 문자열로 입력하세요 (없으면 빈 문자열)",
            )
        if not isinstance(self.tags, list) or not all(isinstance(t, str) for t in self.tags):
            raise ValidationError(
                f"태그는 문자열 목록이어야 합니다: {self.tags!r}",
                "태그는 문자열 목록으로 입력하세요 (없으면 빈 목록)",
            )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def to_json_line(self) -> str:
        # ensure_ascii=False: 한글 메모가 \uXXXX 가 아니라 그대로 보이게 저장한다.
        return json.dumps(self.to_dict(), ensure_ascii=False)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Transaction":
        missing = [key for key in _TX_KEYS if key not in data]
        if missing:
            raise ValidationError(
                f"거래 데이터에 필요한 항목이 없습니다: {', '.join(missing)}",
                f"거래에는 {', '.join(_TX_KEYS)} 항목이 모두 있어야 합니다",
            )
        return cls(**{key: data[key] for key in _TX_KEYS})

    @classmethod
    def from_json_line(cls, line: str) -> "Transaction":
        hint = "한 줄에 거래 하나를 JSON 객체로 적어야 합니다"
        try:
            data = json.loads(line)
        except json.JSONDecodeError as e:
            raise ValidationError(f"JSON 형식이 아닙니다: {e.msg}", hint) from None
        if not isinstance(data, dict):
            raise ValidationError("JSON 객체가 아닙니다", hint)
        return cls.from_dict(data)
