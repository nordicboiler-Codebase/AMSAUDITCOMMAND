from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.core.config import get_settings
from backend.core.logging import configure_logging

settings = get_settings()
configure_logging(settings.log_level)


def create_app() -> FastAPI:
    app = FastAPI(
        title="TechSource Audit Analytics",
        version="0.1.0",
        description="Detector + Template audit analytics platform",
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

    @app.on_event("startup")
    def _start_scheduler() -> None:
        from backend.services import scheduler

        scheduler.start()

    from backend.api import (
        auth,
        audit_log,
        datasets,
        engagements,
        ensemble,
        findings,
        metrics,
        library,
        nlq,
        packs,
        projects,
        reports,
        risk,
        runs,
        schedules,
        settings,
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

    return app


app = create_app()
