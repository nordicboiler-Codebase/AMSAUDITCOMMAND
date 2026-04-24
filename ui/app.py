from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

import httpx
import pandas as pd
import streamlit as st

sys.path.insert(0, str(Path(__file__).parent))
from i18n import SUPPORTED, apply_rtl_if_needed, t  # noqa: E402
from theme import (  # noqa: E402
    COLORS, card_close, card_open, empty_state, group_banner, heat_tile, inject_css,
    metric_card, section_header, severity_badge, status_badge,
)

API_BASE = os.environ.get("API_BASE_URL", "http://localhost:8000")

NAVY = "#0b2a4a"
TEAL = "#15a8a8"

st.set_page_config(
    page_title="TechSource Audit Analytics",
    page_icon="🛡️",
    layout="wide",
    initial_sidebar_state="expanded",
)

inject_css()


def _client() -> httpx.Client:
    headers = {}
    if st.session_state.get("token"):
        headers["Authorization"] = f"Bearer {st.session_state['token']}"
    return httpx.Client(base_url=API_BASE, headers=headers, timeout=60.0)


def api_get(path: str, **kwargs):
    with _client() as c:
        return c.get(path, **kwargs)


def api_post(path: str, **kwargs):
    with _client() as c:
        return c.post(path, **kwargs)


def show_error(resp) -> None:
    try:
        detail = resp.json().get("detail")
        if isinstance(detail, list):
            msgs = [d.get("msg", str(d)) for d in detail]
            st.error("\n".join(msgs))
            return
        if detail:
            st.error(str(detail))
            return
    except Exception:
        pass
    st.error(f"HTTP {resp.status_code}: {resp.text[:500]}")


def call_with_spinner(message: str, fn, *args, **kwargs):
    try:
        with st.spinner(message):
            return fn(*args, **kwargs)
    except Exception as e:
        st.error(f"Request failed: {e}")
        return None


def _fetch_me_with_token(token: str) -> dict | None:
    me = httpx.get(
        f"{API_BASE}/api/auth/me",
        headers={"Authorization": f"Bearer {token}"},
        timeout=15.0,
    )
    return me.json() if me.status_code == 200 else None


def _lang_picker(label_source: str = "login") -> None:
    """Render a compact language picker. label_source is just a unique widget key."""
    current = st.session_state.get("lang", "en")
    choice = st.selectbox(
        t("common.language"),
        options=list(SUPPORTED.keys()),
        format_func=lambda k: SUPPORTED[k],
        index=list(SUPPORTED.keys()).index(current),
        key=f"lang_picker_{label_source}",
    )
    if choice != current:
        st.session_state["lang"] = choice
        st.rerun()


def login_view() -> None:
    apply_rtl_if_needed()
    # Handle SSO redirect: /?sso_token=<jwt>
    params = st.query_params
    if params.get("sso_token"):
        token = params["sso_token"]
        user = _fetch_me_with_token(token)
        if user:
            st.session_state["token"] = token
            st.session_state["user"] = user
            st.query_params.clear()
            st.rerun()
        else:
            st.error("SSO succeeded but profile fetch failed.")
            st.query_params.clear()

    # Cleaner login: centered column, brand strip at top, language in header
    top_l, top_r = st.columns([4, 1])
    with top_r:
        _lang_picker("login")
    st.markdown(
        """
        <div style="text-align:center; padding: 60px 20px 20px 20px;">
          <div style="font-size: 3rem;">🛡️</div>
          <h1 style="margin-top: 8px;">TechSource Audit Analytics</h1>
          <p style="color:#6b7684; margin-top:-4px;">Group-wide internal audit intelligence</p>
        </div>
        """,
        unsafe_allow_html=True,
    )
    center = st.columns([1, 2, 1])[1]
    with center:
        pass  # form below fills centre column

    try:
        sso_status = httpx.get(f"{API_BASE}/api/settings/sso/status", timeout=5.0).json()
    except Exception:
        sso_status = {"enabled": False}

    if sso_status.get("enabled"):
        label_map = {
            "azure_ad": "🪟 Sign in with Microsoft",
            "google": "🅶 Sign in with Google",
            "okta": "🔐 Sign in with Okta",
            "generic_oidc": "🔐 Sign in with SSO",
        }
        label = label_map.get(sso_status.get("provider"), "🔐 Sign in with SSO")
        st.link_button(label, f"{API_BASE}/api/auth/sso/login", use_container_width=True)
        st.markdown(
            "<div style='text-align:center;color:#888;margin:12px 0;'>— or —</div>",
            unsafe_allow_html=True,
        )

    with st.form("login"):
        username = st.text_input(t("auth.username"))
        password = st.text_input(t("auth.password"), type="password")
        submit = st.form_submit_button(t("auth.sign_in"))
    if submit:
        r = httpx.post(
            f"{API_BASE}/api/auth/token",
            data={"username": username, "password": password},
            timeout=30.0,
        )
        if r.status_code == 200:
            data = r.json()
            if data.get("mfa_required"):
                st.session_state["mfa_challenge"] = data["challenge_token"]
                st.rerun()
            else:
                st.session_state["token"] = data["access_token"]
                user = _fetch_me_with_token(st.session_state["token"])
                if user:
                    st.session_state["user"] = user
                st.rerun()
        else:
            st.error(f"Login failed: {r.text}")

    if st.session_state.get("mfa_challenge"):
        st.divider()
        st.info("🔐 Multi-factor authentication required. Enter the 6-digit code from your authenticator app.")
        with st.form("mfa_form"):
            code = st.text_input("Authenticator code", max_chars=6)
            c1, c2 = st.columns(2)
            verify = c1.form_submit_button("Verify")
            cancel = c2.form_submit_button("Cancel")
        if verify and code:
            r = httpx.post(f"{API_BASE}/api/auth/mfa/verify",
                           json={"challenge_token": st.session_state["mfa_challenge"],
                                 "token": code},
                           timeout=15.0)
            if r.status_code == 200:
                st.session_state["token"] = r.json()["access_token"]
                user = _fetch_me_with_token(st.session_state["token"])
                if user:
                    st.session_state["user"] = user
                st.session_state.pop("mfa_challenge", None)
                st.rerun()
            else:
                st.error(r.text)
        if cancel:
            st.session_state.pop("mfa_challenge", None)
            st.rerun()


NAV_GROUPS = [
    ("Overview", [("Dashboard", "📊")]),
    ("Audit workflow", [
        ("Engagements", "📁"), ("Findings", "🔎"), ("Schedules", "⏰"),
    ]),
    ("Data & analysis", [
        ("Datasets", "💾"), ("Connectors", "🔌"), ("Run", "▶️"),
        ("Risk Explorer", "🎯"), ("Test Runs", "📜"),
    ]),
    ("Library", [
        ("Templates", "🧪"), ("Packs", "📦"),
        ("Template Editor", "✏️"), ("Library", "📚"),
    ]),
    ("Governance", [
        ("Subsidiaries", "🏢"), ("Projects", "🗂️"), ("Audit Log", "🛡️"),
    ]),
    ("Insights", [("ML Feedback", "🏷️")]),
    ("Admin", [("Admin", "👥"), ("Settings", "⚙️")]),
]

NAV_KEYS = {
    "Dashboard": "nav.dashboard", "Projects": "nav.projects",
    "Engagements": "nav.engagements", "Datasets": "nav.datasets",
    "Connectors": "nav.connectors", "Templates": "nav.templates",
    "Packs": "nav.packs", "Run": "nav.run",
    "Risk Explorer": "nav.risk_explorer", "Findings": "nav.findings",
    "Schedules": "nav.schedules", "Test Runs": "nav.test_runs",
    "Audit Log": "nav.audit_log", "Template Editor": "nav.template_editor",
    "Library": "nav.library", "Admin": "nav.admin",
    "Settings": "nav.settings", "Subsidiaries": "nav.subsidiaries",
    "ML Feedback": "nav.ml_feedback",
}


def _session_warning() -> None:
    exp = st.session_state.get("user", {}).get("session_expires_at")
    if not exp:
        return
    from datetime import datetime, timezone

    try:
        remaining = (datetime.fromisoformat(exp) - datetime.now(timezone.utc)).total_seconds()
    except Exception:
        return
    if 0 < remaining < 300:
        mins = int(remaining // 60)
        cols = st.columns([5, 1])
        cols[0].warning(f"⏰ Session expires in {mins}m — click to extend")
        if cols[1].button("Extend session"):
            r = api_post("/api/auth/refresh")
            if r.status_code == 200:
                st.session_state["token"] = r.json()["access_token"]
                me = _fetch_me_with_token(st.session_state["token"])
                if me:
                    st.session_state["user"] = me
                st.rerun()


def sidebar() -> str:
    apply_rtl_if_needed()
    _session_warning()
    with st.sidebar:
        # Brand strip
        st.markdown(
            """
            <div style="padding: 8px 0 14px 0; text-align: center;">
              <div style="font-size: 1.6rem;">🛡️</div>
              <div style="color: white; font-weight: 600; font-size: 0.95rem; margin-top: 2px;">
                TechSource Audit
              </div>
              <div style="color: #9aa5b1; font-size: 0.68rem; letter-spacing: 0.08em;
                          text-transform: uppercase; margin-top: 2px;">
                Group audit intelligence
              </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        _lang_picker("sidebar")

        user_name = st.session_state['user']['username']
        role = st.session_state['user']['role']
        st.markdown(
            f"""
            <div style="background: rgba(255,255,255,0.06); border-radius: 8px;
                        padding: 8px 12px; margin: 6px 0;">
              <div style="color: white; font-weight: 600; font-size: 0.9rem;">{user_name}</div>
              <div style="color: #9aa5b1; font-size: 0.72rem;">{role}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        projects = api_get("/api/projects").json() if st.session_state.get("token") else []
        project_names = {p["name"]: p["id"] for p in projects}
        sel_project = st.selectbox(t("common.active_project"), ["(none)"] + list(project_names.keys()))
        st.session_state["project_id"] = project_names.get(sel_project)
        datasets = []
        if st.session_state.get("project_id"):
            r = api_get("/api/projects")
            if r.status_code == 200:
                pass
        sel_dataset = st.text_input(t("common.active_dataset"), st.session_state.get("dataset_id", ""))
        st.session_state["dataset_id"] = sel_dataset or None
        st.divider()
        # Grouped navigation (no visible radio — section header + buttons per item)
        current = st.session_state.get("_nav_page", "Dashboard")
        for group_label, items in NAV_GROUPS:
            st.markdown(
                f"<div class='ts-nav-group'>{group_label}</div>",
                unsafe_allow_html=True,
            )
            for name, icon in items:
                label = f"{icon}  {t(NAV_KEYS.get(name, name))}"
                is_active = (current == name)
                btn_type = "primary" if is_active else "secondary"
                if st.button(label, key=f"nav_{name}", use_container_width=True,
                             type=btn_type):
                    st.session_state["_nav_page"] = name
                    st.rerun()
        page = st.session_state.get("_nav_page", "Dashboard")

        st.divider()
        if st.button(t("auth.sign_out")):
            st.session_state.clear()
            st.rerun()
    return page


def dashboard_view() -> None:
    section_header(
        t("nav.dashboard"),
        "Group-wide audit posture across all subsidiaries, engagements, and open findings.",
    )
    m = api_get("/api/metrics/dashboard").json()
    rollup_resp = api_get("/api/subsidiaries/rollup")
    rollup = rollup_resp.json() if rollup_resp.status_code == 200 else []

    group_banner(
        f"Group audit: {len(rollup)} subsidiaries in scope",
        f"{sum(r['findings_open'] for r in rollup)} open findings "
        f"• {sum(r['findings_high_critical'] for r in rollup)} high / critical "
        f"• {sum(r['test_runs'] for r in rollup)} test runs logged",
    )

    # Primary metrics
    c1, c2, c3, c4 = st.columns(4)
    with c1: metric_card("Open findings", m.get("findings_open", 0),
                         delta=f"+{m.get('findings_this_month', 0)} last 30d",
                         trend="up" if m.get("findings_this_month", 0) > 0 else "flat",
                         icon="📋")
    with c2: metric_card("High / Critical", m.get("findings_high_or_critical", 0),
                         icon="🚨",
                         accent=COLORS["danger"] if m.get("findings_high_or_critical", 0) else None)
    with c3: metric_card("Active engagements", m.get("engagements_in_progress", 0),
                         icon="📁")
    with c4: metric_card("Subsidiaries", len(rollup), icon="🏢")

    st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)

    c5, c6, c7, c8 = st.columns(4)
    with c5: metric_card("Runs last 7 days", m.get("runs_this_week", 0), icon="▶️")
    with c6: metric_card("Active schedules", m.get("schedules_active", 0), icon="⏰")
    with c7: metric_card("Datasets", m.get("datasets", 0), icon="💾")
    with c8: metric_card("Templates", 148, icon="🧪")

    st.markdown("<div style='height:16px'></div>", unsafe_allow_html=True)

    # Subsidiary heatmap + trend side by side
    col_heat, col_trend = st.columns([5, 7])

    with col_heat:
        card_open("Subsidiary risk heatmap")
        if rollup:
            top_subs = rollup[:8]
            cols = st.columns(2)
            for i, r in enumerate(top_subs):
                with cols[i % 2]:
                    meta = (f"{r['findings_open']} open • {r['findings_high_critical']} H/C "
                            f"• {r['test_runs']} runs")
                    heat_tile(r["code"], r["name"] or r["code"],
                              r["max_risk_score"] or 0.0, meta=meta)
        else:
            empty_state("🏢", "No subsidiaries configured",
                        "Admin → Subsidiaries to register your group entities.")
        card_close()

    with col_trend:
        card_open("Findings trend — last 12 weeks")
        trend = m.get("finding_trend_last_84d", [])
        if trend:
            df = pd.DataFrame(trend)
            df["week"] = pd.to_datetime(df["week"])
            st.line_chart(df.set_index("week"), height=180)
        else:
            empty_state("📈", "No historical data yet",
                        "Trend populates once findings accumulate over multiple weeks.")
        card_close()

        card_open("Severity mix (open findings)")
        sev = m.get("findings_by_severity", {})
        if sev:
            df = pd.DataFrame(
                [{"Severity": s, "Count": n} for s, n in sev.items()]
            ).sort_values("Severity")
            st.bar_chart(df.set_index("Severity"), height=140)
        else:
            empty_state("✅", "No open findings", "You're clear across all subsidiaries.")
        card_close()

    # Top risky records — full width card
    card_open("Top 10 records at risk — cross-subsidiary")
    top = m.get("top_risk_records", [])
    if top:
        df = pd.DataFrame([
            {"Record": r["record_key"], "Score": round(r["score"], 1),
             "Detectors that fired": ", ".join(r["detectors"])}
            for r in top
        ])
        st.dataframe(df, use_container_width=True, hide_index=True)
    else:
        empty_state("🎯", "No risk scores yet",
                    "Run a pack and compute an ensemble to see the top-risk roll-up.")
    card_close()


def projects_view() -> None:
    section_header(
        t("nav.projects"),
        "An audit project scopes work to a subsidiary or cross-entity theme.",
    )
    subs = api_get("/api/subsidiaries").json() if st.session_state.get("token") else []
    sub_map = {s["code"]: s for s in subs}

    with st.expander("➕ New project"):
        with st.form("new_project"):
            name = st.text_input("Name", placeholder="Q2 2026 AP Review — SUB-001")
            description = st.text_area("Description")
            sub_codes = [""] + [s["code"] for s in subs]
            subsidiary_code = st.selectbox(
                "Subsidiary", sub_codes,
                format_func=lambda c: (f"{c} — {sub_map[c]['name']}" if c else "(none)"),
            )
            if st.form_submit_button("Create project"):
                r = api_post("/api/projects", json={
                    "name": name, "description": description,
                    "subsidiary_code": subsidiary_code or None,
                })
                if r.status_code == 200:
                    st.toast("Project created", icon="✅")
                    st.rerun()
                else:
                    show_error(r)

    rows = api_get("/api/projects").json()
    if not rows:
        empty_state("🗂️", "No projects yet",
                    "Create your first audit project to start importing data and running packs.")
        return

    cols = st.columns(3)
    for i, p in enumerate(rows):
        sub = sub_map.get(p.get("subsidiary_code"), {})
        with cols[i % 3]:
            st.markdown(
                f"""
                <div class="ts-card" style="min-height: 140px;">
                  <div style="display:flex; justify-content:space-between; align-items:center;">
                    <div style="font-weight:600; color:#0b2a4a;">{p['name']}</div>
                    <span class="ts-badge muted">{p.get('status', 'ACTIVE')}</span>
                  </div>
                  <div style="color:#6b7684; font-size:0.8rem; margin-top:4px;">
                    {sub.get('name', p.get('subsidiary_code') or 'No subsidiary')}
                  </div>
                  <div style="color:#6b7684; font-size:0.82rem; margin-top:10px;">
                    {p.get('description') or ''}
                  </div>
                </div>
                """,
                unsafe_allow_html=True,
            )


SAMPLE_FILES = {
    "ACCOUNTS_PAYABLE": ("samples/accounts_payable_sample.csv",
                         "5 rows — planted duplicate payment, threshold avoidance, late-night reversal"),
    "ACCOUNTS_RECEIVABLE": ("samples/accounts_receivable_sample.csv",
                            "7 rows — credit-limit breach, aged invoice, large write-off"),
    "GENERAL_LEDGER": ("samples/general_ledger_sample.csv",
                       "6 rows — backdated entry, 'test plug' keyword, unbalanced entry"),
    "PAYROLL": ("samples/payroll_sample.csv",
                "6 rows — shared bank account, ghost employee, 50% pay raise"),
}


def datasets_view() -> None:
    section_header(
        t("datasets.title"),
        "Raw source data, hashed on import and stored Fernet-encrypted at rest.",
    )
    if not st.session_state.get("project_id"):
        empty_state("💾", "No active project",
                    "Datasets are scoped to a project — pick one in the sidebar first.")
        return

    with st.expander("📥 Need a sample? Download a ready-made CSV", expanded=False):
        st.caption(
            "Each sample has planted fraud signals — import it, run the matching pack, "
            "and findings fire immediately. Column reference for your own data: see `samples/README.md`."
        )
        for subledger, (path, desc) in SAMPLE_FILES.items():
            p = Path(path)
            if not p.exists():
                continue
            cols = st.columns([2, 3, 2])
            cols[0].markdown(f"**{subledger}**")
            cols[1].caption(desc)
            cols[2].download_button(
                label=f"Download {p.name}",
                data=p.read_bytes(),
                file_name=p.name,
                mime="text/csv",
                key=f"dl_{subledger}",
            )

    with st.expander("Import dataset"):
        with st.form("import"):
            file = st.file_uploader("File (CSV, XLSX, Parquet)")
            name = st.text_input("Dataset name")
            subledger = st.selectbox("Subledger type", [
                "GENERAL_LEDGER", "ACCOUNTS_PAYABLE", "ACCOUNTS_RECEIVABLE", "PAYROLL",
                "FIXED_ASSETS", "INVENTORY", "BANK", "PROCUREMENT", "TE", "SALES", "OTHER",
            ])
            description = st.text_area("Description")
            if st.form_submit_button("Import") and file and name:
                files = {"file": (file.name, file.getvalue())}
                data = {
                    "project_id": st.session_state["project_id"],
                    "name": name,
                    "subledger_type": subledger,
                    "description": description,
                }
                r = call_with_spinner(
                    f"Hashing + importing {file.name}...",
                    api_post, "/api/datasets/import", files=files, data=data,
                )
                if r is None:
                    pass
                elif r.status_code == 200:
                    st.success(f"Imported. Dataset ID: {r.json()['dataset_id']}")
                    st.toast("Import complete", icon="✅")
                else:
                    show_error(r)
    st.subheader("Datasets in this project")
    listing = api_get("/api/datasets", params={"project_id": st.session_state["project_id"]})
    if listing.status_code == 200:
        rows = listing.json()
        if rows:
            df = pd.DataFrame([
                {"id": r["id"], "name": r["name"], "subledger": r["subledger_type"],
                 "records": r["record_count"], "file": r["source_filename"]}
                for r in rows
            ])
            st.dataframe(df, use_container_width=True, hide_index=True)
            picker = {f"{r['name']} ({r['record_count']} rows)": r["id"] for r in rows}
            chosen = st.selectbox("Set as active dataset", ["(none)"] + list(picker.keys()))
            if chosen != "(none)":
                st.session_state["dataset_id"] = picker[chosen]
                st.success(f"Active dataset set to {picker[chosen]}")
        else:
            st.info("No datasets imported yet for this project.")

    if st.session_state.get("dataset_id"):
        info = api_get(f"/api/datasets/{st.session_state['dataset_id']}")
        if info.status_code == 200:
            st.subheader("Dataset details")
            st.json(info.json())
            preview = api_get(f"/api/datasets/{st.session_state['dataset_id']}/preview?rows=100")
            if preview.status_code == 200:
                st.subheader("Preview (first 100)")
                st.dataframe(pd.DataFrame(preview.json()["rows"]), use_container_width=True, hide_index=True)


def templates_view() -> None:
    st.header("Test Templates")
    subledger = st.selectbox("Subledger filter", [
        "", "GENERAL_LEDGER", "ACCOUNTS_PAYABLE", "ACCOUNTS_RECEIVABLE", "PAYROLL",
        "FIXED_ASSETS", "INVENTORY", "BANK", "PROCUREMENT", "TE", "SALES",
    ])
    params: dict[str, Any] = {}
    if subledger:
        params["subledger"] = subledger
    rows = api_get("/api/templates", params=params).json()
    st.dataframe(pd.DataFrame([
        {"code": t["code"], "name": t["name"], "detector": t["detector_name"],
         "category": t["category"], "weight": t["default_weight"]}
        for t in rows
    ]), use_container_width=True, hide_index=True)
    code = st.text_input("Template code to inspect")
    if code:
        detail = api_get(f"/api/templates/{code}")
        if detail.status_code == 200:
            st.json(detail.json())


def packs_view() -> None:
    st.header("Domain Packs")
    rows = api_get("/api/packs").json()
    st.dataframe(pd.DataFrame([
        {"code": p["code"], "name": p["name"], "subledger": p["subledger_type"],
         "templates": len(p.get("template_codes", []))}
        for p in rows
    ]), use_container_width=True, hide_index=True)
    code = st.text_input("Pack code")
    if code:
        d = api_get(f"/api/packs/{code}")
        if d.status_code == 200:
            st.json(d.json())
            if st.button(f"Run {code} on active dataset") and st.session_state.get("dataset_id"):
                r = call_with_spinner(
                    f"Running pack {code} — this can take 30–60s for a full pack...",
                    api_post, "/api/packs/run",
                    json={
                        "dataset_id": st.session_state["dataset_id"], "pack_code": code,
                        "template_overrides": {}
                    },
                )
                if r and r.status_code == 200:
                    data = r.json()
                    s = data.get("summary", {})
                    st.success(f"Pack complete: {s.get('templates_run', 0)} tests ran")
                    st.toast("Pack run complete", icon="✅")
                    st.json(data)
                elif r is not None:
                    show_error(r)


def _render_param_form(schema: dict, prefix: str) -> dict[str, Any]:
    """Auto-render a typed form from a detector schema; return {param: value} dict."""
    values: dict[str, Any] = {}
    for f in schema.get("fields", []):
        name = f["name"]
        default = f.get("default")
        t = f.get("inferred_type", "string")
        key = f"{prefix}_{name}"
        if t == "bool":
            values[name] = st.checkbox(name, value=bool(default), key=key)
        elif t == "int":
            values[name] = st.number_input(name, value=int(default or 0), step=1, key=key)
        elif t == "float":
            values[name] = st.number_input(name, value=float(default or 0.0), key=key)
        elif t == "date":
            s = st.text_input(name, value=str(default or ""), key=key, placeholder="YYYY-MM-DD")
            values[name] = s or None
        elif t == "string_list":
            s = st.text_input(
                name, value=",".join(map(str, default or [])), key=key,
                placeholder="comma-separated",
            )
            values[name] = [x.strip() for x in s.split(",") if x.strip()]
        elif t == "list":
            s = st.text_area(name, value=json.dumps(default or []), key=key)
            try:
                values[name] = json.loads(s or "[]")
            except Exception:
                values[name] = []
        elif t == "dict":
            s = st.text_area(name, value=json.dumps(default or {}, indent=2), key=key)
            try:
                values[name] = json.loads(s or "{}")
            except Exception:
                values[name] = {}
        elif t == "column_ref":
            values[name] = st.text_input(
                name, value=str(default or ""), key=key,
                help="Column name in the dataset",
            )
        else:
            values[name] = st.text_input(name, value=str(default or ""), key=key)
    return values


def run_view() -> None:
    st.header("Run Tests")
    tab1, tab2, tab3 = st.tabs(["Single Template", "Pack", "Custom Detector"])
    dsid = st.session_state.get("dataset_id")
    if not dsid:
        st.warning("Set active dataset ID in the sidebar.")
        return
    with tab1:
        code = st.text_input("Template code", key="t_code")
        overrides: dict[str, Any] = {}
        if code:
            tpl_r = api_get(f"/api/templates/{code}")
            if tpl_r.status_code == 200:
                tpl = tpl_r.json()
                st.caption(f"**{tpl['name']}** — detector: `{tpl['detector_name']}`")
                sch = api_get(f"/api/templates/detectors/{tpl['detector_name']}/schema")
                if sch.status_code == 200:
                    schema = sch.json()
                    # Merge template defaults into schema field defaults
                    tpl_defaults = tpl.get("default_params") or {}
                    for f in schema["fields"]:
                        if f["name"] in tpl_defaults:
                            f["default"] = tpl_defaults[f["name"]]
                    overrides = _render_param_form(schema, prefix=f"t_{code}")
            else:
                st.warning(f"Template not found: {code}")
        if st.button("Run template") and code:
            body = {"dataset_id": dsid, "template_code": code, "param_overrides": overrides}
            r = call_with_spinner(
                f"Running template {code}...", api_post, "/api/runs/template", json=body,
            )
            if r and r.status_code == 200:
                data = r.json()
                st.success(f"Complete: {data.get('findings_count', 0)} findings")
                st.toast("Template run complete", icon="✅")
                st.json(data)
            elif r is not None:
                show_error(r)
    with tab2:
        pack = st.text_input("Pack code", key="p_code")
        if st.button("Run pack") and pack:
            r = call_with_spinner(
                f"Running pack {pack}...", api_post, "/api/packs/run",
                json={"dataset_id": dsid, "pack_code": pack, "template_overrides": {}},
            )
            if r and r.status_code == 200:
                data = r.json()
                s = data.get("summary", {})
                st.success(f"Pack complete: {s.get('templates_run', 0)} tests ran")
                st.json(data)
            elif r is not None:
                show_error(r)
    with tab3:
        det = st.text_input("Detector name", key="d_name",
                            help="e.g. benford, duplicates, weekend_transactions, zscore_outlier")
        params: dict[str, Any] = {}
        if det:
            sch = api_get(f"/api/templates/detectors/{det}/schema")
            if sch.status_code == 200:
                schema = sch.json()
                st.caption(f"**{schema['category']}** — {schema['description']}")
                params = _render_param_form(schema, prefix=f"d_{det}")
            else:
                st.warning(f"Detector not found: {det}")
        if st.button("Run detector") and det and params is not None:
            body = {"dataset_id": dsid, "detector_name": det, "params": params}
            r = call_with_spinner(
                f"Running detector {det}...", api_post, "/api/runs/detector", json=body,
            )
            if r and r.status_code == 200:
                data = r.json()
                st.success(f"Complete: {data.get('findings_count', 0)} findings")
                st.json(data)
            elif r is not None:
                show_error(r)


def risk_view() -> None:
    section_header(
        t("risk.title"),
        "Every record, scored 0–100 with per-detector explainability. Sort, filter, drill down.",
    )
    dsid = st.session_state.get("dataset_id")
    if not dsid:
        empty_state("🎯", "No active dataset",
                    "Pick a dataset on the Datasets page to score it.")
        return

    col_a, col_b = st.columns([3, 1])
    with col_a:
        st.caption("Ensemble scoring aggregates every completed test run on this dataset.")
    with col_b:
        if st.button("Run / refresh ensemble"):
            runs_resp = api_get(f"/api/datasets/{dsid}/runs")
            if runs_resp.status_code != 200:
                show_error(runs_resp)
            else:
                completed = [r["id"] for r in runs_resp.json() if r.get("status") == "COMPLETED"]
                if not completed:
                    st.warning("No completed test runs yet. Run a template or pack first.")
                else:
                    ens = call_with_spinner(
                        f"Scoring ensemble across {len(completed)} runs...",
                        api_post, "/api/ensemble",
                        json={"dataset_id": dsid, "test_run_ids": completed},
                    )
                    if ens and ens.status_code == 200:
                        s = ens.json().get("summary", {})
                        st.success(
                            f"Ensemble complete: {s.get('records_scored', 0)} records | "
                            f"max={round(s.get('max_score', 0), 1)} mean={round(s.get('mean_score', 0), 1)}"
                        )
                        st.toast("Ensemble scored", icon="🎯")
                    elif ens is not None:
                        show_error(ens)

    min_score = st.slider("Minimum score", 0, 100, 50)
    r = api_get(f"/api/datasets/{dsid}/risk-scores",
                params={"min_score": min_score, "limit": 500, "sort": "desc"})
    if r.status_code != 200:
        show_error(r)
        return
    rows = r.json()
    if not rows:
        empty_state("🎯", "No scores in this range",
                    "Lower the threshold, or run a pack + ensemble first.")
        return

    try:
        from st_aggrid import AgGrid, GridOptionsBuilder
        df = pd.DataFrame([
            {
                "record_key": x["record_key"],
                "score": round(x["score"], 1),
                "severity": ("CRITICAL" if x["score"] >= 90 else
                             "HIGH" if x["score"] >= 70 else
                             "MEDIUM" if x["score"] >= 40 else "LOW"),
                "detectors_count": len(x["contributing_detectors"]),
                "detectors": ", ".join(sorted({c.get("detector_name", "")
                                               for c in x["contributing_detectors"]})),
            }
            for x in rows
        ])
        gb = GridOptionsBuilder.from_dataframe(df)
        gb.configure_default_column(filter=True, sortable=True, resizable=True)
        gb.configure_selection(selection_mode="single")
        gb.configure_column("score", width=100,
                            cellStyle={"textAlign": "right", "fontWeight": 600})
        gb.configure_column("detectors", flex=2)
        grid = AgGrid(df, gridOptions=gb.build(), theme="alpine",
                      height=480, fit_columns_on_grid_load=True)
        selected = grid.get("selected_rows") or []
        if len(selected) > 0:
            rec = selected[0]["record_key"] if isinstance(selected, list) else selected.iloc[0]["record_key"]
            detail = api_get(f"/api/datasets/{dsid}/risk-scores/{rec}")
            if detail.status_code == 200:
                d = detail.json()
                card_open(f"Record {rec} — score {d['score']:.1f}")
                for c in d["contributing_detectors"]:
                    st.markdown(
                        f"- **{c.get('detector_name', '')}** "
                        f"(tpl: {c.get('template_code', 'n/a')}, "
                        f"weight {c.get('weight', 1):.1f}) — {c.get('reason', '')}"
                    )
                card_close()
    except ImportError:
        df = pd.DataFrame([{"record_key": x["record_key"], "score": round(x["score"], 1),
                            "detectors": len(x["contributing_detectors"])} for x in rows])
        st.dataframe(df, use_container_width=True, hide_index=True)
        record = st.text_input("Inspect record key")
        if record:
            detail = api_get(f"/api/datasets/{dsid}/risk-scores/{record}")
            if detail.status_code == 200:
                st.json(detail.json())


def runs_view() -> None:
    st.header("Test Runs")
    dsid = st.session_state.get("dataset_id")
    if not dsid:
        st.warning("Set active dataset ID in the sidebar.")
        return
    rows = api_get(f"/api/datasets/{dsid}/runs").json()
    st.dataframe(pd.DataFrame([
        {"id": r["id"], "template": r["template_code"], "detector": r["detector_name"],
         "findings": r["findings_count"], "status": r["status"],
         "started": r["started_at"]}
        for r in rows
    ]), use_container_width=True, hide_index=True)


def audit_log_view() -> None:
    st.header("Audit Log")
    status = api_get("/api/audit-log/verify").json()
    if status.get("ok"):
        st.success(f"Chain VERIFIED — {status['total_entries']} entries")
    else:
        st.error(f"Chain BROKEN at {status.get('broken_at')}: {status.get('reason')}")
    rows = api_get("/api/audit-log/entries").json()
    st.dataframe(pd.DataFrame(rows[-200:]), use_container_width=True, hide_index=True)
    st.markdown(f"[Export PDF]({API_BASE}/api/audit-log/pdf)")


def template_editor_view() -> None:
    st.header("Template Editor")
    with st.form("create_tpl"):
        code = st.text_input("Code")
        name = st.text_input("Name")
        detector = st.text_input("Detector name")
        params = st.text_area("Default params (JSON)", value="{}")
        subledger = st.selectbox("Subledger", ["", "ACCOUNTS_PAYABLE", "GENERAL_LEDGER", "SALES", "PAYROLL"])
        category = st.selectbox("Category", ["ANALYTICAL", "FRAUD", "DATA_QUALITY", "COMPLIANCE"])
        weight = st.number_input("Weight", value=1.0, step=0.1)
        if st.form_submit_button("Create"):
            try:
                body = {
                    "code": code, "name": name, "detector_name": detector,
                    "default_params": json.loads(params or "{}"), "category": category,
                    "default_weight": weight, "visibility": "PRIVATE",
                }
                if subledger:
                    body["subledger"] = subledger
                r = api_post("/api/templates", json=body)
                st.json(r.json())
            except Exception as e:
                st.error(str(e))


def library_view() -> None:
    st.header("Shared Template Library")
    rows = api_get("/api/library/shared").json()
    st.dataframe(pd.DataFrame([
        {"code": t["code"], "name": t["name"], "version": t["version"],
         "subledger": t["subledger_type"], "visibility": t["visibility"]}
        for t in rows
    ]), use_container_width=True, hide_index=True)
    with st.expander("Version history + diff"):
        code = st.text_input("Template code")
        if code:
            versions = api_get(f"/api/library/{code}/versions").json()
            st.dataframe(pd.DataFrame(versions), use_container_width=True, hide_index=True)
            c1, c2 = st.columns(2)
            v1 = c1.number_input("From version", min_value=1, value=1)
            v2 = c2.number_input("To version", min_value=1, value=2)
            if st.button("Diff"):
                d = api_get(f"/api/library/{code}/diff", params={"v1": v1, "v2": v2})
                st.json(d.json())


def findings_view() -> None:
    section_header(
        t("findings.title"),
        "Every flagged issue. Maker creates DRAFT; a reviewer (≠ maker) confirms/closes.",
    )
    if not st.session_state.get("project_id"):
        st.warning("Select an active project in the sidebar first.")
        return
    pid = st.session_state["project_id"]

    # Status counts
    all_rows = api_get("/api/findings", params={"project_id": pid, "limit": 500}).json()
    counts = {s: 0 for s in ["DRAFT", "UNDER_REVIEW", "CONFIRMED", "FALSE_POSITIVE",
                              "REMEDIATED", "ACCEPTED_RISK", "CARRIED_FORWARD"]}
    for r in all_rows:
        counts[r["status"]] = counts.get(r["status"], 0) + 1
    sev_counts = {"LOW": 0, "MEDIUM": 0, "HIGH": 0, "CRITICAL": 0}
    for r in all_rows:
        sev_counts[r["severity"]] = sev_counts.get(r["severity"], 0) + 1

    c = st.columns(4)
    with c[0]: metric_card("Critical", sev_counts["CRITICAL"], icon="🚨", accent=COLORS["critical"])
    with c[1]: metric_card("High", sev_counts["HIGH"], icon="⚠️", accent=COLORS["high"])
    with c[2]: metric_card("Medium", sev_counts["MEDIUM"], icon="🔶", accent=COLORS["medium"])
    with c[3]: metric_card("Low", sev_counts["LOW"], icon="🔵", accent=COLORS["low"])

    st.markdown("<div style='height:10px'></div>", unsafe_allow_html=True)
    sc = st.columns(7)
    labels = [("Draft", "DRAFT"), ("Under review", "UNDER_REVIEW"),
              ("Confirmed", "CONFIRMED"), ("False positive", "FALSE_POSITIVE"),
              ("Remediated", "REMEDIATED"), ("Accepted", "ACCEPTED_RISK"),
              ("Carried fwd", "CARRIED_FORWARD")]
    for i, (lab, key) in enumerate(labels):
        with sc[i]:
            metric_card(lab, counts[key], icon="")

    cols = st.columns(3)
    status_filter = cols[0].selectbox("Status", [
        "", "DRAFT", "UNDER_REVIEW", "CONFIRMED", "FALSE_POSITIVE",
        "REMEDIATED", "ACCEPTED_RISK", "CARRIED_FORWARD",
    ])
    severity_filter = cols[1].selectbox("Severity", ["", "LOW", "MEDIUM", "HIGH", "CRITICAL"])
    params: dict[str, Any] = {"project_id": pid}
    if status_filter:
        params["status"] = status_filter
    if severity_filter:
        params["severity"] = severity_filter

    rows = api_get("/api/findings", params=params).json()
    if rows:
        df = pd.DataFrame([
            {"code": r["code"], "title": r["title"], "severity": r["severity"],
             "status": r["status"], "risk": r.get("risk_score"),
             "due": r.get("due_date"), "records": len(r["record_keys"])}
            for r in rows
        ])
        st.dataframe(df, use_container_width=True, hide_index=True)
    else:
        st.info("No findings yet.")

    with st.expander("➕ Create finding (maker)"):
        with st.form("new_finding"):
            title = st.text_input("Title")
            description = st.text_area("Description")
            severity = st.selectbox("Severity", ["LOW", "MEDIUM", "HIGH", "CRITICAL"], index=1)
            dataset_id = st.text_input("Dataset ID (optional)", value=st.session_state.get("dataset_id", ""))
            record_keys_str = st.text_input("Record keys (comma-separated)", value="")
            templates_str = st.text_input("Linked template codes (comma-separated)", value="")
            tags_str = st.text_input("Tags (comma-separated)", value="")
            due = st.date_input("Due date", value=None)
            if st.form_submit_button("Create"):
                body = {
                    "project_id": pid, "title": title, "description": description,
                    "severity": severity,
                    "record_keys": [x.strip() for x in record_keys_str.split(",") if x.strip()],
                    "linked_template_codes": [x.strip() for x in templates_str.split(",") if x.strip()],
                    "tags": [x.strip() for x in tags_str.split(",") if x.strip()],
                }
                if dataset_id:
                    body["dataset_id"] = dataset_id
                if due:
                    body["due_date"] = due.isoformat()
                r = api_post("/api/findings", json=body)
                if r.status_code == 200:
                    st.success(f"Created {r.json()['code']}")
                    st.rerun()
                else:
                    st.error(r.text)

    with st.expander("🔍 Inspect / transition / comment (checker)"):
        code = st.text_input("Finding code to inspect (e.g. F-2026-00001)")
        if code:
            match = next((r for r in rows if r["code"] == code), None)
            if not match:
                st.warning("Not found in current filter")
                return
            st.json(match)
            cols = st.columns(2)
            next_status = cols[0].selectbox("Transition to", [
                "UNDER_REVIEW", "CONFIRMED", "FALSE_POSITIVE",
                "REMEDIATED", "ACCEPTED_RISK", "CARRIED_FORWARD", "DRAFT",
            ])
            signoff = cols[1].text_input("Review comment (required for checker transitions)")
            if st.button("Apply transition"):
                r = api_post(
                    f"/api/findings/{match['id']}/transition",
                    json={"status": next_status, "comment": signoff or None},
                )
                if r.status_code == 200:
                    st.success(f"Transitioned to {next_status}")
                    st.rerun()
                else:
                    st.error(r.text)

            st.markdown("**Comments**")
            comments = api_get(f"/api/findings/{match['id']}/comments").json()
            for c in comments:
                mark = "✅ sign-off" if c["is_review_signoff"] else "💬"
                st.markdown(f"{mark} *{c['created_at'][:19]}* — {c['body']}")
            new_comment = st.text_area("Add comment", key=f"c_{match['id']}")
            if st.button("Post comment", key=f"btn_{match['id']}") and new_comment.strip():
                api_post(f"/api/findings/{match['id']}/comments", json={"body": new_comment})
                st.rerun()


def connectors_view() -> None:
    st.header("ERP Connectors")
    if not st.session_state.get("project_id"):
        st.warning("Select an active project in the sidebar first.")
        return
    pid = st.session_state["project_id"]

    connectors = api_get("/api/connectors").json()
    chosen = st.selectbox("Connector", [c["name"] for c in connectors])
    schema = next((c for c in connectors if c["name"] == chosen), None)
    if not schema:
        return
    st.caption(schema["description"])

    with st.form("conn_pull"):
        dataset_name = st.text_input("Dataset name (new)", placeholder="AP March 2025 (SAP)")
        subledger = st.selectbox("Subledger", [
            "ACCOUNTS_PAYABLE", "ACCOUNTS_RECEIVABLE", "GENERAL_LEDGER", "PAYROLL",
            "FIXED_ASSETS", "INVENTORY", "BANK", "PROCUREMENT", "TE", "SALES", "OTHER",
        ])
        st.markdown("**Connector config**")
        cfg: dict[str, Any] = {}
        for key, meta in schema["config_schema"].items():
            label = key + (" *" if meta.get("required") else "")
            default = meta.get("default")
            is_secret = meta.get("secret")
            if meta.get("type") == "int":
                cfg[key] = int(st.number_input(label, value=int(default or 0), key=f"c_{key}"))
            elif is_secret:
                cfg[key] = st.text_input(label, value="", type="password",
                                         key=f"c_{key}", help=meta.get("description", ""))
            else:
                cfg[key] = st.text_input(label, value=str(default or ""),
                                         key=f"c_{key}", help=meta.get("description", ""))
        submit = st.form_submit_button("Pull from source and import")
    if submit:
        body = {
            "connector": chosen, "project_id": pid, "dataset_name": dataset_name,
            "subledger_type": subledger, "config": cfg,
        }
        r = call_with_spinner(
            f"Pulling from {chosen} and importing...",
            api_post, "/api/connectors/pull-and-import", json=body,
        )
        if r and r.status_code == 200:
            data = r.json()
            st.success(
                f"Imported {data['record_count']} rows from {chosen} "
                f"(dataset {data['dataset_id']})"
            )
            st.json(data)
        elif r is not None:
            show_error(r)


def ml_feedback_view() -> None:
    section_header(
        "ML Precision Feedback",
        "Human decisions on findings (TP/FP) grade each detector. "
        "Use this to up-weight high-precision tests and prune noisy ones.",
    )
    rep = api_get("/api/feedback/precision").json()
    s = rep["summary"]
    c = st.columns(4)
    with c[0]: metric_card("Total labels", s["total_labels"], icon="🏷️")
    with c[1]: metric_card("True positives", s["true_positive"], icon="✅",
                           accent=COLORS["success"])
    with c[2]: metric_card("False positives", s["false_positive"], icon="❌",
                           accent=COLORS["danger"])
    with c[3]: metric_card("Overall precision", f"{s['overall_precision']:.0%}", icon="🎯")

    st.markdown("<div style='height:12px'></div>", unsafe_allow_html=True)
    card_open("Per-detector precision")
    det = rep.get("per_detector", [])
    if det:
        df = pd.DataFrame(det)
        df["precision"] = df["precision"].map(lambda v: f"{v:.0%}")
        st.dataframe(df, use_container_width=True, hide_index=True)
    else:
        empty_state("🏷️", "No labels yet",
                    "Close findings as CONFIRMED or FALSE_POSITIVE — each one trains the model.")
    card_close()

    card_open("Per-template precision")
    tpl = rep.get("per_template", [])
    if tpl:
        df = pd.DataFrame(tpl)
        df["precision"] = df["precision"].map(lambda v: f"{v:.0%}")
        st.dataframe(df, use_container_width=True, hide_index=True)
    card_close()


def subsidiaries_view() -> None:
    section_header(
        "Subsidiaries",
        "Group entities under audit scope. Risk rating and rollup metrics shown live.",
    )
    subs = api_get("/api/subsidiaries").json()
    rollup_map = {r["code"]: r for r in api_get("/api/subsidiaries/rollup").json()}

    if not subs:
        empty_state("🏢", "No subsidiaries yet",
                    "Register the group entities you audit — one row per subsidiary / entity.")
    else:
        cols = st.columns(4)
        for i, s in enumerate(subs):
            roll = rollup_map.get(s["code"], {})
            with cols[i % 4]:
                rating = s.get("risk_rating") or "UNRATED"
                rating_badge = severity_badge(rating) if rating in {"LOW", "MEDIUM", "HIGH", "CRITICAL"} else \
                    '<span class="ts-badge muted">UNRATED</span>'
                st.markdown(
                    f"""
                    <div class="ts-card" style="padding: 16px;">
                      <div style="display:flex; justify-content:space-between; align-items:center;">
                        <div style="font-weight:600; color:#0b2a4a;">{s['code']}</div>
                        {rating_badge}
                      </div>
                      <div style="font-size:0.95rem; margin-top:4px;">{s['name']}</div>
                      <div style="color:#6b7684; font-size:0.78rem; margin-top:2px;">
                        {s.get('country') or ''} • {s.get('segment') or ''}
                      </div>
                      <div style="margin-top:10px; display:flex; gap:14px;
                                  font-size:0.78rem; color:#6b7684;">
                        <div>🔎 {roll.get('findings_open', 0)} open</div>
                        <div>🚨 {roll.get('findings_high_critical', 0)} H/C</div>
                        <div>🎯 {roll.get('max_risk_score', 0):.0f}</div>
                      </div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

    with st.expander("➕ Register a new subsidiary"):
        with st.form("new_sub"):
            c = st.text_input("Code (e.g. DI-001)")
            n = st.text_input("Name")
            country = st.text_input("Country code (3 letters)", max_chars=4)
            industry = st.text_input("Industry")
            segment = st.text_input("Business segment")
            rating = st.selectbox("Risk rating", ["LOW", "MEDIUM", "HIGH", "CRITICAL"])
            parent = st.text_input("Parent code (for sub-subsidiaries)")
            if st.form_submit_button("Register"):
                r = api_post("/api/subsidiaries", json={
                    "code": c, "name": n, "country": country or None,
                    "industry": industry or None, "segment": segment or None,
                    "risk_rating": rating, "parent_code": parent or None,
                    "is_active": True,
                })
                if r.status_code == 200:
                    st.success(f"Registered {c}")
                    st.rerun()
                else:
                    show_error(r)


def engagements_view() -> None:
    section_header(
        t("engagements.title"),
        "Group the datasets, pack runs, and findings for a single audit period.",
    )
    if not st.session_state.get("project_id"):
        empty_state("📁", "No active project",
                    "Engagements live under a project. Pick one in the sidebar.")
        return
    pid = st.session_state["project_id"]

    rows = api_get("/api/engagements", params={"project_id": pid}).json()
    if rows:
        df = pd.DataFrame([
            {"code": r["code"], "title": r["title"], "status": r["status"],
             "period_start": r.get("period_start"), "period_end": r.get("period_end"),
             "datasets": len(r["dataset_ids"]), "findings": len(r["finding_ids"])}
            for r in rows
        ])
        st.dataframe(df, use_container_width=True, hide_index=True)
    else:
        st.info("No engagements yet. Create one for the current audit period below.")

    with st.expander("➕ Create engagement"):
        with st.form("new_engagement"):
            title = st.text_input("Title", placeholder="Q2 2025 AP Audit")
            cols = st.columns(2)
            period_start = cols[0].date_input("Period start", value=None)
            period_end = cols[1].date_input("Period end", value=None)
            scope = st.text_area("Scope", placeholder="Scope: Q2 2025 AP transactions for Subsidiary DI-001 ...")
            lead = st.text_input("Lead auditor ID (optional — defaults to you)")
            reviewer = st.text_input("Reviewer ID (maker-checker — required to finalise)")
            if st.form_submit_button("Create"):
                body: dict[str, Any] = {"project_id": pid, "title": title, "scope": scope}
                if period_start:
                    body["period_start"] = period_start.isoformat()
                if period_end:
                    body["period_end"] = period_end.isoformat()
                if lead:
                    body["lead_auditor_id"] = lead
                if reviewer:
                    body["reviewer_id"] = reviewer
                r = api_post("/api/engagements", json=body)
                if r.status_code == 200:
                    st.success(f"Created {r.json()['code']}")
                    st.rerun()
                else:
                    show_error(r)

    with st.expander("🗂️ Open engagement workspace"):
        code = st.text_input("Engagement code (e.g. E-2026-0001)")
        if code:
            match = next((r for r in rows if r["code"] == code), None)
            if not match:
                st.warning("Not found in this project")
                return
            st.markdown(f"### {match['code']} — {match['title']}")
            st.caption(f"Status: **{match['status']}** | Period: {match.get('period_start')} → {match.get('period_end')}")
            st.markdown(f"**Scope:** {match.get('scope') or '(none)'}")

            cols = st.columns(3)
            cols[0].metric("Datasets", len(match["dataset_ids"]))
            cols[1].metric("Pack runs", len(match["pack_run_ids"]))
            cols[2].metric("Findings", len(match["finding_ids"]))

            st.divider()
            st.markdown("**Link artifacts to this engagement**")
            acols = st.columns([2, 3, 1])
            kind = acols[0].selectbox("Kind", ["dataset", "pack_run", "finding"], key=f"ak_{code}")
            ref = acols[1].text_input("Artifact UUID", key=f"ar_{code}")
            if acols[2].button("Link", key=f"alink_{code}") and ref:
                r = api_post(
                    f"/api/engagements/{match['id']}/artifact",
                    json={"kind": kind, "ref_id": ref},
                )
                if r.status_code == 200:
                    st.rerun()
                else:
                    show_error(r)

            st.divider()
            st.markdown("**Executive summary**")
            summary = st.text_area(
                "Summary (included in finalised report)",
                value=match.get("executive_summary") or "",
                height=120, key=f"sum_{code}",
            )
            if st.button("Save summary", key=f"savsum_{code}"):
                r = httpx.patch(
                    f"{API_BASE}/api/engagements/{match['id']}",
                    headers={"Authorization": f"Bearer {st.session_state['token']}"},
                    json={"executive_summary": summary}, timeout=15.0,
                )
                if r.status_code == 200:
                    st.success("Saved")
                else:
                    show_error(r)

            st.divider()
            st.divider()
            if st.button("📦 Download workpaper bundle (.zip)", key=f"wp_{code}"):
                r = httpx.get(
                    f"{API_BASE}/api/engagements/{match['id']}/workpaper.zip",
                    headers={"Authorization": f"Bearer {st.session_state['token']}"},
                    timeout=60.0,
                )
                if r.status_code == 200:
                    st.download_button(
                        "Click to save",
                        data=r.content,
                        file_name=f"{match['code']}_workpaper_bundle.zip",
                        mime="application/zip",
                        key=f"dl_{code}",
                    )
                else:
                    show_error(r)

            st.divider()
            tcols = st.columns(4)
            next_status = tcols[0].selectbox(
                "Transition to",
                ["IN_PROGRESS", "REVIEW", "FINALISED", "PLANNING", "ARCHIVED"],
                key=f"tr_{code}",
            )
            if tcols[1].button("Apply", key=f"trb_{code}"):
                r = api_post(
                    f"/api/engagements/{match['id']}/transition",
                    json={"status": next_status},
                )
                if r.status_code == 200:
                    st.success(f"Transitioned to {next_status}")
                    st.rerun()
                else:
                    show_error(r)


def schedules_view() -> None:
    section_header(
        t("schedules.title"),
        "Cron-driven runs that execute packs/templates and alert on risk thresholds.",
    )
    if not st.session_state.get("project_id"):
        empty_state("⏰", "No active project",
                    "Schedules belong to a project — pick one in the sidebar.")
        return
    pid = st.session_state["project_id"]

    rows = api_get("/api/schedules", params={"project_id": pid}).json()
    if rows:
        df = pd.DataFrame([
            {"id": r["id"], "name": r["name"], "kind": r["kind"],
             "target": r.get("pack_code") or r.get("template_code"),
             "cron": r["cron_expr"], "status": r["status"],
             "next_run": r.get("next_run_at"), "alert": r["alert_enabled"]}
            for r in rows
        ])
        st.dataframe(df, use_container_width=True, hide_index=True)
    else:
        st.info("No schedules configured yet.")

    with st.expander("➕ Create schedule"):
        with st.form("new_schedule"):
            name = st.text_input("Name", placeholder="Monthly AP Review")
            kind = st.selectbox("Kind", ["PACK", "TEMPLATE"])
            pack_code = st.text_input("Pack code (for PACK kind)", "AP_STANDARD")
            template_code = st.text_input("Template code (for TEMPLATE kind)", "")
            cron_expr = st.text_input("Cron expression", "0 2 1 * *",
                                      help="Minute Hour Day Month DayOfWeek — e.g. '0 2 1 * *' = 02:00 on the 1st")
            dataset_id = st.text_input("Dataset ID", value=st.session_state.get("dataset_id", ""))
            autoens = st.checkbox("Run ensemble after pack", value=True)
            alert_enabled = st.checkbox("Send email alert", value=False)
            alert_threshold = st.slider("Alert when max risk >=", 0, 100, 80)
            recipients = st.text_input("Alert recipients (comma-separated)")
            description = st.text_area("Description")
            if st.form_submit_button("Create + preview cron"):
                body = {
                    "name": name, "project_id": pid, "dataset_id": dataset_id, "kind": kind,
                    "pack_code": pack_code if kind == "PACK" else None,
                    "template_code": template_code if kind == "TEMPLATE" else None,
                    "cron_expr": cron_expr, "autoensemble": autoens,
                    "alert_enabled": alert_enabled, "alert_min_score": float(alert_threshold),
                    "alert_recipients": [x.strip() for x in recipients.split(",") if x.strip()],
                    "description": description,
                }
                preview = api_post("/api/schedules/preview-cron", json={"cron_expr": cron_expr})
                if preview.status_code == 200:
                    st.info("Next 5 fire times:\n" + "\n".join(preview.json()["next_runs"]))
                r = api_post("/api/schedules", json=body)
                if r.status_code == 200:
                    st.success(f"Created schedule {r.json()['id']}")
                    st.rerun()
                else:
                    show_error(r)

    with st.expander("🎯 Run / manage schedule"):
        sid = st.text_input("Schedule ID")
        if sid:
            detail = api_get(f"/api/schedules/{sid}").json()
            st.json(detail)
            cols = st.columns(3)
            if cols[0].button("Run now"):
                r = call_with_spinner(
                    "Running schedule now...", api_post, f"/api/schedules/{sid}/run-now",
                )
                if r and r.status_code == 200:
                    st.json(r.json())
                elif r is not None:
                    show_error(r)
            if cols[1].button("Pause/Resume"):
                new_status = "PAUSED" if detail["status"] == "ACTIVE" else "ACTIVE"
                r = httpx.patch(
                    f"{API_BASE}/api/schedules/{sid}",
                    headers={"Authorization": f"Bearer {st.session_state['token']}"},
                    json={"status": new_status}, timeout=15.0,
                )
                if r.status_code == 200:
                    st.rerun()
                else:
                    show_error(r)
            if cols[2].button("🗑️ Delete", type="secondary"):
                r = httpx.delete(
                    f"{API_BASE}/api/schedules/{sid}",
                    headers={"Authorization": f"Bearer {st.session_state['token']}"},
                    timeout=15.0,
                )
                if r.status_code == 200:
                    st.success("Deleted")
                    st.rerun()
                else:
                    show_error(r)
            st.subheader("Run history")
            runs = api_get(f"/api/schedules/{sid}/runs").json()
            if runs:
                st.dataframe(pd.DataFrame([
                    {"started": r["started_at"], "finished": r["finished_at"],
                     "status": r["status"], "alert_sent": r["alert_sent"],
                     "findings": r.get("summary", {}).get("templates_run")
                                 or r.get("summary", {}).get("findings")}
                    for r in runs
                ]), use_container_width=True, hide_index=True)


def admin_view() -> None:
    st.header("Admin")
    if st.session_state.get("user", {}).get("role") != "ADMIN":
        st.error("Admin role required")
        return
    rows = api_get("/api/users").json()
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)


def settings_view() -> None:
    st.header("⚙️ Settings")
    if st.session_state.get("user", {}).get("role") != "ADMIN":
        st.error("Admin role required")
        return

    tab_sso, tab_email, tab_mfa, tab_ret = st.tabs(
        ["🔐 Single Sign-On", "✉️ Email", "🔢 My MFA", "🗄️ Data Retention"]
    )

    with tab_sso:
        st.subheader("Single Sign-On (OAuth2 / OIDC)")
        cfg_resp = api_get("/api/settings/sso")
        if cfg_resp.status_code != 200:
            st.error(cfg_resp.text)
            return
        cfg = cfg_resp.json()
        st.caption(
            "Configure Azure AD (Entra ID), Google, Okta, or any OIDC-compliant provider. "
            "Register this app in your identity provider first, then paste the IDs below."
        )
        with st.form("sso_form"):
            enabled = st.toggle("Enabled", value=cfg.get("enabled", False))
            c1, c2 = st.columns(2)
            with c1:
                provider = st.selectbox(
                    "Provider",
                    ["azure_ad", "google", "okta", "generic_oidc"],
                    index=["azure_ad", "google", "okta", "generic_oidc"].index(
                        cfg.get("provider", "azure_ad")
                    ) if cfg.get("provider") in ["azure_ad", "google", "okta", "generic_oidc"] else 0,
                )
                tenant_id = st.text_input("Tenant ID (Directory ID)", value=cfg.get("tenant_id", ""))
                client_id = st.text_input("Client ID (Application ID)", value=cfg.get("client_id", ""))
                client_secret = st.text_input(
                    "Client Secret",
                    value="",
                    type="password",
                    placeholder="Leave blank to keep existing",
                )
            with c2:
                redirect_uri = st.text_input(
                    "Redirect URI",
                    value=cfg.get("redirect_uri", ""),
                    help="Usually https://<your-host>/api/auth/sso/callback",
                )
                scopes = st.text_input(
                    "Scopes (space-separated)",
                    value=" ".join(cfg.get("scopes", ["openid", "email", "profile"])),
                )
                allowed_domains = st.text_input(
                    "Allowed email domains (comma-separated)",
                    value=",".join(cfg.get("allowed_domains", [])),
                    help="Leave blank to allow any domain",
                )
                auto_provision = st.toggle(
                    "Auto-provision new users on first login",
                    value=cfg.get("auto_provision", True),
                )
                default_role = st.selectbox(
                    "Default role for new SSO users",
                    ["ADMIN", "AUDITOR", "VIEWER"],
                    index=["ADMIN", "AUDITOR", "VIEWER"].index(cfg.get("default_role", "AUDITOR")),
                )
            submitted = st.form_submit_button("💾 Save SSO configuration")
            if submitted:
                payload = {
                    "enabled": enabled,
                    "provider": provider,
                    "tenant_id": tenant_id,
                    "client_id": client_id,
                    "redirect_uri": redirect_uri,
                    "scopes": scopes.split(),
                    "allowed_domains": [d.strip() for d in allowed_domains.split(",") if d.strip()],
                    "auto_provision": auto_provision,
                    "default_role": default_role,
                }
                if client_secret:
                    payload["client_secret"] = client_secret
                r = httpx.put(f"{API_BASE}/api/settings/sso", json=payload,
                              headers={"Authorization": f"Bearer {st.session_state['token']}"},
                              timeout=15.0)
                if r.status_code == 200:
                    st.success("SSO configuration saved")
                else:
                    st.error(r.text)

    with tab_email:
        st.subheader("Outbound Email (SMTP or Microsoft Graph)")
        cfg_resp = api_get("/api/settings/email")
        if cfg_resp.status_code != 200:
            st.error(cfg_resp.text)
            return
        cfg = cfg_resp.json()
        st.caption(
            "Configure outbound email for notifications and audit reports. "
            "Use **Microsoft Graph** for modern Entra-authenticated sending, or **SMTP** "
            "with optional XOAUTH2 modern auth."
        )
        with st.form("email_form"):
            enabled = st.toggle("Enabled", value=cfg.get("enabled", False), key="em_en")
            c1, c2 = st.columns(2)
            with c1:
                provider = st.radio("Provider", ["smtp", "graph"],
                                    index=0 if cfg.get("provider", "smtp") == "smtp" else 1,
                                    horizontal=True)
                from_address = st.text_input("From address", value=cfg.get("from_address", ""))
                from_name = st.text_input("From name",
                                          value=cfg.get("from_name", "TechSource Audit Analytics"))
            with c2:
                st.markdown("&nbsp;")

            st.divider()
            if provider == "smtp":
                st.markdown("**SMTP settings**")
                s1, s2 = st.columns(2)
                with s1:
                    smtp_host = st.text_input("SMTP host", value=cfg.get("smtp_host", ""))
                    smtp_port = st.number_input("SMTP port", value=int(cfg.get("smtp_port", 587)))
                    smtp_user = st.text_input("SMTP user", value=cfg.get("smtp_user", ""))
                    smtp_password = st.text_input(
                        "SMTP password",
                        value="",
                        type="password",
                        placeholder="Leave blank to keep existing",
                    )
                with s2:
                    smtp_use_tls = st.toggle("STARTTLS", value=cfg.get("smtp_use_tls", True))
                    smtp_use_ssl = st.toggle("SSL", value=cfg.get("smtp_use_ssl", False))
                    use_oauth2 = st.toggle(
                        "Use OAuth2 (XOAUTH2, modern auth)",
                        value=cfg.get("use_oauth2", False),
                        help="Required by Microsoft 365 after basic auth retirement",
                    )
                    oauth_tenant_id = st.text_input("OAuth tenant ID",
                                                    value=cfg.get("oauth_tenant_id", ""))
                    oauth_client_id = st.text_input("OAuth client ID",
                                                    value=cfg.get("oauth_client_id", ""))
                    oauth_client_secret = st.text_input(
                        "OAuth client secret", value="", type="password",
                        placeholder="Leave blank to keep existing",
                    )
                submit_label = "💾 Save SMTP configuration"
            else:
                st.markdown("**Microsoft Graph (Entra ID) settings**")
                g1, g2 = st.columns(2)
                with g1:
                    graph_tenant_id = st.text_input("Tenant ID",
                                                    value=cfg.get("graph_tenant_id", ""))
                    graph_client_id = st.text_input("Client ID",
                                                    value=cfg.get("graph_client_id", ""))
                with g2:
                    graph_client_secret = st.text_input(
                        "Client secret", value="", type="password",
                        placeholder="Leave blank to keep existing",
                    )
                    graph_sender_upn = st.text_input(
                        "Sender mailbox (UPN)",
                        value=cfg.get("graph_sender_upn", ""),
                        help="The mailbox to send from, e.g. audit-bot@yourcompany.com",
                    )
                submit_label = "💾 Save Graph configuration"

            submitted = st.form_submit_button(submit_label)
            if submitted:
                payload = {
                    "enabled": enabled, "provider": provider,
                    "from_address": from_address, "from_name": from_name,
                }
                if provider == "smtp":
                    payload.update({
                        "smtp_host": smtp_host, "smtp_port": int(smtp_port),
                        "smtp_user": smtp_user,
                        "smtp_use_tls": smtp_use_tls, "smtp_use_ssl": smtp_use_ssl,
                        "use_oauth2": use_oauth2,
                        "oauth_tenant_id": oauth_tenant_id,
                        "oauth_client_id": oauth_client_id,
                        "oauth_scope": "https://outlook.office365.com/.default",
                    })
                    if smtp_password:
                        payload["smtp_password"] = smtp_password
                    if oauth_client_secret:
                        payload["oauth_client_secret"] = oauth_client_secret
                else:
                    payload.update({
                        "graph_tenant_id": graph_tenant_id,
                        "graph_client_id": graph_client_id,
                        "graph_sender_upn": graph_sender_upn,
                    })
                    if graph_client_secret:
                        payload["graph_client_secret"] = graph_client_secret
                r = httpx.put(f"{API_BASE}/api/settings/email", json=payload,
                              headers={"Authorization": f"Bearer {st.session_state['token']}"},
                              timeout=15.0)
                if r.status_code == 200:
                    st.success("Email configuration saved")
                else:
                    st.error(r.text)

        st.divider()
        st.markdown("**Send test email**")
        c1, c2 = st.columns([3, 1])
        test_to = c1.text_input("Send test email to", key="test_to")
        if c2.button("Send test") and test_to:
            r = api_post("/api/settings/email/test", json={"to": test_to})
            if r.status_code == 200:
                st.success(f"Test email sent to {test_to}")
            else:
                st.error(r.text)

    with tab_mfa:
        st.subheader("Your multi-factor authentication")
        me = st.session_state.get("user", {})
        mfa_on = bool(me.get("mfa_enabled"))
        if mfa_on:
            st.success("MFA is **ENABLED** for your account.")
            with st.form("mfa_disable"):
                code = st.text_input("Enter a current TOTP code to disable", max_chars=6)
                submit = st.form_submit_button("Disable MFA")
            if submit and code:
                r = api_post("/api/auth/mfa/disable", json={"token": code})
                if r.status_code == 200:
                    st.session_state["user"]["mfa_enabled"] = False
                    st.success("MFA disabled.")
                    st.rerun()
                else:
                    st.error(r.text)
        else:
            st.warning("MFA is **NOT ENABLED**. We strongly recommend enabling it for ADMIN/AUDITOR roles.")
            st.markdown(
                "1. Click **Start setup** — we'll generate a new secret for your account.\n"
                "2. Scan the QR code (or paste the provisioning URI) into Microsoft Authenticator, "
                "Google Authenticator, 1Password, or any TOTP app.\n"
                "3. Enter the 6-digit code below to confirm."
            )
            if st.button("Start setup / regenerate secret"):
                r = api_post("/api/auth/mfa/setup")
                if r.status_code == 200:
                    st.session_state["mfa_setup"] = r.json()
                else:
                    st.error(r.text)

            setup = st.session_state.get("mfa_setup")
            if setup:
                st.code(setup["provisioning_uri"], language="text")
                st.caption("Paste the URI above into your authenticator app, or scan the QR:")
                qr_src = (
                    "https://api.qrserver.com/v1/create-qr-code/?size=220x220&data="
                    + httpx.URL(setup["provisioning_uri"]).raw_path.decode()
                    if False else
                    f"https://api.qrserver.com/v1/create-qr-code/?size=220x220&data={setup['provisioning_uri']}"
                )
                st.image(qr_src, caption="Scan with an authenticator app", width=220)
                st.caption(f"Manual entry key: `{setup['secret']}`")
                with st.form("mfa_enable"):
                    code = st.text_input("6-digit code from app", max_chars=6)
                    submit = st.form_submit_button("Confirm and enable MFA")
                if submit and code:
                    r = api_post("/api/auth/mfa/enable", json={"token": code})
                    if r.status_code == 200:
                        st.session_state["user"]["mfa_enabled"] = True
                        st.session_state.pop("mfa_setup", None)
                        st.success("MFA enabled. You'll be asked for a code on every sign-in.")
                        st.rerun()
                    else:
                        st.error(r.text)

    with tab_ret:
        st.subheader("Data retention policy")
        st.caption(
            "Enforce automatic purge of old datasets per subledger. "
            "Aligns with UAE PDPL Article 16 (data minimisation) and DI-IT-POL retention schedules."
        )
        pol = api_get("/api/settings/retention").json()
        with st.form("retention"):
            enabled = st.checkbox("Enable retention enforcement", value=pol.get("enabled", False))
            default_days = st.number_input(
                "Default retention (days)", min_value=30, max_value=3650,
                value=int(pol.get("default_days", 2555)), step=30,
            )
            st.markdown("**Per-subledger overrides (days)** — leave blank to use default")
            per_sub = pol.get("per_subledger_days") or {}
            subs = ["GENERAL_LEDGER", "ACCOUNTS_PAYABLE", "ACCOUNTS_RECEIVABLE", "PAYROLL",
                    "FIXED_ASSETS", "INVENTORY", "BANK", "PROCUREMENT", "TE", "SALES"]
            overrides: dict[str, int] = {}
            sub_cols = st.columns(2)
            for i, s in enumerate(subs):
                with sub_cols[i % 2]:
                    v = st.number_input(
                        s, min_value=0, max_value=3650,
                        value=int(per_sub.get(s, 0)), step=30, key=f"ret_{s}",
                    )
                    if v > 0:
                        overrides[s] = v
            preserve = st.checkbox(
                "Preserve datasets referenced by open findings",
                value=bool(pol.get("preserve_findings_referenced", True)),
                help="Datasets linked to findings in any status are excluded from purge",
            )
            if st.form_submit_button("Save policy"):
                r = api_post("/api/settings/retention", json={})
                # use PUT instead
                r = httpx.put(
                    f"{API_BASE}/api/settings/retention",
                    headers={"Authorization": f"Bearer {st.session_state['token']}"},
                    json={
                        "enabled": enabled,
                        "default_days": int(default_days),
                        "per_subledger_days": overrides,
                        "preserve_findings_referenced": preserve,
                    },
                    timeout=15.0,
                )
                if r.status_code == 200:
                    st.success("Policy saved")
                else:
                    st.error(r.text)

        st.divider()
        if st.button("🔍 Scan (dry-run)"):
            scan = api_post("/api/settings/retention/scan").json()
            st.json(scan)

        st.markdown("**Permanent purge**")
        confirm = st.checkbox(
            "I understand this irreversibly deletes stale datasets, test runs, "
            "risk scores and Parquet files.", key="purge_confirm",
        )
        if st.button("⚠️ Purge now", disabled=not confirm):
            purged = api_post("/api/settings/retention/purge").json()
            st.warning(f"Purge complete: {purged.get('purged_datasets', 0)} datasets removed")
            st.json(purged)


def main() -> None:
    if not st.session_state.get("token"):
        login_view()
        return
    page = sidebar()
    views = {
        "Dashboard": dashboard_view,
        "Projects": projects_view,
        "Subsidiaries": subsidiaries_view,
        "ML Feedback": ml_feedback_view,
        "Engagements": engagements_view,
        "Datasets": datasets_view,
        "Connectors": connectors_view,
        "Templates": templates_view,
        "Packs": packs_view,
        "Run": run_view,
        "Risk Explorer": risk_view,
        "Findings": findings_view,
        "Schedules": schedules_view,
        "Test Runs": runs_view,
        "Audit Log": audit_log_view,
        "Template Editor": template_editor_view,
        "Library": library_view,
        "Admin": admin_view,
        "Settings": settings_view,
    }
    views[page]()


if __name__ == "__main__":
    main()
