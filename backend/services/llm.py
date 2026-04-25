"""Provider-agnostic LLM client.

Supports Anthropic Claude, OpenAI, and Google Gemini. Settings are stored
encrypted in app_settings (category="ai_providers"). The active provider
is stored under category="ai_providers", key="active".

All callers should go through `get_active_client(db)` — the rest of the
app does not import provider SDKs directly. The client exposes a single
`.complete(system, user, max_tokens, temperature)` method so the call
sites in nlq.py stay provider-agnostic.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Any, Protocol

from sqlalchemy.orm import Session

from backend.core.config import get_settings
from backend.services import settings_store

log = logging.getLogger(__name__)

settings = get_settings()

CATEGORY = "ai_providers"
SECRET_FIELDS = {"api_key"}

PROVIDERS = ("anthropic", "openai", "gemini")

DEFAULT_MODEL = {
    "anthropic": "claude-sonnet-4-6",
    "openai": "gpt-4o-mini",
    "gemini": "gemini-2.5-flash",
}

# Suggested models surfaced in the UI dropdown (for guidance only).
# Note: gemini-1.5-* family was deprecated by Google late 2025; do not list.
MODEL_CHOICES = {
    "anthropic": [
        "claude-sonnet-4-6",
        "claude-opus-4-7",
        "claude-haiku-4-5-20251001",
    ],
    "openai": ["gpt-4o-mini", "gpt-4o", "gpt-4-turbo"],
    "gemini": [
        "gemini-2.5-flash",
        "gemini-2.5-pro",
        "gemini-2.5-flash-lite",
        "gemini-2.0-flash",
        "gemini-2.0-flash-lite",
    ],
}

# Models we know Google has retired — silently rewrite to DEFAULT_MODEL.
DEPRECATED_MODEL_REWRITES = {
    "gemini": {
        "gemini-1.5-flash": "gemini-2.5-flash",
        "gemini-1.5-pro": "gemini-2.5-pro",
        "gemini-1.5-flash-002": "gemini-2.5-flash",
        "gemini-1.5-pro-002": "gemini-2.5-pro",
        "gemini-2.0-flash-exp": "gemini-2.0-flash",
    },
}

PROVIDER_LABEL = {
    "anthropic": "Anthropic Claude",
    "openai": "OpenAI",
    "gemini": "Google Gemini (free tier available)",
}

PROVIDER_KEY_HINT = {
    "anthropic": "Get a key at console.anthropic.com — paid",
    "openai": "Get a key at platform.openai.com — paid",
    "gemini": (
        "Get a free key at aistudio.google.com/apikey — no card. "
        "Free tier limits per model: ~10 RPM and a few hundred RPD. "
        "If you hit 429, switch to gemini-2.5-flash-lite for higher daily quota."
    ),
}


class LlmClient(Protocol):
    provider: str
    model: str

    def complete(self, *, system: str | None, user: str,
                 max_tokens: int = 1024, temperature: float = 0.2) -> str: ...


def _is_rate_limit(e: Exception) -> bool:
    msg = str(e).lower()
    name = type(e).__name__.lower()
    return (
        "429" in msg
        or "resource_exhausted" in msg
        or "rate limit" in msg
        or "ratelimit" in name
        or "quota" in msg
    )


def _retry_once_on_429(fn):
    """Wrap a callable so a single 429 triggers one retry after ~3s."""
    def wrapper(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except Exception as e:  # noqa: BLE001
            if _is_rate_limit(e):
                log.warning("LLM 429 — retrying once after 3s. Error: %s", e)
                time.sleep(3.0)
                return fn(*args, **kwargs)
            raise
    return wrapper


@dataclass
class _AnthropicClient:
    provider: str
    model: str
    api_key: str

    @_retry_once_on_429
    def complete(self, *, system, user, max_tokens=1024, temperature=0.2):
        from anthropic import Anthropic
        c = Anthropic(api_key=self.api_key)
        kwargs: dict[str, Any] = {
            "model": self.model, "max_tokens": max_tokens, "temperature": temperature,
            "messages": [{"role": "user", "content": user}],
        }
        if system:
            kwargs["system"] = system
        resp = c.messages.create(**kwargs)
        return "".join(b.text for b in resp.content if getattr(b, "type", "") == "text")


@dataclass
class _OpenAIClient:
    provider: str
    model: str
    api_key: str

    @_retry_once_on_429
    def complete(self, *, system, user, max_tokens=1024, temperature=0.2):
        from openai import OpenAI
        c = OpenAI(api_key=self.api_key)
        msgs: list[dict[str, str]] = []
        if system:
            msgs.append({"role": "system", "content": system})
        msgs.append({"role": "user", "content": user})
        resp = c.chat.completions.create(
            model=self.model, messages=msgs,
            max_tokens=max_tokens, temperature=temperature,
        )
        return resp.choices[0].message.content or ""


@dataclass
class _GeminiClient:
    provider: str
    model: str
    api_key: str

    @_retry_once_on_429
    def complete(self, *, system, user, max_tokens=1024, temperature=0.2):
        from google import genai
        from google.genai import types
        client = genai.Client(api_key=self.api_key)
        cfg = types.GenerateContentConfig(
            temperature=temperature,
            max_output_tokens=max_tokens,
            system_instruction=system or None,
        )
        resp = client.models.generate_content(
            model=self.model, contents=user, config=cfg,
        )
        return resp.text or ""


def _sdk_installed(provider: str) -> bool:
    try:
        if provider == "anthropic":
            import anthropic  # noqa: F401
        elif provider == "openai":
            import openai  # noqa: F401
        elif provider == "gemini":
            from google import genai  # noqa: F401
        else:
            return False
        return True
    except ImportError:
        return False


def _load_provider_config(db: Session, provider: str) -> dict[str, Any]:
    """Read stored config for a provider (decrypts api_key, rewrites
    deprecated model names so retired Gemini 1.5.x configs don't 404)."""
    raw = settings_store.get_setting(db, CATEGORY, provider) or {}
    if raw.get("api_key"):
        raw["api_key"] = settings_store.decrypt_secret(raw["api_key"])
    rewrites = DEPRECATED_MODEL_REWRITES.get(provider, {})
    if raw.get("model") in rewrites:
        raw["model"] = rewrites[raw["model"]]
    return raw


def _save_provider_config(
    db: Session, *, provider: str, enabled: bool, api_key: str | None,
    model: str, updated_by=None,
) -> None:
    existing = settings_store.get_setting(db, CATEGORY, provider) or {}
    if api_key is None or api_key == settings_store.SECRET_SENTINEL:
        # User left key untouched — keep existing ciphertext.
        encrypted_key = existing.get("api_key", "")
    else:
        encrypted_key = settings_store.encrypt_secret(api_key) if api_key else ""
    final_model = model or DEFAULT_MODEL[provider]
    rewrites = DEPRECATED_MODEL_REWRITES.get(provider, {})
    if final_model in rewrites:
        final_model = rewrites[final_model]
    settings_store.upsert_setting(
        db, category=CATEGORY, key=provider,
        value={
            "enabled": bool(enabled),
            "api_key": encrypted_key,
            "model": final_model,
        },
        is_secret=True,
        updated_by=updated_by,
    )


def _set_active(db: Session, provider: str | None, *, updated_by=None) -> None:
    settings_store.upsert_setting(
        db, category=CATEGORY, key="__active__",
        value={"provider": provider}, is_secret=False, updated_by=updated_by,
    )


def _get_active_provider(db: Session) -> str | None:
    row = settings_store.get_setting(db, CATEGORY, "__active__") or {}
    p = row.get("provider")
    return p if p in PROVIDERS else None


def get_active_client(db: Session) -> LlmClient | None:
    """Return the configured active LLM client, or None if AI is disabled.

    Falls back to env-based ANTHROPIC_API_KEY (legacy) when no provider is
    explicitly configured in the DB.
    """
    active = _get_active_provider(db)
    if active is None:
        # Legacy fallback: env-based Anthropic key
        if settings.anthropic_api_key and _sdk_installed("anthropic"):
            return _AnthropicClient(
                provider="anthropic",
                model=settings.anthropic_model or DEFAULT_MODEL["anthropic"],
                api_key=settings.anthropic_api_key,
            )
        return None

    cfg = _load_provider_config(db, active)
    if not cfg.get("enabled") or not cfg.get("api_key") or not _sdk_installed(active):
        return None
    model = cfg.get("model") or DEFAULT_MODEL[active]
    if active == "anthropic":
        return _AnthropicClient(provider=active, model=model, api_key=cfg["api_key"])
    if active == "openai":
        return _OpenAIClient(provider=active, model=model, api_key=cfg["api_key"])
    if active == "gemini":
        return _GeminiClient(provider=active, model=model, api_key=cfg["api_key"])
    return None


def get_status(db: Session) -> dict:
    """Status payload for /api/ai/status and the settings UI."""
    active = _get_active_provider(db)
    legacy_active = (
        active is None and settings.anthropic_api_key and _sdk_installed("anthropic")
    )

    providers = []
    for p in PROVIDERS:
        cfg = _load_provider_config(db, p)
        sdk = _sdk_installed(p)
        configured = bool(cfg.get("api_key"))
        enabled = bool(cfg.get("enabled")) and configured and sdk
        providers.append({
            "provider": p,
            "label": PROVIDER_LABEL[p],
            "key_hint": PROVIDER_KEY_HINT[p],
            "enabled": enabled,
            "configured": configured,
            "sdk_installed": sdk,
            "model": cfg.get("model") or DEFAULT_MODEL[p],
            "model_choices": MODEL_CHOICES[p],
            "default_model": DEFAULT_MODEL[p],
        })

    if active is None and legacy_active:
        active = "anthropic"

    active_provider = next((x for x in providers if x["provider"] == active), None)
    overall_enabled = bool(active_provider and active_provider["enabled"]) or bool(legacy_active)

    if overall_enabled:
        reason = "ready"
    elif active and active_provider and not active_provider["sdk_installed"]:
        reason = f"{active_provider['label']} SDK not installed in this environment"
    elif active and active_provider and not active_provider["configured"]:
        reason = f"{active_provider['label']} API key not set"
    elif active and active_provider and not active_provider["enabled"]:
        reason = f"{active_provider['label']} is disabled — toggle it on in Settings"
    else:
        reason = "No active AI provider — pick one in Settings → AI Providers"

    return {
        "enabled": overall_enabled,
        "reason": reason,
        "active": active,
        "model": active_provider["model"] if (active_provider and overall_enabled) else None,
        "providers": providers,
        "legacy_env_active": legacy_active,
    }


def humanise_provider_error(e: Exception) -> str:
    """Translate provider exceptions into actionable single-line messages."""
    msg = str(e)
    name = type(e).__name__
    short = msg if len(msg) <= 400 else msg[:400] + "…"
    low = msg.lower()
    if _is_rate_limit(e):
        return (
            f"{name}: provider quota or rate limit hit. "
            "On Gemini's free tier this is per-minute and per-day — wait, switch to "
            "gemini-2.5-flash-lite (higher daily quota), or pick a different "
            "provider in Settings → AI Providers. "
            f"Details: {short}"
        )
    if "not_found" in low or "404" in msg or "is not found" in low:
        return (
            f"{name}: model not available — likely retired by the provider. "
            "Open Settings → AI Providers and pick a current model. "
            f"Details: {short}"
        )
    if "401" in msg or "unauthorized" in low or "invalid_api_key" in low or "permission_denied" in low:
        return (
            f"{name}: API key rejected. Open Settings → AI Providers and re-enter the key. "
            f"Details: {short}"
        )
    if "402" in msg or "billing" in low or "credit" in low or "insufficient_quota" in low:
        return (
            f"{name}: provider billing / credits issue. Add credits to your provider account. "
            f"Details: {short}"
        )
    if "503" in msg or "unavailable" in low or "overloaded" in low:
        return (
            f"{name}: provider temporarily unavailable. Retry in a moment. "
            f"Details: {short}"
        )
    return f"{name}: {short}"


def test_provider(db: Session, provider: str) -> dict:
    """Make a tiny ping call to verify the provider key works."""
    if provider not in PROVIDERS:
        return {"ok": False, "error": "Unknown provider"}
    if not _sdk_installed(provider):
        return {"ok": False, "error": f"{PROVIDER_LABEL[provider]} SDK not installed"}
    cfg = _load_provider_config(db, provider)
    if not cfg.get("api_key"):
        return {"ok": False, "error": "No API key configured for this provider"}

    model = cfg.get("model") or DEFAULT_MODEL[provider]
    try:
        if provider == "anthropic":
            client: LlmClient = _AnthropicClient(provider, model, cfg["api_key"])
        elif provider == "openai":
            client = _OpenAIClient(provider, model, cfg["api_key"])
        else:
            client = _GeminiClient(provider, model, cfg["api_key"])
        text = client.complete(
            system="Reply with exactly the word OK.", user="ping",
            max_tokens=10, temperature=0,
        )
        return {"ok": True, "model": model, "sample": (text or "").strip()[:120]}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": humanise_provider_error(e)}


def save_provider(
    db: Session, *, provider: str, enabled: bool, api_key: str | None,
    model: str, updated_by=None,
) -> None:
    if provider not in PROVIDERS:
        raise ValueError(f"Unknown provider: {provider}")
    _save_provider_config(
        db, provider=provider, enabled=enabled, api_key=api_key,
        model=model, updated_by=updated_by,
    )


def set_active(db: Session, provider: str | None, *, updated_by=None) -> None:
    if provider is not None and provider not in PROVIDERS:
        raise ValueError(f"Unknown provider: {provider}")
    _set_active(db, provider, updated_by=updated_by)
