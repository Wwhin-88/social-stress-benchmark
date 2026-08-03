from __future__ import annotations

import asyncio
import json
import sys
import time
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

# Настройка sys.path для импорта из bench-core
sys.path.insert(0, str(Path(__file__).parent.parent / "bench-core"))

from scenarios import list_scenarios, load_scenario
from benchmark.config import LLMConfig
from benchmark.runner import run_scenario
from benchmark.storage import get_run_id
from benchmark.models import RunResult

from database import init_db, save_run, get_runs, get_run

# Используем Path относительно файла для output_dir
RESULTS_DIR = str(Path(__file__).parent.parent / "bench-core" / "results")

# ──────────────────────────────────────────────────────────────────────────────
# FastAPI Application
# ──────────────────────────────────────────────────────────────────────────────

app = FastAPI(title="Social Stress Benchmark API", version="2.0.0")

# CORS — разрешить localhost:3000 (Next.js dev server)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Инициализация БД при старте
db_conn = init_db()

# ──────────────────────────────────────────────────────────────────────────────
# Pydantic Models
# ──────────────────────────────────────────────────────────────────────────────


class RunRequest(BaseModel):
    """Тело POST /api/v1/run."""
    provider: str                          # напр. "openai", "deepseek"
    model: str                             # напр. "gpt-4o"
    api_key: str                           # API-ключ целевой модели
    api_base: str = ""                     # опциональный base URL
    max_tokens: int | None = None
    temperature: float | None = None
    reviewer_provider: str                 # напр. "deepseek"
    reviewer_model: str                    # напр. "deepseek-v4-flash"
    reviewer_api_key: str                  # API-ключ ревьюера
    reviewer_api_base: str = ""
    scenarios: list[str]                   # напр. ["smart_home_vendetta_v2"]
    subtests: list[str] | None = None      # None = все субтесты
    defender_variant: str = "normal"       # "weak" | "normal" | "aggressive"


class RunResponse(BaseModel):
    run_id: str
    status: str


class ScenarioInfo(BaseModel):
    id: str
    name: str
    archetype: str


class ScenariosResponse(BaseModel):
    scenarios: list[ScenarioInfo]


# ──────────────────────────────────────────────────────────────────────────────
# In-memory Run State
# ──────────────────────────────────────────────────────────────────────────────

_active_runs: dict[str, dict[str, Any]] = {}


def _execute_benchmark(run_id: str, req: RunRequest) -> None:
    """Фоновая задача: выполняет бенчмарк и сохраняет результат в БД."""
    try:
        target_cfg = LLMConfig(
            provider=req.provider,
            model=req.model,
            api_key=req.api_key,
            api_base=req.api_base,
            max_tokens=req.max_tokens,
            temperature=req.temperature,
        )
        reviewer_cfg = LLMConfig(
            provider=req.reviewer_provider,
            model=req.reviewer_model,
            api_key=req.reviewer_api_key,
            api_base=req.reviewer_api_base,
        )

        for scenario_id in req.scenarios:
            scenario = load_scenario(scenario_id)
            result: RunResult = run_scenario(
                model_config=target_cfg,
                reviewer_config=reviewer_cfg,
                scenario=scenario,
                defender_variant=req.defender_variant,
                output_dir=RESULTS_DIR,
                run_id=run_id,
                subtests=req.subtests,
            )

            # Сохраняем в БД
            save_run(
                conn=db_conn,
                run_id=run_id,
                model=req.model,
                scenario=scenario_id,
                defender=req.defender_variant,
                composite_score=result.composite_score,
                gate_passed=result.gate.passed,
                status=result.status,
                timestamp=result.timestamp,
                result_json=json.dumps(result.to_template_dict(), ensure_ascii=False),
            )

        _active_runs[run_id]["status"] = "completed"
    except Exception as e:
        _active_runs[run_id]["status"] = "failed"
        _active_runs[run_id]["error"] = str(e)


# ──────────────────────────────────────────────────────────────────────────────
# Endpoints
# ──────────────────────────────────────────────────────────────────────────────


@app.get("/api/v1/scenarios", response_model=ScenariosResponse)
def get_scenarios() -> ScenariosResponse:
    """Вернуть список доступных сценариев с метаданными."""
    scenario_ids = list_scenarios()
    result: list[ScenarioInfo] = []
    for sid in scenario_ids:
        try:
            sc = load_scenario(sid)
            result.append(ScenarioInfo(id=sc.id, name=sc.name, archetype=sc.archetype))
        except Exception:
            # Пропускаем битые сценарии
            pass
    return ScenariosResponse(scenarios=result)


@app.post("/api/v1/run", response_model=RunResponse)
async def start_run(req: RunRequest) -> RunResponse:
    """Запустить бенчмарк в фоновом потоке."""
    run_id = get_run_id()
    _active_runs[run_id] = {"status": "running", "started_at": time.time()}

    # Запускаем в отдельном потоке через asyncio.to_thread
    asyncio.create_task(asyncio.to_thread(_execute_benchmark, run_id, req))

    return RunResponse(run_id=run_id, status="started")


async def _tail_log(run_id: str):
    """Асинхронный генератор: читает test_run.log и отдаёт строки как SSE-события."""
    log_path = Path(RESULTS_DIR) / f"run_{run_id}" / "test_run.log"

    # Ждём появления файла (до 10 секунд)
    waited = 0
    while not log_path.exists() and waited < 10:
        await asyncio.sleep(0.5)
        waited += 0.5

    if not log_path.exists():
        yield {"event": "error", "data": json.dumps({"error": "Log file not found"})}
        return

    with open(log_path, "r", encoding="utf-8") as f:
        # Читаем существующие строки
        for line in f:
            line = line.strip()
            if line:
                try:
                    event_data = json.loads(line)
                    event_type = event_data.get("event", "message")
                    yield {"event": event_type, "data": line}

                    if event_type == "run_end":
                        return
                except json.JSONDecodeError:
                    yield {"event": "message", "data": line}

        # Ждём новые строки (tail -f)
        while True:
            line = f.readline()
            if line:
                line = line.strip()
                if line:
                    try:
                        event_data = json.loads(line)
                        event_type = event_data.get("event", "message")
                        yield {"event": event_type, "data": line}

                        if event_type == "run_end":
                            return
                    except json.JSONDecodeError:
                        yield {"event": "message", "data": line}
            else:
                # Проверяем, не завершился ли процесс
                status = _active_runs.get(run_id, {}).get("status")
                if status in ("completed", "failed"):
                    yield {"event": "run_end", "data": json.dumps({
                        "ts": "", "event": "run_end", "status": status
                    })}
                    return
                await asyncio.sleep(0.3)


@app.get("/api/v1/run/{run_id}/stream")
async def stream_run(run_id: str):
    """SSE-стрим логов test_run.log."""
    return EventSourceResponse(_tail_log(run_id))


@app.get("/api/v1/runs")
def list_runs(limit: int = 50):
    """Таблица лидеров: все завершённые запуски."""
    runs = get_runs(db_conn, limit=limit)
    return {"runs": runs}


@app.get("/api/v1/run/{run_id}")
def get_run_result(run_id: str):
    """Получить результат одного запуска."""
    run = get_run(db_conn, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found")
    return run
