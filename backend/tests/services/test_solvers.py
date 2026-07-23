"""Тесты для математических алгоритмов оптимизации (solvers)."""

import pytest

from src.schemas.pinch import StreamData, StreamType
from src.services.solvers import (
    build_cascade_curve,
    calculate_baseline_fresh_h2,
    run_cascade_optimization,
    run_lp_optimization,
    run_mcmf_optimization,
    run_nlp_optimization,
)


@pytest.fixture
def sample_streams():
    """Небольшой набор потоков для тестирования алгоритмов."""
    return [
        StreamData(id=1, name="Sink 1", type=StreamType.SINK, flow_rate=100.0, purity=90.0, allowed_connections=[]),
        StreamData(id=2, name="Sink 2", type=StreamType.SINK, flow_rate=50.0, purity=80.0, allowed_connections=[]),
        StreamData(id=3, name="Source 1", type=StreamType.SOURCE, flow_rate=80.0, purity=95.0, allowed_connections=[1, 2]),
        StreamData(id=4, name="Source 2", type=StreamType.SOURCE, flow_rate=60.0, purity=85.0, allowed_connections=[2]),
    ]

def test_calculate_baseline_fresh_h2(sample_streams):
    """Проверка жадного алгоритма (Baseline)."""
    fresh_h2, topology = calculate_baseline_fresh_h2(sample_streams)
    # Sink 1 (100 @ 90%): Source 1 дает 80 @ 95%. Остаток = 20 (свежий H2).
    # Sink 2 (50 @ 80%): Source 1 пуст. Source 2 дает 50 @ 85%. Остаток = 0.
    # Total fresh = 20.0
    assert fresh_h2 == 20.0
    assert len(topology) == 3 # Source1->Sink1, Свежий->Sink1, Source2->Sink2

def test_build_cascade_curve():
    """Проверка построения каскадной кривой."""
    sources = [{"flow_rate": 80.0, "purity": 95.0}]
    sinks = [{"flow_rate": 100.0, "purity": 90.0}]
    fresh_h2 = 20.0
    
    curve = build_cascade_curve(fresh_h2, sources, sinks)
    assert len(curve) > 0
    # Проверка, что кривая начинается с x=0 и спускается/поднимается
    assert curve[0].x == 0.0

def test_run_lp_optimization(sample_streams):
    """Проверка метода линейного программирования (LP)."""
    sources = [s for s in sample_streams if s.type == StreamType.SOURCE]
    sinks = [s for s in sample_streams if s.type == StreamType.SINK]
    
    result = run_lp_optimization(sources, sinks)
    assert result["success"] is True
    assert result["fresh_h2"] >= 0
    # Топология должна быть сформирована
    assert len(result["topology"]) > 0

def test_run_cascade_optimization(sample_streams):
    """Проверка метода каскадного анализа (Пинч)."""
    sources = [s for s in sample_streams if s.type == StreamType.SOURCE]
    sinks = [s for s in sample_streams if s.type == StreamType.SINK]
    
    result = run_cascade_optimization(sources, sinks)
    assert result["success"] is True
    # Каскад всегда дает теоретический минимум, он должен быть <= baseline (20.0)
    assert result["fresh_h2"] <= 20.0
    assert "pinch_point" in result

def test_run_mcmf_optimization(sample_streams):
    """Проверка метода графов (MCMF)."""
    sources = [s for s in sample_streams if s.type == StreamType.SOURCE]
    sinks = [s for s in sample_streams if s.type == StreamType.SINK]
    
    result = run_mcmf_optimization(sources, sinks)
    assert result["success"] is True
    assert result["fresh_h2"] >= 0
    assert len(result["topology"]) > 0

def test_run_nlp_optimization(sample_streams):
    """Проверка метода нелинейного программирования (NLP)."""
    sources = [s for s in sample_streams if s.type == StreamType.SOURCE]
    sinks = [s for s in sample_streams if s.type == StreamType.SINK]
    
    result = run_nlp_optimization(sources, sinks)
    assert result["success"] is True
    assert result["fresh_h2"] >= 0
    assert len(result["topology"]) > 0
