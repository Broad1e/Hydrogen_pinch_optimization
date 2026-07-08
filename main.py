import csv
import os
from enum import Enum
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, PositiveInt, field_validator
import numpy as np
from scipy.optimize import linprog

try:
    import networkx as nx
except ImportError:
    nx = None


# Типы данных
class StreamType(str, Enum):
    SOURCE = "Source"
    SINK = "Sink"

# Методы оптимизации
class OptMethod(str, Enum):
    LP = "lp"
    CASCADE = "cascade"
    MCMF = "mcmf"


class GraphPoint(BaseModel):
    x: float = Field(..., description="Кумулятивный расход (Flow)")
    y: float = Field(..., description="Чистота водорода (Purity), %")


class StreamData(BaseModel):
    id: PositiveInt = Field(..., description="Идентификатор потока")
    name: str = Field(..., description="Название потока")
    type: StreamType = Field(..., description="Тип потока: Source или Sink")
    flow_rate: float = Field(..., gt=0, description="Расход водорода, Нм3/ч")
    purity: float = Field(..., ge=0, le=100, description="Чистота водорода, %")
    allowed_connections: list[PositiveInt] = Field(
        default=[],
        description="ID стоков, в которые разрешена подача (пусто = без ограничений)",
    )


class StreamCollection(BaseModel):
    streams: list[StreamData] = Field(..., description="Список всех потоков")
    # Проверка уникальности ID потоков
    @field_validator("streams")
    @classmethod
    def check_unique_ids(cls, list_of_streams):
        all_ids = [s.id for s in list_of_streams]
        if len(all_ids) != len(set(all_ids)):
            raise ValueError("Ошибка: в данных есть потоки с одинаковыми ID")
        return list_of_streams


class TopologyLink(BaseModel):
    source_name: str
    sink_name: str
    flow_amount: float = Field(..., description="Объём переданного водорода, Нм3/ч")


class BaselineResponse(BaseModel):
    status: str = Field(default="success")
    baseline_fresh_h2: float = Field(..., description="Расход свежего H2 при жадном назначении, Нм3/ч")
    baseline_curve: list[GraphPoint] = Field(..., description="Каскадная кривая избытка (baseline)")


class OptimizeResponse(BaseModel):
    status: str = Field(..., description="optimized или no_improvement")
    method: str = Field(..., description="Использованный метод: lp, cascade, mcmf")
    is_optimized: bool = Field(..., description="Найдена ли экономия")
    message: str = Field(..., description="Текстовое сообщение с результатом")
    baseline_fresh_h2: float = Field(..., description="Расход свежего H2 при жадном назначении, Нм3/ч")
    optimized_fresh_h2: float = Field(..., description="Оптимальный расход свежего H2, Нм3/ч")
    saved_h2: float = Field(..., description="Абсолютная экономия, Нм3/ч")
    savings_percent: float = Field(..., description="Экономия, %")
    pinch_point: float | None = Field(default=None,description="Пинч-точка: уровень чистоты с нулевым избытком (только cascade)",)
    baseline_curve: list[GraphPoint] = Field(..., description="Каскадная кривая до оптимизации")
    optimized_curve: list[GraphPoint] = Field(..., description="Каскадная кривая после оптимизации")
    new_topology: list[TopologyLink] = Field(..., description="Оптимальный план переключений потоков")

# Вспомогательные функции
# Загрузка потоков из CSV
def load_streams_from_csv(file_path: str = "data.csv") -> list[StreamData]:
    # Парсинг CSV с перехватом ошибок:
    # при отсутствии колонки или неверном значении выдается HTTP 422
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail=f"Файл {file_path} не найден на сервере")

    raw_streams: list[dict] = []
    try:
        with open(file_path, mode="r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row_num, row in enumerate(reader, start=2):
                try:
                    conns_str = row.get("allowed_connections", "").strip()
                    conns = (
                        [int(c.strip()) for c in conns_str.split(",") if c.strip()]
                        if conns_str
                        else []
                    )
                    raw_streams.append(
                        {
                            "id": int(row["id"]),
                            "name": row["name"],
                            "type": row["type"],
                            "flow_rate": float(row["flow_rate"]),
                            "purity": float(row["purity"]),
                            "allowed_connections": conns,
                        }
                    )
                except (KeyError, ValueError) as e:
                    raise HTTPException(status_code=422,detail=f"Ошибка в строке {row_num} CSV: {e}. Данные: {row}",)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ошибка чтения файла: {e}")

    try:
        collection = StreamCollection(streams=raw_streams)
        return collection.streams
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))


# Жадный алгоритм расчёта исходного потребления свежего водорода.
def calculate_baseline_fresh_h2(streams: list[StreamData]) -> float:
    # Базовое распределение: берём самые чистые источники для самых чистых стоков.
    # Остаток покрывается свежим H2.
    # Учитывает разрешенные связи (allowed_connections).
    # Не поддерживает смешение газов (если источник грязнее стока, он не используется).
    sources = [s for s in streams if s.type == StreamType.SOURCE]
    sinks = [s for s in streams if s.type == StreamType.SINK]

    if not sinks:
        return 0.0

    sinks_sorted = sorted(sinks, key=lambda s: s.purity, reverse=True)
    sources_sorted = sorted(sources, key=lambda s: s.purity, reverse=True)
    source_remains = {s.id: s.flow_rate for s in sources}

    fresh_h2 = 0.0

    for snk in sinks_sorted:
        unmet = snk.flow_rate
        for src in sources_sorted:
            if unmet <= 1e-9:
                break
            if src.purity < snk.purity:
                continue
            if source_remains[src.id] <= 1e-9:
                continue
            if src.allowed_connections and snk.id not in src.allowed_connections:
                continue

            transfer = min(unmet, source_remains[src.id])
            unmet -= transfer
            source_remains[src.id] -= transfer

        if unmet > 1e-9:
            fresh_h2 += unmet

    return fresh_h2

# Построение каскадной кривой избытка водорода
def build_cascade_curve(
    fresh_h2: float,
    sources: list[dict],
    sinks: list[dict],
) -> list[GraphPoint]:
    # Считает кумулятивный баланс водорода по уровням чистоты сверху вниз.
    all_purities = sorted(
        set(
            [100.0]
            + [s["purity"] for s in sources]
            + [s["purity"] for s in sinks]
        ),
        reverse=True,
    )

    curve: list[GraphPoint] = []
    cx = 0.0

    for p in all_purities:
        curve.append(GraphPoint(x=round(max(0.0, cx), 4), y=p))

        if abs(p - 100.0) < 1e-9 and fresh_h2 > 1e-9:
            cx += fresh_h2
            curve.append(GraphPoint(x=round(max(0.0, cx), 4), y=p))

        src_flow = sum(
            s["flow_rate"] for s in sources if abs(s["purity"] - p) < 1e-9
        )
        if src_flow > 1e-9:
            cx += src_flow
            curve.append(GraphPoint(x=round(max(0.0, cx), 4), y=p))

        snk_flow = sum(
            s["flow_rate"] for s in sinks if abs(s["purity"] - p) < 1e-9
        )
        if snk_flow > 1e-9:
            cx -= snk_flow
            cx = max(0.0, cx)
            curve.append(GraphPoint(x=round(cx, 4), y=p))

    return curve


# Метод 1 - Линейное программирование (LP)
#Находит оптимальное распределение потоков с учетом смешения и ограничений топологии.
#минимизирует расход свежего H2.
def run_lp_optimization(
    sources: list[StreamData],
    sinks: list[StreamData],
) -> dict:
    N = len(sources)
    M = len(sinks)
    num_vars = N * M + M
    EPS = 1e-6

    # Целевая функция
    c = np.zeros(num_vars)
    for i in range(N):
        for j in range(M):
            purity_gap = abs(sources[i].purity - sinks[j].purity)
            c[i * M + j] = EPS * purity_gap / 100.0
    for j in range(M):
        c[N * M + j] = 1.0

    # Равенства: баланс стоков
    A_eq = np.zeros((M, num_vars))
    b_eq = np.zeros(M)
    for j in range(M):
        for i in range(N):
            A_eq[j, i * M + j] = 1.0
        A_eq[j, N * M + j] = 1.0
        b_eq[j] = sinks[j].flow_rate

    # Неравенства: емкость источников + чистота смеси
    A_ub = np.zeros((N + M, num_vars))
    b_ub = np.zeros(N + M)

    for i in range(N):
        for j in range(M):
            A_ub[i, i * M + j] = 1.0
        b_ub[i] = sources[i].flow_rate

    for j in range(M):
        row = N + j
        for i in range(N):
            A_ub[row, i * M + j] = -sources[i].purity
        A_ub[row, N * M + j] = -100.0
        b_ub[row] = -sinks[j].flow_rate * sinks[j].purity

    # Границы переменных
    bounds: list[tuple] = []
    for i in range(N):
        for j in range(M):
            allowed = sources[i].allowed_connections
            if allowed and sinks[j].id not in allowed:
                bounds.append((0.0, 0.0))
            else:
                bounds.append((0.0, None))
    for j in range(M):
        bounds.append((0.0, None))

    # Запуск
    result = linprog(
        c, A_ub=A_ub, b_ub=b_ub, A_eq=A_eq, b_eq=b_eq,
        bounds=bounds, method="highs",
    )

    if not result.success:
        return {"success": False, "fresh_h2": 0.0, "topology": []}

    # Извлечение результатов
    topology: list[TopologyLink] = []
    total_fresh = 0.0

    for i in range(N):
        for j in range(M):
            flow = result.x[i * M + j]
            if flow > 1e-4:
                topology.append(TopologyLink(
                    source_name=sources[i].name,
                    sink_name=sinks[j].name,
                    flow_amount=round(flow, 2),
                ))

    for j in range(M):
        fresh = result.x[N * M + j]
        total_fresh += fresh
        if fresh > 1e-4:
            topology.append(TopologyLink(
                source_name="Свежий H2 (100%)",
                sink_name=sinks[j].name,
                flow_amount=round(fresh, 2),
            ))

    return {"success": True, "fresh_h2": total_fresh, "topology": topology}


# Метод 2 - Каскадный анализ
#Теоретический минимум потребления свежего водорода, игнорирует ограничения по трубам.
#Показывает абсолютный предел экономии и находит Пинч-точку.
def run_cascade_optimization(
    sources: list[StreamData],
    sinks: list[StreamData],
) -> dict:
    # 1. Собрать уровни чистоты
    all_purities = sorted(
        set(
            [s.purity for s in sources]
            + [s.purity for s in sinks]
            + [100.0]
        ),
        reverse=True,
    )

    # 2. Каскад без свежего H2: найти максимальный дефицит
    cumulative = 0.0
    min_cumulative = 0.0
    pinch_purity = None

    for p in all_purities:
        src_at_level = sum(s.flow_rate for s in sources if abs(s.purity - p) < 1e-9)
        snk_at_level = sum(s.flow_rate for s in sinks if abs(s.purity - p) < 1e-9)
        cumulative += src_at_level - snk_at_level

        if cumulative < min_cumulative - 1e-9:
            min_cumulative = cumulative
            pinch_purity = p

    # 3. Минимальный свежий H2 = компенсация максимального дефицита
    min_fresh = max(0.0, -min_cumulative)

    # 4. Определить пинч-точку (где каскад + fresh = 0)
    if pinch_purity is None and min_fresh < 1e-9:
        # Свежий H2 не нужен, пинча нет
        pinch_purity = None
    elif pinch_purity is not None:
        # Проверяем: при добавлении fresh каскад = 0 на уровне пинча
        cumul_check = min_fresh
        for p in all_purities:
            src_at = sum(s.flow_rate for s in sources if abs(s.purity - p) < 1e-9)
            snk_at = sum(s.flow_rate for s in sinks if abs(s.purity - p) < 1e-9)
            cumul_check += src_at - snk_at
            if abs(cumul_check) < 1e-4:
                pinch_purity = p
                break

    # 5. Построить топологию жадным алгоритмом БЕЗ allowed_connections
    topology = _build_cascade_topology(sources, sinks, min_fresh)

    return {
        "success": True,
        "fresh_h2": min_fresh,
        "topology": topology,
        "pinch_point": pinch_purity,
    }


def _build_cascade_topology(
    sources: list[StreamData],
    sinks: list[StreamData],
    min_fresh: float,
) -> list[TopologyLink]:
    # Построение идеальной топологии для каскада.
    sinks_sorted = sorted(sinks, key=lambda s: s.purity, reverse=True)
    sources_sorted = sorted(sources, key=lambda s: s.purity, reverse=True)
    source_remains = {s.id: s.flow_rate for s in sources}

    topology: list[TopologyLink] = []
    remaining_fresh = min_fresh

    for snk in sinks_sorted:
        needed = snk.flow_rate

        # Сначала используем свежий H2 (для самых чистых стоков)
        if remaining_fresh > 1e-9 and needed > 1e-9:
            use_fresh = min(needed, remaining_fresh)
            remaining_fresh -= use_fresh
            needed -= use_fresh
            if use_fresh > 1e-4:
                topology.append(TopologyLink(
                    source_name="Свежий H2 (100%)",
                    sink_name=snk.name,
                    flow_amount=round(use_fresh, 2),
                ))

        # Затем используем источники (от чистого к грязному)
        for src in sources_sorted:
            if needed <= 1e-9:
                break
            if src.purity < snk.purity:
                continue  # Даже в каскаде, прямая подача грязного невозможна
            if source_remains[src.id] <= 1e-9:
                continue

            transfer = min(needed, source_remains[src.id])
            needed -= transfer
            source_remains[src.id] -= transfer
            if transfer > 1e-4:
                topology.append(TopologyLink(
                    source_name=src.name,
                    sink_name=snk.name,
                    flow_amount=round(transfer, 2),
                ))

        # Если осталось
        if needed > 1e-4:
            topology.append(TopologyLink(
                source_name="Свежий H2 (100%)",
                sink_name=snk.name,
                flow_amount=round(needed, 2),
            ))

    return topology


# Метод 3 - Минимальная стоимость максимального потока (MCMF)
#Оптимизация потоков через графы (без смешения).
#Ищет оптимальный маршрут по существующим трубам (allowed_connections).
def run_mcmf_optimization(
    sources: list[StreamData],
    sinks: list[StreamData],
) -> dict:
    if nx is None:
        return {
            "success": False,
            "fresh_h2": 0.0,
            "topology": [],
            "error": "networkx не установлен. pip install networkx",
        }

    SCALE = 100       # Масштаб: float -> int для числовой устойчивости
    FRESH_COST = 100000  # Штраф за использование свежего H2

    total_sink = sum(s.flow_rate for s in sinks)
    total_source = sum(s.flow_rate for s in sources)

    G = nx.DiGraph()

    #Узлы
    # Источники: supply (demand < 0)
    for src in sources:
        G.add_node(f"src_{src.id}", demand=int(-src.flow_rate * SCALE))

    # Стоки: demand (demand > 0)
    for snk in sinks:
        G.add_node(f"snk_{snk.id}", demand=int(snk.flow_rate * SCALE))

    # Свежий H2: supply = total_sink (покрывает весь дефицит при необходимости)
    G.add_node("fresh", demand=int(-total_sink * SCALE))

    # Отвал: absorbs = total_source (неиспользованные источники)
    #   + excess fresh (total_sink - fresh_used)
    # Баланс: supply = source + fresh = total_source + total_sink
    #          demand = sink + waste = total_sink + total_source
    G.add_node("waste", demand=int(total_source * SCALE))

    #Рёбра
    # source -> sink (только если purity >= required И allowed)
    for src in sources:
        for snk in sinks:
            allowed = src.allowed_connections
            if allowed and snk.id not in allowed:
                continue
            if src.purity < snk.purity:
                continue  # MCMF не поддерживает смешение
            purity_gap = abs(src.purity - snk.purity)
            G.add_edge(
                f"src_{src.id}", f"snk_{snk.id}",
                capacity=int(src.flow_rate * SCALE),
                weight=max(1, int(purity_gap * 10)),  # min cost = 1 (для различения от 0)
            )

    # source -> waste (бесплатно)
    for src in sources:
        G.add_edge(
            f"src_{src.id}", "waste",
            capacity=int(src.flow_rate * SCALE),
            weight=0,
        )

    # fresh -> sink (очень дорого)
    for snk in sinks:
        G.add_edge(
            "fresh", f"snk_{snk.id}",
            capacity=int(snk.flow_rate * SCALE),
            weight=FRESH_COST,
        )

    # fresh -> waste (сброс неиспользованного свежего, бесплатно)
    G.add_edge(
        "fresh", "waste",
        capacity=int(total_sink * SCALE),
        weight=0,
    )

    #Запуск MCMF
    try:
        flow_dict = nx.min_cost_flow(G)
    except nx.NetworkXUnfeasible:
        return {
            "success": False,
            "fresh_h2": 0.0,
            "topology": [],
            "error": "Сеть не имеет допустимого потока",
        }
    except nx.NetworkXError as e:
        return {
            "success": False,
            "fresh_h2": 0.0,
            "topology": [],
            "error": str(e),
        }

    #Извлечение результатов
    topology: list[TopologyLink] = []
    total_fresh = 0.0

    # source -> sink
    for src in sources:
        src_key = f"src_{src.id}"
        if src_key not in flow_dict:
            continue
        for snk in sinks:
            snk_key = f"snk_{snk.id}"
            flow_scaled = flow_dict[src_key].get(snk_key, 0)
            if flow_scaled > 0:
                flow_real = flow_scaled / SCALE
                topology.append(TopologyLink(
                    source_name=src.name,
                    sink_name=snk.name,
                    flow_amount=round(flow_real, 2),
                ))

    # fresh -> sink
    if "fresh" in flow_dict:
        for snk in sinks:
            snk_key = f"snk_{snk.id}"
            flow_scaled = flow_dict["fresh"].get(snk_key, 0)
            if flow_scaled > 0:
                flow_real = flow_scaled / SCALE
                total_fresh += flow_real
                topology.append(TopologyLink(
                    source_name="Свежий H2 (100%)",
                    sink_name=snk.name,
                    flow_amount=round(flow_real, 2),
                ))

    return {"success": True, "fresh_h2": total_fresh, "topology": topology}


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