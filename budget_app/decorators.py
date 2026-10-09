"""[공통 관심사] 명령 핸들러의 예외를 [오류]/[힌트] 메시지와 종료 코드로 바꾸는 데코레이터와, 출력이 끊겨도 main 을 조용히 끝내는 데코레이터(handle_broken_pipe)."""

import functools
import os
import sys
from collections.abc import Callable
from typing import ParamSpec

from budget_app.models import BudgetAppError

EXIT_OK: int = 0
EXIT_ERROR: int = 1

# ParamSpec: 데코레이터로 감싼 뒤에도 원래 함수의 매개변수 타입 정보가 그대로 유지되게 한다.
P = ParamSpec("P")


def print_error(cause: str, hint: str) -> None:
    """stderr 에 [오류] 원인, [힌트] 해결 방법 두 줄을 출력한다."""
    print(f"[오류] {cause}", file=sys.stderr)
    print(f"[힌트] {hint}", file=sys.stderr)


# 출력을 받는 쪽(예: head)이 먼저 닫히면 버퍼에 남은 글자를 보낼 곳이 없다. 그대로 두면 파이썬이
# 끝날 때 다시 보내려다 실패해 영어 원문 경고를 내고 종료 코드를 120 으로 바꾼다. 그래서 stdout 을
# 운영체제의 "버리는 곳"(os.devnull)에 다시 연결해 남은 글자가 조용히 버려지게 한다(파이썬 공식 문서 권장 방법).
def _discard_stdout() -> None:
    if sys.stdout is None:
        # >&- 처럼 stdout 이 아예 닫힌 채 실행되면 파이썬은 sys.stdout 을 None 으로 둔다.
        # 내보낼 곳도 바꿔 끼울 곳도 없으니 아무것도 하지 않는다(확인하지 않으면 None.fileno() 오류가 난다).
        return
    devnull = os.open(os.devnull, os.O_WRONLY)
    os.dup2(devnull, sys.stdout.fileno())
    os.close(devnull)


# 버퍼에 모아 둔 출력을 지금 내보낸다. 파이썬이 끝날 때 알아서 내보내다 나는 오류는 우리 코드가
# 잡을 수 없으므로, 잡을 수 있는 곳에서 먼저 내보낸다.
def _flush_stdout() -> None:
    if sys.stdout is None:
        # >&- 처럼 stdout 이 아예 닫힌 채 실행되면 파이썬은 sys.stdout 을 None 으로 둔다.
        # 내보낼 곳도 바꿔 끼울 곳도 없으니 아무것도 하지 않는다(확인하지 않으면 None.flush() 오류가 난다).
        return
    try:
        sys.stdout.flush()
    except BrokenPipeError:
        raise
    except OSError:
        # 디스크가 꽉 찬 경우 같은 다른 쓰기 오류는 이번에 동작을 바꾸지 않는다.
        # 남은 글자는 버퍼에 그대로 있어 파이썬이 끝날 때 다시 시도하므로 결과가 전과 같다.
        pass


# 데코레이터: 모든 명령 핸들러에 똑같이 필요한 "예외 → 한국어 메시지 + 종료 코드" 변환을
# 핸들러마다 try/except 로 반복해 쓰지 않고, 이 함수 하나로 감싸서 한 곳에서 처리한다.
# 덕분에 어떤 명령에서 오류가 나도 스택트레이스 대신 같은 형식의 메시지가 나온다.
def handle_errors(func: Callable[P, int]) -> Callable[P, int]:
    # functools.wraps: 감싼 뒤에도 원래 함수의 이름·설명(docstring)이 유지되게 한다.
    @functools.wraps(func)
    def wrapper(*args: P.args, **kwargs: P.kwargs) -> int:
        try:
            return func(*args, **kwargs)
        except KeyboardInterrupt:
            # KeyboardInterrupt 는 Exception 하위가 아니라서 따로 잡아야 한다.
            print(file=sys.stderr)
            print_error(
                "사용자가 입력을 중단했습니다 (Ctrl+C)",
                "저장되지 않았습니다. 명령을 처음부터 다시 실행하세요",
            )
        except EOFError:
            # Ctrl+D 로 끝나면 프롬프트 줄이 끊기지 않으므로 Ctrl+C 처리와 같이 빈 줄을 먼저 출력한다.
            print(file=sys.stderr)
            print_error(
                "입력이 끝나 더 읽을 값이 없습니다 (EOF)",
                "모든 항목을 입력하세요. 표준입력으로 넣을 때는 항목마다 한 줄씩 넣으세요",
            )
        except BudgetAppError as e:
            print_error(e.cause, e.hint)
        except UnicodeDecodeError as e:
            print_error(
                f"UTF-8 로 읽을 수 없는 데이터가 있습니다 ({e.reason})",
                "--data-dir 폴더의 .jsonl 파일과 입력이 UTF-8 인코딩인지 확인하세요",
            )
        except BrokenPipeError:
            # BrokenPipeError 는 OSError 의 한 종류라서 OSError 보다 먼저 써야 이 분기로 온다.
            # | head 처럼 받는 쪽이 필요한 만큼 읽고 먼저 끝난 것은 사용자 실수가 아니므로
            # [오류]/[힌트] 없이 조용히 끝낸다. 출력을 끝까지 못 했으므로 종료 코드는 1 이다.
            _discard_stdout()
        except OSError as e:
            if e.filename is None:
                cause = f"파일을 읽거나 쓸 수 없습니다: {e}"
            else:
                cause = f"파일을 읽거나 쓸 수 없습니다: {e.filename} ({e.strerror})"
            print_error(
                cause,
                "경로(--data-dir, --from, --out)가 올바른지, 해당 파일·폴더에 읽기/쓰기 권한이 있는지 확인하세요",
            )
        except Exception as e:
            # 최후 수단: 예상하지 못한 오류도 스택트레이스 대신 한 줄 메시지로 보여 준다.
            print_error(
                f"예상하지 못한 오류가 발생했습니다: {type(e).__name__}: {e}",
                "입력값과 --data-dir 폴더의 파일을 확인한 뒤 다시 실행하세요",
            )
        return EXIT_ERROR

    return wrapper


# 데코레이터: handle_errors 는 명령 핸들러 안의 오류만 잡는다. 출력이 적으면 글자가 버퍼에 있다가
# 핸들러가 끝난 뒤에야 나가고, --help 는 핸들러 전에 argparse 가 출력하고 바로 끝난다. 이 경우까지
# 잡으려고 main 전체를 감싼다. SIGPIPE 를 기본 동작으로 되돌리는 방법은 쓰지 않는다. 프로그램이
# 그 자리에서 강제로 끝나 finally 정리(search 의 정렬용 작업 폴더 삭제 등)가 실행되지 않기 때문이다.
def handle_broken_pipe(func: Callable[P, int]) -> Callable[P, int]:
    @functools.wraps(func)
    def wrapper(*args: P.args, **kwargs: P.kwargs) -> int:
        try:
            try:
                return func(*args, **kwargs)
            finally:
                # 정상 반환 때뿐 아니라 --help 의 SystemExit 로 빠져나갈 때도 여기서 내보내야
                # 끊김을 잡을 수 있으므로 finally 에 둔다.
                _flush_stdout()
        except BrokenPipeError:
            _discard_stdout()
            return EXIT_ERROR

    return wrapper
