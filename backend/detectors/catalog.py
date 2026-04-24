from __future__ import annotations

from backend.detectors.base import Detector
from backend.models.enums import DetectorCategory, SubledgerType

_REGISTRY: dict[str, Detector] = {}


def register(detector: Detector) -> Detector:
    if detector.name in _REGISTRY:
        raise ValueError(f"Detector already registered: {detector.name}")
    _REGISTRY[detector.name] = detector
    return detector


def get(name: str) -> Detector:
    if name not in _REGISTRY:
        raise KeyError(f"Detector not found: {name}. Registered: {sorted(_REGISTRY)}")
    return _REGISTRY[name]


def list_all() -> list[Detector]:
    _ensure_loaded()
    return sorted(_REGISTRY.values(), key=lambda d: (d.category.value, d.name))


def list_by_category(category: DetectorCategory) -> list[Detector]:
    _ensure_loaded()
    return [d for d in _REGISTRY.values() if d.category == category]


def list_for_subledger(subledger: SubledgerType) -> list[Detector]:
    _ensure_loaded()
    out = []
    for d in _REGISTRY.values():
        if d.supported_subledgers is None or subledger in d.supported_subledgers:
            out.append(d)
    return out


_LOADED = False


def _ensure_loaded() -> None:
    global _LOADED
    if _LOADED:
        return
    from backend.detectors import (  # noqa: F401
        benford_fraud,
        data_quality,
        duplicate_sequence,
        ml,
        predictive,
        relational,
        statistical,
        temporal,
        text,
    )

    _LOADED = True


def load_all() -> None:
    _ensure_loaded()
