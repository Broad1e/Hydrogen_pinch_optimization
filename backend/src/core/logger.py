"""Logger configuration using Loguru."""

import logging
import sys

from loguru import logger


class InterceptHandler(logging.Handler):
    """Перехватчик стандартных сообщений логирования для передачи в Loguru.

    Позволяет направить все логи Uvicorn и FastAPI в единый обработчик Loguru,
    чтобы логи были отформатированы и собраны в одном месте.
    """

    def emit(self, record: logging.LogRecord) -> None:
        """Перехватывает стандартный лог и передает его в loguru."""
        # Получаем соответствующий уровень Loguru, если он существует
        try:
            level = logger.level(record.levelname).name
        except ValueError:
            level = record.levelno

        # Находим вызывающую функцию, откуда пришло сообщение лога
        frame, depth = logging.currentframe(), 2
        while frame and frame.f_code.co_filename == logging.__file__:
            frame = frame.f_back
            depth += 1

        logger.opt(depth=depth, exception=record.exc_info).log(
            level, record.getMessage()
        )


def setup_logging():
    """Настроить Loguru для перехвата логов Uvicorn и FastAPI.

    Удаляет стандартные обработчики логов, настраивает формат вывода
    в консоль для Loguru и подключает InterceptHandler к логгерам uvicorn.
    """
    # Удаляем стандартные обработчики
    logging.root.handlers = []
    
    # Настраиваем Loguru
    logger.remove()
    logger.add(sys.stdout, colorize=True, format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>")

    # Перехватываем стандартное логирование
    logging.getLogger("uvicorn.access").handlers = [InterceptHandler()]
    logging.getLogger("uvicorn.error").handlers = [InterceptHandler()]
    logging.getLogger("fastapi").handlers = [InterceptHandler()]
