"""Тесты для эндпоинтов Hydrogen Pinch API."""

import pytest
from fastapi.testclient import TestClient


def test_healthcheck(client: TestClient):
    """Тестирует эндпоинт проверки работоспособности (healthcheck).

    Args:
        client (TestClient): Тестовый клиент FastAPI.
    """
    response = client.get("/api/v1/pinch/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "database": "connected"}


def test_get_datasets(client: TestClient):
    """Тестирует эндпоинт получения списка наборов данных (datasets).

    Args:
        client (TestClient): Тестовый клиент FastAPI.
    """
    response = client.get("/api/v1/pinch/datasets")
    assert response.status_code == 200
    data = response.json()
    assert "datasets" in data
    assert len(data["datasets"]) == 2
    assert data["datasets"][0]["id"] == 1
    assert data["datasets"][1]["id"] == 2


@pytest.mark.parametrize("dataset_id", [1, 2])
def test_get_baseline_data(client: TestClient, dataset_id: int):
    """Тестирует эндпоинт получения базовых данных для различных датасетов.

    Args:
        client (TestClient): Тестовый клиент FastAPI.
        dataset_id (int): Идентификатор набора данных.
    """
    response = client.get(f"/api/v1/pinch/baseline?dataset_id={dataset_id}")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert "baseline_fresh_h2" in data
    assert "baseline_curve" in data
    assert "baseline_topology" in data
    assert len(data["baseline_curve"]) > 0
    assert len(data["baseline_topology"]) > 0


@pytest.mark.parametrize("method", ["lp", "cascade", "mcmf", "nlp"])
def test_optimize_endpoint(client: TestClient, method: str):
    """Тестирует эндпоинт оптимизации со всеми поддерживаемыми методами для датасета 1.

    Args:
        client (TestClient): Тестовый клиент FastAPI.
        method (str): Метод оптимизации ('lp', 'cascade', 'mcmf', 'nlp').
    """
    response = client.get(f"/api/v1/pinch/optimize?method={method}&dataset_id=1")
    assert response.status_code == 200
    data = response.json()
    assert data["method"] == method
    assert "optimized_fresh_h2" in data
    assert "saved_h2" in data
    assert "savings_percent" in data
    assert "optimized_curve" in data
    assert "baseline_topology" in data
    assert "new_topology" in data

    # Проверка физической возможности экономии (>= 0)
    assert data["saved_h2"] >= 0
    assert data["savings_percent"] >= 0

