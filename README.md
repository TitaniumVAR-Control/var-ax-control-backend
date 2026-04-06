# VAR Monitoring Backend

VAR 잉곳 하강 제어 시스템의 백엔드. FastAPI + PostgreSQL.

- 모니터링 화면에 실시간 데이터 WebSocket 스트리밍
- 관리자 패널 REST API
- 센서 로그 적재 및 일별 CSV 내보내기

## 전제 조건

- Python 3.11+
- PostgreSQL 14+ (선택 — 없으면 로그 적재만 비활성화되고 나머지는 정상 동작)
- `AX-cap/` 전체 디렉터리 (`ai/src` 를 import 하므로 단독 실행 불가)

## DB 설정

### 기본 접속 정보

| 항목 | 값 |
| --- | --- |
| Host | `localhost` |
| Port | `5432` |
| Database | `axcap` |
| User | `postgres` |
| Password | `postgres` |

## 환경변수

전부 선택. 기본값으로 로컬 개발 가능.

| 변수 | 기본값 | 설명 |
| --- | --- | --- |
| `BACKEND_PORT` | `8000` | 바인드 포트 |
| `DATABASE_URL` | `postgresql+asyncpg://postgres:postgres@localhost:5432/axcap` | `postgresql+asyncpg://` 스킴 필수 |
| `DATABASE_ENABLED` | `true` | `false` 시 DB 비활성 |
| `SIM_TICK_SEC` | `1.0` | 시뮬레이션 재생 간격(초) |
| `LOG_LEVEL` | `INFO` | |

예시:

```powershell
$env:DATABASE_URL = "postgresql+asyncpg://myuser:mypass@localhost:5432/axcap"
```

## 기동

백엔드만 직접 기동(디버깅용):

```powershell
python -m uvicorn backend.server:app --host 0.0.0.0 --port 8000
```

## API

### REST

| 메서드 | 경로 | 설명 |
| --- | --- | --- |
| GET | `/health` | 헬스체크 |
| GET | `/api/status` | 세션 상태 |
| GET | `/api/data-files` | 테스트 CSV 목록 |
| POST | `/api/power-on` | 전원 ON |
| POST | `/api/power-off` | 전원 OFF |
| POST | `/api/start` | 시뮬레이션 시작 |
| POST | `/api/stop` | 시뮬레이션 중지 |
| POST | `/api/set-target` | 목표 전류 변경(실행 중 가능) |
| POST | `/api/reload-model` | ARX 모델 재로드 |
| GET | `/api/export/daily?day=YYYY-MM-DD` | 일별 센서 로그 CSV 다운로드 |

### WebSocket

| 경로 | 설명 |
| --- | --- |
| `/ws/monitor` | 모니터링 디스플레이 스트리밍 |
| `/ws/admin` | 관리자 패널 상태 스트리밍 |

## 구조

```
backend/
├── main.py          # FastAPI 앱
├── server.py        # manage.ps1 호환 shim
├── config.py        # Settings
├── schemas/         # Pydantic 모델
├── db/              # ORM + 엔진
├── services/        # 비즈니스 로직 (session, controller, runner, repository, export 등)
└── api/             # REST / WebSocket 라우터
```

**계층**: `api` → `services` → `db` (단방향)

실장비 연결 시 `services/data_source.py` 에 `ISensorSource` 구현체만 추가하면 상위 계층 수정 없이 교체 가능

## 일별 데이터 내보내기

```powershell
# 브라우저
http://localhost:8000/api/export/daily?day=2026-04-06

# PowerShell
Invoke-WebRequest -Uri "http://localhost:8000/api/export/daily?day=2026-04-06" -OutFile "sensor_log.csv"
```

`day` 생략 시 오늘(UTC) 기준.
