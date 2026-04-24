from __future__ import annotations

import base64
import io
from typing import Any

NAVY = "#0b2a4a"
TEAL = "#15a8a8"


def _svg_data_uri(fig) -> str:
    buf = io.BytesIO()
    fig.savefig(buf, format="svg", bbox_inches="tight")
    import matplotlib.pyplot as plt

    plt.close(fig)
    svg = buf.getvalue().decode("utf-8")
    b64 = base64.b64encode(svg.encode("utf-8")).decode("ascii")
    return f"data:image/svg+xml;base64,{b64}"


def benford_chart(distribution: list[dict[str, Any]]) -> str | None:
    if not distribution:
        return None
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        return None

    digits = [d["digit"] for d in distribution]
    observed_pct = [d["observed_pct"] * 100 for d in distribution]
    expected_pct = [d["expected_pct"] * 100 for d in distribution]

    fig, ax = plt.subplots(figsize=(7, 3.2), dpi=120)
    x = list(range(len(digits)))
    width = 0.38
    ax.bar([i - width / 2 for i in x], observed_pct, width, label="Observed", color=NAVY)
    ax.bar([i + width / 2 for i in x], expected_pct, width, label="Benford Expected", color=TEAL)
    ax.set_xticks(x)
    ax.set_xticklabels([str(d) for d in digits], fontsize=7)
    ax.set_ylabel("Percentage", fontsize=9)
    ax.set_title("Benford Distribution", fontsize=11, color=NAVY)
    ax.legend(fontsize=8, loc="upper right")
    ax.grid(axis="y", alpha=0.3)
    return _svg_data_uri(fig)


def aging_chart(buckets: list[dict[str, Any]]) -> str | None:
    if not buckets:
        return None
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        return None

    labels = []
    counts = []
    for b in buckets:
        lo = b.get("from", 0)
        hi = b.get("to")
        labels.append(f"{lo}-{hi}" if hi is not None else f"{lo}+")
        counts.append(b.get("count", 0))

    fig, ax = plt.subplots(figsize=(6, 3), dpi=120)
    ax.bar(labels, counts, color=NAVY, edgecolor=TEAL)
    ax.set_ylabel("Records", fontsize=9)
    ax.set_xlabel("Age bucket (days)", fontsize=9)
    ax.set_title("Aging Analysis", fontsize=11, color=NAVY)
    ax.grid(axis="y", alpha=0.3)
    for i, c in enumerate(counts):
        ax.text(i, c, str(c), ha="center", va="bottom", fontsize=8)
    return _svg_data_uri(fig)


def pareto_chart(rows: list[dict[str, Any]], label_field: str, value_field: str,
                 title: str = "Top Contributors", top_n: int = 10) -> str | None:
    if not rows:
        return None
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        return None

    items = [(str(r.get(label_field, "")), float(r.get(value_field, 0) or 0)) for r in rows]
    items.sort(key=lambda x: x[1], reverse=True)
    items = items[:top_n]
    labels = [i[0][:20] for i in items]
    values = [i[1] for i in items]
    cumulative = []
    total = sum(values) or 1.0
    running = 0.0
    for v in values:
        running += v
        cumulative.append(running / total * 100)

    fig, ax1 = plt.subplots(figsize=(7, 3.2), dpi=120)
    ax1.bar(labels, values, color=NAVY)
    ax1.set_ylabel("Value", fontsize=9, color=NAVY)
    ax1.tick_params(axis="x", labelrotation=30, labelsize=7)
    ax2 = ax1.twinx()
    ax2.plot(labels, cumulative, color=TEAL, marker="o", linewidth=1.5)
    ax2.set_ylabel("Cumulative %", fontsize=9, color=TEAL)
    ax2.set_ylim(0, 105)
    ax1.set_title(title, fontsize=11, color=NAVY)
    ax1.grid(axis="y", alpha=0.3)
    return _svg_data_uri(fig)


def histogram_chart(histogram: list[dict[str, Any]], title: str = "Distribution") -> str | None:
    if not histogram:
        return None
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        return None

    labels = [f"{int(h['from']):,}-{int(h['to']):,}" for h in histogram]
    counts = [h.get("count", 0) for h in histogram]
    fig, ax = plt.subplots(figsize=(7, 3), dpi=120)
    ax.bar(labels, counts, color=NAVY)
    ax.tick_params(axis="x", labelrotation=45, labelsize=6)
    ax.set_title(title, fontsize=11, color=NAVY)
    ax.grid(axis="y", alpha=0.3)
    return _svg_data_uri(fig)


def score_histogram_chart(scores: list[float]) -> str | None:
    if not scores:
        return None
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        return None

    fig, ax = plt.subplots(figsize=(7, 3), dpi=120)
    bins = [0, 10, 20, 30, 40, 50, 60, 70, 80, 90, 100]
    ax.hist(scores, bins=bins, color=NAVY, edgecolor=TEAL)
    ax.set_xlabel("Risk score", fontsize=9)
    ax.set_ylabel("Records", fontsize=9)
    ax.set_title("Risk Score Distribution", fontsize=11, color=NAVY)
    ax.axvline(50, color="orange", linestyle="--", linewidth=1, label="Review threshold")
    ax.axvline(80, color="red", linestyle="--", linewidth=1, label="Critical threshold")
    ax.legend(fontsize=8)
    ax.grid(axis="y", alpha=0.3)
    return _svg_data_uri(fig)


def render_chart_for_summary(detector_name: str, summary: dict[str, Any]) -> str | None:
    if detector_name == "benford" and summary.get("distribution"):
        return benford_chart(summary["distribution"])
    if detector_name == "age" and summary.get("buckets"):
        return aging_chart(summary["buckets"])
    if detector_name in {"histogram", "stratify"} and summary.get("histogram"):
        return histogram_chart(summary["histogram"], title=detector_name.title())
    if detector_name in {"stratify"} and summary.get("buckets"):
        return histogram_chart(
            [{"from": b["from"], "to": b["to"], "count": b["count"]} for b in summary["buckets"]],
            title="Stratification",
        )
    if detector_name in {"summarize", "classify"} and (summary.get("rows") or summary.get("groups")):
        rows = summary.get("rows") or summary.get("groups") or []
        if not rows:
            return None
        keys = list(rows[0].keys())
        label_field = next((k for k in keys if k != "count" and not k.startswith("sum_")), keys[0])
        value_field = "count"
        for k in keys:
            if k.startswith("sum_"):
                value_field = k
                break
        return pareto_chart(rows, label_field, value_field, title="Top Contributors")
    return None
