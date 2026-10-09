# 7단계 설계서 (보강): 사용법 오류(argparse)의 원인 문장 한국어화

> 개정 1 (총괄 결정 반영: Python 3.15 대비 보강)
> - K3(없는 명령) 정규식이 `(choose from …)` 앞의 제안 꼬리 `, maybe you meant '…'?` 를 선택적으로 허용한다. 꼬리가 붙어도 "알 수 없는 명령입니다" 로 번역하고, 한국어 문장에는 제안을 넣지 않는다(3.3, 3.4, 5장, 6.2 S6·X, 7장 #3).
> - 3.4 의 선택지 따옴표 서술을 에이전트 2 실측(3.14.7 에서 제안이 켜지면 따옴표 있는 목록)에 맞게 고쳤다. 목록 부분을 읽지 않으므로 결과에는 영향이 없다.

## 1. 목표

- argparse 가 만드는 사용법 오류의 **원인 문장만** 한국어로 바꾼다. 예: `[오류] the following arguments are required: --month` → `[오류] 필수 옵션이 없습니다: --month`. 다른 오류처럼 `[오류] 원인` / `[힌트] 해결` 이 모두 한국어로 보이게 된다.
- `[힌트]` 문장, 종료 코드 2, 출력 위치(stderr), `--help` 도움말 본문, 정상 실행 출력, 다른 오류(종료 코드 1)는 한 글자도 바뀌지 않는다. 명령·옵션 추가는 없다.
- 영어 원문이 이 설계에 없는 모양이면(새 파이썬 버전 등) 원문을 그대로 보여 준다. 그래서 최악의 경우에도 지금과 같은 결과가 나온다.

## 2. 대상 요구사항

| REQUIREMENTS.md 항목 | 이번 단계 충족 범위 |
| --- | --- |
| 4장 예외 처리 "스택트레이스 출력 금지, 원인 + 해결 힌트" | 사용법 오류도 다른 오류와 같은 한국어 "원인" 문장으로 보여 준다. 한국어로 맞추는 것 자체는 사용자 결정이다(7장 #1) |
| 4장 종료 코드 "정상 0, 오류 0 아닌 값" | 사용법 오류 종료 코드 2 를 그대로 둔다(2단계 3.0 결정) |
| 0장 Python 3.10 이상, 표준 라이브러리만 | 표준 라이브러리 `re` 만 추가한다. 3.10~3.14 의 argparse 원문 차이를 흡수하고, 3.15 의 제안 꼬리도 대비한다(3.4, 총괄 결정) |
| 0장 "모든 명령에 `--help` 동작" | 도움말 출력은 바뀌지 않는다(6.2 H 절에서 변경 전과 글자 단위로 비교) |
| 4장 모듈화(4계층), 타입 힌트 | 처리는 CLI 계층(`cli.py`)에만 둔다. 새 함수 1개에 타입 힌트를 단다 |
| 4장 README | 바꾸지 않는다(3.6) |

## 3. 파일/모듈 설계

### 3.0 공통 결정

| 항목 | 결정 | 근거 |
| --- | --- | --- |
| 처리 위치 | `cli.py` 의 기존 `_ArgumentParser.error(message)` 한 곳이다. argparse 가 만든 사용법 오류는 모두 이 메서드로 들어온다. 하위 파서도 `add_subparsers` 가 부모 파서 클래스를 쓰므로 같은 메서드를 거친다(2단계 3.4) | ← 4장 예외 처리, 4장 모듈화(CLI 계층이 사용자 입출력 담당) |
| 구현 방식 | **영어 완성 문장을 정규식으로 알아보고 한국어 문장으로 바꾼다.** 새 모듈 함수 `_usage_error_cause(message)` 가 `re.fullmatch` 6개를 차례로 시도한다. 하나도 맞지 않으면 `message` 를 그대로 돌려준다 | ← 4장 예외 처리 |
| 다른 방식을 쓰지 않는 이유 | ① argparse 내부 함수 덮어쓰기(`_check_value`, `_match_argument` 등)는 공개 API 가 아니다. 3.12~3.14 에서 내부 구조가 여러 번 바뀌어 버전마다 깨질 수 있고, 학습자에게 설명하기도 어렵다. ② gettext 번역 카탈로그는 `.po`/`.mo` 파일을 만들어 설치하고 언어 설정을 해야 한다. 또 argparse 의 문장 원본(msgid)도 버전마다 다르다. ③ 완성 문장 대조는 함수 하나와 `if` 6개로 끝난다. 모르는 문장은 그대로 통과시키므로 안전하다 | ← 0장 표준 라이브러리만, 과설계 금지 |
| 안전한 기본값 | 정규식은 `re.fullmatch`(문장 전체 일치)로만 쓴다. 맞지 않으면 원문을 그대로 돌려준다. 함수 안에서 예외가 나지 않는다(문자열 비교와 `replace` 만 사용) | ← 4장 예외 처리(스택트레이스 금지) |
| 명령 목록 표시 | "사용 가능" 명령 목록은 영어 문장 끝의 `(choose from ...)` 이 아니라 **앞쪽 `{add,list,...}`(우리가 정한 metavar)** 에서 꺼낸다. 버전·설정마다 따옴표 표시가 다를 수 있는 부분을 읽지 않으므로 모든 버전에서 같은 한국어 문장이 나온다(3.4) | ← 0장 3.10 이상 |
| 제안 꼬리 (총괄 결정) | `invalid choice` 원문의 값 바로 뒤, `(choose from …)` 앞에 `, maybe you meant '…'?` 가 붙어도 K3 로 번역한다. 한국어 문장에는 제안을 넣지 않는다(새 출력 항목을 만들지 않음) | ← 0장 3.10 이상(이후 버전 대비), 총괄 결정 |
| `[힌트]`·종료 코드 | `print_error(<한국어 원인>, f"{self.prog} --help 로 사용법을 확인하세요")` 와 `self.exit(2)` 는 그대로다. 원인 인자만 `_usage_error_cause(message)` 로 감싼다 | ← 4장 종료 코드, 총괄 지시(힌트 불변) |
| 도움말 본문 | `usage:`, `options:`, `show this help message and exit` 등 argparse 가 만드는 영어 도움말은 범위 밖이라 바꾸지 않는다. `build_parser` 는 한 글자도 바꾸지 않는다 | ← 총괄 지시(범위 밖) |

### 3.1 변경 파일 / 변경 금지 파일

- 변경: `budget_app/cli.py` 한 파일만 바꾼다. ① `import re` 1줄, ② 새 함수 `_usage_error_cause` 1개, ③ `_ArgumentParser.error` 본문 첫 줄에서 `message` 를 `_usage_error_cause(message)` 로 바꾼다. ④ 3.5 의 주석을 넣는다.
- **변경 금지**: `models.py`, `storage.py`, `services.py`, `decorators.py`, `__main__.py`, `__init__.py`, `README.md`. 6.2 S0 에서 착수 전 기준선 사본(6.0)과 바이트 단위로 비교한다.
- `cli.py` 안에서도 위 ①~④ 밖(`build_parser`, `_with_help`, `main`, `_cmd_*`, `_prompt`, `_format_tx`, `_summary_lines`, docstring, 다른 import)은 바꾸지 않는다. 6.2 S6 이 AST 로 확인한다.

### 3.2 이 앱에서 실제로 나는 argparse 사용법 오류 (전수)

argparse 소스(3.10~3.14)에서 `self.error(...)` 로 이어지는 모든 경로를 이 앱의 파서 구성과 맞춰 보았다. 파서 구성은 `add_help=False` + `--help` 만, `allow_abbrev=False`, 하위 파서 `required=True` + metavar 지정, 모든 옵션은 `--` 이름 1개에 값 1개(nargs 기본), `type=`/`choices=`/상호 배타 그룹/위치 인자는 없음이다.

| # | 종류 | 발생 예 | argparse 원문 (3.14 기본 설정) | 한국어 원인 문장 | 근거 |
| --- | --- | --- | --- | --- | --- |
| K1 | 명령(하위 명령) 없음 | `python -m budget_app` / `-h` / `category` / `budget` | `the following arguments are required: {add,list,…,export}` (`category` 는 `{add,list,remove}`, `budget` 은 `{set}`) | `명령을 입력하세요 (사용 가능: add, list, search, summary, budget, update, delete, category, import, export)` (`category` → `(사용 가능: add, list, remove)`, `budget` → `(사용 가능: set)`) | ← 4장 예외 처리, 3장 명령 목록 |
| K2 | 필수 옵션 누락 | `summary`, `budget set`, `update --memo x`, `delete`, `import`, `export --month 2024-01` | `the following arguments are required: --month` (여러 개면 `--month, --amount`) | `필수 옵션이 없습니다: --month` / `필수 옵션이 없습니다: --month, --amount` | ← 3장 #4·#5·#7~#10 필수 옵션, 4장 예외 처리 |
| K3 | 없는 명령(하위 명령) | `nosuchcmd`, `category nosuch`, `budget get`, `--data-dir X list`(명령 자리에 `X`) | `argument {add,…,export}: invalid choice: 'nosuchcmd' (choose from …)` (제안이 켜지면 값 뒤에 `, maybe you meant '…'?` 가 붙음) | `알 수 없는 명령입니다: 'nosuchcmd' (사용 가능: add, list, …, export)` (제안 꼬리가 있어도 같은 문장, 총괄 결정) | ← 4장 예외 처리, 2장 `--data-dir` 위치(2단계 3.0) |
| K4 | 옵션 값 누락 | `list --limit`, `list --data-dir`, `summary --month`, `update --id TX-000001 --memo --tags a`, `search --from` | `argument --limit: expected one argument` | `--limit 옵션에 값이 필요합니다` | ← 3장 각 옵션, 4장 예외 처리 |
| K5 | `--help` 에 값을 붙임 | `--help=x`, `category list --help=x` | `argument --help: ignored explicit argument 'x'` | `--help 옵션에는 값을 붙일 수 없습니다: 'x'` | ← 0장 `--help`, 4장 예외 처리 |
| K6 | 알 수 없는 인자 (없는 옵션, `-h`, 옵션 줄임말, 남는 값, 명령 앞의 `--data-dir` 만 있는 경우) | `list --bogus`, `list -h`, `search --cat=food`, `list extra` | `unrecognized arguments: --bogus` (여러 개면 공백으로 이어짐) | `알 수 없는 옵션 또는 값입니다: --bogus` | ← 0장 옵션 규칙(`--` 전체 이름만), 4장 예외 처리 |

- `-h` 만 주면(최상위) argparse 는 `-h` 를 "모르는 옵션"으로 미뤄 두고, 먼저 "명령 없음"(K1)으로 끝난다. 하위 명령 뒤의 `-h` 는 K6 이다.
- `--data-dir X list` 는 `--data-dir` 를 모르는 옵션으로 미뤄 두고 `X` 를 명령으로 읽는다. 그래서 K3(`'X'`)이 된다.
- 옵션 줄임말을 띄어 쓰면(`search --cat food`) K6 에 두 단어가 공백으로 이어져 나온다(`--cat food`). 순서는 입력 순서 그대로다.

**이 앱에서 나지 않는 argparse 오류** (번역 코드를 넣지 않는다. 혹시 나면 원문 그대로 나온다)

| 원문 | 나지 않는 이유 |
| --- | --- |
| `ambiguous option: … could match …` | `allow_abbrev=False` 이고, 모든 옵션이 `--` 로 시작해 `-x` 형태와 겹치지 않는다 |
| `argument …: not allowed with argument …` | 상호 배타 그룹이 없다 |
| `argument …: invalid <type> value: …` | `type=` 을 쓰지 않는다(값 검증은 서비스가 함, 종료 코드 1) |
| `expected at most one argument` / `at least one` / `expected N arguments` | `nargs` 를 쓰지 않는다(모두 값 1개) |
| 옵션의 `invalid choice` (`argument --type: invalid choice: …`) | 옵션에 `choices=` 를 쓰지 않는다 |
| `unknown parser … (choices: …)` | argparse 가 그 전에 K3 검사에서 끝낸다(3.10~3.14 모두) |

### 3.3 `budget_app/cli.py` — [CLI] (최소 변경)

import 추가: `import re`. 위치는 `import argparse` 바로 다음 줄이다(6.2 S6 이 확인한다).

| 시그니처 | 책임 | 근거 |
| --- | --- | --- |
| `def _usage_error_cause(message: str) -> str` (신규, 모듈 함수) | argparse 의 영어 사용법 오류 원인 문장을 3.2 표의 한국어 문장으로 바꾼다. 모르는 모양이면 `message` 를 그대로 돌려준다. 위치는 `T = TypeVar("T")` 다음, `class _ArgumentParser` **바로 앞**이다 | ← 4장 예외 처리, 3.2 K1~K6 |
| `def error(self, message: str) -> NoReturn` (변경) | 본문 첫 줄만 `print_error(_usage_error_cause(message), f"{self.prog} --help 로 사용법을 확인하세요")` 로 바꾼다. 둘째 줄 `self.exit(2)` 와 클래스 docstring 은 그대로다 | ← 4장 예외 처리, 종료 코드 |

**정규식 6개** (순서대로. 6.2 S6 `WANT_PATTERNS` 와 같다)

| # | 패턴 | 한국어 |
| --- | --- | --- |
| 1 | `the following arguments are required: \{(?P<choices>[^{}]*)\}` | K1 |
| 2 | `the following arguments are required: (?P<options>--[a-z-]+(?:, --[a-z-]+)*)` | K2 |
| 3 | `argument \{(?P<choices>[^{}]*)\}: invalid choice: (?P<value>'[^']*')(?:, maybe you meant '[^']*'\?)? \(choose from [^()]*\)` | K3 (제안 꼬리는 선택. 총괄 결정) |
| 4 | `argument (?P<option>--[a-z-]+): expected one argument` | K4 |
| 5 | `argument (?P<option>--[a-z-]+): ignored explicit argument (?P<value>.*)` | K5 |
| 6 | `unrecognized arguments: (?P<args>.+)` | K6 |

**골격** (함수 본문은 이대로 쓴다. `# [주석 N]` 은 3.5 의 "왜" 주석 자리다. 함수 docstring 은 넣어도 된다)

```python
# [주석 1]
def _usage_error_cause(message: str) -> str:
    m = re.fullmatch(r"the following arguments are required: \{(?P<choices>[^{}]*)\}", message)
    if m:
        choices = m["choices"].replace(",", ", ")
        return f"명령을 입력하세요 (사용 가능: {choices})"
    m = re.fullmatch(r"the following arguments are required: (?P<options>--[a-z-]+(?:, --[a-z-]+)*)", message)
    if m:
        return f"필수 옵션이 없습니다: {m['options']}"
    # [주석 2]
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
    # [주석 3]
    return message


class _ArgumentParser(argparse.ArgumentParser):
    """argparse 사용법 오류도 [오류]/[힌트] 형식으로 출력한다."""

    def error(self, message: str) -> NoReturn:
        # [주석 4]
        print_error(_usage_error_cause(message), f"{self.prog} --help 로 사용법을 확인하세요")
        self.exit(2)
```

구현 주의 (모두 이전 단계 검사와 3.10 호환 때문이다)
- 정규식 6개는 위 문자열과 **글자 하나까지 같게** 쓰고, 순서도 위와 같게 한다. `m = re.fullmatch(...)` 는 한 줄에 쓴다(6.2 S6 이 패턴 목록과 순서를 비교한다).
- f-string 안의 따옴표는 바깥과 다른 종류를 쓴다(`f"…{m['options']}"`). 바깥과 같은 따옴표를 안에 쓰는 것은 3.12 이상 문법이라 3.10 에서 깨진다.
- 함수 안에서는 `re.fullmatch` 와 문자열 `.replace` 만 호출한다. argparse 의 어떤 속성도 바꾸지 않는다.
- `cli.py` 의 **주석·docstring 포함 어디에도** 다음 글자를 쓰지 않는다. 이전 단계 grep 검사가 파일 전체 글자를 본다. `@handle_errors`(3·4단계 S7 개수 12), `suggest_on_error`, `color=`(S3), `open(`(S8/S9), `.read()`, `readlines(`(S4). 제안 꼬리를 주석에서 설명할 때도 argparse 인자 이름은 쓰지 말고 "혹시 이것? 제안" 처럼 풀어 쓴다.
- 새 `print` 는 없다. cli.py 의 `print(` 호출은 14개 그대로다(6단계 S7). `sys` 는 import 하지 않는다.

### 3.4 Python 버전별 원문 차이 (3.10 ~ 3.15)

로컬에는 3.14 만 있어, 아래는 CPython `Lib/argparse.py` 소스와 변경 기록에 대한 지식, 그리고 에이전트 2 의 3.14 실측으로 정리했다. 6.2 U 절이 3.14 에서 실측한다. PATH 에 `python3.10`~`python3.13` 이 있으면 그 버전으로도 같은 검사를 돌린다(V).

| 원문 | 3.10 ~ 3.11 | 3.12 ~ 3.13 | 3.14 | 설계 대응 |
| --- | --- | --- | --- | --- |
| K3 `(choose from …)` 의 선택지 | `'add', 'list', …` (repr, 따옴표 있음) | 같은 것으로 안다 (패치 릴리스 변경 여부는 **확인 못 함**) | 에이전트 2 실측(3.14.7): 제안이 켜진 경우 **따옴표 있는 목록**. 제안이 꺼진 기본 상태의 표시는 이 설계서에서 단정하지 않는다(따옴표 없는 목록으로 바뀌었다는 변경 기록이 있으나 미확인) | 이 부분은 `[^()]*` 로 건너뛰기만 하고 읽지 않는다. 목록은 metavar `{…}` 에서 꺼낸다 → 따옴표 유무와 상관없이 같은 결과. X 절이 두 형식을 모두 시험한다 |
| K3 입력값 `'nosuchcmd'` | `%(value)r` → `'nosuchcmd'` | 같음 | 따옴표 유지 (실측) | `'[^']*'` 로 따옴표째 잡아 그대로 보여 준다. 따옴표 없이 나오는 버전이 있으면 정규식이 맞지 않아 원문 그대로다(안전장치) |
| K3 제안 꼬리 `, maybe you meant 'list'?` | 없음 | 없음 | argparse 인자로 켤 때만 붙는다(기본은 꺼짐). 이 앱은 그 인자를 쓰지 않는다(2단계 3.10 호환 규칙). 위치는 **값 바로 뒤, `(choose from …)` 앞** (에이전트 2 가 3.14 소스·실측 확인) | 3.15 부터 기본으로 켜진다고 알려져 있다(3.15 는 확인 못 함). **총괄 결정**: 정규식 3번이 이 꼬리를 선택적으로 허용해 K3 로 번역한다. 제안 내용은 한국어 문장에 넣지 않는다. 꼬리 모양이 이와 다르면(`?` 없음, 다른 문구, 다른 위치) 정규식이 맞지 않아 원문 그대로다(안전장치) |
| K1·K2 `the following arguments are required: …` | `self.error(...)` 직접 호출 | 내부에서 `ArgumentError(None, msg)` 로 바뀐 뒤 `str(err)` 로 `error()` 에 전달. 글자는 같음 | 같음 | 같은 정규식 |
| K1 이름 표시 `_get_action_name` | metavar 가 있으면 metavar | 같음 (3.12+ 는 choices 표시 분기가 추가됐지만 metavar 가 먼저) | 같음 | metavar `{…}` 를 지정했으므로 모든 버전 같음 |
| K6 `unrecognized arguments: …` | 최상위 `parse_args` 가 보고 | 같음 | 같음 | 같은 정규식. 힌트의 prog 는 최상위(`python -m budget_app --help`)이고 기존 그대로다 |
| K4 `expected one argument`, K5 `ignored explicit argument %r` | 같은 문장 | `consume_optional` 구조는 바뀌었지만 문장은 같음 | 같음 | 같은 정규식 |
| 번역 환경 | argparse 문장은 `gettext` 를 거친다. 파이썬은 번역 파일을 함께 배포하지 않으므로 보통 영어다 | | | 어떤 환경에 번역 파일이 있어 이미 번역된 문장이 오면, 정규식이 맞지 않아 그 문장이 그대로 나온다(안전장치) |
| `list --` 같은 `--` 구분자 처리 | 3.13 에서 동작이 바뀌었다(오류 여부가 버전마다 다를 수 있음) | | | 문장 번역과 무관하다. 오류가 나면 K6 로 번역된다. 동작 차이는 범위 밖이다 |

**안전장치 요약**: 맞추는 정규식은 모두 `fullmatch` 이고, 어느 하나도 맞지 않으면 `return message` 다. 따라서 어떤 버전·환경에서든 최악의 결과는 "지금처럼 영어 원인 문장 + 한국어 힌트 + 종료 코드 2" 다. 6.2 X 절이 모르는 모양 문장 16개(제안 꼬리 모양이 다른 3개 포함)로 이를 단위 시험한다.

### 3.5 학습자(비전공자)용 "왜" 주석 위치

짧은 한국어 주석 1~3줄로 아래 내용을 담는다(문장은 자유). 3.3 "구현 주의"의 금지 글자는 쓰지 않는다.

| 위치 | 담을 내용 |
| --- | --- |
| [주석 1] `def _usage_error_cause` 바로 위 | argparse 는 사용법 오류(없는 명령, 빠진 옵션 등)의 원인 문장을 영어로 만든다. 다른 오류와 똑같이 한국어로 보이도록, argparse 가 다 만든 영어 문장을 정해 둔 모양(정규식)과 맞춰 보고 한국어 문장으로 바꾼다. argparse 내부 함수를 바꿔 끼우거나 번역 파일을 쓰는 방법은 파이썬 버전마다 내부가 달라 깨지기 쉽고 준비할 것이 많아서 쓰지 않는다 |
| [주석 2] invalid choice 정규식 줄 바로 위 | 고를 수 있는 명령 목록은 문장 끝의 `(choose from …)` 이 아니라 앞쪽 `{add,list,…}` 에서 꺼낸다. 끝부분은 파이썬 버전·설정에 따라 따옴표 표시가 달라질 수 있어서, 앞쪽을 쓰면 어느 버전에서나 같은 문장이 나온다. 새 파이썬 버전이 값 뒤에 붙이는 "혹시 이것?" 제안은 건너뛰고 한국어 문장에는 넣지 않는다 |
| [주석 3] 마지막 `return message` 바로 위 | 모르는 모양의 문장(새 파이썬 버전에서 바뀐 문장 등)은 바꾸지 않고 그대로 돌려준다. 그래서 최악의 경우에도 영어 원인 문장이 그대로 나올 뿐, 오류 메시지가 사라지거나 프로그램이 멈추지 않는다 |
| [주석 4] `error` 안, `print_error(` 바로 위 | 바꾸는 것은 `[오류]` 줄의 원인 문장뿐이다. `[힌트]` 문장과 종료 코드 2 는 그대로다 |

### 3.6 `README.md` — 바꾸지 않는다

- `## 오류와 종료 코드` 절은 사용법 오류를 한국어로 설명하고(`2` 행: "없는 명령·옵션, 필수 옵션 누락, `-h`, 옵션 줄임말, `--data-dir` 를 명령 앞에 둠") 영어 원문을 인용하지 않는다. 이번 변경 후에도 내용이 맞다.
- `console` 예시 블록(4단계 N4 재생 검사 대상)에는 사용법 오류 예가 없다. 있는 `[오류]` 예 3개는 모두 종료 코드 1 오류(날짜·없는 id·사용 중 카테고리)라 출력이 바뀌지 않는다.
- 따라서 README 는 변경 금지 파일로 두고 6.2 S0 에서 기준선과 비교한다. 4단계 N(README 재생)은 R 절 회귀로 다시 확인된다.

## 4. 계층 규칙

1~6단계와 같다. 새 import 는 `cli.py` 의 표준 라이브러리 `re` 하나뿐이다.

```
__main__.py → cli.py → services.py → storage.py → models.py
                 └──→ decorators.py ──→ models.py
```

| 모듈 | import 가능한 `budget_app` 모듈 | 이번 단계 변화 |
| --- | --- | --- |
| `models.py` | 없음 | 없음 (변경 금지) |
| `storage.py` | `models` | 없음 (변경 금지) |
| `services.py` | `storage`, `models` | 없음 (변경 금지) |
| `decorators.py` | `models` | 없음 (변경 금지) |
| `cli.py` | `services`, `decorators`, `models` (`storage` 금지) | 표준 라이브러리 `re` 추가. `budget_app` import 는 그대로 |
| `__main__.py` | `cli` | 없음 (변경 금지) |

- 번역은 사용자에게 보여 줄 문장을 다루는 일이므로 CLI 계층에만 둔다. `decorators.py` 의 `print_error` 는 그대로 쓴다.
- 상대 import 금지. 표준 라이브러리 밖의 모듈 금지.

## 5. 예외/경계 상황

| 상황 | 처리 | 종료 코드 |
| --- | --- | --- |
| 3.2 K1~K6 | `[오류] <3.2 의 한국어 문장>` + 기존 `[힌트]` 줄(stderr). stdout 은 비어 있다. data 폴더를 만들지 않는다 | 2 |
| 필수 옵션 2개 누락 (`budget set`) | `필수 옵션이 없습니다: --month, --amount` (argparse 가 준 순서 그대로) | 2 |
| 남는 인자가 여러 개 (`list --bogus x`) | `알 수 없는 옵션 또는 값입니다: --bogus x` (공백으로 이어 그대로) | 2 |
| 명령 이름에 작은따옴표가 들어 있음 (예: `"it's"`) | argparse 가 큰따옴표로 감싸 표시하므로 K3 정규식이 맞지 않는다. 영어 원문 그대로 나온다(안전장치, 드문 경우) | 2 |
| 인자에 줄바꿈이 들어 있음 | 정규식(`.`)이 줄바꿈과 맞지 않아 원문 그대로 | 2 |
| 3.2 "나지 않는 오류" 또는 모르는 모양의 문장 | 원문 그대로 | 2 |
| 없는 명령 원문에 제안 꼬리 `, maybe you meant '…'?` 가 붙음 (3.15 기본 동작으로 알려짐) | **총괄 결정**: K3 와 같이 `알 수 없는 명령입니다: '<값>' (사용 가능: …)`. 제안 내용은 넣지 않는다 | 2 |
| 제안 꼬리의 모양이 다름 (`?` 없음, `did you mean` 등 다른 문구, `(choose from …)` 뒤에 붙음) | 정규식이 맞지 않아 원문 그대로(안전장치) | 2 |
| stdout 이 닫힌 채 실행 (`>&-`) 또는 닫힌 파이프 | stderr 출력은 그대로라 같은 한국어 문장이 나온다. 6단계 P3·Z 와 같다 | 2 |
| `--help` (모든 명령) | 변화 없음 (영어 도움말 본문 그대로) | 0 |
| 정상 실행, 종료 코드 1 오류(입력값 오류, 없는 id, 파일 문제, Ctrl+C, EOF 등) | 변화 없음 | 0 / 1 |
| 어떤 경우에도 | `Traceback` 없음. `_usage_error_cause` 는 예외를 내지 않는다 | — |

## 6. 완료 기준 (에이전트 3 검증 절차)

### 6.0 착수 전 기준선 사본 (총괄이 에이전트 2 착수 **전에** 1회 실행)

변경 전 코드와 결과를 글자 단위로 비교하려고, 지금의 `budget_app/` 과 `README.md` 를 스크래치 폴더에 복사해 둔다. 6.2 는 이 사본을 `STEP7_BASE` 로 받는다. 사본이 없거나 이미 바뀐 코드면 6.2 가 바로 `FAIL` 을 낸다.

```bash
B="/private/tmp/claude-501/-Users-khm04-codessey-pocket-money/855a1fd3-08d3-41b4-892b-10f168a6772d/scratchpad/step7-base"   # 다른 스크래치 경로도 됨
rm -rf "$B" && mkdir -p "$B" \
  && cp -R "/Users/khm04/codessey/pocket money/budget_app" "/Users/khm04/codessey/pocket money/README.md" "$B/" \
  && find "$B" -name __pycache__ -prune -exec rm -rf {} + \
  && ls "$B" "$B/budget_app"
```

### 6.1 이전 단계 검사에 주는 영향 (전수 조사)

**영어 원문을 기대하는 검사: 0건.** 1~6단계 설계서의 bash 코드 블록 전체에서 `unrecognized`, `are required`, `invalid choice`, `expected one argument`, `choose from`, `ignored explicit` 를 찾았다. 나온 곳은 2단계 3.4 아래 설명 문장(169행)과 3단계 3.4 설명 문장(222행)의 `invalid choice` 뿐이다. 둘 다 스크립트가 아니다. 그래서 **치환할 기대값이 없다.** 6.2 R0 이 이 사실을 실행할 때마다 다시 확인한다. 나중에 누가 영어 기대를 넣으면 R0 이 FAIL 을 낸다.

사용법 오류(종료 코드 2)와 관련된 이전 검사와 7단계 후 결과

| 단계 / 위치 | 검사 내용 | 7단계 후 |
| --- | --- | --- |
| 2단계 B (3단계 R 이 `import export` 만 남김) | `import`, `export` → 2, `[오류]`/`[힌트]` 각 1 | K2 `--from`/`--out` → 통과 |
| 2단계 B | 명령 없음, `--data-dir DD list`, `category --data-dir DD` → 2, data 폴더 생성 없음 | K1 / K3 / K3 → 통과 |
| 2단계 F·G | `update --amount 100`, `delete --data-dir DD` → 2, 개수 1 | K2 → 통과 |
| 3단계 B | `-h`, 줄임말, 없는 옵션, `summary` 등 → 2, 개수 1. `err_has "--month"`, `err_no "budget_command"` | K2 문장에 `--month` 가 들어 있고, 내부 이름은 나오지 않음 → 통과 |
| 4단계 B | `import`·`export` 누락 → `err_has "--from"`, `err_has "--out"`, 나머지 2 + 개수 1 | K2 문장에 옵션 이름이 들어 있음 → 통과 |
| 6단계 P3 | 없는 옵션·`-h`·명령 없음: 2, 개수 1, 닫힌 stdout 일 때와 stderr 동일 | stderr 는 번역 후에도 두 실행이 같음 → 통과 |
| 6단계 Z | `>&-` 로 없는 옵션: 2, 개수 1 | 통과 |
| 4단계 N | README 재생(사용법 오류 예 없음), 옵션 이름 | README 변경 없음 → 통과 |

이번 코드가 지켜야 하는 이전 정적 검사 (회귀로 다시 실행됨)

| 검사 | 지키는 방법 |
| --- | --- |
| SHA-256 변경 금지 | **cli.py 는 어느 단계 S0 해시에도 없다.** 3단계 S0(models·storage·decorators·`__main__`·`__init__`, 4단계 R 이 storage·decorators 줄 삭제), 4·5·6단계 S0(models·`__main__`·`__init__`). 이번에 바꾸지 않는 파일들이므로 해시 치환이 필요 없다 |
| 6단계 S7 | `main` 본문·데코레이터, decorators 에서 import 하는 이름 4개, `print` 14개, 파이프 처리 이름 없음, `정렬용 임시 폴더` 주석 → 모두 그대로 |
| 3·4단계 S7 | `grep -c "@handle_errors"` 12 → 주석에 이 글자를 쓰지 않음 |
| 3~6단계 S3 | `suggest_on_error\|color=` grep → 주석에 쓰지 않음 |
| 3단계 S8, 5단계 S6 | cli.py 에 `sorted`·`.sort`·`nlargest`·`nsmallest` 금지 → `.replace` 만 씀 |
| 4·5단계 `open(` grep, S4 `.read()` grep | 쓰지 않음 |
| 4·5·6단계 S4/S5 계층·표준 라이브러리 | `re` 는 표준 라이브러리 |

**회귀 실행 방식**: 6단계 6.2 스크립트를 꺼내 **임시 폴더(`W`) 줄 하나만** 이 스크립트의 `$W` 아래로 바꿔 실행한다(6단계가 5단계를 다룬 방식과 같다). 6단계 스크립트가 R 절에서 5 → 4 → 3 → 1·2단계를 차례로 다시 실행하므로 1~6단계 전체가 다시 실행된다. 기대값 치환과 해시 치환은 없다.

**7단계 검사 항목**

| # | 검사 | 기대 |
| --- | --- | --- |
| 기준선 | `STEP7_BASE` 폴더에 `budget_app/cli.py`, `README.md` 있음 | 있음 |
| S0 | models·`__main__`·`__init__` SHA-256(6단계와 같음). `budget_app/*.py` 파일 목록이 기준선과 같고, cli.py 외 모든 .py 와 README.md 가 기준선과 바이트 단위로 같음. 기준선 cli.py 는 변경 전 코드이고, 현재 cli.py 는 기준선과 다름 | 위반 없음 |
| S1~S5 | 파일 7개, 3.10 문법, 3.11+ API grep, 계층·표준 라이브러리만·`signal` 금지, 타입 힌트 | 위반 없음 |
| S6 | cli.py 구조(AST). ① `import re` 가 `import argparse` 바로 다음에 1개. ② `_usage_error_cause` 위치(`class _ArgumentParser` 바로 앞)·시그니처·정규식 6개의 문자열과 순서(3.3 표)·`re.fullmatch(…, message)` 형태·함수 안 호출은 `re.fullmatch`·`.replace` 뿐·마지막 문장 `return message`. ③ `_ArgumentParser` 메서드는 `error` 하나이고 본문은 `print_error(_usage_error_cause(message), <기존 힌트>)`, `self.exit(2)`. `_usage_error_cause` 사용은 이 1곳. ④ ①②의 추가분을 빼고 ③의 번역 호출을 걷어 내면, 기준선 cli.py 와 **AST 가 완전히 같음**(도움말·명령·다른 출력 불변). ⑤ 3.5 주석 4곳 | 위반 없음 |
| X | 같은 프로세스 단위 시험. 번역 15건(선택지 따옴표 있는 형식·없는 형식, 제안 꼬리가 붙은 형식 포함)이 기대 문자열과 같음. 모르는 모양 16건(제안 꼬리 모양이 다른 3건 포함)은 원문 그대로. `build_parser().error(임의 문장)` 이 stderr 에 원문 + 기존 힌트를 쓰고 `SystemExit(2)` | `CAUSE_UNIT_OK` |
| U | 3.2 의 25가지 사용법 오류를 변경 전(기준선)·변경 후 코드로 각각 실행한다. ① 둘 다 종료 코드 2, stdout 빈 문자열, stderr 2줄. ② 변경 전 첫 줄에 해당 영어 원문 핵심 구절이 있음(설계 전제 확인). ③ 변경 후 stderr 가 정확히 `[오류] <기대 한국어>\n<변경 전 [힌트] 줄>\n`. ④ 변경 후 `[오류]` 줄에 영어 원문 단어 없음. ⑤ data 폴더 등 아무 파일도 생기지 않음 | `USAGE_KO_OK` |
| V | PATH 에 `python3.10`~`python3.13` 이 있으면 그 버전으로 U 를 반복(없으면 "건너뜀" 안내 1줄씩) | U 와 같음 |
| H | `--help` 15가지(최상위·모든 명령·하위 명령)의 stdout 이 변경 전과 글자 단위로 같고, 종료 코드 0, stderr 빈 문자열, `show this help message and exit` 그대로 | `HELP_SAME_OK` |
| N | 정상 실행 16개와 종료 코드 1 오류 16개를 변경 전·후 코드로 같은 순서로 실행. 종료 코드·stdout·stderr 가 모두 같고, 마지막 저장 파일(jsonl 3개, export CSV)도 같음 | `NORMAL_SAME_OK` |
| R0 | 1~6단계 설계서 bash 블록에 영어 argparse 원문 기대가 없음(6.1 조사 결과 재확인) | `REGRESSION_TEXT_OK` |
| R | 1~6단계 회귀 (위 방식) | `STEP6_ALL_OK` 포함, `FAIL` 없음 |
| 마무리 | `$W/systmp` 에 `budget_app_search_*` 잔존 없음. `./data`·`__pycache__`·루트의 예상 밖 파일 없음 | `STEP7_ALL_OK` |

**실행 방법**
- 6.0 기준선이 있어야 한다. 6.2 코드 블록 내용을 스크래치패드에 파일로 저장하고 `STEP7_BASE=<6.0 의 B 경로> bash <파일>` 로 실행한다(macOS 기본 bash 3.2 에서 동작). 실행이 끝나면 저장한 스크립트 파일을 지운다. 기준선 폴더는 7단계 검토가 끝난 뒤 지운다.
- **백그라운드(`&`)로 실행하지 않는다.** 회귀(2단계 CTRL_C, 4단계 SIGNAL, 5단계 B절)가 Ctrl+C 신호를 보낸다.
- `python` 이 없는 환경이므로 첫머리에서 `python → python3` 링크를 만들어 PATH 앞에 둔다. 모든 임시 파일은 `W="$(mktemp -d)"` 아래에 만들고 `trap` 으로 지운다. `TMPDIR` 은 `$W/systmp` 로 바꾼다.
- 예상 실행 시간은 4~5분이다(6단계 회귀 3~4분 + 7단계 자체 실행 약 150회).

**성공 기준**: `FAIL` 로 시작하는 줄이 하나도 없어야 한다. `CAUSE_UNIT_OK`, `USAGE_KO_OK`, `HELP_SAME_OK`, `NORMAL_SAME_OK`, `REGRESSION_TEXT_OK`, 그리고 마지막 줄 `STEP7_ALL_OK` 가 나와야 한다. U 절의 `U <파이썬 버전>: 25건` 줄과 V 의 "건너뜀" 줄, R 절 뒤 5단계 M절 측정값 6줄은 보고용이다. 에이전트 3 은 이 줄들을 보고서에 그대로 옮긴다.

### 6.2 검증 스크립트

```bash
# 7단계 검증 스크립트. 실행: STEP7_BASE=<기준선 폴더> bash <이 파일>   (백그라운드 & 로 실행하지 말 것)
cd "/Users/khm04/codessey/pocket money" || exit 1
export PYTHONDONTWRITEBYTECODE=1
export ROOT="$PWD"
W="$(mktemp -d)"; export W                      # 이 스크립트의 임시 파일은 전부 여기 아래
cleanup() { chmod -R u+rwx "$W" 2>/dev/null; rm -rf "$W"; }
trap cleanup EXIT
mkdir "$W/bin" && ln -s "$(command -v python3)" "$W/bin/python" || exit 1   # python 이 없어서 python3 로 연결
export PATH="$W/bin:$PATH"
python --version || exit 1
mkdir "$W/systmp" && export TMPDIR="$W/systmp" || exit 1   # search 정렬용 "시스템 임시 폴더"
FAIL=0
fail() { echo "FAIL $*"; FAIL=1; }
# 기준선: 착수 전에 복사해 둔 변경 전 budget_app/ 과 README.md (설계서 6.0)
BASE="$(cd "${STEP7_BASE:-/nonexistent}" 2>/dev/null && pwd)"; export BASE
if [ -z "$BASE" ] || [ ! -f "$BASE/budget_app/cli.py" ] || [ ! -f "$BASE/README.md" ]; then
  echo "FAIL 기준선 폴더가 없음: STEP7_BASE 에 변경 전 사본(budget_app/, README.md) 경로를 주세요 (설계서 6.0)"; exit 1
fi

# ======================= S. 정적 검사 =======================
# S0 변경 금지 파일 (6단계와 같은 해시) + 기준선 대비 변경 범위
shasum -a 256 -c - >/dev/null <<'SUMS' || fail "S0 변경 금지 파일이 바뀜 (models/__main__/__init__)"
08b6a94954a6ca8d6619a69a026ac2fd2d028844e17a8c55cb8d6f02faca513f  budget_app/models.py
6958ee4078ab3cdd31564e022cd9fccc673a5f2f8509c241b4771646a4e72753  budget_app/__main__.py
0cb00a1323d1945aa0e71486ffebaf612fde2efe434f13182806c00515b3605c  budget_app/__init__.py
SUMS
python3 - <<'PY' || fail "S0 기준선 대비 변경 범위 (cli.py 만 바꿈)"
import os, sys
B = os.environ["BASE"]
def data(p):
    with open(p, "rb") as f:
        return f.read()
bad = []
cur = sorted(f for f in os.listdir("budget_app") if f.endswith(".py"))
old = sorted(f for f in os.listdir(os.path.join(B, "budget_app")) if f.endswith(".py"))
if cur != old:
    bad.append(f"budget_app 의 .py 파일 목록이 기준선과 다름: {cur} != {old}")
for name in [os.path.join("budget_app", f) for f in cur if f != "cli.py" and f in old] + ["README.md"]:
    if data(name) != data(os.path.join(B, name)):
        bad.append(f"{name} 이 기준선과 다름 (이번 단계 변경 금지)")
base_cli = data(os.path.join(B, "budget_app", "cli.py"))
if b"_usage_error_cause" in base_cli or b"\nimport re\n" in base_cli:
    bad.append("기준선 cli.py 가 이미 바뀐 코드임 (6.0 기준선은 에이전트 2 착수 전에 만들어야 함)")
if data(os.path.join("budget_app", "cli.py")) == base_cli:
    bad.append("cli.py 가 기준선과 같음 (아직 구현되지 않음)")
print(*bad, sep="\n") if bad else None
sys.exit(1 if bad else 0)
PY
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
# S4 계층 규칙 + 표준 라이브러리만 + signal 미사용
python3 - <<'PY' || fail "S4 계층 규칙 / 표준 라이브러리만 / signal 금지"
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
            if top == "signal":
                bad.append((m, "signal 모듈 사용 금지"))
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
# S6 cli.py 구조: 바뀐 곳은 import re / _usage_error_cause / error 본문 1곳뿐
python3 - <<'PY' || fail "S6 cli.py 구조 (설계서 3.3)"
import ast, os, sys
U = ast.unparse
B = os.environ["BASE"]
src = open("budget_app/cli.py", encoding="utf-8").read()
new = ast.parse(src)
old = ast.parse(open(os.path.join(B, "budget_app", "cli.py"), encoding="utf-8").read())
bad = []
WANT_PATTERNS = [
    r"the following arguments are required: \{(?P<choices>[^{}]*)\}",
    r"the following arguments are required: (?P<options>--[a-z-]+(?:, --[a-z-]+)*)",
    r"argument \{(?P<choices>[^{}]*)\}: invalid choice: (?P<value>'[^']*')(?:, maybe you meant '[^']*'\?)? \(choose from [^()]*\)",
    r"argument (?P<option>--[a-z-]+): expected one argument",
    r"argument (?P<option>--[a-z-]+): ignored explicit argument (?P<value>.*)",
    r"unrecognized arguments: (?P<args>.+)",
]
def strip_doc(b):
    if b and isinstance(b[0], ast.Expr) and isinstance(b[0].value, ast.Constant) and isinstance(b[0].value.value, str):
        return b[1:]
    return b
def is_import_re(n):
    return isinstance(n, ast.Import) and [(a.name, a.asname) for a in n.names] == [("re", None)]
def is_cause_fn(n):
    return isinstance(n, ast.FunctionDef) and n.name == "_usage_error_cause"
# ① import re
idx = [i for i, n in enumerate(new.body) if is_import_re(n)]
if len(idx) != 1 or idx[0] == 0 or U(new.body[idx[0] - 1]) != "import argparse":
    bad.append("import re 는 모듈 최상위의 import argparse 바로 다음에 1개")
# ② _usage_error_cause
fi = [i for i, n in enumerate(new.body) if is_cause_fn(n)]
if len(fi) != 1:
    bad.append("_usage_error_cause 가 모듈 최상위에 1개가 아님")
else:
    f = new.body[fi[0]]
    nxt = new.body[fi[0] + 1] if fi[0] + 1 < len(new.body) else None
    if not (isinstance(nxt, ast.ClassDef) and nxt.name == "_ArgumentParser"):
        bad.append("_usage_error_cause 는 class _ArgumentParser 바로 앞에 둠")
    a = f.args
    if not ([x.arg for x in a.args] == ["message"] and a.args[0].annotation is not None and U(a.args[0].annotation) == "str"
            and f.returns is not None and U(f.returns) == "str" and not a.posonlyargs and not a.kwonlyargs
            and a.vararg is None and a.kwarg is None and not a.defaults and not f.decorator_list):
        bad.append("시그니처는 def _usage_error_cause(message: str) -> str")
    calls = [c for c in ast.walk(f) if isinstance(c, ast.Call)]
    fm = [c for c in calls if U(c.func) == "re.fullmatch"]
    pats = [c.args[0].value if c.args and isinstance(c.args[0], ast.Constant) else None for c in fm]
    if pats != WANT_PATTERNS:
        bad.append(f"정규식 6개의 문자열·순서가 설계서 3.3 과 다름: {pats}")
    if any(len(c.args) != 2 or U(c.args[1]) != "message" or c.keywords for c in fm):
        bad.append("re.fullmatch(<패턴>, message) 형태가 아님")
    others = [U(c.func) for c in calls if c not in fm and not (isinstance(c.func, ast.Attribute) and c.func.attr == "replace")]
    if others:
        bad.append(f"_usage_error_cause 안에서 re.fullmatch·replace 외 호출: {others}")
    if any(isinstance(n, ast.Attribute) and isinstance(n.ctx, ast.Store) for n in ast.walk(f)):
        bad.append("_usage_error_cause 안에서 속성에 값을 넣음 (argparse 덮어쓰기 금지)")
    b = strip_doc(f.body)
    if not b or U(b[-1]) != "return message":
        bad.append("마지막 문장은 return message (모르는 모양은 원문 그대로)")
nuse = sum(1 for n in ast.walk(new) if isinstance(n, ast.Name) and n.id == "_usage_error_cause")
if nuse != 1:
    bad.append(f"_usage_error_cause 사용 {nuse}곳 (error 안 1곳)")
# ③ error 본문
cls = [n for n in new.body if isinstance(n, ast.ClassDef) and n.name == "_ArgumentParser"]
meths = [m for m in cls[0].body if isinstance(m, ast.FunctionDef)] if len(cls) == 1 else []
eb = strip_doc(meths[0].body) if [m.name for m in meths] == ["error"] else []
call = eb[0].value if len(eb) == 2 and isinstance(eb[0], ast.Expr) and isinstance(eb[0].value, ast.Call) else None
inner = call.args[0] if call is not None and len(call.args) == 2 and isinstance(call.args[0], ast.Call) else None
if not (call is not None and U(call.func) == "print_error" and inner is not None and U(inner) == "_usage_error_cause(message)"
        and U(eb[1]) == "self.exit(2)"):
    bad.append("_ArgumentParser 는 error 하나, 본문은 print_error(_usage_error_cause(message), <기존 힌트>) 와 self.exit(2)")
else:
    call.args[0] = inner.args[0]                  # 번역 호출을 걷어 내 변경 전 모양으로 되돌린다
# ④ 나머지는 기준선과 AST 가 완전히 같아야 함
new.body = [n for n in new.body if not is_import_re(n) and not is_cause_fn(n)]
if ast.dump(new) != ast.dump(old):
    bad.append("cli.py 에서 import re / _usage_error_cause / error 본문 1곳 외의 코드·docstring 이 바뀜 (도움말·명령·출력 불변)")
# ⑤ "왜" 주석 4곳 (설계서 3.5)
L = src.split("\n")
def comment_above(i, n=1):
    return any(L[j].strip().startswith("#") for j in range(max(0, i - n), i))
d = [i for i, l in enumerate(L) if l.startswith("def _usage_error_cause(")]
r = [i for i, l in enumerate(L) if l == "    return message"]
c = [i for i, l in enumerate(L) if "invalid choice" in l and "fullmatch" in l]
p = [i for i, l in enumerate(L) if l.strip().startswith("print_error(_usage_error_cause(")]
for name, hits in (("[주석 1] def 위", d), ("[주석 3] return message 위", r), ("[주석 2] invalid choice 정규식 위", c), ("[주석 4] error 안", p)):
    if len(hits) != 1 or not comment_above(hits[0], 2 if name.startswith("[주석 2]") else 1):
        bad.append(f"{name} 주석이 없음")
print(*bad, sep="\n") if bad else None
sys.exit(1 if bad else 0)
PY

# ======================= X. 번역 함수 단위 시험 (같은 프로세스) =======================
python - <<'PY' || FAIL=1
import contextlib, io, sys
from budget_app.cli import _usage_error_cause, build_parser
TOPM = "{add,list,search,summary,budget,update,delete,category,import,export}"
TOP = "add, list, search, summary, budget, update, delete, category, import, export"
QTOP = "'add', 'list', 'search', 'summary', 'budget', 'update', 'delete', 'category', 'import', 'export'"
ok = True
def need(cond, msg):
    global ok
    if not cond:
        print("FAIL", msg); ok = False
TRANSLATE = [
    (f"the following arguments are required: {TOPM}", f"명령을 입력하세요 (사용 가능: {TOP})"),
    ("the following arguments are required: {add,list,remove}", "명령을 입력하세요 (사용 가능: add, list, remove)"),
    ("the following arguments are required: {set}", "명령을 입력하세요 (사용 가능: set)"),
    ("the following arguments are required: --month", "필수 옵션이 없습니다: --month"),
    ("the following arguments are required: --month, --amount", "필수 옵션이 없습니다: --month, --amount"),
    (f"argument {TOPM}: invalid choice: 'nosuchcmd' (choose from {QTOP})", f"알 수 없는 명령입니다: 'nosuchcmd' (사용 가능: {TOP})"),  # 따옴표 있는 목록
    (f"argument {TOPM}: invalid choice: 'nosuchcmd' (choose from {TOP})", f"알 수 없는 명령입니다: 'nosuchcmd' (사용 가능: {TOP})"),   # 따옴표 없는 목록
    (f"argument {TOPM}: invalid choice: 'lst', maybe you meant 'list'? (choose from {QTOP})", f"알 수 없는 명령입니다: 'lst' (사용 가능: {TOP})"),  # 제안 꼬리 (3.14.7 실측 형식, 총괄 결정)
    (f"argument {TOPM}: invalid choice: 'lst', maybe you meant 'list'? (choose from {TOP})", f"알 수 없는 명령입니다: 'lst' (사용 가능: {TOP})"),   # 제안 꼬리 + 따옴표 없는 목록
    ("argument {set}: invalid choice: '없는명령' (choose from 'set')", "알 수 없는 명령입니다: '없는명령' (사용 가능: set)"),
    ("argument --limit: expected one argument", "--limit 옵션에 값이 필요합니다"),
    ("argument --data-dir: expected one argument", "--data-dir 옵션에 값이 필요합니다"),
    ("argument --help: ignored explicit argument 'x'", "--help 옵션에는 값을 붙일 수 없습니다: 'x'"),
    ("unrecognized arguments: --bogus", "알 수 없는 옵션 또는 값입니다: --bogus"),
    ("unrecognized arguments: --bogus x -h", "알 수 없는 옵션 또는 값입니다: --bogus x -h"),
]
KEEP = [                                          # 모르는 모양 → 원문 그대로 (안전장치)
    "임의의 문장입니다",
    "something unexpected happened",
    "",
    "the following arguments are required: month",
    "the following arguments are required: {add,list}, --month",
    "argument --limit: expected at most one argument",
    "argument --limit: expected one argument.",
    f"argument {TOPM}: invalid choice: 'lst', maybe you meant 'list' (choose from {TOP})",     # 제안 꼬리에 ? 가 빠짐
    f"argument {TOPM}: invalid choice: 'lst', did you mean 'list'? (choose from {TOP})",      # 다른 제안 문구
    f"argument {TOPM}: invalid choice: 'lst' (choose from {TOP}), maybe you meant 'list'?",   # 꼬리가 (choose from …) 뒤
    "argument {set}: invalid choice: \"it's\" (choose from set)",
    "argument --type: invalid choice: 'x' (choose from 'income', 'expense')",
    "unrecognized arguments: ",
    "unrecognized arguments: a\nb",
    "ambiguous option: --li could match --limit, --list",
    "argument --month: not allowed with argument --from",
]
for src, want in TRANSLATE:
    got = _usage_error_cause(src)
    need(got == want, f"X 번역: {src!r} → {got!r} (기대 {want!r})")
for src in KEEP:
    got = _usage_error_cause(src)
    need(got == src, f"X 원문 유지: {src!r} → {got!r}")
HINT = "[힌트] python -m budget_app --help 로 사용법을 확인하세요\n"
for msg, cause in (("임의 문장 abc (모르는 모양)", "임의 문장 abc (모르는 모양)"),
                   ("the following arguments are required: --month", "필수 옵션이 없습니다: --month")):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        try:
            build_parser().error(msg)
            code = "반환됨"
        except SystemExit as e:
            code = e.code
    need(code == 2 and out.getvalue() == "" and err.getvalue() == f"[오류] {cause}\n{HINT}",
         f"X error({msg!r}): code={code!r} out={out.getvalue()!r} err={err.getvalue()!r}")
print("CAUSE_UNIT_OK" if ok else "CAUSE_UNIT_FAIL")
sys.exit(0 if ok else 1)
PY

# ======================= U / V. 사용법 오류 25가지: 변경 전·후 비교 (버전별) =======================
PYS="$(command -v python3)"
for v in 3.10 3.11 3.12 3.13; do
  p="$(command -v "python$v" 2>/dev/null)"
  if [ -n "$p" ]; then PYS="$PYS $p"; else echo "  V python$v 없음 (이 버전 실측은 건너뜀)"; fi
done
python - $PYS <<'PY' || FAIL=1
import os, subprocess, sys
ROOT, B, W = os.environ["ROOT"], os.environ["BASE"], os.environ["W"]
TOP = "add, list, search, summary, budget, update, delete, category, import, export"
CAT, BUD = "add, list, remove", "set"
REQ, CHO, EXP, IGN, UNR = ("the following arguments are required", "invalid choice", "expected one argument",
                           "ignored explicit argument", "unrecognized arguments")
CASES = [
    ("U1 명령 없음", [], f"명령을 입력하세요 (사용 가능: {TOP})", REQ),
    ("U2 최상위 -h", ["-h"], f"명령을 입력하세요 (사용 가능: {TOP})", REQ),
    ("U3 category 만", ["category"], f"명령을 입력하세요 (사용 가능: {CAT})", REQ),
    ("U4 budget 만", ["budget"], f"명령을 입력하세요 (사용 가능: {BUD})", REQ),
    ("U5 없는 명령", ["nosuchcmd"], f"알 수 없는 명령입니다: 'nosuchcmd' (사용 가능: {TOP})", CHO),
    ("U6 category 없는 하위 명령", ["category", "nosuch"], f"알 수 없는 명령입니다: 'nosuch' (사용 가능: {CAT})", CHO),
    ("U7 budget 없는 하위 명령", ["budget", "get"], f"알 수 없는 명령입니다: 'get' (사용 가능: {BUD})", CHO),
    ("U8 --data-dir 를 명령 앞에", ["--data-dir", "X", "list"], f"알 수 없는 명령입니다: 'X' (사용 가능: {TOP})", CHO),
    ("U9 summary --month 누락", ["summary"], "필수 옵션이 없습니다: --month", REQ),
    ("U10 budget set 둘 다 누락", ["budget", "set"], "필수 옵션이 없습니다: --month, --amount", REQ),
    ("U11 update --id 누락", ["update", "--memo", "x"], "필수 옵션이 없습니다: --id", REQ),
    ("U12 delete --id 누락", ["delete"], "필수 옵션이 없습니다: --id", REQ),
    ("U13 import --from 누락", ["import"], "필수 옵션이 없습니다: --from", REQ),
    ("U14 export --out 누락", ["export", "--month", "2024-01"], "필수 옵션이 없습니다: --out", REQ),
    ("U15 없는 옵션", ["list", "--bogus"], "알 수 없는 옵션 또는 값입니다: --bogus", UNR),
    ("U16 하위 명령 뒤 -h", ["list", "-h"], "알 수 없는 옵션 또는 값입니다: -h", UNR),
    ("U17 옵션 줄임말", ["search", "--cat=food"], "알 수 없는 옵션 또는 값입니다: --cat=food", UNR),
    ("U18 남는 값", ["list", "extra"], "알 수 없는 옵션 또는 값입니다: extra", UNR),
    ("U19 --limit 값 없음", ["list", "--limit"], "--limit 옵션에 값이 필요합니다", EXP),
    ("U20 --data-dir 값 없음", ["list", "--data-dir"], "--data-dir 옵션에 값이 필요합니다", EXP),
    ("U21 --month 값 없음", ["summary", "--month"], "--month 옵션에 값이 필요합니다", EXP),
    ("U22 --memo 뒤에 바로 옵션", ["update", "--id", "TX-000001", "--memo", "--tags", "a"], "--memo 옵션에 값이 필요합니다", EXP),
    ("U23 --from 값 없음", ["search", "--from"], "--from 옵션에 값이 필요합니다", EXP),
    ("U24 --help=값", ["--help=x"], "--help 옵션에는 값을 붙일 수 없습니다: 'x'", IGN),
    ("U25 하위 명령 --help=값", ["category", "list", "--help=x"], "--help 옵션에는 값을 붙일 수 없습니다: 'x'", IGN),
]
EN_WORDS = ("the following", "required", "unrecognized", "argument", "invalid", "choice", "choose", "expected", "ignored",
            "explicit", "maybe you meant")
ok = True
def need(cond, msg):
    global ok
    if not cond:
        print("FAIL", msg); ok = False
def run(py, code_root, cwd, argv):
    r = subprocess.run([py, "-m", "budget_app", *argv], cwd=cwd, input="", capture_output=True, text=True, timeout=60,
                       env={**os.environ, "PYTHONPATH": code_root})
    return r.returncode, r.stdout, r.stderr
for i, py in enumerate(sys.argv[1:]):
    ver = subprocess.run([py, "--version"], capture_output=True, text=True).stdout.strip()
    co, cn = os.path.join(W, "u", str(i), "old"), os.path.join(W, "u", str(i), "new")   # 빈 작업 폴더 (cwd)
    os.makedirs(co); os.makedirs(cn)
    n = 0
    for label, argv, ko, key in CASES:
        rc0, out0, err0 = run(py, B, co, argv)
        rc1, out1, err1 = run(py, ROOT, cn, argv)
        l0, l1 = err0.splitlines(), err1.splitlines()
        pre = (rc0 == 2 and out0 == "" and len(l0) == 2 and l0[0].startswith("[오류] ") and key in l0[0]
               and l0[1].startswith("[힌트] "))
        need(pre, f"U {ver} {label}: 변경 전 출력이 설계 전제와 다름 rc={rc0} err={err0!r}")
        need(rc1 == 2 and out1 == "", f"U {ver} {label}: 종료 코드 {rc1} (기대 2) / stdout={out1!r}")
        if pre:
            need(err1 == f"[오류] {ko}\n{l0[1]}\n", f"U {ver} {label}: stderr={err1!r} (기대 {('[오류] ' + ko)!r} + 변경 전 힌트 {l0[1]!r})")
        first = l1[0] if l1 else ""
        hit = [w for w in EN_WORDS if w in first]
        need(not hit, f"U {ver} {label}: [오류] 줄에 영어 원문 단어 {hit}: {first!r}")
        need("Traceback" not in err0 + err1, f"U {ver} {label}: Traceback")
        n += 1
    need(os.listdir(co) == [] and os.listdir(cn) == [], f"U {ver}: 사용법 오류에서 파일·폴더가 생김 {os.listdir(co)} {os.listdir(cn)}")
    print(f"  U {ver}: {n}건")
print("USAGE_KO_OK" if ok else "USAGE_KO_FAIL")
sys.exit(0 if ok else 1)
PY

# ======================= H. --help 출력이 변경 전과 같음 =======================
python - <<'PY' || FAIL=1
import os, subprocess, sys
ROOT, B, W = os.environ["ROOT"], os.environ["BASE"], os.environ["W"]
ok = True
def need(cond, msg):
    global ok
    if not cond:
        print("FAIL", msg); ok = False
def run(code_root, cwd, argv):
    r = subprocess.run([sys.executable, "-m", "budget_app", *argv], cwd=cwd, input="", capture_output=True, text=True,
                       timeout=60, env={**os.environ, "PYTHONPATH": code_root})
    return r.returncode, r.stdout, r.stderr
co, cn = os.path.join(W, "h", "old"), os.path.join(W, "h", "new")
os.makedirs(co); os.makedirs(cn)
HELP = [[], ["add"], ["list"], ["search"], ["summary"], ["budget"], ["budget", "set"], ["update"], ["delete"],
        ["category"], ["category", "add"], ["category", "list"], ["category", "remove"], ["import"], ["export"]]
for c in HELP:
    r0, r1 = run(B, co, c + ["--help"]), run(ROOT, cn, c + ["--help"])
    need(r0[0] == 0 and r0[2] == "" and r1 == r0, f"H {c} --help: 변경 전과 다름\n  전: {r0!r}\n  후: {r1!r}")
    need(r1[1].startswith("usage: python -m budget_app") and "show this help message and exit" in r1[1],
         f"H {c} --help: 도움말 본문이 바뀜")
need(os.listdir(co) == [] and os.listdir(cn) == [], "H --help 가 파일·폴더를 만듦")
print("HELP_SAME_OK" if ok else "HELP_SAME_FAIL")
sys.exit(0 if ok else 1)
PY

# ======================= N. 정상 실행·다른 오류(종료 코드 1)가 변경 전과 같음 =======================
python - <<'PY' || FAIL=1
import os, subprocess, sys
ROOT, B, W = os.environ["ROOT"], os.environ["BASE"], os.environ["W"]
ok = True
def need(cond, msg):
    global ok
    if not cond:
        print("FAIL", msg); ok = False
def run(code_root, cwd, argv, stdin):
    r = subprocess.run([sys.executable, "-m", "budget_app", *argv], cwd=cwd, input=stdin, capture_output=True, text=True,
                       timeout=60, env={**os.environ, "PYTHONPATH": code_root})
    return r.returncode, r.stdout, r.stderr
co, cn = os.path.join(W, "n", "old"), os.path.join(W, "n", "new")
for c in (co, cn):
    os.makedirs(c)
    with open(os.path.join(c, "afile"), "w", encoding="utf-8"):
        pass                                      # --data-dir 에 파일을 준 경우용
D = ["--data-dir", "d"]                           # 작업 폴더 기준 상대 경로 → 출력 문구가 양쪽에서 같음
STEPS = [
    (["category", "list", *D], "", 0),
    (["category", "add", *D], "hobby\n", 0),
    (["add", *D], "2024-13-40\n2024-01-15\nexpense\nfood\n15000\n점심\nmeal\n", 0),
    (["add", *D], "2024-01-14\nincome\netc\n3000000\n월급\n\n", 0),
    (["list", *D], "", 0),
    (["list", "--limit", "1", *D], "", 0),
    (["search", "--category", "food", *D], "", 0),
    (["search", "--q", "점심", "--tag", "meal", *D], "", 0),
    (["summary", "--month", "2024-01", *D], "", 0),
    (["budget", "set", "--month", "2024-01", "--amount", "10000", *D], "", 0),
    (["summary", "--month", "2024-01", "--top", "1", *D], "", 0),
    (["update", "--id", "TX-000001", "--memo", "저녁", *D], "", 0),
    (["export", "--out", "e.csv", "--month", "2024-01", *D], "", 0),
    (["import", "--from", "e.csv", *D], "", 0),
    (["delete", "--id", "TX-000002", *D], "", 0),
    (["category", "remove", *D], "hobby\n", 0),
    (["search", *D], "", 1),
    (["list", "--limit", "0", *D], "", 1),
    (["summary", "--month", "2024-13", *D], "", 1),
    (["summary", "--month", "2024-01", "--top", "0", *D], "", 1),
    (["budget", "set", "--month", "2024-01", "--amount", "0", *D], "", 1),
    (["update", "--id", "TX-999999", "--memo", "x", *D], "", 1),
    (["update", "--id", "TX-000001", *D], "", 1),
    (["delete", "--id", "TX-999999", *D], "", 1),
    (["category", "remove", *D], "food\n", 1),
    (["category", "remove", *D], "nope\n", 1),
    (["search", "--category", "nope", *D], "", 1),
    (["import", "--from", "none.csv", *D], "", 1),
    (["export", "--out", "e2.csv", *D], "", 1),
    (["export", "--out", "e.csv", "--month", "2024-01", *D], "", 1),
    (["add", *D], "2024-01-15\n", 1),
    (["list", "--data-dir", "afile"], "", 1),
]
for argv, stdin, want in STEPS:
    r0, r1 = run(B, co, argv, stdin), run(ROOT, cn, argv, stdin)
    need(r0[0] == want, f"N 변경 전 코드의 종료 코드 {r0[0]} (기대 {want}): {argv} {r0[2]!r}")
    need(r1 == r0, f"N 결과가 변경 전과 다름: {argv}\n  전: {r0!r}\n  후: {r1!r}")
    need("Traceback" not in r1[2], f"N Traceback: {argv}")
for rel in ("d/transactions.jsonl", "d/categories.jsonl", "d/budgets.jsonl", "e.csv"):
    with open(os.path.join(co, rel), "rb") as fa, open(os.path.join(cn, rel), "rb") as fb:
        need(fa.read() == fb.read(), f"N 마지막 저장 파일이 변경 전과 다름: {rel}")
print("NORMAL_SAME_OK" if ok else "NORMAL_SAME_FAIL")
sys.exit(0 if ok else 1)
PY

# ======================= R0. 이전 단계 스크립트에 영어 원문 기대가 없음 (설계서 6.1) =======================
python3 - <<'PY' || FAIL=1
import glob, re, sys
FENCE = "`" * 3                                  # 설계서 코드 블록이 끊기지 않도록 백틱 3개를 직접 쓰지 않는다
WORDS = ("unrecognized", "are required", "invalid choice", "expected one argument", "choose from", "ignored explicit")
files = sorted(glob.glob("docs/plans/step[1-6]-*.md"))
hits = []
for f in files:
    for blk in re.findall(FENCE + r"bash\n(.*?)" + FENCE, open(f, encoding="utf-8").read(), re.S):
        hits += [(f, w) for w in WORDS if w in blk]
if len(files) != 6 or hits:
    print("FAIL R0 이전 단계 스크립트가 영어 argparse 원문을 기대함 (7단계 회귀에서 치환 필요):", hits, "설계서 수:", len(files))
    sys.exit(1)
print("REGRESSION_TEXT_OK")
PY

# ======================= R. 1~6단계 회귀 (6단계 스크립트 → 5 → 4 → 3 → 1·2단계) =======================
# 6단계 설계서 6.2 스크립트를 꺼내 임시 폴더(W) 줄 하나만 $W 아래로 바꾼다. 기대값·해시 치환은 없다 (설계서 6.1).
python3 - <<'PY' || FAIL=1
import os
W = os.environ["W"]
FENCE = "`" * 3
sec = open("docs/plans/step6-broken-pipe.md", encoding="utf-8").read().split("### 6.2", 1)[1]
s6 = sec.split(FENCE + "bash\n", 1)[1].split(FENCE, 1)[0]
old_w = 'W="$(mktemp -d)"; export W'
assert s6.count(old_w) == 2 and s6.index(old_w) < s6.index("# ======================= S. 정적 검사"), "6단계 스크립트의 W 줄을 찾지 못함"
s6 = s6.replace(old_w, 'W="$(mktemp -d "$W/s6.XXXXXX")"; export W', 1)   # 첫 줄만 (R 절 안의 같은 문자열은 그대로)
open(os.path.join(W, "step6.sh"), "w", encoding="utf-8").write(s6)
PY
bash "$W/step6.sh" >"$W/r6" 2>&1
if grep -qx "STEP6_ALL_OK" "$W/r6" && ! grep -q "^FAIL" "$W/r6"; then :; else echo "FAIL 1~6단계 회귀"; cat "$W/r6"; FAIL=1; fi
grep -E "^  (searchN|search10|control) " "$W/r6"     # 5단계 M절 측정값 (보고용)

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
[ "$FAIL" = 0 ] && echo "STEP7_ALL_OK"
```

**기대 출력**
- `FAIL` 로 시작하는 줄이 없어야 한다.
- `CAUSE_UNIT_OK`, `  U Python 3.14.x: 25건`(V 로 다른 버전이 있으면 그 버전 줄도), `USAGE_KO_OK`, `HELP_SAME_OK`, `NORMAL_SAME_OK`, `REGRESSION_TEXT_OK`, 5단계 M절 측정값 6줄, 마지막 줄 `STEP7_ALL_OK` 가 나와야 한다.
- 스크립트가 끝나면 `$W` 는 지워져 있어야 한다(`trap`).

**결함 감지 확인 (에이전트 3 참고, 필수 아님. 할 때는 별도 복사본에서만)**
- 변경 전 코드(기준선과 같은 cli.py): S0("아직 구현되지 않음"), S6, X, U 가 FAIL.
- 모르는 문장에 빈 문자열이나 고정 문구를 돌려주는 구현: X 의 "원문 유지"가 FAIL.
- `build_parser` 의 help 문구나 `_with_help` 를 함께 고친 구현: S6 ④ 와 H 가 FAIL.
- `(choose from …)` 부분에서 명령 목록을 읽는 구현: X 의 따옴표 있는 목록 또는 없는 목록 형식 중 하나가 FAIL.
- 제안 꼬리를 허용하지 않는 정규식(개정 전): S6 ② 와 X 의 제안 꼬리 번역 2건이 FAIL. 꼬리를 아무 문자나 허용하는 정규식: X 의 KEEP 3건(꼬리 모양이 다름)이 FAIL.

## 7. 총괄 확인 필요

1. **한국어 원인 문장의 근거**: REQUIREMENTS/PDF 에는 "원인 + 해결 힌트" 만 있고 "한국어로" 라는 규칙은 없다. 다른 오류와 맞추기로 한 사용자 결정을 근거로 삼았다. 문구는 비전공자용으로 다음처럼 정했다. 다르게 원하면 3.2 표와 6.2 의 기대 문자열(X·U)만 같이 바꾸면 된다.
   - K6 은 총괄 예시 "알 수 없는 인자입니다" 대신 **"알 수 없는 옵션 또는 값입니다"** 로 했다. "인자"는 전문 용어이고, K6 에는 옵션(`--bogus`)과 남는 값(`extra`)이 모두 들어오기 때문이다.
   - K1 은 `category`·`budget` 뒤의 하위 명령에도 같은 "명령을 입력하세요" 를 쓴다. `[힌트]` 의 `python -m budget_app category --help` 가 어느 명령인지 알려 준다.
   - 최상위 `-h` 는 argparse 동작상 K1("명령을 입력하세요")으로 나온다(3.2). `--data-dir X list` 는 K3("알 수 없는 명령입니다: 'X'")으로 나온다. 둘 다 동작은 그대로이고 문장만 번역된다.
2. **K5 (`--help=x`) 포함**: 총괄 예시 목록에는 없지만, 이 앱에서 실제로 나는 사용법 오류라 같은 방식으로 번역했다. 새 기능이나 옵션은 아니다. 빼기를 원하면 정규식 1개와 X·U 의 해당 줄을 지운다.
3. **3.15 이상과 확인 못 한 부분**: ① **(총괄 결정)** 3.15 에서 argparse 의 "혹시 이것?" 제안이 기본으로 켜진다고 알려져 있어, 정규식 3번이 값 바로 뒤·`(choose from …)` 앞의 `, maybe you meant '…'?` 꼬리를 선택적으로 허용한다. 이 꼬리가 붙어도 "알 수 없는 명령입니다" 로 번역하고 제안 내용은 한국어 문장에 넣지 않는다. 꼬리 모양이 이와 다르면 원문 그대로 나온다(안전장치). 3.15 의 실제 문장은 확인하지 못했고, 꼬리 위치는 에이전트 2 의 3.14 소스·실측(제안을 켠 경우)에 근거한다. ② 선택지 목록의 따옴표 표시는 버전·설정마다 다를 수 있다(3.14.7 에서 제안을 켜면 따옴표 있는 목록). 3.12·3.13 패치 릴리스와 3.14 기본 상태의 표시는 확인 못 했다. 설계상 그 부분을 읽지 않으므로 결과는 같다. ③ 3.10~3.13 실측은 PATH 에 그 버전이 있을 때만 V 로 한다. 로컬에는 3.14 만 있으므로 3.10~3.13 은 소스 지식과 X 의 원문 형식 시험으로 대신한다.
4. **기준선 사본(6.0)이 필요하다**: "정상·다른 오류·`--help` 출력이 이전과 동일" 과 "변경 파일 외 해시 불변" 을 글자 단위로 확인하려고, 에이전트 2 착수 **전에** 총괄이 6.0 명령으로 사본을 만들어야 한다. 착수 뒤에 만들면 S0 이 "기준선이 이미 바뀐 코드" 로 FAIL 을 낸다. 그때는 7단계 변경을 되돌린 상태에서 다시 만들어야 한다.
5. **힌트의 prog**: K6(알 수 없는 인자)은 argparse 가 최상위 파서에서 보고하므로, `list --bogus` 의 힌트도 `python -m budget_app --help` 다(기존 그대로). 힌트는 이번 범위 밖이라 바꾸지 않았다.
6. **README 미변경**: 영어 원문 인용이 없어 갱신할 곳이 없다고 판단했다(3.6). 사용법 오류 문장 예시를 README 에 새로 넣는 것은 지시 범위 밖이라 하지 않았다.
