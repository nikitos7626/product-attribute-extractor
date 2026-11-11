import sys
from pathlib import Path

_backend_dir = Path(__file__).resolve().parent.parent
if str(_backend_dir) not in sys.path:
    sys.path.insert(0, str(_backend_dir))

from fastapi import FastAPI

from app.config import settings
from app.exceptions import setup_exception_handlers
from app.lifespan import lifespan, startup_configuration_checks
from app.middlewares import setup_middlewares
from app.routers import extract, system

try:
    from app.routers import tasks
    has_tasks = True
except ImportError:
    has_tasks = False

app = FastAPI(
    title="E-Commerce Product Attribute Extraction API",
    description="Промышленный сервис извлечения характеристик товаров М.Видео AI с многоуровневым каскадом.",
    version="0.2.1",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

setup_middlewares(app)
setup_exception_handlers(app)

app.include_router(extract.router)
if has_tasks:
    app.include_router(tasks.router)
app.include_router(system.router)

# Re-exports for test suite and backward compatibility
from app.routers.system import *  # noqa: F401, F403
from app.routers.system import FRONTEND_DIR, get_frontend_dir  # noqa: F401

__all__ = ["app", "startup_configuration_checks"]
