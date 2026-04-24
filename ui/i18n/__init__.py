"""Lightweight i18n for the Streamlit UI.

Translation files live next to this module as en.json / ar.json etc.
Call t("key") from the UI; the active language is read from Streamlit session_state.
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

import streamlit as st

DEFAULT_LANG = "en"
SUPPORTED = {"en": "English", "ar": "العربية"}
RTL_LANGS = {"ar", "he", "fa", "ur"}


@lru_cache(maxsize=8)
def _catalog(lang: str) -> dict[str, str]:
    path = Path(__file__).parent / f"{lang}.json"
    if not path.exists():
        path = Path(__file__).parent / f"{DEFAULT_LANG}.json"
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def current_lang() -> str:
    return st.session_state.get("lang", DEFAULT_LANG)


def is_rtl() -> bool:
    return current_lang() in RTL_LANGS


def t(key: str, default: str | None = None) -> str:
    cat = _catalog(current_lang())
    value = cat.get(key)
    if value is None:
        value = _catalog(DEFAULT_LANG).get(key, default if default is not None else key)
    return value


def apply_rtl_if_needed() -> None:
    if is_rtl():
        st.markdown(
            """
            <style>
              .stApp { direction: rtl; text-align: right; }
              .stSidebar { direction: rtl; text-align: right; }
              [data-testid="stSidebarNav"] { direction: rtl; }
              .stMarkdown, .stText, .stSelectbox, .stTextInput { direction: rtl; }
              table, th, td { text-align: right; }
            </style>
            """,
            unsafe_allow_html=True,
        )
