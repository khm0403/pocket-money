# 용돈 기입장 (budget_app)

터미널에서 쓰는 가계부 프로그램입니다. 수입·지출을 기록하면 파일(JSONL)에 저장되어 프로그램을 껐다 켜도 남아 있습니다.
Python 3.10 이상에서 동작하고, 표준 라이브러리만 사용합니다.

## 실행 방법

- Python 3.10 이상이 필요합니다. 따로 설치할 패키지는 없습니다.
- 프로젝트 루트(이 README.md 가 있는 폴더)에서 아래처럼 실행합니다.

```bash
python -m budget_app <command> [options]
```

- `python` 명령이 없는 환경(예: macOS 기본 설정)에서는 `python3` 을 씁니다.

```bash
python3 --version
python3 -m budget_app list
```

- 도움말: 전체는 `--help`, 명령별로는 명령 뒤에 `--help` 를 붙입니다.

```bash
python -m budget_app --help
python -m budget_app search --help
python -m budget_app category add --help
```

- 옵션은 `--` 로 시작하는 전체 이름만 받습니다. `-h` 나 옵션 이름을 줄여 쓴 것(예: `--limit` 을 줄인 것)은 사용법 오류입니다.
- 데이터 폴더를 바꾸려면 `--data-dir <경로>` 를 **명령 뒤**에 씁니다. 명령 앞에 쓰면 사용법 오류입니다.

```bash
python -m budget_app list --data-dir ./mydata
```

## 저장 파일 위치와 형식

- 기본 폴더는 명령을 실행한 현재 폴더 기준 `./data` 이고, `--data-dir` 로 바꿀 수 있습니다.
- 처음 실행하면 폴더와 파일 3개를 자동으로 만듭니다. (`--help` 나 사용법 오류일 때는 만들지 않습니다.)
- 형식: JSONL(한 줄에 JSON 객체 하나), UTF-8.

| 파일 | 내용 | 한 줄 예 |
| --- | --- | --- |
| `data/transactions.jsonl` | 거래 | `{"id": "TX-000001", "type": "expense", "date": "2024-01-15", "amount": 15000, "category": "food", "memo": "점심", "tags": ["meal"]}` |
| `data/categories.jsonl` | 카테고리 | `{"name": "food"}` |
| `data/budgets.jsonl` | 월 예산 | `{"month": "2024-01", "amount": 500000}` |

- 거래 id 는 `TX-000001` 형식이고, 새 id 는 현재 가장 큰 번호 + 1 입니다.
- **카테고리 파일이 비어 있으면(안 A)** 기본 카테고리 `food, transport, rent, etc` 를 자동으로 만듭니다. 카테고리를 모두 지워 파일이 비면 다음 실행 때 다시 생깁니다.
- 안전한 저장: update, delete, budget set, import 는 임시 파일에 전체 내용을 쓴 뒤 `os.replace` 로 한 번에 바꿉니다. 도중에 멈춰도 원래 파일이 그대로 남습니다. export 결과 파일도 같은 방식으로 만듭니다.
- 파일에 손상된 줄이 있으면 파일 경로와 줄 번호를 알려 주는 오류로 끝납니다.

## 명령 요약

| 명령 | 입력 방식 | 옵션 | 하는 일 |
| --- | --- | --- | --- |
| `add` | 대화형 | 없음 | 거래 추가 |
| `list` | 옵션 | `--limit N` (기본 20) | 최신순 거래 목록 |
| `search` | 옵션 | `--from --to --category --type --q --tag` 중 1개 이상 | 조건 검색 |
| `summary` | 옵션 | `--month` (필수), `--top N` (기본 3) | 월별 요약 |
| `budget set` | 옵션 | `--month --amount` | 월 예산 저장 |
| `category add` / `category remove` | 대화형 (이름 입력) | 없음 | 카테고리 추가 / 삭제 |
| `category list` | 옵션 | 없음 | 카테고리 목록 |
| `update` | **옵션 방식(안 A)** | `--id` (필수) + `--date --type --category --amount --memo --tags` 중 1개 이상 | 거래 수정 |
| `delete` | 옵션 | `--id` | 거래 삭제 |
| `import` | 옵션 | `--from CSV` | CSV 의 거래를 한 번에 추가 |
| `export` | 옵션 | `--out CSV` + (`--month` 또는 `--from`/`--to`) | 조건에 맞는 거래를 CSV 로 저장 |

모든 명령에 `--help` 와 `--data-dir` 를 쓸 수 있습니다.

## 주요 명령 예시

처음 실행이라 `data` 폴더가 아직 없는 상태의 프로젝트 루트에서 아래 순서대로 실행한 실제 화면입니다. 대화형 입력은 프롬프트 뒤에 입력한 값을 함께 적었습니다.

카테고리 목록 확인과 추가:

```console
$ python -m budget_app category list
- food
- transport
- rent
- etc
$ python -m budget_app category add
카테고리명: salary
[저장 완료] category=salary
```

거래 추가 (잘못된 날짜는 오류를 보여 준 뒤 그 항목만 다시 묻습니다):

```console
$ python -m budget_app add
날짜(YYYY-MM-DD): 2024-13-40
[오류] 존재하지 않는 날짜입니다: '2024-13-40'
[힌트] YYYY-MM-DD 형식의 실제 날짜를 입력하세요 (예: 2024-05-01)
날짜(YYYY-MM-DD): 2024-01-15
타입(income/expense): expense
카테고리: food
금액(양수): 15000
메모(선택): 점심
태그(쉼표로 구분, 없으면 엔터): meal
[저장 완료] id=TX-000001
```

CSV 가져오기: 먼저 아래 "import/export CSV 스키마" 절의 예시 내용을 프로젝트 루트에 `import.csv` 파일로 저장한 뒤 실행하세요. 등록되지 않은 `hobby` 행은 건너뜁니다.

```console
$ python -m budget_app import --from import.csv
[완료] imported=4, skipped=1
```

목록과 검색:

```console
$ python -m budget_app list --limit 3
TX-000005 | 2024-01-15 | expense | food | 30000 | 저녁
TX-000001 | 2024-01-15 | expense | food | 15000 | 점심
TX-000002 | 2024-01-14 | income | salary | 3000000 | 월급
$ python -m budget_app search --category food
TX-000005 | 2024-01-15 | expense | food | 30000 | 저녁
TX-000001 | 2024-01-15 | expense | food | 15000 | 점심
$ python -m budget_app search --from 2024-01-12 --to 2024-01-14
TX-000002 | 2024-01-14 | income | salary | 3000000 | 월급
TX-000003 | 2024-01-12 | expense | transport | 20000 | 버스
```

예산과 월별 요약:

```console
$ python -m budget_app budget set --month 2024-01 --amount 500000
[저장 완료] 2024-01 예산 500000원
$ python -m budget_app summary --month 2024-01 --top 3
총 수입: 3000000원
총 지출: 215000원
잔액: 2785000원
예산: 500000원 (사용률 43.0%)
지출 TOP 3
1) rent 150000원
2) food 45000원
3) transport 20000원
```

수정과 삭제 (없는 id 는 오류):

```console
$ python -m budget_app update --id TX-000003 --amount 25000 --memo "버스 왕복"
[수정 완료] id=TX-000003
$ python -m budget_app delete --id TX-000005
[삭제 완료] id=TX-000005
$ python -m budget_app delete --id TX-999999
[오류] 없는 데이터입니다: id=TX-999999
[힌트] list 로 거래 id 를 확인한 뒤 다시 시도하세요
```

사용 중인 카테고리는 삭제할 수 없습니다:

```console
$ python -m budget_app category remove
카테고리명: food
[오류] 사용 중인 카테고리는 삭제할 수 없습니다: 'food'
[힌트] 이 카테고리를 쓰는 거래를 update --category 로 바꾸거나 delete 로 삭제한 뒤 다시 시도하세요
```

CSV 내보내기:

```console
$ python -m budget_app export --out export.csv --month 2024-01
[완료] export.csv (4 records)
$ cat export.csv
date,type,category,amount,memo,tags
2024-01-15,expense,food,15000,점심,meal
2024-01-14,income,salary,3000000,월급,
2024-01-12,expense,transport,25000,버스 왕복,commute
2024-01-05,expense,rent,150000,1월 월세,"house,fixed"
```

## import/export CSV 스키마

공통: UTF-8, 헤더 포함, id 컬럼 없음(import 할 때 새 id 를 발급). 헤더 줄은 `date,type,category,amount,memo,tags` 입니다.

| column | required | 설명 |
| --- | --- | --- |
| date | Y | YYYY-MM-DD |
| type | Y | income / expense |
| category | Y | 등록된 카테고리 |
| amount | Y | 양수 정수 |
| memo | N | 문자열 |
| tags | N | 쉼표(,) 구분 문자열 |

**import 규칙**

- 컬럼 순서는 자유입니다. 스키마에 없는 컬럼(`id` 포함)은 무시합니다. `memo`, `tags` 컬럼은 없어도 됩니다.
- UTF-8 BOM 이 붙은 파일도 읽습니다. 값의 앞뒤 공백은 지웁니다.
- tags 는 쉼표로 구분합니다. 태그가 여러 개면 `"meal,friend"` 처럼 따옴표로 감쌉니다.
- 건너뛰는 행(skipped): 날짜·type·amount 가 틀린 행, 등록되지 않은 category(대소문자 구분), 필수 값이 빈 행, 칸 수가 헤더와 다른 행. 빈 줄은 무시하고 세지 않습니다. 건너뛴 행의 위치는 출력하지 않고 개수만 보여 줍니다.
- 파일 오류(파일 없음, 헤더 없음·필수 컬럼 누락·컬럼 중복, UTF-8 아님, CSV 형식이 깨진 줄)는 오류로 끝나고 아무것도 저장하지 않습니다.
- 도중에 실패하거나 Ctrl+C 로 멈춰도 거래 파일은 그대로입니다.
- 같은 내용의 거래가 이미 있어도 새로 추가합니다(중복 검사 없음).

**export 규칙**

- `--month` 또는 `--from`+`--to` 중 하나 이상이 필요합니다. `--from` 과 `--to` 는 함께 써야 합니다.
- 둘 다 주면 두 조건을 모두 만족하는 거래만 내보냅니다. 날짜는 양 끝을 포함합니다.
- 행 순서는 저장된 순서(추가한 순서)이고, 컬럼 순서는 위 헤더 순서로 고정입니다. 파일은 UTF-8(BOM 없음)입니다.
- `--out` 파일이 이미 있으면 덮어쓰지 않고 오류입니다. `--out` 의 폴더가 없어도 오류입니다(폴더를 만들지 않음).
- 맞는 거래가 0건이면 헤더만 있는 파일을 만들고 `(0 records)` 를 출력합니다.
- export 한 파일은 그대로 import 할 수 있습니다.

**예시 파일** (`import.csv`, 위 "주요 명령 예시"에서 사용):

```csv import.csv
date,type,category,amount,memo,tags
2024-01-14,income,salary,3000000,월급,
2024-01-12,expense,transport,20000,버스,commute
2024-01-05,expense,rent,150000,1월 월세,"house,fixed"
2024-01-15,expense,food,30000,저녁,"meal,friend"
2024-01-20,expense,hobby,12000,영화,
```

## 동작 규칙

- **update 는 옵션 방식(안 A)으로 고정**: 준 항목만 바뀌고, 바꿀 항목이 1개 이상 필요합니다. `--memo ""`, `--tags ""` 는 메모·태그를 비웁니다. 없는 id 는 "없는 데이터" 오류입니다. delete 도 없는 id 는 오류입니다.
- **카테고리**
  - 카테고리 파일이 비어 있으면 기본 4개를 만듭니다(안 A).
  - 이름: 빈 이름과 이미 있는 이름은 거부하고 다시 묻습니다. 앞뒤 공백은 지웁니다. 대소문자를 구분합니다(`Food` 와 `food` 는 다름).
  - **사용 중인 카테고리는 삭제할 수 없습니다.** 그 카테고리를 쓰는 거래를 update 또는 delete 한 뒤 삭제하세요.
  - 거래에는 등록된 카테고리만 쓸 수 있습니다.
- **입력 검증**: 날짜는 `YYYY-MM-DD` 형식의 실제 날짜, 금액은 1 이상의 정수(쉼표 불가), type 은 `income` 또는 `expense`. add 는 틀린 항목만 다시 묻고, 옵션으로 받는 명령은 오류로 끝납니다. 태그는 쉼표로 구분합니다.
- **최신순**: 날짜가 늦은 것 먼저, 같은 날짜면 id 번호가 큰 것 먼저입니다(list 는 기본 20건).
- **search**: 조건이 1개 이상 필요합니다(없으면 오류). 모든 조건을 만족하는 거래만 보여 줍니다.
  - `--from`/`--to` 는 그 날짜를 포함하고, 하나만 줘도 됩니다. `--from` 이 `--to` 보다 늦으면 결과가 없습니다.
  - `--category` 는 등록된 이름만 받습니다(없으면 오류).
  - `--q` 는 메모 부분 일치(대소문자 구분), `--tag` 는 태그 하나와 정확히 일치입니다.
  - 맞는 거래가 1000건을 넘으면 메모리를 아끼려고 1000건씩 최신순으로 정렬해 시스템 임시 폴더(환경 변수 TMPDIR 가 가리키는 폴더, 없으면 /tmp)에 임시 파일로 나눠 쓴 뒤, 그 파일들을 합치면서 한 줄씩 출력합니다. 임시 파일은 검색이 끝나면(오류나 Ctrl+C 로 멈춰도) 지워지고, data 폴더에는 아무것도 쓰지 않습니다.
- **summary**: `--top` 기본값은 3 입니다. 거래가 없는 달은 `YYYY-MM 데이터 없음` 을 출력합니다. 예산이 있으면 사용률(소수 첫째 자리 반올림)을 보여 주고, 지출이 예산보다 크면 `[경고] 예산을 초과했습니다` 를 출력합니다. TOP 금액이 같으면 이름순입니다.
- **budget set**: 같은 월을 다시 저장하면 덮어씁니다.

## 오류와 종료 코드

오류는 `[오류] 원인` 과 `[힌트] 해결 방법` 두 줄을 표준 오류(stderr)로 출력합니다. 스택트레이스는 보여 주지 않습니다.

| 종료 코드 | 의미 |
| --- | --- |
| `0` | 정상 (결과가 없어도, import 에 skipped 가 있어도 0) |
| `1` | 실행 오류: 입력값 오류, 없는 id, 사용 중 카테고리 삭제, 파일 문제, Ctrl+C, 입력 끝(EOF) |
| `2` | 사용법 오류: 없는 명령·옵션, 필수 옵션 누락, `-h`, 옵션 줄임말, `--data-dir` 를 명령 앞에 둠 |

`[경고]` 줄은 표준 출력(stdout)에 나오고 종료 코드는 0 입니다.

출력을 받는 프로그램이 먼저 끝나면(예: `| head -1` 로 앞부분만 볼 때) 남은 출력은 버리고 `[오류]` 없이 종료 코드 1 로 끝납니다. 그때까지 저장·삭제한 내용은 그대로 남습니다.
