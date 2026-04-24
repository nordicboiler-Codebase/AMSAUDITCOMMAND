"""Create a default admin user and Pilot project if they don't exist."""
from __future__ import annotations

from sqlalchemy import select

from backend.core.db import SessionLocal
from backend.core.security import hash_password
from backend.models import AuditAction, Project, User
from backend.models.enums import UserRole
from backend.services import audit_log


ADMIN_USERNAME = "admin"
ADMIN_PASSWORD = "admin123"
ADMIN_EMAIL = "admin@test.local"
PROJECT_NAME = "Pilot"


def main() -> None:
    db = SessionLocal()
    try:
        admin = db.execute(select(User).where(User.username == ADMIN_USERNAME)).scalar_one_or_none()
        if not admin:
            admin = User(
                username=ADMIN_USERNAME,
                email=ADMIN_EMAIL,
                password_hash=hash_password(ADMIN_PASSWORD),
                role=UserRole.ADMIN,
            )
            db.add(admin)
            db.flush()
            audit_log.log_action(
                db, user_id=admin.id, action=AuditAction.LOGIN,
                entity_type="user", entity_id=str(admin.id),
                details={"seed": True, "username": ADMIN_USERNAME},
            )
            print(f"[admin] created username={ADMIN_USERNAME} password={ADMIN_PASSWORD}")
        else:
            print(f"[admin] already exists: {ADMIN_USERNAME}")

        project = db.execute(select(Project).where(Project.name == PROJECT_NAME)).scalar_one_or_none()
        if not project:
            project = Project(
                name=PROJECT_NAME,
                description="Pilot project for end-to-end verification",
                subsidiary_code="DI-001",
                owner_id=admin.id,
            )
            db.add(project)
            db.flush()
            print(f"[project] created id={project.id}")
        else:
            print(f"[project] already exists: {PROJECT_NAME}")

        db.commit()
    finally:
        db.close()


if __name__ == "__main__":
    main()
