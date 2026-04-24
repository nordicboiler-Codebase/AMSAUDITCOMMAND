from __future__ import annotations


def test_seed_data_has_148_templates():
    from backend.templates.seed_data import TEMPLATES

    assert len(TEMPLATES) == 148, f"Expected 148 templates, got {len(TEMPLATES)}"


def test_every_template_detector_exists(detector_catalog):
    from backend.templates.seed_data import TEMPLATES

    registered = {d.name for d in detector_catalog.list_all()}
    missing = []
    for tpl in TEMPLATES:
        code, name, detector, *_ = tpl
        if detector not in registered:
            missing.append((code, detector))
    assert not missing, f"Templates reference unregistered detectors: {missing}"


def test_template_codes_are_unique():
    from backend.templates.seed_data import TEMPLATES

    codes = [t[0] for t in TEMPLATES]
    assert len(codes) == len(set(codes)), "Duplicate template codes found"


def test_subledger_coverage():
    from backend.templates.seed_data import TEMPLATES

    by_subledger: dict[str | None, int] = {}
    for t in TEMPLATES:
        sub = t[4]
        by_subledger[sub] = by_subledger.get(sub, 0) + 1
    assert by_subledger.get(None, 0) == 15, "Universal template count mismatch"
    assert by_subledger.get("ACCOUNTS_PAYABLE", 0) >= 25
    assert by_subledger.get("GENERAL_LEDGER", 0) >= 20
    assert by_subledger.get("PAYROLL", 0) >= 15


def test_pack_template_codes_resolve_against_seed_data():
    import importlib.util
    from pathlib import Path

    from backend.templates.seed_data import TEMPLATES

    template_codes = {t[0] for t in TEMPLATES}
    migration_path = Path(__file__).parent.parent / "alembic" / "versions" / "0003_seed_packs.py"
    spec = importlib.util.spec_from_file_location("packs_migration", migration_path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    for _code, _name, _sub, _desc, codes in mod.PACKS:
        for c in codes:
            assert c in template_codes, f"Pack template code {c} missing from seed_data"
