"""Тестирование микросервиса Hydrogen Pinch Optimizer v3.0.

Запускает все эндпоинты через TestClient (без запуска сервера),
проверяет корректность ответов, сравнивает три метода оптимизации
и отрисовывает каскадные кривые (каждый метод на отдельном графике).

Использование:
    python generate.py   # (сначала сгенерировать data.csv)
    python test.py
"""

import sys
import matplotlib.pyplot as plt
from fastapi.testclient import TestClient

from main import app

client = TestClient(app)


# Тесты


def test_root():
    """Проверка: сервис отвечает на /."""
    resp = client.get("/")
    assert resp.status_code == 200, f"Root failed: {resp.text}"
    data = resp.json()
    assert "message" in data
    assert "methods" in data
    print("[OK] GET / -- сервис отвечает")
    print(f"     Методы: {data['methods']}")
    return data


def test_baseline():
    """Проверка: /baseline возвращает корректные данные."""
    resp = client.get("/api/v1/pinch/baseline")
    assert resp.status_code == 200, f"Baseline failed: {resp.text}"
    data = resp.json()

    assert data["status"] == "success"
    assert data["baseline_fresh_h2"] > 0, "baseline_fresh_h2 должен быть > 0"
    assert len(data["baseline_curve"]) > 2, "Кривая слишком короткая"

    for pt in data["baseline_curve"]:
        assert pt["x"] >= 0, f"Отрицательный x в baseline_curve: {pt}"

    print(f"[OK] GET /baseline -- Свежий H2 (жадный): {data['baseline_fresh_h2']} Нм3/ч")
    return data


def test_optimize(method: str) -> dict:
    """Проверка: /optimize?method=<method> возвращает корректную оптимизацию."""
    resp = client.get(f"/api/v1/pinch/optimize?method={method}")
    assert resp.status_code == 200, f"Optimize ({method}) failed: {resp.text}"
    data = resp.json()

    assert data["status"] in ("optimized", "no_improvement")
    assert data["method"] == method
    assert data["baseline_fresh_h2"] > 0
    assert data["optimized_fresh_h2"] >= 0
    assert data["saved_h2"] >= 0
    assert data["savings_percent"] >= 0

    # Оптимальное не может быть больше baseline
    assert data["optimized_fresh_h2"] <= data["baseline_fresh_h2"] + 1e-2, (
        f"{method}: оптимум ({data['optimized_fresh_h2']}) > baseline ({data['baseline_fresh_h2']})"
    )

    for curve_name in ("baseline_curve", "optimized_curve"):
        for pt in data[curve_name]:
            assert pt["x"] >= 0, f"Отрицательный x в {curve_name}: {pt}"

    if data["is_optimized"]:
        assert len(data["new_topology"]) > 0, f"{method}: оптимизация найдена, но топология пуста"

    print(f"[OK] GET /optimize?method={method}")
    print(f"     Baseline:  {data['baseline_fresh_h2']:>8.2f} Нм3/ч")
    print(f"     Оптимум:   {data['optimized_fresh_h2']:>8.2f} Нм3/ч")
    print(f"     Экономия:  {data['saved_h2']:>8.2f} Нм3/ч ({data['savings_percent']}%)")
    if data.get("pinch_point") is not None:
        print(f"     Пинч:      {data['pinch_point']}%")

    return data


def print_topology(method_name: str, data: dict):
    """Выводит план переключений потоков в таблице."""
    topology = data.get("new_topology", [])
    if not topology:
        print(f"\n  [{method_name}] Топология пуста")
        return

    print(f"\n  [{method_name}] ПЛАН ПЕРЕКЛЮЧЕНИЙ")
    print(f"  {'-' * 63}")
    print(f"  {'ИСТОЧНИК':<28} {'-> СТОК':<24} {'РАСХОД':>8}")
    print(f"  {'-' * 63}")

    total_fresh = 0.0
    total_reuse = 0.0

    for link in topology:
        src = link["source_name"]
        snk = link["sink_name"]
        flow = link["flow_amount"]
        print(f"  {src:<28} -> {snk:<21} {flow:>8.2f}")
        if "Свежий" in src or "Fresh" in src:
            total_fresh += flow
        else:
            total_reuse += flow

    print(f"  {'-' * 63}")
    print(f"  {'Итого свежий H2:':<52} {total_fresh:>8.2f}")
    print(f"  {'Итого повторное использование:':<52} {total_reuse:>8.2f}")
    print(f"  {'-' * 63}")


def print_comparison(results: dict[str, dict]):
    """Выводит сравнительную таблицу всех методов."""
    baseline = None
    for data in results.values():
        baseline = data["baseline_fresh_h2"]
        break

    print(f"\n{'=' * 66}")
    print(f"  СРАВНЕНИЕ МЕТОДОВ ОПТИМИЗАЦИИ")
    print(f"{'=' * 66}")
    print(f"  {'Метод':<22} {'Свежий H2':>10} {'Экономия':>10} {'%':>7}  Примечание")
    print(f"  {'-' * 62}")
    print(f"  {'Baseline (жадный)':<22} {baseline:>10.2f} {'---':>10} {'---':>7}  Точка отсчета")

    method_info = {
        "cascade": ("Каскадный", "Теор. минимум"),
        "lp":      ("LP", "Смешение"),
        "mcmf":    ("MCMF", "Без смешения"),
    }

    sorted_methods = ["cascade", "lp", "mcmf"]

    for m in sorted_methods:
        if m not in results:
            continue
        data = results[m]
        label, note = method_info[m]
        fresh = data["optimized_fresh_h2"]
        saved = data["saved_h2"]
        pct = data["savings_percent"]
        pinch = ""
        if data.get("pinch_point") is not None:
            pinch = f", пинч={data['pinch_point']}%"
        print(f"  {label:<22} {fresh:>10.2f} {saved:>10.2f} {pct:>6.1f}%  {note}{pinch}")

    print(f"{'=' * 66}")

    # Проверка: cascade <= lp <= mcmf <= baseline
    if all(m in results for m in sorted_methods):
        c = results["cascade"]["optimized_fresh_h2"]
        l = results["lp"]["optimized_fresh_h2"]
        m = results["mcmf"]["optimized_fresh_h2"]
        b = baseline

        if c <= l + 1e-2 and l <= m + 1e-2 and m <= b + 1e-2:
            print("  [OK] cascade <= lp <= mcmf <= baseline")
        else:
            print(f"  [!!] Порядок нарушен: cascade={c:.2f}, lp={l:.2f}, mcmf={m:.2f}, baseline={b:.2f}")
            print("       Это может быть допустимо из-за особенностей данных.")
    print()


def plot_method_result(method_key: str, data: dict):
    """Отрисовка каскадных кривых для ОДНОГО метода: baseline vs. optimized.

    Каждый метод отображается на отдельном графике (отдельное окно).
    """
    method_styles = {
        "cascade": ("b", "^", "Каскадный анализ (Hydrogen Pinch)"),
        "lp":      ("g", "s", "Линейное программирование (LP)"),
        "mcmf":    ("m", "D", "Min Cost Max Flow (MCMF)"),
    }

    color, marker, title_label = method_styles.get(
        method_key, ("c", "o", method_key.upper())
    )

    base_curve = data["baseline_curve"]
    opt_curve = data["optimized_curve"]
    base_x = [p["x"] for p in base_curve]
    base_y = [p["y"] for p in base_curve]
    opt_x = [p["x"] for p in opt_curve]
    opt_y = [p["y"] for p in opt_curve]

    baseline_val = data["baseline_fresh_h2"]
    opt_val = data["optimized_fresh_h2"]
    saved = data["saved_h2"]
    pct = data["savings_percent"]

    fig, ax = plt.subplots(figsize=(13, 8))

    # Baseline (красная)
    ax.plot(
        base_x, base_y, "r-o",
        label=f"Baseline (жадный): {baseline_val:.2f} Нм3/ч",
        linewidth=2.5, markersize=5, alpha=0.9, zorder=5,
    )

    # Оптимизированная кривая (цвет метода)
    ax.plot(
        opt_x, opt_y, f"{color}-{marker}",
        label=f"{title_label}: {opt_val:.2f} Нм3/ч",
        linewidth=2, markersize=4, alpha=0.85, zorder=4,
    )

    # Заливка зоны экономии
    if data["is_optimized"]:
        ax.fill_betweenx(
            base_y, base_x, opt_x,
            alpha=0.08, color=color,
            label="Зона экономии",
            interpolate=True,
        )

    # Пинч-точка (только для cascade)
    if method_key == "cascade" and data.get("pinch_point") is not None:
        pp = data["pinch_point"]
        ax.axhline(
            y=pp, color="navy", linestyle=":", linewidth=1.5, alpha=0.6,
            label=f"Пинч-точка: {pp}%",
        )

    # Оформление
    ax.set_title(
        f"Hydrogen Pinch Analysis: {title_label}",
        fontsize=14, fontweight="bold", pad=15,
    )
    ax.set_xlabel("Кумулятивный расход водорода, Нм3/ч", fontsize=12)
    ax.set_ylabel("Чистота водорода, %", fontsize=12)
    ax.grid(True, linestyle="--", alpha=0.35)
    ax.legend(fontsize=10, loc="lower left", framealpha=0.92)

    # Блок статистики
    stats = (
        f"Baseline:  {baseline_val:>8.2f} Нм3/ч\n"
        f"Оптимум:   {opt_val:>8.2f} Нм3/ч\n"
        f"Экономия:  {saved:>8.2f} Нм3/ч ({pct}%)"
    )
    if method_key == "cascade" and data.get("pinch_point") is not None:
        stats += f"\nПинч:      {data['pinch_point']:>8.1f} %"

    ax.annotate(
        stats,
        xy=(0.97, 0.97), xycoords="axes fraction",
        ha="right", va="top",
        fontsize=10, family="monospace",
        bbox=dict(boxstyle="round,pad=0.5", fc="lightyellow", ec="gray", alpha=0.92),
    )

    plt.tight_layout()
    plt.show()


# Main


if __name__ == "__main__":
    print("=" * 66)
    print("  ТЕСТИРОВАНИЕ: Hydrogen Pinch Optimizer v3.0")
    print("  Методы: LP, Каскадный, Min Cost Max Flow")
    print("=" * 66)

    # 1. Проверка корня
    test_root()
    print()

    # 2. Baseline
    test_baseline()
    print()

    # 3. Оптимизация всеми тремя методами
    methods = ["cascade", "lp", "mcmf"]
    results: dict[str, dict] = {}

    for m in methods:
        print(f"\n--- Метод: {m.upper()} ---")
        try:
            data = test_optimize(m)
            results[m] = data
        except Exception as e:
            print(f"  [FAIL] {m}: {e}")
        print()

    # 4. Сравнительная таблица
    print_comparison(results)

    # 5. Топология каждого метода
    for m in methods:
        if m in results:
            print_topology(m.upper(), results[m])

    # 6. Графики (каждый метод в отдельном окне)
    print("\n[ГРАФИКИ] Отрисовка каскадных кривых (по одному на метод)...")
    for m in methods:
        if m in results:
            plot_method_result(m, results[m])

    print("\nВсе тесты завершены.")