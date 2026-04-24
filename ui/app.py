from __future__ import annotations

import json
import os
from typing import Any

import httpx
import pandas as pd
import streamlit as st

API_BASE = os.environ.get("API_BASE_URL", "http://localhost:8000")

NAVY = "#0b2a4a"
TEAL = "#15a8a8"

st.set_page_config(page_title="TechSource Audit Analytics", layout="wide")

st.markdown(
    f"""
    <style>
      .stApp {{ background: #f6f8fb; }}
      .block-container {{ padding-top: 1.5rem; }}
      .stButton>button {{ background: {NAVY}; color: white; border: 0; }}
      .stButton>button:hover {{ background: {TEAL}; color: white; }}
      h1, h2, h3 {{ color: {NAVY}; }}
      .metric {{ color: {NAVY}; font-weight: 700; }}
    </style>
    """,
    unsafe_allow_html=True,
)


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


def login_view() -> None:
    st.title("TechSource Audit Analytics")
    st.caption("Internal audit data analytics platform")
    with st.form("login"):
        username = st.text_input("Username")
        password = st.text_input("Password", type="password")
        submit = st.form_submit_button("Sign in")
    if submit:
        r = httpx.post(
            f"{API_BASE}/api/auth/token",
            data={"username": username, "password": password},
            timeout=30.0,
        )
        if r.status_code == 200:
            st.session_state["token"] = r.json()["access_token"]
            me = httpx.get(
                f"{API_BASE}/api/auth/me",
                headers={"Authorization": f"Bearer {st.session_state['token']}"},
                timeout=15.0,
            )
            if me.status_code == 200:
                st.session_state["user"] = me.json()
            st.rerun()
        else:
            st.error(f"Login failed: {r.text}")


def sidebar() -> str:
    with st.sidebar:
        st.markdown(f"### {st.session_state['user']['username']}")
        st.caption(st.session_state["user"]["role"])
        projects = api_get("/api/projects").json() if st.session_state.get("token") else []
        project_names = {p["name"]: p["id"] for p in projects}
        sel_project = st.selectbox("Active project", ["(none)"] + list(project_names.keys()))
        st.session_state["project_id"] = project_names.get(sel_project)
        datasets = []
        if st.session_state.get("project_id"):
            r = api_get("/api/projects")
            if r.status_code == 200:
                pass
        sel_dataset = st.text_input("Active dataset ID (UUID)", st.session_state.get("dataset_id", ""))
        st.session_state["dataset_id"] = sel_dataset or None
        st.divider()
        page = st.radio(
            "Navigate",
            ["Dashboard", "Projects", "Datasets", "Templates", "Packs", "Run",
             "Risk Explorer", "Test Runs", "Audit Log", "Template Editor", "Library", "Admin"],
        )
        st.divider()
        if st.button("Sign out"):
            st.session_state.clear()
            st.rerun()
    return page


def dashboard_view() -> None:
    st.header("Dashboard")
    col1, col2, col3 = st.columns(3)
    projects = api_get("/api/projects").json()
    templates = api_get("/api/templates").json()
    col1.metric("Projects", len(projects))
    col2.metric("Templates", len(templates))
    col3.metric("Detectors", 36)
    st.caption("Navigate via sidebar → Datasets to import, Run to execute tests, Risk Explorer to review findings.")


def projects_view() -> None:
    st.header("Projects")
    with st.expander("Create project"):
        with st.form("new_project"):
            name = st.text_input("Name")
            description = st.text_area("Description")
            subsidiary_code = st.text_input("Subsidiary code")
            if st.form_submit_button("Create"):
                api_post("/api/projects", json={
                    "name": name, "description": description, "subsidiary_code": subsidiary_code
                })
                st.rerun()
    rows = api_get("/api/projects").json()
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)


def datasets_view() -> None:
    st.header("Datasets")
    if not st.session_state.get("project_id"):
        st.warning("Select an active project in the sidebar first.")
        return
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
                r = api_post("/api/datasets/import", files=files, data=data)
                if r.status_code == 200:
                    st.success(f"Imported. Dataset ID: {r.json()['dataset_id']}")
                else:
                    st.error(r.text)
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
                r = api_post("/api/packs/run", json={
                    "dataset_id": st.session_state["dataset_id"], "pack_code": code,
                    "template_overrides": {}
                })
                st.json(r.json())


def run_view() -> None:
    st.header("Run Tests")
    tab1, tab2, tab3 = st.tabs(["Single Template", "Pack", "Custom Detector"])
    dsid = st.session_state.get("dataset_id")
    if not dsid:
        st.warning("Set active dataset ID in the sidebar.")
        return
    with tab1:
        code = st.text_input("Template code", key="t_code")
        overrides = st.text_area("Param overrides (JSON)", value="{}", key="t_over")
        if st.button("Run template") and code:
            try:
                r = api_post("/api/runs/template", json={
                    "dataset_id": dsid, "template_code": code,
                    "param_overrides": json.loads(overrides or "{}")
                })
                st.json(r.json())
            except Exception as e:
                st.error(str(e))
    with tab2:
        pack = st.text_input("Pack code", key="p_code")
        if st.button("Run pack") and pack:
            r = api_post("/api/packs/run", json={
                "dataset_id": dsid, "pack_code": pack, "template_overrides": {}
            })
            st.json(r.json())
    with tab3:
        det = st.text_input("Detector name", key="d_name")
        params = st.text_area("Params (JSON)", value="{}", key="d_params")
        if st.button("Run detector") and det:
            try:
                r = api_post("/api/runs/detector", json={
                    "dataset_id": dsid, "detector_name": det,
                    "params": json.loads(params or "{}")
                })
                st.json(r.json())
            except Exception as e:
                st.error(str(e))


def risk_view() -> None:
    st.header("Risk Explorer")
    dsid = st.session_state.get("dataset_id")
    if not dsid:
        st.warning("Set active dataset ID in the sidebar.")
        return
    min_score = st.slider("Minimum score", 0, 100, 50)
    r = api_get(f"/api/datasets/{dsid}/risk-scores",
                params={"min_score": min_score, "limit": 200, "sort": "desc"})
    if r.status_code != 200:
        st.error(r.text)
        return
    rows = r.json()
    if not rows:
        st.info("No risk scores yet. Run a pack + ensemble first.")
        return
    df = pd.DataFrame([{"record_key": x["record_key"], "score": x["score"],
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


def admin_view() -> None:
    st.header("Admin")
    if st.session_state.get("user", {}).get("role") != "ADMIN":
        st.error("Admin role required")
        return
    rows = api_get("/api/users").json()
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)


def main() -> None:
    if not st.session_state.get("token"):
        login_view()
        return
    page = sidebar()
    views = {
        "Dashboard": dashboard_view,
        "Projects": projects_view,
        "Datasets": datasets_view,
        "Templates": templates_view,
        "Packs": packs_view,
        "Run": run_view,
        "Risk Explorer": risk_view,
        "Test Runs": runs_view,
        "Audit Log": audit_log_view,
        "Template Editor": template_editor_view,
        "Library": library_view,
        "Admin": admin_view,
    }
    views[page]()


if __name__ == "__main__":
    main()
