"""API Router definitions for FastAPI."""

from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import text, func
from loguru import logger

from src.db.session import get_db
from src.db.models import StreamModel
from src.schemas.pinch import (
    OptMethod, BaselineResponse, OptimizeResponse, 
    StreamData, StreamCollection, DatasetInfo, DatasetsResponse
)
from src.services.optimization import process_optimization
from src.services.solvers import build_cascade_curve, calculate_baseline_fresh_h2

router = APIRouter(prefix="/api/v1/pinch", tags=["Pinch Optimization"])


@router.get("/health", summary="Healthcheck endpoint")
def healthcheck(db: Session = Depends(get_db)):
    """Проверка статуса подключения к базе данных.

    Args:
        db (Session): Сессия подключения к БД (внедряется через Depends).

    Returns:
        dict: Статус приложения и подключения к БД.

    Raises:
        HTTPException: Если подключение к БД недоступно (код 503).
    """
    try:
        db.execute(text("SELECT 1"))
        return {"status": "ok", "database": "connected"}
    except Exception as e:
        logger.error(f"Database connection failed: {e}")
        raise HTTPException(status_code=503, detail="Database is unreachable")


@router.get("/datasets", response_model=DatasetsResponse)
def get_datasets(db: Session = Depends(get_db)):
    """Получить список доступных датасетов.

    Выполняет группировку потоков по `dataset_id` и возвращает информацию
    по каждому доступному датасету в базе данных.

    Args:
        db (Session): Сессия подключения к БД.

    Returns:
        DatasetsResponse: Список информации о датасетах.
    """
    # Count streams per dataset
    results = db.query(StreamModel.dataset_id, func.count(StreamModel.id)).group_by(StreamModel.dataset_id).all()
    
    datasets = []
    for d_id, count in results:
        datasets.append(DatasetInfo(
            id=d_id,
            name=f"Dataset {d_id} (из init_db.py)" if d_id == 1 else f"Dataset {d_id} (Вариация)",
            stream_count=count
        ))
        
    return DatasetsResponse(datasets=datasets)


@router.get("/baseline", response_model=BaselineResponse)
def get_baseline_data(
    dataset_id: int = Query(default=1, description="ID датасета для расчетов"),
    db: Session = Depends(get_db)
):
    """Рассчитать базовое потребление водорода без математической оптимизации.

    Используется простой (жадный) алгоритм назначения источников на стоки.
    Показывает потребление свежего H2 "как есть" (базовый сценарий).

    Args:
        dataset_id (int): Идентификатор датасета в БД. По умолчанию 1.
        db (Session): Сессия подключения к БД.

    Returns:
        BaselineResponse: Базовый расход H2, каскадная кривая и жадная топология.

    Raises:
        HTTPException: Если датасет не найден или в нем отсутствуют стоки.
    """
    logger.info(f"Handling baseline request for dataset {dataset_id}")
    
    rows = db.query(StreamModel).filter(StreamModel.dataset_id == dataset_id).all()
    if not rows:
        raise HTTPException(status_code=404, detail=f"Датасет {dataset_id} не найден (таблица пуста)")

    # Serialize to Pydantic models
    raw_streams = []
    for r in rows:
        raw_streams.append({
            "id": r.id,
            "name": r.name,
            "type": r.type,
            "flow_rate": r.flow_rate,
            "purity": r.purity,
            "allowed_connections": r.allowed_connections or []
        })

    try:
        collection = StreamCollection(streams=raw_streams)
        streams = collection.streams
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))

    sources = [s for s in streams if s.type == "Source"]
    sinks = [s for s in streams if s.type == "Sink"]

    if not sinks:
        raise HTTPException(status_code=422, detail="В данных отсутствуют стоки (Sink)")

    baseline_fresh, topology = calculate_baseline_fresh_h2(streams)

    src_dicts = [{"flow_rate": s.flow_rate, "purity": s.purity} for s in sources]
    snk_dicts = [{"flow_rate": s.flow_rate, "purity": s.purity} for s in sinks]
    curve = build_cascade_curve(baseline_fresh, src_dicts, snk_dicts)

    return BaselineResponse(
        status="success",
        baseline_fresh_h2=round(baseline_fresh, 2),
        baseline_curve=curve,
        baseline_topology=topology,
    )


@router.get("/optimize", response_model=OptimizeResponse)
def run_optimization(
    method: OptMethod = Query(default=OptMethod.LP),
    dataset_id: int = Query(default=1, description="ID датасета для оптимизации"),
    db: Session = Depends(get_db)
):
    """Выполнить математическую оптимизацию водородной сети.

    Позволяет применить один из 4-х доступных методов оптимизации (LP, Cascade, MCMF, NLP).

    Args:
        method (OptMethod): Выбранный метод оптимизации (по умолчанию LP).
        dataset_id (int): Идентификатор датасета в БД. По умолчанию 1.
        db (Session): Сессия подключения к БД.

    Returns:
        OptimizeResponse: Оптимальный расход, экономия, каскадные кривые и новые связи.

    Raises:
        HTTPException: В случае ошибки парсинга, отсутствия данных или сбоя солвера (код 422/404).
    """
    logger.info(f"Handling optimization request for method: {method.value}, dataset: {dataset_id}")
    
    rows = db.query(StreamModel).filter(StreamModel.dataset_id == dataset_id).all()
    if not rows:
        raise HTTPException(status_code=404, detail=f"Датасет {dataset_id} не найден")

    raw_streams = []
    for r in rows:
        raw_streams.append({
            "id": r.id,
            "name": r.name,
            "type": r.type,
            "flow_rate": r.flow_rate,
            "purity": r.purity,
            "allowed_connections": r.allowed_connections or []
        })

    try:
        collection = StreamCollection(streams=raw_streams)
        streams = collection.streams
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))

    try:
        result_dict = process_optimization(streams, method)
        return OptimizeResponse(**result_dict)
    except ValueError as e:
        logger.warning(f"Optimization failed: {e}")
        raise HTTPException(status_code=422, detail=str(e))
