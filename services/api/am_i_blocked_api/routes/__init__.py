"""Route registration for api and UI."""

from .api import router as api_router
from .ui import router as ui_router

__all__ = ["api_router", "ui_router"]
