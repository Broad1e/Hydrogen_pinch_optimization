# Точка входа: FastAPI-сервер
# Инициализация приложения и маршруты API

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from models import (
    StreamType, OptMethod,
    BaselineResponse, OptimizeResponse,
)
from data_loader import load_streams_from_csv
from solvers import (
    calculate_baseline_fresh_h2,
    build_cascade_curve,
    run_lp_optimization,
    run_cascade_optimization,
    run_mcmf_optimization,
)


# Инициализация FastAPI
app = FastAPI(
    title="Hydrogen Pinch Optimizer",
    description=(
        "Оптимизация потребления водорода на НПЗ "
        "методом водородного пинча. Поддерживает три метода: "
        "LP (линейное программирование), Cascade (каскадный анализ), "
        "MCMF (Min Cost Max Flow)."
    ),
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Маршруты
@app.get("/")
def read_root():
    return {
        "message": "Hydrogen Pinch Optimizer",
        "version": "1.0.0",
        "methods": ["lp", "cascade", "mcmf"],
    }


@app.get("/api/v1/pinch/baseline", response_model=BaselineResponse)
def get_baseline_data():
    # Расчёт baseline: жадное распределение без глобальной оптимизации
    streams = load_streams_from_csv("data.csv")
    sources = [s for s in streams if s.type == StreamType.SOURCE]
    sinks = [s for s in streams if s.type == StreamType.SINK]

    if not sinks:
        raise HTTPException(status_code=422, detail="В данных отсутствуют стоки (Sink)")

    baseline_fresh = calculate_baseline_fresh_h2(streams)

    src_dicts = [{"flow_rate": s.flow_rate, "purity": s.purity} for s in sources]
    snk_dicts = [{"flow_rate": s.flow_rate, "purity": s.purity} for s in sinks]
    curve = build_cascade_curve(baseline_fresh, src_dicts, snk_dicts)

    return BaselineResponse(
        status="success",
        baseline_fresh_h2=round(baseline_fresh, 2),
        baseline_curve=curve,
    )


@app.get("/api/v1/pinch/optimize", response_model=OptimizeResponse)
def run_optimization(
    method: OptMethod = Query(
        default=OptMethod.LP,
        description=(
            "Метод оптимизации: "
            "lp (линейное программирование, смешение разрешено), "
            "cascade (каскадный анализ, теоретический минимум), "
            "mcmf (Min Cost Max Flow, прямые подключения)"
        ),
    ),
):

    streams = load_streams_from_csv("data.csv")
    sources = [s for s in streams if s.type == StreamType.SOURCE]
    sinks = [s for s in streams if s.type == StreamType.SINK]

    if not sinks:
        raise HTTPException(status_code=422, detail="В данных отсутствуют стоки (Sink)")
    if not sources:
        raise HTTPException(status_code=422, detail="В данных отсутствуют источники (Source)")

    # Baseline
    baseline_fresh = calculate_baseline_fresh_h2(streams)

    # Выбор метода
    method_labels = {
        OptMethod.LP: "Линейное программирование",
        OptMethod.CASCADE: "Каскадный анализ",
        OptMethod.MCMF: "Min Cost Max Flow (MCMF)",
    }
    method_notes = {
        OptMethod.LP: "Учитывает топологию, разрешает смешение потоков",
        OptMethod.CASCADE: "Теоретический минимум (топология игнорируется)",
        OptMethod.MCMF: "Учитывает топологию, только прямые подключения (без смешения)",
    }

    pinch_point = None

    if method == OptMethod.LP:
        result = run_lp_optimization(sources, sinks)
    elif method == OptMethod.CASCADE:
        result = run_cascade_optimization(sources, sinks)
        pinch_point = result.get("pinch_point")
    elif method == OptMethod.MCMF:
        result = run_mcmf_optimization(sources, sinks)
        if not result["success"] and "error" in result:
            raise HTTPException(status_code=500, detail=result["error"])
    else:
        raise HTTPException(status_code=400, detail=f"Неизвестный метод: {method}")

    # Каскадные кривые
    src_dicts = [{"flow_rate": s.flow_rate, "purity": s.purity} for s in sources]
    snk_dicts = [{"flow_rate": s.flow_rate, "purity": s.purity} for s in sinks]
    baseline_curve = build_cascade_curve(baseline_fresh, src_dicts, snk_dicts)

    if result["success"]:
        opt_fresh = result["fresh_h2"]
        saved = baseline_fresh - opt_fresh
        pct = (saved / baseline_fresh * 100.0) if baseline_fresh > 1e-9 else 0.0
        is_optimized = saved > 1e-4

        opt_curve = build_cascade_curve(opt_fresh, src_dicts, snk_dicts)

        label = method_labels[method]
        note = method_notes[method]

        if is_optimized:
            msg = (
                f"[{label}] Экономия свежего H2: "
                f"{round(saved, 2)} Нм3/ч ({round(pct, 1)}%). "
                f"{note}."
            )
            if pinch_point is not None:
                msg += f" Пинч-точка: {pinch_point}%."
        else:
            msg = (
                f"[{label}] Дальнейшая экономия невозможна. {note}."
            )
    else:
        opt_fresh = baseline_fresh
        saved = 0.0
        pct = 0.0
        is_optimized = False
        opt_curve = baseline_curve
        result["topology"] = []
        msg = (
            f"[{method_labels[method]}] Решение не найдено. "
            "Проверьте входные данные."
        )

    return OptimizeResponse(
        status="optimized" if is_optimized else "no_improvement",
        method=method.value,
        is_optimized=is_optimized,
        message=msg,
        baseline_fresh_h2=round(baseline_fresh, 2),
        optimized_fresh_h2=round(opt_fresh, 2),
        saved_h2=round(max(0.0, saved), 2),
        savings_percent=round(max(0.0, pct), 1),
        pinch_point=pinch_point,
        baseline_curve=baseline_curve,
        optimized_curve=opt_curve,
        new_topology=result["topology"],
    )