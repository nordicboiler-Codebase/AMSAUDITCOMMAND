from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.core.config import get_settings
from backend.core.logging import configure_logging
from backend.core.rate_limit import global_rate_limit

settings = get_settings()
configure_logging(settings.log_level)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    from backend.services import scheduler
    scheduler.start()
    yield
    # on shutdown: nothing critical — APScheduler daemon threads die with the process


def create_app() -> FastAPI:
    app = FastAPI(
        title="TechSource Audit Analytics",
        version="0.1.0",
        description="Detector + Template audit analytics platform",
        dependencies=[Depends(global_rate_limit)],
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/health")
    def health() -> dict:
        return {"status": "ok", "service": "techsource-audit-analytics"}

    from backend.api import (
        auth,
        audit_log,
        bi_export,
        connectors,
        datasets,
        engagements,
        ensemble,
        findings,
        metrics,
        monitors,
        library,
        nlq,
        packs,
        projects,
        reports,
        risk,
        runs,
        schedules,
        settings,
        subsidiaries,
        templates,
        users,
    )

    app.include_router(auth.router, prefix="/api/auth", tags=["auth"])
    app.include_router(users.router, prefix="/api/users", tags=["users"])
    app.include_router(projects.router, prefix="/api/projects", tags=["projects"])
    app.include_router(datasets.router, prefix="/api/datasets", tags=["datasets"])
    app.include_router(templates.router, prefix="/api/templates", tags=["templates"])
    app.include_router(packs.router, prefix="/api/packs", tags=["packs"])
    app.include_router(runs.router, prefix="/api", tags=["runs"])
    app.include_router(ensemble.router, prefix="/api", tags=["ensemble"])
    app.include_router(risk.router, prefix="/api/datasets", tags=["risk"])
    app.include_router(audit_log.router, prefix="/api/audit-log", tags=["audit-log"])
    app.include_router(nlq.router, prefix="/api", tags=["nlq"])
    app.include_router(reports.router, prefix="/api", tags=["reports"])
    app.include_router(library.router, prefix="/api/library", tags=["library"])
    app.include_router(settings.router, prefix="/api/settings", tags=["settings"])
    app.include_router(findings.router, prefix="/api/findings", tags=["findings"])
    app.include_router(schedules.router, prefix="/api/schedules", tags=["schedules"])
    app.include_router(engagements.router, prefix="/api/engagements", tags=["engagements"])
    app.include_router(metrics.router, prefix="/api/metrics", tags=["metrics"])
    app.include_router(connectors.router, prefix="/api/connectors", tags=["connectors"])
    app.include_router(bi_export.router, prefix="/api/bi", tags=["bi_export"])
    app.include_router(monitors.router, prefix="/api/monitors", tags=["monitors"])
    app.include_router(subsidiaries.router, prefix="/api/subsidiaries", tags=["subsidiaries"])

    return app


app = create_app()
