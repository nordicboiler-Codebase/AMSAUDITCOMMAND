"""Design system — colors, spacing, typography, UI primitives.

Usage:
    from theme import inject_css, metric_card, section_header, empty_state
    inject_css()
    section_header("Dashboard", "Group-wide audit posture")
    metric_card("Open findings", 42, delta="+3 this week", trend="up")
"""
from __future__ import annotations

import streamlit as st

# ---- Design tokens ----
COLORS = {
    "primary": "#0b2a4a",        # deep navy — brand
    "primary_light": "#1f4e7a",
    "accent": "#15a8a8",          # teal
    "accent_light": "#1fd1d1",
    "bg": "#f5f7fa",
    "card": "#ffffff",
    "border": "#e4e8ee",
    "text": "#1b2735",
    "text_muted": "#6b7684",
    "text_subtle": "#9aa5b1",
    "success": "#15803d",
    "warning": "#b45309",
    "danger": "#b91c1c",
    "info": "#1d4ed8",
    "critical": "#7c1d1d",
    "high": "#b91c1c",
    "medium": "#b45309",
    "low": "#0f766e",
}

_SEVERITY_COLOR = {
    "CRITICAL": COLORS["critical"], "HIGH": COLORS["high"],
    "MEDIUM": COLORS["medium"], "LOW": COLORS["low"],
}

_STATUS_COLOR = {
    "DRAFT": COLORS["text_muted"],
    "UNDER_REVIEW": COLORS["info"],
    "CONFIRMED": COLORS["danger"],
    "FALSE_POSITIVE": COLORS["text_subtle"],
    "REMEDIATED": COLORS["success"],
    "ACCEPTED_RISK": COLORS["warning"],
    "CARRIED_FORWARD": COLORS["info"],
    "ACTIVE": COLORS["success"], "PAUSED": COLORS["text_muted"],
    "PLANNING": COLORS["text_muted"], "IN_PROGRESS": COLORS["info"],
    "REVIEW": COLORS["warning"], "FINALISED": COLORS["success"],
    "ARCHIVED": COLORS["text_subtle"],
    "COMPLETED": COLORS["success"], "RUNNING": COLORS["info"],
    "PENDING": COLORS["text_muted"], "FAILED": COLORS["danger"],
}


CSS = """
<style>
/* ---- Base ---- */
html, body, [data-testid="stAppViewContainer"] {
  background: #f5f7fa;
  color: #1b2735;
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Inter", sans-serif;
}
.block-container { padding-top: 1.25rem; padding-bottom: 3rem; max-width: 1400px; }
h1, h2, h3, h4 { color: #0b2a4a; font-weight: 600; letter-spacing: -0.01em; }
h1 { font-size: 1.75rem; margin-bottom: 0.3rem; }
h2 { font-size: 1.25rem; }
h3 { font-size: 1.05rem; }

/* ---- Hero / section header ---- */
.ts-section-header {
  display: flex; align-items: center; justify-content: space-between;
  padding: 12px 0 22px 0; margin-bottom: 8px;
  border-bottom: 1px solid #e4e8ee;
}
.ts-section-title { font-size: 1.5rem; font-weight: 600; color: #0b2a4a; margin: 0; }
.ts-section-subtitle { color: #6b7684; font-size: 0.9rem; margin-top: 2px; }
.ts-section-actions { display: flex; gap: 8px; }

/* ---- Metric card ---- */
.ts-metric {
  background: #ffffff; border: 1px solid #e4e8ee; border-radius: 12px;
  padding: 18px 20px; box-shadow: 0 1px 2px rgba(11,42,74,0.04);
  transition: transform 0.1s ease, box-shadow 0.1s ease;
}
.ts-metric:hover { transform: translateY(-1px); box-shadow: 0 4px 12px rgba(11,42,74,0.08); }
.ts-metric-label { color: #6b7684; font-size: 0.78rem; font-weight: 500;
                   text-transform: uppercase; letter-spacing: 0.05em; }
.ts-metric-value { color: #0b2a4a; font-size: 2rem; font-weight: 600;
                   line-height: 1.1; margin-top: 6px; }
.ts-metric-delta { font-size: 0.82rem; margin-top: 6px; }
.ts-metric-delta.up { color: #b91c1c; }
.ts-metric-delta.down { color: #15803d; }
.ts-metric-delta.flat { color: #6b7684; }
.ts-metric-icon { font-size: 1.5rem; float: right; opacity: 0.6; }

/* ---- Card ---- */
.ts-card {
  background: #ffffff; border: 1px solid #e4e8ee; border-radius: 12px;
  padding: 20px; box-shadow: 0 1px 2px rgba(11,42,74,0.04); margin-bottom: 16px;
}
.ts-card h3 { margin-top: 0; }

/* ---- Badges ---- */
.ts-badge {
  display: inline-block; padding: 2px 10px; border-radius: 999px;
  font-size: 0.75rem; font-weight: 500; letter-spacing: 0.02em;
  background: rgba(11,42,74,0.08); color: #0b2a4a;
}
.ts-badge.critical { background: rgba(124,29,29,0.12); color: #7c1d1d; }
.ts-badge.high     { background: rgba(185,28,28,0.12); color: #b91c1c; }
.ts-badge.medium   { background: rgba(180,83,9,0.15);  color: #b45309; }
.ts-badge.low      { background: rgba(15,118,110,0.12); color: #0f766e; }
.ts-badge.success  { background: rgba(21,128,61,0.12); color: #15803d; }
.ts-badge.warning  { background: rgba(180,83,9,0.15);  color: #b45309; }
.ts-badge.danger   { background: rgba(185,28,28,0.12); color: #b91c1c; }
.ts-badge.info     { background: rgba(29,78,216,0.1);  color: #1d4ed8; }
.ts-badge.muted    { background: rgba(107,118,132,0.12); color: #6b7684; }

/* ---- Empty state ---- */
.ts-empty {
  text-align: center; padding: 40px 20px; color: #6b7684;
  background: #ffffff; border: 2px dashed #e4e8ee; border-radius: 12px;
}
.ts-empty-icon { font-size: 2.5rem; margin-bottom: 8px; }
.ts-empty-title { font-size: 1rem; color: #1b2735; margin: 4px 0; font-weight: 600; }
.ts-empty-desc { font-size: 0.85rem; }

/* ---- Sidebar ---- */
section[data-testid="stSidebar"] { background: #0b2a4a; }
section[data-testid="stSidebar"] * { color: #e4e8ee !important; }
section[data-testid="stSidebar"] .stSelectbox [data-baseweb="select"] > div { background: #1f4e7a; }
section[data-testid="stSidebar"] input, section[data-testid="stSidebar"] textarea {
  background: #1f4e7a !important; color: #fff !important; border-color: #1f4e7a !important;
}
section[data-testid="stSidebar"] h1, section[data-testid="stSidebar"] h2,
section[data-testid="stSidebar"] h3 { color: #ffffff !important; }
section[data-testid="stSidebar"] hr { border-color: rgba(255,255,255,0.1); }
section[data-testid="stSidebar"] .ts-nav-group {
  color: #9aa5b1 !important; font-size: 0.7rem; font-weight: 600;
  text-transform: uppercase; letter-spacing: 0.08em;
  padding: 14px 0 4px 8px;
}
section[data-testid="stSidebar"] [data-testid="stRadio"] label { color: #e4e8ee !important; }

/* ---- Buttons ---- */
.stButton > button {
  background: #0b2a4a; color: white; border: 1px solid #0b2a4a;
  font-weight: 500; border-radius: 8px; padding: 8px 14px;
  transition: all 0.1s ease;
}
.stButton > button:hover { background: #15a8a8; border-color: #15a8a8; color: white; }
.stButton > button:focus { box-shadow: 0 0 0 3px rgba(21,168,168,0.25); }
.stButton > button[kind="secondary"] {
  background: white; color: #0b2a4a; border-color: #e4e8ee;
}
.stDownloadButton > button { background: #15a8a8; border-color: #15a8a8; color: white; }

/* ---- Tables ---- */
[data-testid="stDataFrame"] { border: 1px solid #e4e8ee; border-radius: 10px; overflow: hidden; }
[data-testid="stDataFrame"] thead tr th { background: #f5f7fa !important; color: #1b2735 !important;
                                          font-weight: 600 !important; font-size: 0.8rem !important; }

/* ---- Inputs ---- */
[data-baseweb="input"], [data-baseweb="select"] { border-radius: 8px !important; }

/* ---- Misc ---- */
[data-testid="stMetricLabel"] { color: #6b7684 !important; }
hr { border-color: #e4e8ee; }
.stAlert { border-radius: 10px; }

/* ---- Top-banner for group-level context ---- */
.ts-group-banner {
  background: linear-gradient(90deg, #0b2a4a, #15a8a8);
  color: white; padding: 14px 20px; border-radius: 12px; margin-bottom: 18px;
}
.ts-group-banner h4 { color: white; margin: 0; font-size: 1.1rem; }
.ts-group-banner p { color: rgba(255,255,255,0.85); margin: 4px 0 0 0; font-size: 0.85rem; }

/* ---- Risk heat tiles ---- */
.ts-heat-tile {
  background: white; border: 1px solid #e4e8ee; border-radius: 10px;
  padding: 14px; margin-bottom: 10px;
}
.ts-heat-tile .code { font-size: 0.72rem; color: #6b7684; font-weight: 600; letter-spacing: 0.05em; }
.ts-heat-tile .name { font-size: 0.95rem; color: #1b2735; font-weight: 600; margin-top: 2px; }
.ts-heat-tile .score { font-size: 1.5rem; font-weight: 700; }
.ts-heat-tile .meta { font-size: 0.75rem; color: #6b7684; }
</style>
"""


def inject_css() -> None:
    if "_ts_css_injected" in st.session_state:
        pass
    st.markdown(CSS, unsafe_allow_html=True)
    st.session_state["_ts_css_injected"] = True


def section_header(title: str, subtitle: str | None = None) -> None:
    sub_html = f'<div class="ts-section-subtitle">{subtitle}</div>' if subtitle else ""
    st.markdown(
        f"""
        <div class="ts-section-header">
          <div>
            <div class="ts-section-title">{title}</div>
            {sub_html}
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def metric_card(
    label: str, value, *, delta: str | None = None, trend: str = "flat",
    icon: str = "", accent: str | None = None,
) -> None:
    value_str = f"{value:,}" if isinstance(value, (int, float)) and not isinstance(value, bool) else str(value)
    delta_html = ""
    if delta:
        delta_html = f'<div class="ts-metric-delta {trend}">{delta}</div>'
    icon_html = f'<span class="ts-metric-icon">{icon}</span>' if icon else ""
    style = f'style="border-left: 4px solid {accent};"' if accent else ""
    st.markdown(
        f"""
        <div class="ts-metric" {style}>
          {icon_html}
          <div class="ts-metric-label">{label}</div>
          <div class="ts-metric-value">{value_str}</div>
          {delta_html}
        </div>
        """,
        unsafe_allow_html=True,
    )


def severity_badge(severity: str) -> str:
    c = severity.lower()
    return f'<span class="ts-badge {c}">{severity}</span>'


def status_badge(status: str) -> str:
    color = _STATUS_COLOR.get(status, COLORS["text_muted"])
    return f'<span class="ts-badge" style="background: {color}22; color: {color};">{status.replace("_", " ")}</span>'


def empty_state(icon: str, title: str, description: str, cta_label: str | None = None,
                cta_key: str | None = None) -> bool:
    st.markdown(
        f"""
        <div class="ts-empty">
          <div class="ts-empty-icon">{icon}</div>
          <div class="ts-empty-title">{title}</div>
          <div class="ts-empty-desc">{description}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    if cta_label and cta_key:
        return st.button(cta_label, key=cta_key)
    return False


def group_banner(title: str, description: str) -> None:
    st.markdown(
        f"""
        <div class="ts-group-banner">
          <h4>{title}</h4>
          <p>{description}</p>
        </div>
        """,
        unsafe_allow_html=True,
    )


def heat_tile(code: str, name: str, score: float, meta: str = "") -> None:
    color = (
        COLORS["critical"] if score >= 90 else
        COLORS["high"] if score >= 70 else
        COLORS["medium"] if score >= 40 else
        COLORS["low"]
    )
    st.markdown(
        f"""
        <div class="ts-heat-tile" style="border-left: 4px solid {color};">
          <div class="code">{code}</div>
          <div class="name">{name}</div>
          <div class="score" style="color: {color};">{score:.0f}</div>
          <div class="meta">{meta}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def card_open(title: str | None = None) -> None:
    st.markdown(f'<div class="ts-card">{"<h3>" + title + "</h3>" if title else ""}',
                unsafe_allow_html=True)


def card_close() -> None:
    st.markdown("</div>", unsafe_allow_html=True)
