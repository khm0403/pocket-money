# 6단계 설계서 (보강): 출력이 중간에 끊길 때(BrokenPipe) 조용히 종료

> 개정 1 (에이전트 3 검토 반영)
> - [필수] stdout 이 아예 닫힌 채 실행되면(`>&-`, `sys.stdout` 이 `None`) `_flush_stdout`·`_discard_stdout` 이 아무것도 하지 않고 돌아간다. 6.2 S6 을 새 본문에 맞췄고, Z절(`>&-` 회귀)을 추가했다.
> - [권장] decorators.py 모듈 docstring 에 `handle_broken_pipe` 를 언급한다. cli.py `_cmd_search` 주석의 "임시 파일" 을 "정렬용 임시 폴더" 로 바꾼다.

## 1. 목표

- `python -m budget_app list ... | head -1` 처럼 출력을 받는 쪽이 먼저 닫혀도 다음 세 가지가 나오지 않게 한다. ① `[오류] 파일을 읽거나 쓸 수 없습니다: [Errno 32] Broken pipe` 와 상황에 맞지 않는 `--data-dir` 힌트, ② 파이썬 원문 `Exception ignored ... BrokenPipeError`, ③ 종료 코드 120. 대신 **추가 출력 없이 종료 코드 1** 로 끝난다(사용자 확정).
- 명령 실행 중 끊기는 경우, 명령이 끝난 뒤 남은 버퍼를 내보내다 끊기는 경우, `--help` 출력이 끊기는 경우를 모두 처리한다. search 외부 정렬 도중 끊겨도 정렬용 임시 폴더는 지워진다.
- 명령·옵션·출력 문구·다른 오류 처리는 하나도 바뀌지 않는다. stdout 이 아예 닫힌 채(`>&-`) 실행해도 6단계 이전과 같은 결과가 나온다.

## 2. 대상 요구사항

| REQUIREMENTS.md 항목 | 이번 단계 충족 범위 |
| --- | --- |
| 4장 예외 처리 "스택트레이스 출력 금지, 원인 + 해결 힌트" (PDF 4장·7장) | 파이프가 끊겼을 때 파이썬 원문 메시지(`Exception ignored …`)와 원인에 맞지 않는 `[오류]/[힌트]` 를 없앤다. stdout 이 닫힌 실행에서 새 스택트레이스가 생기지 않게 한다 |
| 4장 종료 코드 "정상 0, 오류 0 아닌 값" | 출력을 끝까지 못 했으므로 `EXIT_ERROR`(1)로 끝내고 120 이 나오지 않게 한다. `>&-` 실행의 종료 코드는 바꾸지 않는다 |
| 4장 데코레이터 "공통 관심사 1개 이상" | 파이프 끊김 처리를 `decorators.py` 한 곳에 둔다(`handle_errors` 에 분기 1개, `main` 용 데코레이터 1개) |
| 3장 #2 list, #3 search "스트리밍" | 출력 도중 끊겨도 search 의 `closing` → `finally` 정리 구조가 그대로 동작한다(5단계 구조 유지) |
| 0장 "모든 명령에 `--help` 동작" | `--help` 출력이 끊겨도 원문 메시지가 나오지 않는다 |
| 4장 README (4단계 3.8 "오류와 종료 코드" 절) | 이 동작을 한 줄로 적는다 |
| 4장 타입 힌트, 0장 표준 라이브러리만 | 새 함수 모두 타입 힌트. `os`, `sys` 만 사용 |

## 3. 파일/모듈 설계

### 3.0 공통 결정

| 항목 | 결정 | 근거 |
| --- | --- | --- |
| 처리 방식 | 파이썬 공식 문서(signal 모듈 "Note on SIGPIPE")의 권장 방식을 따른다. `BrokenPipeError` 를 잡은 뒤 `os.devnull` 을 stdout(fd 1)에 `os.dup2` 한다. 그러면 파이썬이 끝날 때 남은 버퍼를 내보내도 "버리는 곳"으로 간다 | ← 4장 예외 처리 (원문 메시지 금지) |
| 종료 코드 | `EXIT_ERROR`(1). 공식 문서 예시도 `sys.exit(1)` 이고, README 표도 종료 코드 0/1/2 만 쓴다. 141(SIGPIPE 로 죽은 프로세스의 셸 종료 코드)은 쓰지 않는다 | ← 4장 종료 코드, 사용자 확정 |
| `signal.signal(SIGPIPE, SIG_DFL)` 방식 | **쓰지 않는다.** 프로세스가 그 자리에서 죽어 search 의 `finally`(정렬용 임시 폴더 삭제)가 실행되지 않고, 종료 코드도 141 이 된다. `signal` 모듈은 import 하지 않는다 | ← 3장 #3 (5단계 임시 파일 정리 유지) |
| 명령 실행 중 끊김 | `handle_errors` 에 `except BrokenPipeError:` 를 **`except OSError` 바로 앞에** 추가한다(`BrokenPipeError` 는 `OSError` 의 하위 클래스). 분기 안에서는 `_discard_stdout()` 만 부른다. 그 뒤 기존 마지막 줄 `return EXIT_ERROR` 로 끝나고, 아무것도 출력하지 않는다 | ← 4장 데코레이터·예외 처리 |
| 핸들러 밖 끊김 | 새 데코레이터 `handle_broken_pipe` 를 **`cli.main`** 에 적용한다. 이 데코레이터는 `main` 이 끝날 때 `finally` 에서 stdout 을 직접 flush 해서, 끊김이 우리 코드 안에서 `BrokenPipeError` 로 나게 한다. 다음 두 경우를 잡는다. ① 출력이 적어 버퍼에만 있다가 핸들러가 끝난 뒤 나가는 경우. ② `--help` 처럼 argparse 가 출력하고 `SystemExit` 로 빠지는 경우 | ← 4장 예외 처리, 0장 `--help` |
| `__main__.py` 가 아니라 `cli.main` 인 이유 | ① 계층 규칙상 `__main__` 은 `cli` 만 import 할 수 있다(1~5단계 S4/S5: `"__main__": {"cli"}`). 그래서 `EXIT_ERROR`·`_discard_stdout` 을 쓰지 못해 코드가 중복된다. ② `__main__.py` 는 3·4·5단계 S0 에서 SHA-256 으로 고정되어 있어, 바꾸면 회귀 스크립트 세 곳을 치환해야 한다. `cli.main` 은 이미 `decorators` 를 import 하고 해시 검사 대상도 아니다. **결과적으로 `__main__.py` 는 바꾸지 않는다** | ← 4장 모듈화(계층), 최소 변경 |
| stdout 이 아예 닫힌 채 실행 (`>&-`) | 이때 파이썬은 `sys.stdout` 을 `None` 으로 두고, `print` 는 조용히 아무것도 하지 않는다. `_flush_stdout`·`_discard_stdout` 은 첫 줄에서 `sys.stdout is None` 이면 바로 돌아간다. 그러면 6단계 이전과 같은 종료 코드(list 0, `--help` 0, 사용법 오류 2, 없는 id 1, budget set 0)와 같은 `[오류]/[힌트]` 가 나온다. 이 확인이 없으면 `None.flush()` 의 `AttributeError` 로 모든 명령에서 스택트레이스가 난다 | ← 4장 예외 처리(스택트레이스 금지), 총괄 지시 4 (다른 동작 불변) |
| 다른 쓰기 오류(디스크 가득 참 등) | 이번 단계에서 동작을 바꾸지 않는다. `_flush_stdout` 은 `BrokenPipeError` 가 아닌 `OSError` 를 그냥 넘긴다. 남은 글자는 버퍼에 그대로 있어 파이썬이 끝날 때 다시 쓰려 하므로 결과가 이전과 같다. 넘기지 않으면 이전에 없던 스택트레이스가 생긴다 | ← 총괄 지시 4 (다른 오류 처리 불변) |
| 출력 문구 | 새 출력은 없다. `print` 호출 수는 decorators 4개, cli 14개로 그대로다 | ← 총괄 지시 4 |

### 3.1 변경 파일 / 변경 금지 파일

- 변경: `budget_app/decorators.py`(추가 위주, 모듈 docstring 1줄), `budget_app/cli.py`(import 이름 1개, `main` 위 데코레이터 1줄과 주석, `_cmd_search` 주석), `README.md`(1줄).
- **변경 금지**: `models.py`, `storage.py`, `services.py`, `__main__.py`, `__init__.py`. 6.2 S0 에서 models·`__main__`·`__init__` 은 해시로 확인한다. storage·services 는 S6 와 5단계 회귀로 확인한다(총괄 확인 5).

### 3.2 `budget_app/decorators.py` — [공통 관심사]

import 추가: `import os` (표준 라이브러리, `functools` 와 `sys` 사이).

모듈 docstring (교체): `"""[공통 관심사] 명령 핸들러의 예외를 [오류]/[힌트] 메시지와 종료 코드로 바꾸는 데코레이터와, 출력이 끊겨도 main 을 조용히 끝내는 데코레이터(handle_broken_pipe)."""` ← 4장 데코레이터 (학습자 안내)

| 시그니처 | 책임 | 근거 |
| --- | --- | --- |
| `def _discard_stdout() -> None` | `sys.stdout` 이 `None` 이면 바로 돌아간다. 아니면 fd 1(stdout)을 `os.devnull` 로 바꿔 끼워, 버퍼에 남은 글자를 파이썬이 끝날 때 내보내도 조용히 버려지게 한다. 본문은 아래 골격 그대로 | ← 4장 예외 처리(원문 메시지·스택트레이스 금지), 공식 문서 권장 방식 |
| `def _flush_stdout() -> None` | `sys.stdout` 이 `None` 이면 바로 돌아간다. 아니면 `sys.stdout.flush()` 를 지금 실행하고, `BrokenPipeError` 는 다시 올리며 그 밖의 `OSError` 는 넘긴다(3.0 "다른 쓰기 오류") | ← 4장 예외 처리, 4장 종료 코드 |
| `def handle_errors(func: Callable[P, int]) -> Callable[P, int]` (변경) | 기존 그대로에 `except BrokenPipeError:` 분기 1개만 추가한다. 위치는 `UnicodeDecodeError` 다음, `OSError` 앞이다. 분기 본문은 `_discard_stdout()` 한 줄이다(`as e` 없음, 출력 없음). 이후 기존 `return EXIT_ERROR` 로 끝난다. try 본문, 다른 분기, 문구는 바꾸지 않는다 | ← 4장 데코레이터·예외 처리·종료 코드 |
| `def handle_broken_pipe(func: Callable[P, int]) -> Callable[P, int]` | `main` 을 감싸는 데코레이터로, 아래 골격 그대로 쓴다. `func` 가 정상으로 끝나든 `SystemExit` 로 빠지든 `finally` 에서 `_flush_stdout()` 을 부른다. `BrokenPipeError` 가 나면 `_discard_stdout()` 후 `EXIT_ERROR` 를 반환하고, 다른 예외는 그대로 통과시킨다 | ← 4장 데코레이터·예외 처리, 0장 `--help` |

**골격** (`# [주석 N]` 은 3.5 의 "왜" 주석 자리. 함수 순서는 `print_error` → `_discard_stdout` → `_flush_stdout` → `handle_errors` → `handle_broken_pipe`)

```python
# [주석 1]
def _discard_stdout() -> None:
    if sys.stdout is None:
        # [주석 9]
        return
    devnull = os.open(os.devnull, os.O_WRONLY)
    os.dup2(devnull, sys.stdout.fileno())
    os.close(devnull)


# [주석 2]
def _flush_stdout() -> None:
    if sys.stdout is None:
        # [주석 9]
        return
    try:
        sys.stdout.flush()
    except BrokenPipeError:
        raise
    except OSError:
        # [주석 3]
        pass


# handle_errors: 기존 코드에서 아래 분기만 추가 (UnicodeDecodeError 분기와 OSError 분기 사이)
        except BrokenPipeError:
            # [주석 4]
            _discard_stdout()


# [주석 5]
def handle_broken_pipe(func: Callable[P, int]) -> Callable[P, int]:
    @functools.wraps(func)
    def wrapper(*args: P.args, **kwargs: P.kwargs) -> int:
        try:
            try:
                return func(*args, **kwargs)
            finally:
                # [주석 6]
                _flush_stdout()
        except BrokenPipeError:
            _discard_stdout()
            return EXIT_ERROR

    return wrapper
```

- 함수 본문은 위 그대로 쓴다. 6.2 S6 이 AST 로 문장 단위까지 비교한다. 함수 docstring 은 넣어도 된다.
- **decorators.py 의 주석·docstring 에는 `TMPDIR`, `tempfile`, `임시` 를 쓰지 않는다.** 5단계 S0 회귀 검사가 이 단어들을 금지한다. 임시 폴더는 "정렬용 작업 폴더"라고 쓴다. `open(` 은 `os.open(` 형태로만 쓴다(4·5단계 `open(` 위치 검사).
- `EXIT_OK`/`EXIT_ERROR`, `P`, `print_error`, `handle_errors` 의 기존 주석은 바꾸지 않는다. 모듈 docstring 만 위 문장으로 바꾼다.

`handle_errors` 가 잡는 예외 (위에서부터 순서대로, 2단계 3.2 표의 갱신본)

| 예외 | 처리 |
| --- | --- |
| `KeyboardInterrupt` | 기존 그대로 |
| `EOFError` | 기존 그대로 |
| `BudgetAppError` | 기존 그대로 |
| `UnicodeDecodeError` | 기존 그대로 |
| **`BrokenPipeError`** (신규) | 출력 없음. `_discard_stdout()` 후 `EXIT_ERROR` |
| `OSError` | 기존 그대로(문구 `경로(--data-dir, --from, --out)…` 그대로) |
| `Exception` | 기존 그대로 |

### 3.3 `budget_app/cli.py` — [CLI] (최소 변경)

| 변경 | 내용 | 근거 |
| --- | --- | --- |
| import | `from budget_app.decorators import EXIT_OK, handle_broken_pipe, handle_errors, print_error`. `sys`·`os` 는 import 하지 않는다 | ← 4장 모듈화 |
| `@handle_broken_pipe def main(argv: list[str] \| None = None) -> int` | 본문 두 줄(`args = build_parser().parse_args(argv)`, `return args.handler(args)`)은 그대로 두고, 데코레이터 1줄과 그 위 [주석 7] 만 추가한다 | ← 0장 `--help`, 4장 예외 처리·종료 코드 |
| `_cmd_search` | 코드는 그대로 두고 기존 `closing` 주석만 고친다([주석 8]). 기존 주석의 `(임시 파일 삭제)` 를 `(정렬용 임시 폴더 삭제)` 로 바꾸고, 끝에 한 줄을 덧붙인다 | ← 3장 #3 (학습자 주석) |

- `@handle_errors` 는 12개, `_cmd_*` 함수는 그대로다. `print(` 호출은 14개 그대로다.
- `BrokenPipeError`, `flush`, `dup2`, `devnull`, `stdout` 은 cli.py 코드(AST)에 나오지 않는다. 처리는 모두 decorators.py 에서 한다.

### 3.4 `README.md` (1줄 추가)

**판단: 추가한다.** `| head` 뒤에 메시지 없이 종료 코드 1 이 나오면 사용자가 볼 수 있다. 또 완료 문구만 못 냈을 뿐 저장은 끝났을 수 있으므로 문서에 적는다. 근거: 4장 README, PDF 4장 3·6번 "문서에 명확히".

위치: `## 오류와 종료 코드` 절의 마지막 줄(`` `[경고]` 줄은 표준 출력(stdout)에 나오고 종료 코드는 0 입니다. ``) 다음. 빈 줄 하나를 두고 아래 한 줄을 그대로 넣는다.

```
출력을 받는 프로그램이 먼저 끝나면(예: `| head -1` 로 앞부분만 볼 때) 남은 출력은 버리고 `[오류]` 없이 종료 코드 1 로 끝납니다. 그때까지 저장·삭제한 내용은 그대로 남습니다.
```

- `--` 로 시작하는 단어가 없어 4단계 N3 "help 에 없는 옵션" 검사가 유지된다. console 블록과 표는 바꾸지 않는다(4단계 N4 재생 유지).

### 3.5 학습자(비전공자)용 "왜" 주석 위치

짧은 한국어 주석 1~3줄로 아래 내용을 담는다(문장은 자유). decorators.py 쪽 주석에는 `임시`·`TMPDIR`·`tempfile` 을 쓰지 않는다.

| 위치 | 담을 내용 |
| --- | --- |
| [주석 1] `_discard_stdout` 위 | 출력을 받는 쪽(예: `head`)이 닫히면 버퍼에 남은 글자를 보낼 곳이 없다. 그대로 두면 파이썬이 끝날 때 다시 보내려다 실패해 영어 원문 경고를 내고, 종료 코드를 120 으로 바꾼다. 그래서 stdout 을 운영체제의 "버리는 곳"(`os.devnull`)에 다시 연결해 남은 글자가 조용히 버려지게 한다(파이썬 공식 문서가 권하는 방법) |
| [주석 2] `_flush_stdout` 위 | 버퍼에 모아 둔 출력을 지금 내보낸다. 파이썬이 끝날 때 알아서 내보내다 나는 오류는 우리 코드가 잡을 수 없으므로, 잡을 수 있는 곳에서 먼저 내보낸다 |
| [주석 3] `except OSError: pass` | 디스크가 꽉 찬 경우 같은 다른 쓰기 오류는 이번에 동작을 바꾸지 않는다. 남은 글자는 버퍼에 그대로 있어 파이썬이 끝날 때 다시 시도하므로 결과가 전과 같다 |
| [주석 4] `handle_errors` 의 `except BrokenPipeError:` | `BrokenPipeError` 는 `OSError` 의 한 종류라서 `OSError` 보다 먼저 써야 이 분기로 온다. `\| head` 처럼 받는 쪽이 필요한 만큼 읽고 먼저 끝난 것은 사용자 실수가 아니므로 `[오류]/[힌트]` 없이 조용히 끝낸다. 출력을 끝까지 못 했으므로 종료 코드는 1 |
| [주석 5] `handle_broken_pipe` 위 | `handle_errors` 는 명령 핸들러 안의 오류만 잡는다. 출력이 적으면 글자가 버퍼에 있다가 핸들러가 끝난 뒤에야 나가고, `--help` 는 핸들러 전에 argparse 가 출력하고 바로 끝난다. 이 경우까지 잡으려고 `main` 전체를 감싼다. SIGPIPE 를 기본 동작으로 되돌리는 방법은 쓰지 않는다. 프로그램이 그 자리에서 강제로 끝나 `finally` 정리(search 의 정렬용 작업 폴더 삭제 등)가 실행되지 않기 때문이다 |
| [주석 6] `finally: _flush_stdout()` | 정상 반환뿐 아니라 `--help` 의 `SystemExit` 로 빠져나갈 때도 여기서 내보내야 끊김을 잡을 수 있으므로 `finally` 에 둔다 |
| [주석 7] cli `main` 위 | 명령이 끝난 뒤 남은 출력과 `--help` 출력이 끊기는 경우까지 조용히 끝내도록 `main` 전체를 감싼다. 명령 실행 중의 끊김은 `handle_errors` 가 처리한다 |
| [주석 8] cli `_cmd_search` 의 기존 `closing` 주석 | 기존 문장의 `(임시 파일 삭제)` 를 `(정렬용 임시 폴더 삭제)` 로 바꾼다. 끝에 "출력 받는 쪽이 먼저 닫혀(`BrokenPipeError`) 반복이 끊길 때도 마찬가지로 정렬용 임시 폴더가 바로 지워진다." 를 덧붙인다 |
| [주석 9] `if sys.stdout is None: return` (두 곳) | `>&-` 처럼 stdout 이 아예 닫힌 채 실행되면 파이썬은 `sys.stdout` 을 `None` 으로 둔다. 내보낼 곳도 바꿔 끼울 곳도 없으니 아무것도 하지 않는다. 확인하지 않으면 `None` 에 `flush()` 를 불러 스택트레이스가 난다 |

## 4. 계층 규칙

1~5단계와 같다. 새 import 는 표준 라이브러리 `os`(decorators) 하나뿐이다.

```
__main__.py → cli.py → services.py → storage.py → models.py
                 └──→ decorators.py ──→ models.py
```

| 모듈 | import 가능한 `budget_app` 모듈 | 이번 단계 변화 |
| --- | --- | --- |
| `models.py` | 없음 | 없음 (변경 금지) |
| `storage.py` | `models` | 없음 (변경 금지) |
| `services.py` | `storage`, `models` | 없음 (변경 금지) |
| `decorators.py` | `models` | 표준 라이브러리 `os` 추가 |
| `cli.py` | `services`, `decorators`, `models` (`storage` 금지) | decorators 에서 `handle_broken_pipe` 추가 import |
| `__main__.py` | `cli` | 없음 (변경 금지) |

- `signal` 모듈은 어느 파일에서도 import 하지 않는다.
- `print`/`input` 은 `cli.py`, `decorators.py` 에만 둔다(새 `print` 없음).
- 상대 import 금지. 표준 라이브러리 밖의 모듈 금지.

## 5. 예외/경계 상황

| 상황 | 처리 | 종료 코드 |
| --- | --- | --- |
| 출력이 많은 명령이 출력 중 끊김 (`list --limit 100000 \| head -1`) | `print` 중 `BrokenPipeError` → `handle_errors` 새 분기 → stdout 을 버리는 곳으로 연결한다. stderr 에는 아무것도 나오지 않는다 | 1 |
| search 외부 정렬(매칭 > 1000) 출력 중 끊김 | `print` 에서 `BrokenPipeError` → `closing` 이 제너레이터를 닫음 → 서비스 `finally` 가 임시 폴더 삭제 → `handle_errors` 새 분기. 5단계 구조 그대로 | 1 |
| search 조각을 쓰는 중(출력 전)에 받는 쪽이 끝남 | 쓰기 전에는 알 수 없다. 첫 출력 때 위와 같이 처리하고 임시 폴더를 삭제한다 | 1 |
| 출력이 적어 핸들러가 끝난 뒤 버퍼를 내보낼 때 끊김 (summary, category list, 0건 안내 등) | `handle_broken_pipe` 의 `finally` flush 에서 `BrokenPipeError` → 버리는 곳으로 연결 | 1 |
| `--help` 출력이 끊김 (최상위·하위 명령 모두) | argparse 가 버퍼에 쓰고 `SystemExit(0)` → `finally` flush 의 `BrokenPipeError` 가 `SystemExit` 를 대신함 → 잡아서 1 | 1 |
| 출력이 적어 받는 쪽이 닫히기 전에 다 써진 경우 (`summary \| head -1` 대부분) | 끊김이 없으므로 기존 그대로 | 0 |
| 완료 문구를 내기 전에 끊김 (budget set, update, delete, import, export) | 저장·삭제·파일 생성은 문구 출력 전에 이미 끝났으므로 그대로 남는다. 문구만 버려진다(README 에 명시) | 1 |
| 대화형 명령의 stdout 이 닫힌 파이프 (add, category add/remove) | 프롬프트 출력이 막힌다. 그 뒤에는 파이썬 `input()` 동작에 따라 바로 끝나거나, 표준입력을 다 읽고 저장한 뒤 끝난다. 어느 쪽이든 stderr 출력은 없다 | 1 |
| **stdout 이 아예 닫힌 채 실행 (`>&-`, `sys.stdout` 이 `None`)** | `print` 는 원래대로 조용히 아무것도 하지 않는다. `_flush_stdout`·`_discard_stdout` 은 바로 돌아간다. 6단계 이전과 같은 종료 코드와 `[오류]/[힌트]` 가 나오고, 저장도 그대로 된다. 스택트레이스는 없다 | 이전과 같음 (list 0, `--help` 0, 사용법 오류 2, 없는 id 1, budget set 0) |
| stdout 이 닫힌 파이프일 때 다른 오류 (조건 없는 search, `--limit 0`, 없는 id, 사용법 오류 등) | stdout 에 쓸 것이 없으므로 끊김이 일어나지 않는다. stderr 의 `[오류]/[힌트]` 문구와 종료 코드는 끊기지 않았을 때와 **완전히 같다** | 1 / 2 |
| `OSError`(권한, EIO 등 `BrokenPipeError` 가 아닌 것) | 기존 `OSError` 분기와 문구 그대로 | 1 |
| stdout 이 디스크 가득 참 등 다른 쓰기 오류 | 범위 밖이라 기존 동작 그대로다(핸들러 안이면 기존 `[오류]` 문구, 끝 flush 면 파이썬 종료 처리) | 기존과 같음 |
| stderr 쪽 파이프가 끊김 (`2>&1 \| head -1` 로 `[오류]` 줄 중간에 끊김) | 범위 밖. stderr 가 닫혀 있으므로 보이는 출력은 없다. 종료 코드는 0 이 아니다(1 또는 120) | ≠0 |
| Ctrl+C, EOF | 기존 그대로 | 1 |
| 어떤 경우에도 | `Traceback`, `Exception ignored` 없음 | — |

- 5단계 설계서 5장 표의 "출력이 파이프로 이어지다 끊김 → 기존 데코레이터 `OSError` 메시지" 행은 이 단계에서 위 표로 대체된다. 그 행은 설명 문장이고, 5단계 검증 스크립트에는 이를 기대하는 검사가 없다(6.1).

### Python 3.10 호환

`os.dup2`, `os.devnull`, `os.O_WRONLY`, `BrokenPipeError`, `try/finally` 안의 `return`, stdout 이 닫혔을 때 `sys.stdout` 이 `None` 이 되는 동작은 모두 3.10 에서 같다. 검사 스크립트의 `ast.unparse` 는 3.9+, `sys.stdlib_module_names` 는 3.10+ 이다.

## 6. 완료 기준 (에이전트 3 검증 절차)

### 6.1 이전 단계 검사에 주는 영향과 이번 단계 검사 항목

**이전 단계 검사 영향 분석** (변경 파일: decorators.py, cli.py, README.md)

| 이전 검사 | 이번 변경 후 | 6단계 스크립트의 처리 |
| --- | --- | --- |
| 5단계 S0: models·`__main__`·`__init__` SHA-256 | 세 파일을 바꾸지 않으므로 통과 | 그대로. **해시 치환 불필요** |
| 5단계 S0: decorators.py 에 `경로(--data-dir, --from, --out)…` 문구가 있고 `TMPDIR\|tempfile\|임시` 는 없어야 함 | 문구는 그대로이고, 주석·docstring 에 금지 단어를 쓰지 않으면 통과(3.2) | 그대로 + 6단계 S0 에서도 확인 |
| 4단계 S0 (models·`__main__`·`__init__`) | 통과 | 그대로 |
| 3단계 S0 (4단계 R 이 storage·decorators 해시 줄을 지운 뒤 남은 models·`__main__`·`__init__`) | decorators 해시 줄은 이미 지워졌고 나머지는 그대로라 통과 | 그대로 |
| 3·4단계 S7: `def handle_errors` 1개, `@handle_errors` 12개, `_cmd_*` 12개 전부 적용 | `def handle_broken_pipe`·`@handle_broken_pipe` 는 이 grep 에 걸리지 않음. `main` 은 `_cmd_*` 가 아님 | 그대로 |
| 4단계 S9 / 5단계 S8: `open(` 은 storage 에서만 (`[^A-Za-z0-9_.]open\(`) | `os.open(` 은 앞 글자가 `.` 이라 걸리지 않음 | 그대로 |
| 2단계 A (`--help` 종료 코드 0, stdout 에 `usage:`) | 파일로 받으므로 끊김이 없다. `finally` flush 가 성공하고 `SystemExit(0)` 이 그대로 나감 | 그대로 |
| 2단계 CTRL_C, 4단계 SIGNAL, 5단계 B4·B5 (Ctrl+C) | stdout 파이프를 끝까지 읽으므로 끊김이 없고 Ctrl+C 처리 순서도 그대로 | 그대로 |
| 3·5단계 M (tracemalloc, 같은 프로세스에서 `main` 호출) | `StringIO`·devnull 파일·`LineCounter` 의 `flush()` 는 무해하고 메모리 변화는 무시할 만함 | 그대로 |
| 4단계 N (README 재생·옵션·필수 문구) | console 블록은 그대로이고 새 줄에 `--` 단어가 없음 | 그대로 |
| "Broken pipe → `[오류]`" 를 기대하는 검사 | 1~5단계 설계서 전체에서 `pipe`/`Broken`/`EPIPE` 를 검색했다. 5단계 5장 표의 설명 문장 1행뿐이고 스크립트 검사는 없음 | 영향 없음 |

**회귀 실행 방식**: 5단계 6.2 스크립트를 꺼내 **임시 폴더(`W`) 줄 하나만** 이 스크립트의 `$W` 아래로 바꿔 실행한다. 5단계 스크립트가 R 절에서 4단계 → 3단계 → 1·2단계 스크립트를 차례로 다시 실행하므로 1~5단계 전체가 다시 실행된다. `__main__.py` 를 바꾸지 않으므로 해시 치환은 없다.

(참고: 총괄이 `__main__.py` 쪽 처리를 택하면 치환할 곳은 세 곳이다. 5단계 S0 의 `__main__` 해시 줄, 4단계 S0 의 같은 줄(5단계 R 안에 치환 추가), 3단계 S0 의 같은 줄(4단계 R 안에 치환 추가). 또 `__main__` 에서 decorators 를 import 하면 1~5단계 S4/S5 계층 검사가 깨지므로 코드를 중복해야 한다.)

**6단계 검사 항목**

| # | 검사 | 기대 |
| --- | --- | --- |
| S0 | models·`__main__`·`__init__` SHA-256 이 5단계와 같음. decorators.py 에 `TMPDIR\|tempfile\|임시` 없음 | 일치 / 없음 |
| S1 | 파일 7개 존재 | 존재 |
| S2 | 3.10 문법 | 통과 |
| S3 | 3.11+ 전용 API grep | 없음 |
| S4 | 계층 규칙 + 표준 라이브러리만 + `signal` import 없음 | 위반 없음 |
| S5 | 모든 함수(중첩 포함)의 타입 힌트 | 누락 없음 |
| S6 | decorators.py 구조(AST). ① 3.2 골격과 문장 단위로 같음(`_discard_stdout`·`_flush_stdout` 첫 문장은 `if sys.stdout is None: return`). ② `handle_errors` 의 except 순서. ③ `print` 4개. ④ 모듈 docstring 에 `handle_broken_pipe`. ⑤ `sys.stdout.flush()`·`os.dup2` 는 패키지 전체에서 decorators 에 1회씩. ⑥ models·storage·services 에 `BrokenPipeError`/`dup2`/`devnull`/`stdout` 없음 | 위반 없음 |
| S7 | cli.py 구조(AST): `main` 의 데코레이터가 `handle_broken_pipe` 하나, 본문 2줄 그대로, decorators 에서 import 하는 이름 4개, `print` 14개, 파이프 처리 이름 없음. `_cmd_search` 주석에 `정렬용 임시 폴더` | 위반 없음 |
| S8 | decorators.py 의 기존 문구 13개가 글자 그대로 있음 | 있음 |
| S9 | README 에 3.4 의 한 줄이 그대로 있음 | 있음 |
| F | 시험 데이터 준비(big 6만 건, small 3건, mod, empty, CSV) | — |
| E | 같은 프로세스에서 `handle_errors` 의 기존 분기(KeyboardInterrupt, EOF, BudgetAppError, UnicodeDecodeError, OSError 2종, OSError 하위 ConnectionResetError, Exception) 출력이 기존 문구와 글자 하나까지 같고 종료 코드 1 | `ERROR_TEXT_OK` |
| N | 끊기지 않은 정상 실행(파이프를 끝까지 읽음)의 출력이 기대 문자열과 같음. 6만 건 list 와 search(외부 정렬)의 출력이 서로 같음. 임시 폴더 잔존 없음 | `NORMAL_OK` |
| P | stdout 으로 **읽는 쪽이 이미 닫힌 파이프**를 줘서 끊김을 항상 일으킨다(타이밍과 무관). ① 성공하는 출력 명령 13가지(`--help` 5종, list·search 소량/0건/대량, summary, category list): 종료 코드 1, stderr 완전히 빈 문자열, 임시 폴더 잔존 없음. ② 데이터를 바꾸는 명령 8가지(budget set, update, delete, import, export, add, category add, category remove): 종료 코드 1, stderr 빈 문자열, budget set·update·delete·import·export 결과가 저장되어 있음. ③ 오류 명령 7가지: 종료 코드와 stderr 가 끊기지 않았을 때와 완전히 같음 | `PIPE_OK` |
| H | 실제 bash 파이프 `\| head -n 1` 의 `PIPESTATUS[0]`. list·search 대량(6만 줄)은 1, summary·category list·`--help`·`search --help` 는 0 또는 1. 모두 stderr 가 비어 있고, head 가 받은 줄이 끊기지 않은 실행의 첫 줄과 같고, 임시 폴더 잔존이 없음. 조건 없는 search 는 파이프여도 1 과 `[오류]/[힌트]` 각 1줄 | `HEAD_OK` |
| Z | **stdout 을 아예 닫고(`>&-`) 실행**. list 0, `--help` 0, 없는 옵션 2(`[오류]/[힌트]` 각 1), 없는 id 1(`[오류]/[힌트]` 각 1), budget set 0. 이 값들은 6단계 이전과 같다. stderr 에 `Traceback`·`Exception ignored`·`AttributeError` 가 없고, budget set 결과가 저장되어 있음 | `CLOSED_STDOUT_OK` |
| R | 1~5단계 회귀 (위 방식) | `STEP5_ALL_OK` 포함, `FAIL` 없음 |
| 마무리 | `$W/systmp` 에 `budget_app_search_*` 잔존 없음. `./data`·`__pycache__`·루트의 예상 밖 파일 없음 | `STEP6_ALL_OK` |

**PIPESTATUS 기대값 근거**
- 6만 줄(약 3.3MB)은 파이프 버퍼(macOS 최대 64KB, 리눅스 기본 64KB·최대 1MB)보다 훨씬 크다. 그래서 `head` 가 끝난 뒤에도 쓸 것이 반드시 남아 끊김이 확실히 일어나고, 기대값은 1 이다.
- 출력이 몇 줄뿐이면 `head` 가 닫히기 전에 다 써질 수 있어 0 도 정상이다. 이 명령들이 끊겼을 때 1 이 되는지는 P 절(닫힌 파이프)이 타이밍과 무관하게 확인한다.

**Z절 기대값 근거**: 총괄이 6단계 이전 코드에서 확인한 값(list 0 / `--help` 0 / 없는 옵션 2 / 없는 id 1 / budget set 0)을 그대로 쓴다. stdout 이 `None` 이면 argparse 는 도움말을 stderr 로 보낼 수 있으므로, `--help` 는 stderr 내용을 비교하지 않고 원문 오류가 없는지만 본다.

**실행 방법**
- 6.2 코드 블록 내용을 스크래치패드에 파일로 저장하고 `bash <파일>` 로 실행한다(macOS 기본 bash 3.2 에서 동작). 실행이 끝나면 저장한 스크립트 파일을 지운다.
- **백그라운드(`&`)로 실행하지 않는다.** 회귀(5단계 B절, 2단계 CTRL_C, 4단계 SIGNAL)가 Ctrl+C 신호를 보낸다.
- `python` 이 없는 환경이므로 첫머리에서 `python → python3` 링크를 만들어 PATH 앞에 둔다. 모든 임시 파일은 `W="$(mktemp -d)"` 아래에 만들고 `trap` 으로 지운다. `TMPDIR` 는 `$W/systmp` 로 바꾼다.
- 예상 실행 시간은 3~4분이다(5단계 회귀 2~3분 + 6만 건 실행 약 12회).

**성공 기준**: `FAIL` 로 시작하는 줄이 하나도 없어야 한다. `ERROR_TEXT_OK`, `NORMAL_OK`, `PIPE_OK`, `HEAD_OK`, `CLOSED_STDOUT_OK`, 그리고 마지막 줄 `STEP6_ALL_OK` 가 나와야 한다. R 절 뒤에는 5단계 M절 측정값 6줄이 보고용으로 출력되며, 에이전트 3 은 이를 보고서에 그대로 옮긴다.

### 6.2 검증 스크립트

```bash
# 6단계 검증 스크립트. 실행: bash <이 파일>   (백그라운드 & 로 실행하지 말 것)
cd "/Users/khm04/codessey/pocket money" || exit 1
export PYTHONDONTWRITEBYTECODE=1
W="$(mktemp -d)"; export W                      # 이 스크립트의 임시 파일은 전부 여기 아래
cleanup() { chmod -R u+rwx "$W" 2>/dev/null; rm -rf "$W"; }
trap cleanup EXIT
mkdir "$W/bin" && ln -s "$(command -v python3)" "$W/bin/python" || exit 1   # python 이 없어서 python3 로 연결
export PATH="$W/bin:$PATH"
python --version || exit 1
mkdir "$W/systmp" && export TMPDIR="$W/systmp" || exit 1   # search 정렬용 "시스템 임시 폴더"
FAIL=0
fail() { echo "FAIL $*"; FAIL=1; }

# ======================= S. 정적 검사 =======================
# S0 변경 금지 파일 (5단계와 같은 해시) + 5단계 S0 의 decorators.py 금지 단어
shasum -a 256 -c - >/dev/null <<'SUMS' || fail "S0 변경 금지 파일이 바뀜 (models/__main__/__init__)"
08b6a94954a6ca8d6619a69a026ac2fd2d028844e17a8c55cb8d6f02faca513f  budget_app/models.py
6958ee4078ab3cdd31564e022cd9fccc673a5f2f8509c241b4771646a4e72753  budget_app/__main__.py
0cb00a1323d1945aa0e71486ffebaf612fde2efe434f13182806c00515b3605c  budget_app/__init__.py
SUMS
if grep -nE "TMPDIR|tempfile|임시" budget_app/decorators.py; then fail "S0 decorators.py 에 TMPDIR/tempfile/임시 (5단계 S0 규칙: 주석에도 쓰지 않음)"; fi
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
                bad.append((m, "signal 모듈 사용 금지 (SIGPIPE 를 기본 동작으로 되돌리지 않음)"))
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
# S6 decorators.py 구조 (설계서 3.2 골격과 문장 단위 비교)
python3 - <<'PY' || fail "S6 decorators.py 구조"
import ast, sys
U = ast.unparse
def body(fn):                                     # docstring 을 뺀 문장 목록
    b = fn.body
    if b and isinstance(b[0], ast.Expr) and isinstance(b[0].value, ast.Constant) and isinstance(b[0].value.value, str):
        b = b[1:]
    return b
def exc_names(t):
    return [h.type.id if isinstance(h.type, ast.Name) else (U(h.type) if h.type else None) for h in t.handlers]
def wrapper_of(fn):
    ws = [n for n in fn.body if isinstance(n, ast.FunctionDef) and n.name == "wrapper"]
    if len(ws) != 1: return None
    return ws[0] if any(isinstance(d, ast.Call) and U(d.func) == "functools.wraps" for d in ws[0].decorator_list) else None
def none_guard(s):                                # if sys.stdout is None: return
    return (isinstance(s, ast.If) and U(s.test) == "sys.stdout is None" and len(s.body) == 1
            and isinstance(s.body[0], ast.Return) and s.body[0].value is None and not s.orelse)
tree = ast.parse(open("budget_app/decorators.py", encoding="utf-8").read())
fs = {n.name: n for n in tree.body if isinstance(n, ast.FunctionDef)}
bad = []
if "handle_broken_pipe" not in (ast.get_docstring(tree) or ""):
    bad.append("모듈 docstring 에 handle_broken_pipe 언급이 없음 (설계서 3.2)")
order = [n.name for n in tree.body if isinstance(n, ast.FunctionDef)]
if order != ["print_error", "_discard_stdout", "_flush_stdout", "handle_errors", "handle_broken_pipe"]:
    bad.append(f"함수 목록/순서 {order}")
consts = {U(n.target): U(n.value) for n in tree.body if isinstance(n, ast.AnnAssign) and n.value is not None}
if consts.get("EXIT_OK") != "0" or consts.get("EXIT_ERROR") != "1":
    bad.append("EXIT_OK = 0, EXIT_ERROR = 1 이 바뀜")
ds = fs.get("_discard_stdout")
b = body(ds) if ds else []
if not (len(b) == 4 and none_guard(b[0]) and [U(s) for s in b[1:]] == [
        "devnull = os.open(os.devnull, os.O_WRONLY)", "os.dup2(devnull, sys.stdout.fileno())", "os.close(devnull)"]):
    bad.append("_discard_stdout 본문이 설계서 3.2 와 다름 (None 확인 + devnull dup2 세 줄)")
fl = fs.get("_flush_stdout")
b = body(fl) if fl else []
t = b[1] if len(b) == 2 and isinstance(b[1], ast.Try) else None
if not (t is not None and none_guard(b[0]) and [U(s) for s in t.body] == ["sys.stdout.flush()"]
        and exc_names(t) == ["BrokenPipeError", "OSError"]
        and len(t.handlers[0].body) == 1 and isinstance(t.handlers[0].body[0], ast.Raise) and t.handlers[0].body[0].exc is None
        and len(t.handlers[1].body) == 1 and isinstance(t.handlers[1].body[0], ast.Pass)
        and not t.orelse and not t.finalbody):
    bad.append("_flush_stdout 본문이 설계서 3.2 와 다름 (None 확인 / flush / BrokenPipeError 는 raise / 다른 OSError 는 pass)")
he = fs.get("handle_errors")
w = wrapper_of(he) if he else None
if w is None or not (len(body(w)) == 2 and isinstance(body(w)[0], ast.Try) and U(body(w)[1]) == "return EXIT_ERROR"):
    bad.append("handle_errors wrapper 는 try 하나 + return EXIT_ERROR 여야 함 (기존 구조)")
else:
    t = body(w)[0]
    if [U(s) for s in t.body] != ["return func(*args, **kwargs)"] or t.orelse or t.finalbody:
        bad.append("handle_errors 의 try 본문/else/finally 가 바뀜 (flush 등을 넣지 않음)")
    want = ["KeyboardInterrupt", "EOFError", "BudgetAppError", "UnicodeDecodeError", "BrokenPipeError", "OSError", "Exception"]
    if exc_names(t) != want:
        bad.append(f"handle_errors except 순서 {exc_names(t)} != {want}")
    else:
        bp = t.handlers[4]
        if bp.name is not None or [U(s) for s in bp.body] != ["_discard_stdout()"]:
            bad.append("handle_errors 의 BrokenPipeError 분기는 `except BrokenPipeError:` + _discard_stdout() 한 줄이어야 함")
hb = fs.get("handle_broken_pipe")
w = wrapper_of(hb) if hb else None
ok_hb = False
if w is not None and len(body(w)) == 1 and isinstance(body(w)[0], ast.Try):
    t = body(w)[0]
    inner = t.body[0] if len(t.body) == 1 and isinstance(t.body[0], ast.Try) else None
    ok_hb = (exc_names(t) == ["BrokenPipeError"] and t.handlers[0].name is None
             and [U(s) for s in t.handlers[0].body] == ["_discard_stdout()", "return EXIT_ERROR"]
             and not t.orelse and not t.finalbody and inner is not None
             and [U(s) for s in inner.body] == ["return func(*args, **kwargs)"] and not inner.handlers
             and not inner.orelse and [U(s) for s in inner.finalbody] == ["_flush_stdout()"])
if not ok_hb or [U(s) for s in body(hb)][-1:] != ["return wrapper"]:
    bad.append("handle_broken_pipe 가 설계서 3.2 골격과 다름 (try/finally _flush_stdout + except BrokenPipeError)")
nprint = sum(1 for n in ast.walk(tree) if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == "print")
if nprint != 4: bad.append(f"decorators.py 의 print 호출 {nprint}개 (기존 4개 그대로여야 함, 새 출력 금지)")
for m in ("models", "storage", "services", "decorators", "cli", "__main__", "__init__"):
    tr = ast.parse(open(f"budget_app/{m}.py", encoding="utf-8").read())
    calls = [U(n) for n in ast.walk(tr) if isinstance(n, ast.Call)]
    nflush, ndup = calls.count("sys.stdout.flush()"), sum(c.startswith("os.dup2(") for c in calls)
    if (nflush, ndup) != ((1, 1) if m == "decorators" else (0, 0)):
        bad.append(f"{m}: sys.stdout.flush() {nflush}회, os.dup2 {ndup}회 (decorators 에만 각 1회)")
    if m in ("models", "storage", "services"):
        names = {n.id for n in ast.walk(tr) if isinstance(n, ast.Name)} | {n.attr for n in ast.walk(tr) if isinstance(n, ast.Attribute)}
        hit = names & {"BrokenPipeError", "dup2", "devnull", "stdout"}
        if hit: bad.append(f"{m}.py 에 파이프 처리 코드 {sorted(hit)} (변경 금지 파일)")
print(*bad, sep="\n") if bad else None
sys.exit(1 if bad else 0)
PY
# S7 cli.py 구조
python3 - <<'PY' || fail "S7 cli.py 구조"
import ast, sys
U = ast.unparse
src = open("budget_app/cli.py", encoding="utf-8").read()
tree = ast.parse(src)
bad = []
mains = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "main"]
if len(mains) != 1:
    bad.append("main 없음")
else:
    m = mains[0]
    if [U(d) for d in m.decorator_list] != ["handle_broken_pipe"]:
        bad.append(f"main 의 데코레이터 {[U(d) for d in m.decorator_list]} != ['handle_broken_pipe']")
    if [U(s) for s in m.body] != ["args = build_parser().parse_args(argv)", "return args.handler(args)"]:
        bad.append("main 본문이 바뀜 (5단계 그대로 2줄)")
imp = [n for n in tree.body if isinstance(n, ast.ImportFrom) and n.module == "budget_app.decorators"]
names = sorted(a.name for n in imp for a in n.names)
if names != ["EXIT_OK", "handle_broken_pipe", "handle_errors", "print_error"]:
    bad.append(f"decorators 에서 import 하는 이름 {names}")
nprint = sum(1 for n in ast.walk(tree) if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == "print")
if nprint != 14: bad.append(f"cli.py 의 print 호출 {nprint}개 (5단계 14개 그대로여야 함)")
used = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)} | {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)}
hit = used & {"BrokenPipeError", "flush", "dup2", "devnull", "stdout"}
if hit: bad.append(f"cli.py 코드에 파이프 처리 {sorted(hit)} (decorators.py 에서만 처리)")
if "정렬용 임시 폴더" not in src:
    bad.append("_cmd_search 의 closing 주석에 '정렬용 임시 폴더' 가 없음 (설계서 3.5 [주석 8])")
print(*bad, sep="\n") if bad else None
sys.exit(1 if bad else 0)
PY
# S8 decorators.py 기존 문구 그대로
python3 - <<'PY' || fail "S8 decorators.py 기존 문구가 바뀜"
src = open("budget_app/decorators.py", encoding="utf-8").read()
must = [
    'print(f"[오류] {cause}", file=sys.stderr)',
    'print(f"[힌트] {hint}", file=sys.stderr)',
    '"사용자가 입력을 중단했습니다 (Ctrl+C)"',
    '"저장되지 않았습니다. 명령을 처음부터 다시 실행하세요"',
    '"입력이 끝나 더 읽을 값이 없습니다 (EOF)"',
    '"모든 항목을 입력하세요. 표준입력으로 넣을 때는 항목마다 한 줄씩 넣으세요"',
    'f"UTF-8 로 읽을 수 없는 데이터가 있습니다 ({e.reason})"',
    '"--data-dir 폴더의 .jsonl 파일과 입력이 UTF-8 인코딩인지 확인하세요"',
    'f"파일을 읽거나 쓸 수 없습니다: {e}"',
    'f"파일을 읽거나 쓸 수 없습니다: {e.filename} ({e.strerror})"',
    '"경로(--data-dir, --from, --out)가 올바른지, 해당 파일·폴더에 읽기/쓰기 권한이 있는지 확인하세요"',
    'f"예상하지 못한 오류가 발생했습니다: {type(e).__name__}: {e}"',
    '"입력값과 --data-dir 폴더의 파일을 확인한 뒤 다시 실행하세요"',
]
miss = [s for s in must if s not in src]
print(*miss, sep="\n") if miss else None
raise SystemExit(1 if miss else 0)
PY
# S9 README
grep -qxF '출력을 받는 프로그램이 먼저 끝나면(예: `| head -1` 로 앞부분만 볼 때) 남은 출력은 버리고 `[오류]` 없이 종료 코드 1 로 끝납니다. 그때까지 저장·삭제한 내용은 그대로 남습니다.' README.md || fail "S9 README 에 파이프 끊김 설명 줄(설계서 3.4)이 없음"

# ======================= F. 시험 데이터 준비 =======================
python - <<'PY' || FAIL=1
import json, os, subprocess, sys
P = os.path.join(os.environ["W"], "pipe"); os.makedirs(P)
APP = [sys.executable, "-m", "budget_app"]
def tx(i, type_, date, cat, amount, memo):
    return {"id": f"TX-{i:06d}", "type": type_, "date": date, "amount": amount, "category": cat, "memo": memo, "tags": []}
def make(name, rows):
    d = os.path.join(P, name)
    subprocess.run(APP + ["category", "list", "--data-dir", d], capture_output=True, check=True)   # 저장 파일 3개 + 기본 카테고리
    with open(os.path.join(d, "transactions.jsonl"), "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
SMALL = [tx(1, "expense", "2024-01-10", "food", 12000, "점심"),
         tx(2, "expense", "2024-01-11", "transport", 3000, "버스"),
         tx(3, "income", "2024-01-12", "rent", 500000, "용돈")]          # etc 는 쓰지 않음 (category remove 용)
make("small", SMALL)
make("mod", SMALL)
make("empty", [])
make("big", [tx(i, "expense", f"2024-{i % 12 + 1:02d}-{i % 28 + 1:02d}", "food", i % 997 + 1, f"메모 {i}")
             for i in range(1, 60_001)])                                 # 약 3.3MB 출력, search 는 외부 정렬(조각 60개)
with open(os.path.join(P, "in.csv"), "w", encoding="utf-8") as f:
    f.write("date,type,category,amount,memo,tags\n2024-01-20,expense,food,1000,가져옴,\n")
PY

# ======================= E. 다른 오류 문구 그대로 (같은 프로세스) =======================
python - <<'PY' || FAIL=1
import contextlib, errno, io, sys
from budget_app.decorators import handle_errors
from budget_app.models import BudgetAppError
OS_HINT = "[힌트] 경로(--data-dir, --from, --out)가 올바른지, 해당 파일·폴더에 읽기/쓰기 권한이 있는지 확인하세요\n"
cases = [
    ("KeyboardInterrupt", KeyboardInterrupt(),
     "\n[오류] 사용자가 입력을 중단했습니다 (Ctrl+C)\n[힌트] 저장되지 않았습니다. 명령을 처음부터 다시 실행하세요\n"),
    ("EOFError", EOFError(),
     "\n[오류] 입력이 끝나 더 읽을 값이 없습니다 (EOF)\n[힌트] 모든 항목을 입력하세요. 표준입력으로 넣을 때는 항목마다 한 줄씩 넣으세요\n"),
    ("BudgetAppError", BudgetAppError("원인 A", "힌트 B"), "[오류] 원인 A\n[힌트] 힌트 B\n"),
    ("UnicodeDecodeError", UnicodeDecodeError("utf-8", b"\xff", 0, 1, "invalid start byte"),
     "[오류] UTF-8 로 읽을 수 없는 데이터가 있습니다 (invalid start byte)\n"
     "[힌트] --data-dir 폴더의 .jsonl 파일과 입력이 UTF-8 인코딩인지 확인하세요\n"),
    ("OSError(파일 이름 없음)", OSError(errno.EIO, "Input/output error"),
     f"[오류] 파일을 읽거나 쓸 수 없습니다: [Errno {errno.EIO}] Input/output error\n" + OS_HINT),
    ("PermissionError(파일 이름 있음)", PermissionError(errno.EACCES, "Permission denied", "/x/y"),
     "[오류] 파일을 읽거나 쓸 수 없습니다: /x/y (Permission denied)\n" + OS_HINT),
    ("ConnectionResetError(BrokenPipe 아닌 OSError)", ConnectionResetError(errno.ECONNRESET, "Connection reset by peer"),
     f"[오류] 파일을 읽거나 쓸 수 없습니다: [Errno {errno.ECONNRESET}] Connection reset by peer\n" + OS_HINT),
    ("Exception", ValueError("x"),
     "[오류] 예상하지 못한 오류가 발생했습니다: ValueError: x\n[힌트] 입력값과 --data-dir 폴더의 파일을 확인한 뒤 다시 실행하세요\n"),
]
ok = True
for label, exc, want in cases:
    @handle_errors
    def boom() -> int:
        raise exc
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        try:
            rc = boom()
        except BaseException as e:                  # 밖으로 새면 실제 실행에서는 스택트레이스가 나온다
            rc = f"예외 누출 {type(e).__name__}"
    if rc != 1 or out.getvalue() != "" or err.getvalue() != want:
        ok = False
        print(f"FAIL E {label}: rc={rc!r} out={out.getvalue()!r} err={err.getvalue()!r}")
print("ERROR_TEXT_OK" if ok else "ERROR_TEXT_FAIL")
sys.exit(0 if ok else 1)
PY

# ======================= N. 끊기지 않은 정상 실행 =======================
python - <<'PY' || FAIL=1
import glob, os, subprocess, sys
P = os.path.join(os.environ["W"], "pipe")
S, PD, EMPTY = (os.path.join(P, n) for n in ("small", "big", "empty"))
APP = [sys.executable, "-m", "budget_app"]
ok = True
def need(cond, msg):
    global ok
    if not cond:
        print("FAIL", msg); ok = False
def run(args):
    r = subprocess.run(APP + args, capture_output=True, text=True, timeout=300)   # 파이프를 끝까지 읽음 = 끊기지 않음
    return r.returncode, r.stdout, r.stderr
EXPECT = [
    (["list", "--data-dir", S],
     "TX-000003 | 2024-01-12 | income | rent | 500000 | 용돈\n"
     "TX-000002 | 2024-01-11 | expense | transport | 3000 | 버스\n"
     "TX-000001 | 2024-01-10 | expense | food | 12000 | 점심\n"),
    (["list", "--data-dir", EMPTY], "거래 내역이 없습니다.\n"),
    (["search", "--category", "food", "--data-dir", S], "TX-000001 | 2024-01-10 | expense | food | 12000 | 점심\n"),
    (["search", "--tag", "없는태그", "--data-dir", S], "조건에 맞는 거래가 없습니다.\n"),
    (["summary", "--month", "2024-01", "--data-dir", S],
     "총 수입: 500000원\n총 지출: 15000원\n잔액: 485000원\n지출 TOP 3\n1) food 12000원\n2) transport 3000원\n"),
    (["category", "list", "--data-dir", S], "- food\n- transport\n- rent\n- etc\n"),
]
for args, want in EXPECT:
    rc, out, err = run(args)
    need(rc == 0 and err == "" and out == want, f"N {' '.join(args[:2])}: rc={rc} out={out!r} err={err!r}")
for h in (["--help"], ["search", "--help"]):
    rc, out, err = run(h)
    need(rc == 0 and err == "" and out.startswith("usage: python -m budget_app"), f"N {h}: rc={rc} err={err!r}")
rc1, out1, err1 = run(["list", "--limit", "100000", "--data-dir", PD])
rc2, out2, err2 = run(["search", "--category", "food", "--data-dir", PD])
need(rc1 == 0 and rc2 == 0 and err1 == "" and err2 == "", f"N 대량: rc={rc1},{rc2} err={err1[-200:]!r} {err2[-200:]!r}")
need(len(out1.splitlines()) == 60_000 and out1 == out2, "N 대량: 줄 수 != 60000 이거나 list 와 search(외부 정렬) 출력이 다름")
left = glob.glob(os.path.join(os.environ["TMPDIR"], "budget_app_search_*"))
need(left == [], f"N 대량 search 뒤 임시 폴더가 남음: {left}")
print("NORMAL_OK" if ok else "NORMAL_FAIL")
sys.exit(0 if ok else 1)
PY

# ======================= P. 읽는 쪽이 이미 닫힌 파이프 (항상 끊김, 타이밍 무관) =======================
python - <<'PY' || FAIL=1
import glob, os, subprocess, sys
P = os.path.join(os.environ["W"], "pipe")
S, M, PD, EMPTY = (os.path.join(P, n) for n in ("small", "mod", "big", "empty"))
CSV, OUT = os.path.join(P, "in.csv"), os.path.join(P, "out.csv")
SYS = os.environ["TMPDIR"]
APP = [sys.executable, "-m", "budget_app"]
ok = True
def need(cond, msg):
    global ok
    if not cond:
        print("FAIL", msg); ok = False
def normal(args, stdin=""):
    r = subprocess.run(APP + args, input=stdin, capture_output=True, text=True, timeout=300)
    return r.returncode, r.stdout, r.stderr
def closed(args, stdin=""):
    rfd, wfd = os.pipe()
    os.close(rfd)                                  # 출력 받는 프로그램이 이미 끝난 상태: 첫 쓰기부터 EPIPE
    try:
        r = subprocess.run(APP + args, input=stdin, stdout=wfd, stderr=subprocess.PIPE, text=True, timeout=300)
    finally:
        os.close(wfd)
    return r.returncode, r.stderr
def leftovers():
    return glob.glob(os.path.join(SYS, "budget_app_search_*"))
# P1 성공하는 출력 명령: 끊기면 출력 없이 1
READ = [
    ("--help", ["--help"]),
    ("list --help", ["list", "--help"]),
    ("search --help", ["search", "--help"]),
    ("budget set --help", ["budget", "set", "--help"]),
    ("category add --help", ["category", "add", "--help"]),
    ("list 소량", ["list", "--data-dir", S]),
    ("list 0건", ["list", "--data-dir", EMPTY]),
    ("list 대량", ["list", "--limit", "100000", "--data-dir", PD]),
    ("search 소량", ["search", "--category", "food", "--data-dir", S]),
    ("search 0건", ["search", "--tag", "없는태그", "--data-dir", S]),
    ("search 대량(외부 정렬)", ["search", "--category", "food", "--data-dir", PD]),
    ("summary", ["summary", "--month", "2024-01", "--data-dir", S]),
    ("category list", ["category", "list", "--data-dir", S]),
]
for label, args in READ:
    rc0, _, err0 = normal(args)
    need(rc0 == 0 and err0 == "", f"P1 {label}: 끊기지 않은 실행이 실패함 rc={rc0} err={err0[-200:]!r}")
    rc, err = closed(args)
    need(rc == 1 and err == "", f"P1 {label}: 종료 코드 {rc} (기대 1), stderr={err[-400:]!r}")
    need(leftovers() == [], f"P1 {label}: search 임시 폴더가 남음 {leftovers()}")
# P2 데이터를 바꾸는 명령: 끊기면 출력 없이 1, 이미 저장·삭제한 내용은 그대로
MOD = [
    ("budget set", ["budget", "set", "--month", "2024-01", "--amount", "50000", "--data-dir", M], ""),
    ("update", ["update", "--id", "TX-000001", "--memo", "바뀜", "--data-dir", M], ""),
    ("delete", ["delete", "--id", "TX-000002", "--data-dir", M], ""),
    ("import", ["import", "--from", CSV, "--data-dir", M], ""),
    ("export", ["export", "--out", OUT, "--month", "2024-01", "--data-dir", M], ""),
    ("add", ["add", "--data-dir", M], "2024-01-25\nexpense\nfood\n2000\n저녁\n\n"),
    ("category add", ["category", "add", "--data-dir", M], "hobby\n"),
    ("category remove", ["category", "remove", "--data-dir", M], "etc\n"),
]
for label, args, stdin in MOD:
    rc, err = closed(args, stdin)
    need(rc == 1 and err == "", f"P2 {label}: 종료 코드 {rc} (기대 1), stderr={err[-400:]!r}")
rc, out, _ = normal(["summary", "--month", "2024-01", "--data-dir", M])
need(rc == 0 and "예산: 50000원" in out, f"P2 budget set 결과가 저장되지 않음: {out!r}")
rc, out, _ = normal(["list", "--data-dir", M])
lines = out.splitlines()
need(any(l.startswith("TX-000001 ") and l.endswith("| 바뀜") for l in lines), "P2 update 결과가 저장되지 않음")
need(not any(l.startswith("TX-000002 ") for l in lines), "P2 delete 결과가 저장되지 않음")
need(any(l.endswith("| 가져옴") for l in lines), "P2 import 결과가 저장되지 않음")
with open(OUT, encoding="utf-8") if os.path.exists(OUT) else open(os.devnull, encoding="utf-8") as f:
    head = f.readline().rstrip("\r\n")
need(head == "date,type,category,amount,memo,tags", "P2 export 파일이 만들어지지 않음")
# P3 오류 명령: stdout 이 닫혀 있어도 종료 코드와 stderr 문구가 끊기지 않았을 때와 완전히 같음
ERR = [
    ("조건 없는 search", ["search", "--data-dir", S], 1),
    ("list --limit 0", ["list", "--limit", "0", "--data-dir", S], 1),
    ("summary 잘못된 월", ["summary", "--month", "2024-13", "--data-dir", S], 1),
    ("update 없는 id", ["update", "--id", "TX-999999", "--memo", "x", "--data-dir", S], 1),
    ("없는 옵션", ["list", "--bogus", "--data-dir", S], 2),
    ("-h", ["-h"], 2),
    ("명령 없음", [], 2),
]
for label, args, want in ERR:
    rc0, out0, err0 = normal(args)
    rc1, err1 = closed(args)
    need(rc0 == want and rc1 == want, f"P3 {label}: 종료 코드 {rc0}/{rc1} (기대 {want})")
    need(out0 == "" and err0.count("[오류]") == 1 and err0.count("[힌트]") == 1, f"P3 {label}: 기존 오류 출력 형식이 아님 {err0!r}")
    need(err1 == err0, f"P3 {label}: stdout 이 닫혔을 때 오류 문구가 달라짐 {err1!r} != {err0!r}")
need(leftovers() == [], f"P 끝: search 임시 폴더가 남음 {leftovers()}")
print("PIPE_OK" if ok else "PIPE_FAIL")
sys.exit(0 if ok else 1)
PY

# ======================= H. 실제 파이프 | head -n 1 (bash PIPESTATUS) =======================
P="$W/pipe"; PD="$P/big"; S="$P/small"; HF=0
hfail() { HF=1; fail "$@"; }
# hcheck <라벨> <허용 종료 코드: "1" 또는 "0 1"> <budget_app 인자...>
hcheck() {
  local label=$1 want=$2; shift 2
  python -m budget_app "$@" >"$P/full" 2>"$P/ferr"
  local frc=$?
  { [ "$frc" = 0 ] && [ ! -s "$P/ferr" ]; } || hfail "H $label: 끊기지 않은 실행이 실패함 rc=$frc"
  python -m budget_app "$@" 2>"$P/err" | head -n 1 >"$P/head"
  local rc="${PIPESTATUS[0]}"
  case " $want " in *" $rc "*) ;; *) hfail "H $label: 종료 코드 $rc (허용: $want)" ;; esac
  if [ -s "$P/err" ]; then hfail "H $label: stderr 가 비어 있지 않음"; cat "$P/err"; fi
  [ "$(cat "$P/head")" = "$(head -n 1 "$P/full")" ] || hfail "H $label: head 가 받은 줄이 끊기지 않은 실행의 첫 줄과 다름"
  local left
  left="$(find "$TMPDIR" -maxdepth 1 -name 'budget_app_search_*')"
  [ -z "$left" ] || hfail "H $label: search 임시 폴더가 남음: $left"
}
hcheck "list 대량"              1     list --limit 100000 --data-dir "$PD"
hcheck "search 대량(외부 정렬)" 1     search --category food --data-dir "$PD"
hcheck "summary"                "0 1" summary --month 2024-01 --data-dir "$S"
hcheck "category list"          "0 1" category list --data-dir "$S"
hcheck "--help"                 "0 1" --help
hcheck "search --help"          "0 1" search --help
# 오류는 파이프여도 그대로 stderr 로 나온다
python -m budget_app search --data-dir "$S" 2>"$P/err" | head -n 1 >"$P/head"
rc="${PIPESTATUS[0]}"
if [ "$rc" = 1 ] && [ ! -s "$P/head" ] && [ "$(grep -c '^\[오류\]' "$P/err")" = 1 ] && [ "$(grep -c '^\[힌트\]' "$P/err")" = 1 ]; then :; else
  hfail "H 조건 없는 search | head: rc=$rc"; cat "$P/err"
fi
[ "$HF" = 0 ] && echo "HEAD_OK"

# ======================= Z. stdout 을 아예 닫고 실행 (>&-, sys.stdout 이 None) =======================
# 기대 종료 코드는 6단계 이전 값 그대로: list 0, --help 0, 없는 옵션 2, 없는 id 1, budget set 0
ZF=0
zfail() { ZF=1; fail "$@"; }
# zcheck <라벨> <기대 종료 코드> <[오류]/[힌트] 줄 수> <budget_app 인자...>
zcheck() {
  local label=$1 want=$2 nerr=$3; shift 3
  python -m budget_app "$@" >&- 2>"$P/zerr"
  local rc=$?
  [ "$rc" = "$want" ] || zfail "Z $label: 종료 코드 $rc (기대 $want, 6단계 이전 값)"
  if grep -qE "Traceback|Exception ignored|AttributeError" "$P/zerr"; then zfail "Z $label: 파이썬 원문 오류가 나옴"; cat "$P/zerr"; fi
  if [ "$(grep -c '^\[오류\]' "$P/zerr")" = "$nerr" ] && [ "$(grep -c '^\[힌트\]' "$P/zerr")" = "$nerr" ]; then :; else
    zfail "Z $label: [오류]/[힌트] 줄 수 != $nerr"; cat "$P/zerr"
  fi
}
zcheck "list"       0 0 list --data-dir "$S"
zcheck "--help"     0 0 --help
zcheck "없는 옵션"  2 1 list --bogus --data-dir "$S"
zcheck "없는 id"    1 1 update --id TX-999999 --memo x --data-dir "$S"
zcheck "budget set" 0 0 budget set --month 2024-02 --amount 70000 --data-dir "$P/mod"
python -m budget_app summary --month 2024-02 --data-dir "$P/mod" >"$P/zsum" 2>&1
grep -qF "예산: 70000원" "$P/zsum" || { zfail "Z budget set: >&- 로 실행한 저장 결과가 없음"; cat "$P/zsum"; }
[ "$ZF" = 0 ] && echo "CLOSED_STDOUT_OK"

# ======================= R. 1~5단계 회귀 (5단계 스크립트 → 4단계 → 3단계 → 1·2단계) =======================
# 5단계 설계서 6.2 스크립트를 꺼내 임시 폴더(W) 줄 하나만 $W 아래로 바꾼다.
# __main__.py 를 바꾸지 않으므로 해시 기대값 치환은 없다 (설계서 6.1).
python3 - <<'PY' || FAIL=1
import os
W = os.environ["W"]
FENCE = "`" * 3                                  # 설계서 코드 블록이 끊기지 않도록 백틱 3개를 직접 쓰지 않는다
sec = open("docs/plans/step5-search-external-sort.md", encoding="utf-8").read().split("### 6.2", 1)[1]
s5 = sec.split(FENCE + "bash\n", 1)[1].split(FENCE, 1)[0]
old_w = 'W="$(mktemp -d)"; export W'
assert s5.count(old_w) == 2 and s5.index(old_w) < s5.index("# ======================= S. 정적 검사"), "5단계 스크립트의 W 줄을 찾지 못함"
s5 = s5.replace(old_w, 'W="$(mktemp -d "$W/s5.XXXXXX")"; export W', 1)   # 첫 줄만 (R 절 안의 같은 문자열은 그대로)
open(os.path.join(W, "step5.sh"), "w", encoding="utf-8").write(s5)
PY
bash "$W/step5.sh" >"$W/r5" 2>&1
if grep -qx "STEP5_ALL_OK" "$W/r5" && ! grep -q "^FAIL" "$W/r5"; then :; else echo "FAIL 1~5단계 회귀"; cat "$W/r5"; FAIL=1; fi
grep -E "^  (searchN|search10|control) " "$W/r5"     # 5단계 M절 측정값 (보고용)

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
[ "$FAIL" = 0 ] && echo "STEP6_ALL_OK"
```

**기대 출력**
- `FAIL` 로 시작하는 줄이 없어야 한다.
- `ERROR_TEXT_OK`, `NORMAL_OK`, `PIPE_OK`, `HEAD_OK`, `CLOSED_STDOUT_OK`, 5단계 M절 측정값 6줄, 마지막 줄 `STEP6_ALL_OK` 가 나와야 한다.
- 스크립트가 끝나면 `$W` 는 지워져 있어야 한다(`trap`).

**결함 감지 확인 (에이전트 3 참고)**: 다음 상태의 코드로 이 스크립트를 돌리면 해당 절이 FAIL 이어야 한다. 그래야 검사가 의미 있다는 증거가 된다.
- 변경 전 코드(5단계 상태):
  - P1 의 대량 출력에서 `[오류] 파일을 읽거나 쓸 수 없습니다: [Errno 32] Broken pipe` 가 나와 stderr 가 비지 않는다.
  - P1 의 소량 출력과 `--help` 에서 `Exception ignored` 가 나오고 종료 코드가 120 이다.
  - S6·S7 구조 검사가 실패한다.
- 개정 전 6단계 초안 코드(`None` 확인 없음): Z절의 모든 명령에서 `AttributeError` 스택트레이스가 나온다.

이 확인은 필수가 아니다. 할 때는 코드를 고치지 말고 별도 복사본에서만 한다.

## 7. 총괄 확인 필요

1. **처리 위치**: 지시는 "decorators.py, 필요하면 `__main__.py`" 였다. 이 설계는 핸들러 밖 끊김을 `__main__.py` 대신 `cli.main` 에 데코레이터(`handle_broken_pipe`)를 붙여 처리한다(3.0). 이유는 두 가지다. `__main__` 은 계층 규칙상 decorators 를 import 할 수 없다. 또 `__main__` 해시가 3·4·5단계 검사에 고정되어 있다. 덕분에 `__main__.py` 는 바뀌지 않고 회귀 해시 치환도 필요 없다. `__main__.py` 쪽을 원하면 6.1 참고 문단의 치환 세 곳과 코드 중복이 생긴다.
2. **저장은 끝났는데 종료 코드 1**: budget set, update, delete, import, export(그리고 대화형 add 등)는 완료 문구만 못 내도 1 로 끝난다. 사용자 확정("0 이 아닌 값")을 그대로 적용했고, README 에 "저장·삭제한 내용은 그대로 남는다"고 적었다.
3. **범위 밖으로 둔 두 경우**: 둘 다 이번 지시("다른 오류 처리는 하나도 바뀌지 않는다")에 따라 손대지 않았고, 고치려면 별도 단계가 필요하다.
   - stderr 쪽 파이프 끊김(`2>&1 | head -1` 로 `[오류]` 줄 사이가 끊김): 보이는 출력은 없고 종료 코드는 1 또는 120 이다.
   - stdout 의 다른 쓰기 오류(디스크 가득 참): 기존 동작 그대로라 파이썬 원문 `Exception ignored … OSError` 가 나올 수 있다.
4. **"export 이외 출력 명령" 해석**: 닫힌 파이프 검사(P)는 export 를 포함한 12개 명령 전부와 `--help` 를 대상으로 했다. 실제 `| head -n 1` 검사(H)는 출력이 여러 줄인 list·search·summary·category list·`--help` 만 대상으로 했다.
5. **storage.py·services.py 변경 금지의 해시 고정**: 설계 단계에서는 SHA-256 을 계산할 수 없어 S0 에는 알려진 3개 파일만 넣었다. 두 파일은 S6(파이프 처리 코드 없음)과 5단계 회귀(S6/S7 구조, A·B·C 동작)로 확인한다. 엄격히 고정하려면 총괄이 착수 전 `shasum -a 256 budget_app/storage.py budget_app/services.py` 값을 주면 S0 에 추가한다.
