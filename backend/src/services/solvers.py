# Алгоритмы оптимизации водородной сети
# Три метода: LP (смешение), Cascade (теоретический минимум), MCMF (графы без смешения)
# + Baseline (жадный алгоритм) и построение каскадных кривых

import numpy as np
from scipy.optimize import linprog, minimize

try:
    import networkx as nx
except ImportError:
    nx = None

from src.schemas.pinch import StreamType, StreamData, GraphPoint, TopologyLink


def calculate_baseline_fresh_h2(streams: list[StreamData]) -> tuple[float, list[TopologyLink]]:
    """Жадный алгоритм расчёта базового потребления свежего водорода.

    Выполняет базовое (жадное) распределение: берёт самые чистые источники для
    самых чистых стоков. Остаток потребности покрывается свежим водородом (100% чистота).
    Учитывает разрешенные связи (`allowed_connections`).
    Не поддерживает смешение газов: если источник грязнее стока, он не используется.

    Args:
        streams (list[StreamData]): Список всех водородных потоков (источники и стоки).

    Returns:
        tuple[float, list[TopologyLink]]: Кортеж, где первый элемент — объем 
            свежего H2 (Нм3/ч), второй — базовая топология потоков (было/стало).
    """
    sources = [s for s in streams if s.type == StreamType.SOURCE]
    sinks = [s for s in streams if s.type == StreamType.SINK]

    if not sinks:
        return 0.0, []

    sinks_sorted = sorted(sinks, key=lambda s: s.purity, reverse=True)
    sources_sorted = sorted(sources, key=lambda s: s.purity, reverse=True)
    source_remains = {s.id: s.flow_rate for s in sources}

    fresh_h2 = 0.0
    topology: list[TopologyLink] = []

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
            
            if transfer > 1e-4:
                topology.append(TopologyLink(
                    source_name=src.name,
                    sink_name=snk.name,
                    flow_amount=round(transfer, 2)
                ))

        if unmet > 1e-9:
            fresh_h2 += unmet
            topology.append(TopologyLink(
                source_name="Свежий H2 (100%)",
                sink_name=snk.name,
                flow_amount=round(unmet, 2)
            ))

    return fresh_h2, topology


def build_cascade_curve(
    fresh_h2: float,
    sources: list[dict],
    sinks: list[dict],
) -> list[GraphPoint]:
    """Построение каскадной кривой избытка водорода.

    Вычисляет кумулятивный баланс водорода по уровням чистоты (сверху вниз,
    от самой высокой концентрации к самой низкой). Кривая используется
    на фронтенде для визуализации избытка.

    Args:
        fresh_h2 (float): Объем свежего 100% водорода, подаваемого в систему.
        sources (list[dict]): Список источников с ключами 'flow_rate' и 'purity'.
        sinks (list[dict]): Список стоков с ключами 'flow_rate' и 'purity'.

    Returns:
        list[GraphPoint]: Список точек (x, y), где x - объем, y - чистота.
    """
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


def run_lp_optimization(
    sources: list[StreamData],
    sinks: list[StreamData],
) -> dict:
    """Метод оптимизации на базе Линейного Программирования (LP).

    Находит оптимальное распределение потоков с учетом смешения и ограничений топологии.
    Оптимизатор минимизирует общий расход свежего водорода (целевая функция).
    Использует библиотеку SciPy (`scipy.optimize.linprog`).

    Args:
        sources (list[StreamData]): Список источников.
        sinks (list[StreamData]): Список стоков.

    Returns:
        dict: Словарь с результатами (успех, расход H2, расписание связей, ошибки).
    """
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


def run_cascade_optimization(
    sources: list[StreamData],
    sinks: list[StreamData],
) -> dict:
    """Метод оптимизации на основе Каскадного Анализа (Пинч-анализ).

    Рассчитывает теоретический минимум потребления свежего водорода, игнорируя
    ограничения топологии (считает, что все трубы можно провести куда угодно).
    Определяет 'Пинч-точку' - уровень чистоты, при котором избыток водорода равен нулю.

    Args:
        sources (list[StreamData]): Список источников.
        sinks (list[StreamData]): Список стоков.

    Returns:
        dict: Словарь с результатами (успех, расход H2, расписание связей, пинч-точка).
    """
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
    """Вспомогательная функция для построения идеальной каскадной топологии.

    Формирует "жадное" распределение от самых чистых источников к самым чистым стокам,
    но с использованием уже вычисленного теоретического минимума свежего водорода (min_fresh).
    Не учитывает ограничения по трубам (allowed_connections).

    Args:
        sources (list[StreamData]): Список источников.
        sinks (list[StreamData]): Список стоков.
        min_fresh (float): Минимальный необходимый объем свежего H2 (из каскада).

    Returns:
        list[TopologyLink]: Идеализированная схема связей (для сравнения).
    """
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


def run_mcmf_optimization(
    sources: list[StreamData],
    sinks: list[StreamData],
) -> dict:
    """Метод оптимизации на основе графов (Min Cost Max Flow).

    Ищет оптимальный маршрут по существующим трубам (`allowed_connections`).
    В отличие от LP, этот метод НЕ поддерживает смешение потоков: источник
    должен быть чище или равен стоку по чистоте для прямой подачи.

    Args:
        sources (list[StreamData]): Список источников.
        sinks (list[StreamData]): Список стоков.

    Returns:
        dict: Словарь с результатами (успех, расход H2, расписание связей).
    """
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

    # Узлы
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

    # Рёбра
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

    # Запуск MCMF
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

    # Извлечение результатов
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


def run_nlp_optimization(
    sources: list[StreamData],
    sinks: list[StreamData],
) -> dict:
    """Метод нелинейной оптимизации (NLP) на базе алгоритма SLSQP.

    Оптимизация с нелинейной целевой функцией. В отличие от LP, метод штрафует
    за избыточный перерасход чистоты (квадратичный штраф), что даёт более
    равномерное и физически реалистичное распределение потоков. Поддерживает
    смешение потоков и учитывает топологию (`allowed_connections`).

    Args:
        sources (list[StreamData]): Список источников.
        sinks (list[StreamData]): Список стоков.

    Returns:
        dict: Словарь с результатами (успех, расход H2, расписание связей).
    """
    N = len(sources)
    M = len(sinks)
    num_vars = N * M + M  # x[i,j] + fresh[j]
    PENALTY = 1e-3  # Штраф за перерасход чистоты

    # Маска запрещённых связей: True = связь запрещена
    blocked = np.zeros(N * M, dtype=bool)
    for i in range(N):
        for j in range(M):
            allowed = sources[i].allowed_connections
            if allowed and sinks[j].id not in allowed:
                blocked[i * M + j] = True

    # Целевая функция: sum(fresh[j]) + penalty * sum((purity_excess[j])^2)
    # purity_excess[j] = (чистота_смеси_j - требуемая_j), если > 0
    def objective(x):
        total_fresh = sum(x[N * M + j] for j in range(M))

        purity_penalty = 0.0
        for j in range(M):
            total_flow_to_j = sum(x[i * M + j] for i in range(N)) + x[N * M + j]
            if total_flow_to_j > 1e-9:
                purity_mix = (
                    sum(x[i * M + j] * sources[i].purity for i in range(N))
                    + x[N * M + j] * 100.0
                ) / total_flow_to_j
                excess = max(0.0, purity_mix - sinks[j].purity)
                purity_penalty += excess ** 2

        return total_fresh + PENALTY * purity_penalty

    # Ограничения
    constraints = []

    # Равенство: каждый сток получает ровно свой flow_rate
    for j in range(M):
        def eq_sink(x, j=j):
            return sum(x[i * M + j] for i in range(N)) + x[N * M + j] - sinks[j].flow_rate
        constraints.append({"type": "eq", "fun": eq_sink})

    # Неравенство: каждый источник не отдаёт больше своего flow_rate
    for i in range(N):
        def ineq_src(x, i=i):
            return sources[i].flow_rate - sum(x[i * M + j] for j in range(M))
        constraints.append({"type": "ineq", "fun": ineq_src})

    # Неравенство: чистота смеси в каждом стоке >= требуемой
    for j in range(M):
        def ineq_purity(x, j=j):
            return (
                sum(x[i * M + j] * sources[i].purity for i in range(N))
                + x[N * M + j] * 100.0
                - sinks[j].flow_rate * sinks[j].purity
            )
        constraints.append({"type": "ineq", "fun": ineq_purity})

    # Границы переменных
    bounds = []
    for i in range(N):
        for j in range(M):
            if blocked[i * M + j]:
                bounds.append((0.0, 0.0))
            else:
                bounds.append((0.0, sources[i].flow_rate))
    for j in range(M):
        bounds.append((0.0, sinks[j].flow_rate))

    # Начальное приближение: всё покрывается свежим H2
    x0 = np.zeros(num_vars)
    for j in range(M):
        x0[N * M + j] = sinks[j].flow_rate

    # Запуск SLSQP
    result = minimize(
        objective, x0,
        method="SLSQP",
        bounds=bounds,
        constraints=constraints,
        options={"maxiter": 1000, "ftol": 1e-10},
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

