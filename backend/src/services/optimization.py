"""Бизнес-логика для управления процессом оптимизации."""

from src.schemas.pinch import StreamType, OptMethod, StreamData
from src.services.solvers import (
    calculate_baseline_fresh_h2,
    build_cascade_curve,
    run_lp_optimization,
    run_cascade_optimization,
    run_mcmf_optimization,
    run_nlp_optimization,
)


def process_optimization(streams: list[StreamData], method: OptMethod) -> dict:
    """Запустить выбранный алгоритм оптимизации и подготовить ответ.

    Данная функция является фасадом для математических солверов. Она подготавливает
    данные, вызывает нужный алгоритм (LP, Cascade, MCMF или NLP), вычисляет
    сэкономленный объем H2 и строит каскадные кривые для отрисовки графиков.

    Args:
        streams (list[StreamData]): Список водородных потоков (источники и стоки).
        method (OptMethod): Метод оптимизации (один из вариантов Enum).

    Returns:
        dict: Словарь с результатами оптимизации (расходы, кривые, топология),
              готовый для сериализации в Pydantic модель OptimizeResponse.

    Raises:
        ValueError: Если отсутствуют стоки/источники, либо если солвер завершился с ошибкой.
    """
    sources = [s for s in streams if s.type == StreamType.SOURCE]
    sinks = [s for s in streams if s.type == StreamType.SINK]

    if not sinks:
        raise ValueError("В данных отсутствуют стоки (Sink)")
    if not sources:
        raise ValueError("В данных отсутствуют источники (Source)")

    baseline_fresh, baseline_topology = calculate_baseline_fresh_h2(streams)

    method_labels = {
        OptMethod.LP: "Линейное программирование",
        OptMethod.CASCADE: "Каскадный анализ",
        OptMethod.MCMF: "Min Cost Max Flow (MCMF)",
        OptMethod.NLP: "Нелинейное программирование (NLP)",
    }
    method_notes = {
        OptMethod.LP: "Учитывает топологию, разрешает смешение потоков",
        OptMethod.CASCADE: "Теоретический минимум (топология игнорируется)",
        OptMethod.MCMF: "Учитывает топологию, только прямые подключения (без смешения)",
        OptMethod.NLP: "Учитывает топологию, смешение + штраф за перерасход чистоты",
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
            raise ValueError(result["error"])
    elif method == OptMethod.NLP:
        result = run_nlp_optimization(sources, sinks)
    else:
        raise ValueError(f"Неизвестный метод: {method}")

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
            msg = f"[{label}] Дальнейшая экономия невозможна. {note}."
    else:
        opt_fresh = baseline_fresh
        saved = 0.0
        pct = 0.0
        is_optimized = False
        opt_curve = baseline_curve
        result["topology"] = []
        msg = f"[{method_labels[method]}] Решение не найдено. Проверьте входные данные."

    return {
        "status": "optimized" if is_optimized else "no_improvement",
        "method": method.value,
        "is_optimized": is_optimized,
        "message": msg,
        "baseline_fresh_h2": round(baseline_fresh, 2),
        "optimized_fresh_h2": round(opt_fresh, 2),
        "saved_h2": round(max(0.0, saved), 2),
        "savings_percent": round(max(0.0, pct), 1),
        "pinch_point": pinch_point,
        "baseline_curve": baseline_curve,
        "optimized_curve": opt_curve,
        "baseline_topology": baseline_topology,
        "new_topology": result["topology"],
    }
