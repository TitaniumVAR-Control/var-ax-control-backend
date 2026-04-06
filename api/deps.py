from __future__ import annotations

from starlette.requests import HTTPConnection

from ..config import settings
from ..db.engine import Database
from ..services.broadcast import BroadcastHub
from ..services.controller import ARXControllerService
from ..services.data_source import CsvSourceCatalog
from ..services.export import DailyExportService
from ..services.repository import ISensorRepository, build_repository
from ..services.runner import SimulationRunner
from ..services.session import SessionService


class AppContext:
    def __init__(self) -> None:
        self.database = Database()
        self.broadcast = BroadcastHub()
        self.controller_service = ARXControllerService()
        self.session_service = SessionService()
        self.catalog = CsvSourceCatalog(settings.processed_data_dir)
        self.repository: ISensorRepository = build_repository(self.database)
        self.export_service = DailyExportService(self.repository)

    async def startup(self) -> None:
        await self.database.connect()
        self.repository = build_repository(self.database)
        self.export_service = DailyExportService(self.repository)
        self.controller_service.load()

    async def shutdown(self) -> None:
        task = self.session_service.state.sim_task
        if task and not task.done():
            task.cancel()
        await self.database.disconnect()

    def build_runner(self) -> SimulationRunner:
        return SimulationRunner(
            self.session_service,
            self.controller_service,
            self.broadcast,
            self.repository,
        )


# FastAPI 의존성 함수

def get_context(conn: HTTPConnection) -> AppContext:
    return conn.app.state.ctx


def get_session_service(conn: HTTPConnection) -> SessionService:
    return conn.app.state.ctx.session_service


def get_controller_service(conn: HTTPConnection) -> ARXControllerService:
    return conn.app.state.ctx.controller_service


def get_catalog(conn: HTTPConnection) -> CsvSourceCatalog:
    return conn.app.state.ctx.catalog


def get_broadcast(conn: HTTPConnection) -> BroadcastHub:
    return conn.app.state.ctx.broadcast


def get_repository(conn: HTTPConnection) -> ISensorRepository:
    return conn.app.state.ctx.repository


def get_export_service(conn: HTTPConnection) -> DailyExportService:
    return conn.app.state.ctx.export_service