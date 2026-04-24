"""Competition-grade design system.

Tokens + primitives used across the UI. Injects a heavy custom CSS pass that
overrides Streamlit defaults and delivers a consistent, polished look.
"""
from __future__ import annotations

import streamlit as st

# ---------- Design tokens ----------
COLORS = {
    # Brand
    "primary": "#0f2a47",
    "primary_600": "#12365b",
    "primary_700": "#0b2039",
    "accent": "#13c4b7",
    "accent_600": "#0fa89d",
    "accent_soft": "#d9f5f2",
    # Surfaces
    "bg": "#f5f7fa",
    "bg_2": "#eef2f6",
    "surface": "#ffffff",
    "surface_muted": "#fafbfc",
    "border": "#e5e9ef",
    "border_strong": "#cfd6df",
    # Text
    "text": "#0f172a",
    "text_muted": "#556070",
    "text_subtle": "#8b95a3",
    "text_on_dark": "#e8edf3",
    "text_on_dark_muted": "#9aa5b4",
    # Sidebar
    "sb_bg": "#0c1c33",
    "sb_bg_2": "#10253f",
    "sb_hover": "rgba(255,255,255,0.07)",
    "sb_active_bg": "rgba(19,196,183,0.14)",
    "sb_active_text": "#13c4b7",
    # Semantic
    "success": "#0d8a4d",
    "success_soft": "#e8f6ee",
    "warning": "#b76e00",
    "warning_soft": "#fdf3e1",
    "danger": "#c2342f",
    "danger_soft": "#fae4e3",
    "info": "#2563eb",
    "info_soft": "#e4ecfe",
    "critical": "#821b1a",
    "critical_soft": "#f6dada",
    "high": "#c2342f",
    "high_soft": "#fae4e3",
    "medium": "#b76e00",
    "medium_soft": "#fdf3e1",
    "low": "#0f766e",
    "low_soft": "#dff4f1",
}


def _sev_classes() -> str:
    return "\n".join(
        f".ts-badge.{k.lower()} {{ background: {COLORS[k.lower() + '_soft']}; color: {COLORS[k.lower()]}; }}"
        for k in ["CRITICAL", "HIGH", "MEDIUM", "LOW"]
    )


CSS = f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap');

/* ---------- Base ---------- */
html, body, [data-testid="stAppViewContainer"] {{
  background: {COLORS['bg']};
  color: {COLORS['text']};
  font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
  font-size: 14px;
}}
* {{ box-sizing: border-box; }}

.main > div.block-container {{
  padding-top: 1rem;
  padding-bottom: 2.5rem;
  padding-left: 2rem;
  padding-right: 2rem;
  max-width: 1440px;
}}
/* Main content vertical rhythm — let our cards do the spacing */
.main [data-testid="stVerticalBlock"] {{
  gap: 12px;
}}
.main [data-testid="stHorizontalBlock"] {{
  gap: 14px !important;
}}
.main [data-testid="stVerticalBlockBorderWrapper"] {{
  gap: 8px !important;
}}
/* Reset Streamlit's default element spacing in main area */
.main [data-testid="element-container"] {{
  margin-bottom: 0 !important;
}}
code, pre {{ font-family: 'JetBrains Mono', monospace; font-size: 0.85em; }}

h1, h2, h3, h4, h5 {{
  color: {COLORS['text']};
  font-weight: 600;
  letter-spacing: -0.01em;
  line-height: 1.3;
}}
h1 {{ font-size: 1.75rem; margin: 0 0 4px 0; }}
h2 {{ font-size: 1.25rem; }}
h3 {{ font-size: 1.05rem; }}
p {{ color: {COLORS['text']}; }}
small, .muted {{ color: {COLORS['text_muted']}; }}

/* ---------- Hide Streamlit chrome we don't want ---------- */
#MainMenu {{ visibility: hidden; }}
footer {{ visibility: hidden; }}
header[data-testid="stHeader"] {{ background: transparent; }}
[data-testid="stDecoration"] {{ display: none; }}

/* ---------- Section header ---------- */
.ts-section-header {{
  display: flex; align-items: flex-start; justify-content: space-between;
  gap: 16px; padding: 4px 0 20px 0; margin-bottom: 12px;
  border-bottom: 1px solid {COLORS['border']};
}}
.ts-section-title {{
  font-size: 1.6rem; font-weight: 600; color: {COLORS['text']};
  margin: 0; letter-spacing: -0.01em;
}}
.ts-section-subtitle {{
  color: {COLORS['text_muted']}; font-size: 0.88rem; margin-top: 3px;
  max-width: 720px; line-height: 1.5;
}}

/* ---------- Metric card ---------- */
.ts-metric {{
  background: {COLORS['surface']};
  border: 1px solid {COLORS['border']};
  border-radius: 14px;
  padding: 18px 20px;
  box-shadow: 0 1px 2px rgba(15,42,71,0.04);
  transition: all 0.15s ease;
  position: relative;
  min-height: 108px;
}}
.ts-metric:hover {{
  border-color: {COLORS['border_strong']};
  box-shadow: 0 4px 14px rgba(15,42,71,0.06);
  transform: translateY(-1px);
}}
.ts-metric-label {{
  color: {COLORS['text_muted']};
  font-size: 0.72rem; font-weight: 600;
  text-transform: uppercase; letter-spacing: 0.08em;
}}
.ts-metric-value {{
  color: {COLORS['text']};
  font-size: 2rem; font-weight: 600;
  line-height: 1.15; margin-top: 8px;
  font-variant-numeric: tabular-nums;
}}
.ts-metric-delta {{ font-size: 0.8rem; margin-top: 8px; font-weight: 500; }}
.ts-metric-delta.up   {{ color: {COLORS['danger']}; }}
.ts-metric-delta.down {{ color: {COLORS['success']}; }}
.ts-metric-delta.flat {{ color: {COLORS['text_muted']}; }}
.ts-metric-icon {{
  position: absolute; top: 16px; right: 18px;
  font-size: 1.3rem; opacity: 0.55;
}}

/* ---------- Card ---------- */
.ts-card {{
  background: {COLORS['surface']};
  border: 1px solid {COLORS['border']};
  border-radius: 14px;
  padding: 22px;
  box-shadow: 0 1px 2px rgba(15,42,71,0.04);
  margin-bottom: 16px;
}}
.ts-card h3 {{ margin-top: 0; margin-bottom: 14px; font-size: 0.95rem;
              color: {COLORS['text_muted']}; text-transform: uppercase;
              letter-spacing: 0.06em; font-weight: 600; }}

/* ---------- Badge ---------- */
.ts-badge {{
  display: inline-flex; align-items: center;
  padding: 3px 10px; border-radius: 20px;
  font-size: 0.72rem; font-weight: 600; letter-spacing: 0.02em;
  background: {COLORS['bg_2']}; color: {COLORS['text_muted']};
  white-space: nowrap;
}}
{_sev_classes()}
.ts-badge.success {{ background: {COLORS['success_soft']}; color: {COLORS['success']}; }}
.ts-badge.warning {{ background: {COLORS['warning_soft']}; color: {COLORS['warning']}; }}
.ts-badge.danger  {{ background: {COLORS['danger_soft']};  color: {COLORS['danger']}; }}
.ts-badge.info    {{ background: {COLORS['info_soft']};    color: {COLORS['info']}; }}
.ts-badge.muted   {{ background: {COLORS['bg_2']}; color: {COLORS['text_muted']}; }}

/* ---------- Empty state ---------- */
.ts-empty {{
  text-align: center; padding: 48px 24px;
  background: {COLORS['surface']};
  border: 1px dashed {COLORS['border_strong']};
  border-radius: 14px;
  color: {COLORS['text_muted']};
}}
.ts-empty-icon {{ font-size: 2.75rem; margin-bottom: 10px; opacity: 0.85; }}
.ts-empty-title {{ font-size: 1.05rem; color: {COLORS['text']}; margin: 4px 0;
                   font-weight: 600; }}
.ts-empty-desc {{ font-size: 0.86rem; max-width: 440px; margin: 0 auto; }}

/* ---------- Group banner ---------- */
.ts-group-banner {{
  background: linear-gradient(135deg, {COLORS['primary']} 0%, {COLORS['primary_600']} 55%, {COLORS['accent_600']} 120%);
  color: white; padding: 18px 24px; border-radius: 14px; margin-bottom: 22px;
  display: flex; align-items: center; gap: 20px;
  box-shadow: 0 6px 20px rgba(15,42,71,0.18);
}}
.ts-group-banner .icon {{ font-size: 1.8rem; }}
.ts-group-banner h4 {{ color: white; margin: 0; font-size: 1.1rem; }}
.ts-group-banner p  {{ color: rgba(255,255,255,0.85); margin: 2px 0 0 0; font-size: 0.86rem; }}

/* ---------- Heat tile ---------- */
.ts-heat-tile {{
  background: {COLORS['surface']};
  border: 1px solid {COLORS['border']};
  border-left-width: 4px;
  border-radius: 10px;
  padding: 14px 16px; margin-bottom: 10px;
  transition: all 0.15s ease;
}}
.ts-heat-tile:hover {{ border-color: {COLORS['border_strong']};
                      box-shadow: 0 2px 6px rgba(15,42,71,0.06); }}
.ts-heat-tile .code   {{ font-size: 0.7rem; color: {COLORS['text_muted']};
                         font-weight: 600; letter-spacing: 0.06em; }}
.ts-heat-tile .name   {{ font-size: 0.95rem; color: {COLORS['text']};
                         font-weight: 600; margin-top: 2px; }}
.ts-heat-tile .score  {{ font-size: 1.6rem; font-weight: 700;
                         font-variant-numeric: tabular-nums; margin-top: 4px;
                         line-height: 1; }}
.ts-heat-tile .meta   {{ font-size: 0.75rem; color: {COLORS['text_muted']};
                         margin-top: 6px; }}

/* ---------- SIDEBAR — dark, branded, tight ---------- */
section[data-testid="stSidebar"] {{
  background: {COLORS['sb_bg']};
  border-right: 1px solid {COLORS['primary_700']};
  width: 248px !important;
  min-width: 248px !important;
  max-width: 248px !important;
}}
section[data-testid="stSidebar"] > div {{
  padding-top: 0 !important;
}}
section[data-testid="stSidebar"] > div > div {{
  padding: 0.5rem 0.75rem 1rem 0.75rem !important;
  gap: 0 !important;
}}
section[data-testid="stSidebar"] [data-testid="stVerticalBlock"] {{
  gap: 2px !important;
}}
section[data-testid="stSidebar"] [data-testid="stVerticalBlockBorderWrapper"] {{
  gap: 0 !important;
}}
section[data-testid="stSidebar"] [data-testid="element-container"] {{
  margin-bottom: 0 !important;
}}
/* Collapse default element padding */
section[data-testid="stSidebar"] [data-testid="stElementContainer"] {{
  margin: 0 !important;
}}
section[data-testid="stSidebar"] * {{ color: {COLORS['text_on_dark']}; }}
section[data-testid="stSidebar"] h1,
section[data-testid="stSidebar"] h2,
section[data-testid="stSidebar"] h3 {{ color: white !important; }}
section[data-testid="stSidebar"] hr {{
  border-color: rgba(255,255,255,0.08);
  margin: 10px 0 6px 0;
}}
section[data-testid="stSidebar"] label {{
  color: rgba(255,255,255,0.6) !important;
  font-size: 0.68rem !important;
  font-weight: 600 !important;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  padding-bottom: 2px !important;
}}

/* Inputs in sidebar — compact */
section[data-testid="stSidebar"] input,
section[data-testid="stSidebar"] textarea,
section[data-testid="stSidebar"] [data-baseweb="select"] > div {{
  background: {COLORS['sb_bg_2']} !important;
  color: {COLORS['text_on_dark']} !important;
  border-color: rgba(255,255,255,0.08) !important;
  border-radius: 8px !important;
  font-size: 0.82rem !important;
  min-height: 34px !important;
}}
section[data-testid="stSidebar"] [data-baseweb="select"] span,
section[data-testid="stSidebar"] [data-baseweb="select"] div {{
  color: {COLORS['text_on_dark']} !important;
}}
section[data-testid="stSidebar"] [data-baseweb="select"] {{ margin-bottom: 4px !important; }}
section[data-testid="stSidebar"] .stSelectbox {{ margin-bottom: 6px !important; }}

/* Nav group label */
section[data-testid="stSidebar"] .ts-nav-group {{
  color: rgba(255,255,255,0.38) !important;
  font-size: 0.6rem; font-weight: 700;
  text-transform: uppercase; letter-spacing: 0.14em;
  padding: 10px 6px 2px 8px;
}}

/* Sidebar buttons — ultra-tight nav items */
section[data-testid="stSidebar"] .stButton {{
  margin: 0 !important;
  padding: 0 !important;
}}
section[data-testid="stSidebar"] div[data-testid="element-container"]:has(.stButton) {{
  margin: 1px 0 !important;
}}
section[data-testid="stSidebar"] .stButton > button {{
  background: transparent !important;
  color: rgba(255,255,255,0.72) !important;
  border: none !important;
  border-left: 3px solid transparent !important;
  border-radius: 6px !important;
  padding: 7px 10px 7px 11px !important;
  font-weight: 500 !important;
  font-size: 0.84rem !important;
  text-align: left !important;
  justify-content: flex-start !important;
  width: 100% !important;
  box-shadow: none !important;
  transition: all 0.1s ease;
  min-height: unset !important;
  height: auto !important;
  line-height: 1.2 !important;
  margin: 0 !important;
}}
section[data-testid="stSidebar"] .stButton > button:hover {{
  background: {COLORS['sb_hover']} !important;
  color: white !important;
  transform: none !important;
}}
section[data-testid="stSidebar"] .stButton > button:focus {{
  box-shadow: none !important;
  outline: none !important;
}}
section[data-testid="stSidebar"] .stButton > button[kind="primary"] {{
  background: {COLORS['sb_active_bg']} !important;
  color: {COLORS['sb_active_text']} !important;
  font-weight: 600 !important;
  border-left-color: {COLORS['accent']} !important;
}}

/* Sign-out button */
section[data-testid="stSidebar"] .stButton.ts-signout {{ margin-top: 6px !important; }}
section[data-testid="stSidebar"] .stButton.ts-signout > button {{
  background: rgba(194,52,47,0.15) !important;
  color: #ffd4d3 !important;
  text-align: center !important; justify-content: center !important;
  border: 1px solid rgba(194,52,47,0.3) !important;
  border-left: 1px solid rgba(194,52,47,0.3) !important;
  font-size: 0.8rem !important;
  padding: 6px 10px !important;
}}

/* Brand strip / user card — compact */
.ts-sb-brand {{
  padding: 4px 4px 10px 4px; text-align: center;
}}
.ts-sb-brand .logo {{ font-size: 1.5rem; line-height: 1; }}
.ts-sb-brand .title {{
  color: white; font-weight: 700; font-size: 0.88rem;
  margin-top: 4px; letter-spacing: -0.01em;
}}
.ts-sb-brand .tag {{
  color: rgba(255,255,255,0.4); font-size: 0.58rem;
  text-transform: uppercase; letter-spacing: 0.12em; margin-top: 1px;
}}
.ts-sb-user {{
  background: rgba(255,255,255,0.04);
  border: 1px solid rgba(255,255,255,0.06);
  border-radius: 8px; padding: 7px 10px; margin: 6px 0 8px 0;
}}
.ts-sb-user .name {{ color: white; font-weight: 600; font-size: 0.82rem; line-height: 1.1; }}
.ts-sb-user .role {{ color: rgba(255,255,255,0.5); font-size: 0.62rem;
                    text-transform: uppercase; letter-spacing: 0.1em; margin-top: 2px; }}

/* ---------- BUTTONS (main area) ---------- */
.stButton > button {{
  background: {COLORS['primary']};
  color: white;
  border: 1px solid {COLORS['primary']};
  font-weight: 500; border-radius: 10px;
  padding: 8px 16px;
  font-size: 0.88rem;
  transition: all 0.12s ease;
  box-shadow: 0 1px 2px rgba(15,42,71,0.08);
}}
.stButton > button:hover {{
  background: {COLORS['primary_600']};
  border-color: {COLORS['primary_600']};
  color: white;
  transform: translateY(-1px);
  box-shadow: 0 4px 10px rgba(15,42,71,0.12);
}}
.stButton > button:focus {{
  box-shadow: 0 0 0 3px {COLORS['accent_soft']};
  outline: none;
}}
.stButton > button[kind="secondary"] {{
  background: white; color: {COLORS['text']};
  border: 1px solid {COLORS['border_strong']};
}}
.stButton > button[kind="secondary"]:hover {{
  background: {COLORS['surface_muted']}; border-color: {COLORS['text_muted']};
  color: {COLORS['text']};
}}
.stDownloadButton > button {{
  background: {COLORS['accent']};
  border-color: {COLORS['accent']}; color: white;
}}
.stDownloadButton > button:hover {{
  background: {COLORS['accent_600']}; border-color: {COLORS['accent_600']};
}}

/* ---------- Inputs ---------- */
[data-baseweb="input"] > div, [data-baseweb="textarea"] > div,
[data-baseweb="select"] > div {{
  border-radius: 10px !important;
  border-color: {COLORS['border']} !important;
  transition: border-color 0.12s ease, box-shadow 0.12s ease;
}}
[data-baseweb="input"] > div:focus-within,
[data-baseweb="textarea"] > div:focus-within,
[data-baseweb="select"] > div:focus-within {{
  border-color: {COLORS['accent']} !important;
  box-shadow: 0 0 0 3px {COLORS['accent_soft']} !important;
}}

/* ---------- Forms ---------- */
[data-testid="stForm"] {{
  background: {COLORS['surface']};
  border: 1px solid {COLORS['border']};
  border-radius: 14px; padding: 20px; margin: 6px 0;
}}

/* ---------- Tables / dataframe ---------- */
[data-testid="stDataFrame"] {{
  border: 1px solid {COLORS['border']}; border-radius: 12px; overflow: hidden;
}}
[data-testid="stDataFrame"] [class*="header"] {{
  background: {COLORS['surface_muted']} !important;
  color: {COLORS['text']} !important; font-weight: 600 !important;
  font-size: 0.78rem !important; text-transform: uppercase;
  letter-spacing: 0.05em;
}}

/* ---------- Expanders ---------- */
[data-testid="stExpander"] {{
  background: {COLORS['surface']};
  border: 1px solid {COLORS['border']};
  border-radius: 12px;
  margin-bottom: 12px;
  box-shadow: 0 1px 2px rgba(15,42,71,0.03);
}}
[data-testid="stExpander"] summary {{ font-weight: 600; color: {COLORS['text']}; }}

/* ---------- Tabs ---------- */
[data-testid="stTabs"] [data-baseweb="tab-list"] {{
  gap: 4px; border-bottom: 1px solid {COLORS['border']};
}}
[data-testid="stTabs"] [data-baseweb="tab"] {{
  color: {COLORS['text_muted']}; font-weight: 500; padding: 10px 18px;
  border-radius: 8px 8px 0 0; background: transparent;
}}
[data-testid="stTabs"] [aria-selected="true"] {{
  color: {COLORS['primary']} !important; font-weight: 600;
  background: transparent !important;
  border-bottom: 2px solid {COLORS['accent']} !important;
}}

/* ---------- Alerts ---------- */
.stAlert {{ border-radius: 12px; border: 1px solid {COLORS['border']}; }}

/* ---------- Metric widget (when used) ---------- */
[data-testid="stMetric"] {{
  background: {COLORS['surface']};
  border: 1px solid {COLORS['border']};
  border-radius: 14px; padding: 16px;
}}
[data-testid="stMetricLabel"] {{ color: {COLORS['text_muted']} !important;
                                 font-weight: 600 !important;
                                 text-transform: uppercase; letter-spacing: 0.06em;
                                 font-size: 0.7rem !important; }}
[data-testid="stMetricValue"] {{ color: {COLORS['text']} !important;
                                 font-variant-numeric: tabular-nums; }}

/* ---------- Hero strip (login) ---------- */
.ts-hero {{
  background: linear-gradient(135deg, {COLORS['primary']}, {COLORS['primary_600']});
  border-radius: 20px; padding: 40px;
  color: white; box-shadow: 0 20px 50px rgba(15,42,71,0.25);
}}
.ts-hero h1 {{ color: white; font-size: 2rem; margin: 0; }}
.ts-hero p {{ color: rgba(255,255,255,0.8); margin-top: 6px; }}

/* ---------- Auth form wrapper ---------- */
.ts-auth-box {{
  background: {COLORS['surface']};
  border: 1px solid {COLORS['border']};
  border-radius: 18px; padding: 28px;
  box-shadow: 0 12px 40px rgba(15,42,71,0.08);
}}

/* ---------- Scrollbars ---------- */
::-webkit-scrollbar {{ width: 10px; height: 10px; }}
::-webkit-scrollbar-track {{ background: transparent; }}
::-webkit-scrollbar-thumb {{ background: {COLORS['border_strong']}; border-radius: 10px; }}
::-webkit-scrollbar-thumb:hover {{ background: {COLORS['text_muted']}; }}

/* ---------- Divider ---------- */
hr {{ border: none; border-top: 1px solid {COLORS['border']}; margin: 12px 0; }}

/* ---------- Pill filter chips ---------- */
.ts-chip {{
  display: inline-flex; align-items: center; gap: 6px;
  background: {COLORS['surface']}; border: 1px solid {COLORS['border']};
  border-radius: 999px; padding: 5px 12px; margin-right: 6px;
  font-size: 0.78rem; color: {COLORS['text_muted']}; font-weight: 500;
}}
.ts-chip.active {{ background: {COLORS['primary']}; color: white;
                    border-color: {COLORS['primary']}; }}
</style>
"""


def inject_css() -> None:
    st.markdown(CSS, unsafe_allow_html=True)


# ---------- Primitives ----------
def section_header(title: str, subtitle: str | None = None, actions_html: str = "") -> None:
    sub = f'<div class="ts-section-subtitle">{subtitle}</div>' if subtitle else ""
    st.markdown(
        f"""
        <div class="ts-section-header">
          <div>
            <div class="ts-section-title">{title}</div>
            {sub}
          </div>
          <div>{actions_html}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def metric_card(
    label: str, value, *, delta: str | None = None, trend: str = "flat",
    icon: str = "", accent: str | None = None,
) -> None:
    value_str = f"{value:,}" if isinstance(value, (int, float)) and not isinstance(value, bool) else str(value)
    delta_html = f'<div class="ts-metric-delta {trend}">{delta}</div>' if delta else ""
    icon_html = f'<span class="ts-metric-icon">{icon}</span>' if icon else ""
    style = f'style="border-left: 3px solid {accent};"' if accent else ""
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
    return f'<span class="ts-badge {severity.lower()}">{severity}</span>'


_STATUS_CLASS = {
    "DRAFT": "muted", "UNDER_REVIEW": "info", "CONFIRMED": "danger",
    "FALSE_POSITIVE": "muted", "REMEDIATED": "success",
    "ACCEPTED_RISK": "warning", "CARRIED_FORWARD": "info",
    "ACTIVE": "success", "PAUSED": "muted",
    "PLANNING": "muted", "IN_PROGRESS": "info",
    "REVIEW": "warning", "FINALISED": "success", "ARCHIVED": "muted",
    "COMPLETED": "success", "RUNNING": "info",
    "PENDING": "muted", "FAILED": "danger",
}


def status_badge(status: str) -> str:
    cls = _STATUS_CLASS.get(status, "muted")
    return f'<span class="ts-badge {cls}">{status.replace("_", " ")}</span>'


def empty_state(icon: str, title: str, description: str,
                cta_label: str | None = None, cta_key: str | None = None) -> bool:
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


def group_banner(title: str, description: str, icon: str = "🏢") -> None:
    st.markdown(
        f"""
        <div class="ts-group-banner">
          <div class="icon">{icon}</div>
          <div>
            <h4>{title}</h4>
            <p>{description}</p>
          </div>
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
        <div class="ts-heat-tile" style="border-left-color: {color};">
          <div class="code">{code}</div>
          <div class="name">{name}</div>
          <div class="score" style="color: {color};">{score:.0f}</div>
          <div class="meta">{meta}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def card_open(title: str | None = None) -> None:
    header = f'<h3>{title}</h3>' if title else ''
    st.markdown(f'<div class="ts-card">{header}', unsafe_allow_html=True)


def card_close() -> None:
    st.markdown("</div>", unsafe_allow_html=True)


def sb_brand() -> None:
    st.markdown(
        """
        <div class="ts-sb-brand">
          <div class="logo">🛡️</div>
          <div class="title">TechSource Audit</div>
          <div class="tag">Group audit intelligence</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def sb_user(username: str, role: str) -> None:
    st.markdown(
        f'<div class="ts-sb-user"><div class="name">{username}</div>'
        f'<div class="role">{role}</div></div>',
        unsafe_allow_html=True,
    )


def sb_nav_group_label(label: str) -> None:
    st.markdown(f'<div class="ts-nav-group">{label}</div>', unsafe_allow_html=True)
