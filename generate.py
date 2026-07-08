import csv


def generate_refinery_data(filename="data.csv"):
    """Генерирует реалистичный набор данных водородной сети НПЗ.

    Сценарий: типичный НПЗ средней мощности (~8 млн т/год).

    ПРОБЛЕМА 1 — Дефицит чистого водорода:
      Стоки (гидрокрекинг, ГО ДТ, ГО нафты) требуют суммарно ~830 Нм³/ч
      водорода с чистотой ≥ 90%, а единственный высокочистотный источник
      (PSA) даёт всего 220 Нм³/ч. Дефицит покрывается закупкой свежего H₂.

    ПРОБЛЕМА 2 — Избыток грязного водорода:
      Отходящий газ FCC (65%), продувочный газ (55%) и сбросной газ НТС (50%)
      суммарно дают 650 Нм³/ч, но сейчас сбрасываются в факел/топливную сеть,
      потому что ни одна установка не принимает газ такой чистоты напрямую.

    ПОТЕНЦИАЛ ОПТИМИЗАЦИИ (водородный пинч):
      LP-оптимизатор может предложить смешение грязных потоков со свежим H₂
      для подачи в низко- и среднечистотные стоки, высвободив чистые источники
      для требовательных установок. Ожидаемая экономия: 40–55% свежего H₂.
    """
    streams = [
        # ═══════════════════════════════════════════════════════════════
        #  СТОКИ (SINKS) — потребители водорода
        # ═══════════════════════════════════════════════════════════════

        # ─── Высокочистотные потребители (главный дефицит) ───────────
        {"id": 1, "name": "Гидрокрекинг",
         "type": "Sink", "flow_rate": 350.0, "purity": 97.0,
         "allowed_connections": ""},
        {"id": 2, "name": "ГО дизельного топлива",
         "type": "Sink", "flow_rate": 280.0, "purity": 93.0,
         "allowed_connections": ""},
        {"id": 3, "name": "ГО нафты (риформат)",
         "type": "Sink", "flow_rate": 200.0, "purity": 90.0,
         "allowed_connections": ""},

        # ─── Среднечистотные потребители ────────────────────────────
        {"id": 4, "name": "Гидродепарафинизация",
         "type": "Sink", "flow_rate": 160.0, "purity": 85.0,
         "allowed_connections": ""},
        {"id": 5, "name": "Изомеризация С5/С6",
         "type": "Sink", "flow_rate": 130.0, "purity": 80.0,
         "allowed_connections": ""},

        # ─── Низкочистотные потребители (сюда можно грязный газ) ────
        {"id": 6, "name": "ГО мазута (HDS)",
         "type": "Sink", "flow_rate": 250.0, "purity": 75.0,
         "allowed_connections": ""},
        {"id": 7, "name": "Подпитка ЦВС-компрессора",
         "type": "Sink", "flow_rate": 180.0, "purity": 70.0,
         "allowed_connections": ""},
        {"id": 8, "name": "Регенерация катализатора",
         "type": "Sink", "flow_rate": 120.0, "purity": 60.0,
         "allowed_connections": ""},

        # ═══════════════════════════════════════════════════════════════
        #  ИСТОЧНИКИ (SOURCES) — рецикловые и побочные потоки H₂
        # ═══════════════════════════════════════════════════════════════

        # ─── Высокочистотный (ограниченная мощность PSA) ────────────
        {"id": 11, "name": "PSA-установка",
         "type": "Source", "flow_rate": 220.0, "purity": 99.5,
         "allowed_connections": "1,2"},

        # ─── Средне-высокий ─────────────────────────────────────────
        {"id": 12, "name": "Кат. риформинг",
         "type": "Source", "flow_rate": 300.0, "purity": 88.0,
         "allowed_connections": "2,3,4"},

        # ─── Средние (рецикловые сепараторы) ─────────────────────────
        {"id": 13, "name": "Сепаратор ВСГ (ГК)",
         "type": "Source", "flow_rate": 160.0, "purity": 82.0,
         "allowed_connections": "3,4,5"},
        {"id": 14, "name": "Сепаратор ВСГ (ГО ДТ)",
         "type": "Source", "flow_rate": 130.0, "purity": 78.0,
         "allowed_connections": "4,5,6"},

        # ─── Грязные потоки (ИЗБЫТОК → сейчас идут в факел) ─────────
        {"id": 15, "name": "Отходящий газ FCC",
         "type": "Source", "flow_rate": 270.0, "purity": 65.0,
         "allowed_connections": "6,7,8"},
        {"id": 16, "name": "Продувочный газ",
         "type": "Source", "flow_rate": 200.0, "purity": 55.0,
         "allowed_connections": "7,8"},
        {"id": 17, "name": "Сбросной газ НТС",
         "type": "Source", "flow_rate": 180.0, "purity": 50.0,
         "allowed_connections": "8"},
    ]

    with open(filename, mode="w", encoding="utf-8", newline="") as f:
        fieldnames = [
            "id", "name", "type", "flow_rate", "purity", "allowed_connections"
        ]
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(streams)

    # ─── Статистика ──────────────────────────────────────────────────
    total_sink = sum(s["flow_rate"] for s in streams if s["type"] == "Sink")
    total_src = sum(s["flow_rate"] for s in streams if s["type"] == "Source")
    hi_sink = sum(
        s["flow_rate"] for s in streams
        if s["type"] == "Sink" and s["purity"] >= 90
    )
    hi_src = sum(
        s["flow_rate"] for s in streams
        if s["type"] == "Source" and s["purity"] >= 90
    )
    dirty_src = sum(
        s["flow_rate"] for s in streams
        if s["type"] == "Source" and s["purity"] <= 70
    )

    print(f"{'=' * 60}")
    print(f"  Датасет НПЗ сгенерирован: {filename}")
    print(f"{'=' * 60}")
    print(f"  Стоков:      {sum(1 for s in streams if s['type'] == 'Sink')} шт, "
          f"суммарный расход: {total_sink} Нм3/ч")
    print(f"  Источников:  {sum(1 for s in streams if s['type'] == 'Source')} шт, "
          f"суммарный расход: {total_src} Нм3/ч")
    print(f"  Общий дефицит: {total_sink - total_src} Нм3/ч")
    print(f"  {'-' * 49}")
    print(f"  Спрос на чистый H2 (>=90%):     {hi_sink} Нм3/ч")
    print(f"  Предложение чистого H2 (>=90%): {hi_src} Нм3/ч")
    print(f"  -> Дефицит чистого H2:          {hi_sink - hi_src} Нм3/ч")
    print(f"  {'-' * 49}")
    print(f"  Грязные источники (<=70%):       {dirty_src} Нм3/ч (-> факел)")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    generate_refinery_data()