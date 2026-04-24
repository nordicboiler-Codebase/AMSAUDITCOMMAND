.PHONY: help setup run smoke test migrate reset stop db-logs api-logs ui-logs clean

help:
	@echo "TechSource Audit Analytics — dev commands"
	@echo ""
	@echo "  make setup      Full bootstrap: Postgres + deps + migrations + admin + sample data"
	@echo "  make run        Start API (:8000) + Streamlit UI (:8501)"
	@echo "  make smoke      Run end-to-end smoke test against a running API"
	@echo "  make test       Run pytest"
	@echo "  make migrate    Apply Alembic migrations only"
	@echo "  make reset      Drop and recreate the audit DB schema (destructive)"
	@echo "  make stop       Stop API + UI processes"
	@echo "  make db-logs    Tail Postgres logs"
	@echo "  make api-logs   Tail API logs"
	@echo "  make ui-logs    Tail UI logs"
	@echo "  make clean      Remove logs and data directories"

setup:
	./scripts/bootstrap.sh

run:
	./scripts/run.sh

smoke:
	./scripts/smoke.sh

test:
	pytest -q

migrate:
	DATABASE_URL=$${DATABASE_URL:-postgresql+psycopg2://audit:audit@127.0.0.1:5432/audit} \
	  alembic upgrade head

reset:
	docker compose exec -T db psql -U audit -d audit \
	  -c "DROP SCHEMA public CASCADE; CREATE SCHEMA public; GRANT ALL ON SCHEMA public TO audit;"
	$(MAKE) migrate
	python3 scripts/seed_admin.py
	python3 scripts/sample_data.py

stop:
	-pkill -f "uvicorn backend.main" || true
	-pkill -f "streamlit run ui/app.py" || true

db-logs:
	docker compose logs -f db

api-logs:
	tail -f logs/api.log

ui-logs:
	tail -f logs/ui.log

clean:
	rm -rf logs data
