from __future__ import annotations

import json
import os
from pathlib import Path
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


def login_view() -> None:
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

    st.title("TechSource Audit Analytics")
    st.caption("Internal audit data analytics platform")

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
        username = st.text_input("Username")
        password = st.text_input("Password", type="password")
        submit = st.form_submit_button("Sign in with password")
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
             "Risk Explorer", "Findings", "Schedules", "Test Runs", "Audit Log",
             "Template Editor", "Library", "Admin", "Settings"],
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
    st.header("Datasets")
    if not st.session_state.get("project_id"):
        st.warning("Select an active project in the sidebar first.")
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
                body = {
                    "dataset_id": dsid, "template_code": code,
                    "param_overrides": json.loads(overrides or "{}"),
                }
            except Exception as e:
                st.error(f"Invalid JSON in overrides: {e}")
                return
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
        det = st.text_input("Detector name", key="d_name")
        params = st.text_area("Params (JSON)", value="{}", key="d_params")
        if st.button("Run detector") and det:
            try:
                body = {
                    "dataset_id": dsid, "detector_name": det,
                    "params": json.loads(params or "{}"),
                }
            except Exception as e:
                st.error(f"Invalid JSON: {e}")
                return
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
    st.header("Risk Explorer")
    dsid = st.session_state.get("dataset_id")
    if not dsid:
        st.warning("Set active dataset ID in the sidebar.")
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


def findings_view() -> None:
    st.header("Findings Register")
    if not st.session_state.get("project_id"):
        st.warning("Select an active project in the sidebar first.")
        return
    pid = st.session_state["project_id"]

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


def schedules_view() -> None:
    st.header("Scheduled Runs & Alerts")
    if not st.session_state.get("project_id"):
        st.warning("Select an active project in the sidebar first.")
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
        cols = st.columns(2)
        if cols[0].button("🔍 Scan (dry-run)"):
            scan = api_post("/api/settings/retention/scan").json()
            st.json(scan)
        if cols[1].button("⚠️ Purge now (irreversible)"):
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
        "Datasets": datasets_view,
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
