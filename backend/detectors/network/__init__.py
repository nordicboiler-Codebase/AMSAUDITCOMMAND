"""Network / graph detectors — transaction graph anomalies, community detection.

These build a directed weighted graph from a transactions DataFrame and surface
suspicious topology (cycles, isolated tight clusters, unusually central nodes).
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

import polars as pl

from backend.detectors.base import Detector, DetectorResult, PerRecordScore, add_key_column
from backend.detectors.catalog import register
from backend.models.enums import DetectorCategory, SubledgerType


def _build_edges(df: pl.DataFrame, src: str, dst: str, amt: str | None) -> list[tuple]:
    edges: list[tuple] = []
    for r in df.iter_rows(named=True):
        s = str(r.get(src) or "")
        d = str(r.get(dst) or "")
        if not s or not d or s == d:
            continue
        a = float(r.get(amt) or 1.0) if amt and amt in df.columns else 1.0
        edges.append((s, d, a))
    return edges


@dataclass
class TransactionGraphDetector:
    """Build a vendor↔customer↔employee graph; flag suspicious cycles + central nodes."""
    name: str = "transaction_graph"
    category: DetectorCategory = DetectorCategory.RELATIONAL
    description: str = "Build transaction graph; flag cycles + abnormal centrality"
    default_weight: float = 0.7
    default_params: dict[str, Any] = field(
        default_factory=lambda: {
            "from_field": "from_party",
            "to_field": "to_party",
            "amount_field": "amount",
            "min_cycle_length": 3,
            "max_cycle_length": 5,
            "centrality_z_threshold": 3.0,
        }
    )
    supported_subledgers: list[SubledgerType] | None = None

    def run(self, df: pl.DataFrame, params: dict[str, Any]) -> DetectorResult:
        try:
            import networkx as nx
        except ImportError:
            return DetectorResult(flagged=df.head(0),
                                  summary={"flagged_count": 0, "reason": "networkx_missing"})
        s, d = params["from_field"], params["to_field"]
        amt = params.get("amount_field")
        min_c = int(params.get("min_cycle_length", 3))
        max_c = int(params.get("max_cycle_length", 5))
        z_thr = float(params.get("centrality_z_threshold", 3.0))
        if s not in df.columns or d not in df.columns:
            return DetectorResult(flagged=df.head(0), summary={"flagged_count": 0, "reason": "missing_field"})
        edges = _build_edges(df, s, d, amt)
        if not edges:
            return DetectorResult(flagged=df.head(0), summary={"flagged_count": 0, "reason": "no_edges"})
        G = nx.DiGraph()
        for src, dst, w in edges:
            if G.has_edge(src, dst):
                G[src][dst]["weight"] += w
            else:
                G.add_edge(src, dst, weight=w)

        # Cycles (capped to avoid combinatorial blow-up on huge graphs)
        cycles: list[list[str]] = []
        try:
            for cyc in nx.simple_cycles(G):
                if min_c <= len(cyc) <= max_c:
                    cycles.append(cyc)
                if len(cycles) >= 50:
                    break
        except Exception:
            pass

        # Centrality (degree)
        degree = dict(G.degree())
        if degree:
            import statistics

            mean_d = statistics.mean(degree.values())
            std_d = statistics.pstdev(degree.values()) or 1.0
            central = [(n, deg) for n, deg in degree.items()
                       if (deg - mean_d) / std_d > z_thr]
        else:
            central = []

        df2 = add_key_column(df)
        suspect_nodes = {n for cyc in cycles for n in cyc} | {n for n, _ in central}
        flagged = df2.filter(
            pl.col(s).cast(pl.Utf8, strict=False).is_in(list(suspect_nodes)) |
            pl.col(d).cast(pl.Utf8, strict=False).is_in(list(suspect_nodes))
        )
        scores = [
            PerRecordScore(r["_record_key"], 1.0,
                          f"in suspicious cycle or hub: {r.get(s)}→{r.get(d)}")
            for r in flagged.iter_rows(named=True)
        ]
        return DetectorResult(
            flagged=flagged,
            summary={
                "flagged_count": flagged.height,
                "node_count": G.number_of_nodes(),
                "edge_count": G.number_of_edges(),
                "cycle_count": len(cycles),
                "cycles_sample": [{"path": c, "length": len(c)} for c in cycles[:20]],
                "high_centrality_nodes": [{"node": n, "degree": d} for n, d in central[:30]],
            },
            per_record_scores=scores,
        )


@dataclass
class CommunityDetectionDetector:
    """Find tight clusters of entities transacting predominantly with each other."""
    name: str = "community_detection"
    category: DetectorCategory = DetectorCategory.RELATIONAL
    description: str = "Greedy modularity communities; flag isolated tight clusters"
    default_weight: float = 0.6
    default_params: dict[str, Any] = field(
        default_factory=lambda: {
            "from_field": "from_party",
            "to_field": "to_party",
            "amount_field": "amount",
            "min_community_size": 3,
        }
    )
    supported_subledgers: list[SubledgerType] | None = None

    def run(self, df: pl.DataFrame, params: dict[str, Any]) -> DetectorResult:
        try:
            import networkx as nx
            from networkx.algorithms.community import greedy_modularity_communities
        except ImportError:
            return DetectorResult(flagged=df.head(0),
                                  summary={"flagged_count": 0, "reason": "networkx_missing"})
        s, d = params["from_field"], params["to_field"]
        amt = params.get("amount_field")
        min_size = int(params.get("min_community_size", 3))
        if s not in df.columns or d not in df.columns:
            return DetectorResult(flagged=df.head(0), summary={"flagged_count": 0, "reason": "missing_field"})
        edges = _build_edges(df, s, d, amt)
        if not edges:
            return DetectorResult(flagged=df.head(0), summary={"flagged_count": 0, "reason": "no_edges"})
        G = nx.Graph()
        for src, dst, w in edges:
            if G.has_edge(src, dst):
                G[src][dst]["weight"] += w
            else:
                G.add_edge(src, dst, weight=w)
        try:
            communities = list(greedy_modularity_communities(G, weight="weight"))
        except Exception:
            communities = []
        big_communities = [c for c in communities if len(c) >= min_size]
        suspect_nodes: set[str] = set()
        for c in big_communities:
            suspect_nodes.update(c)

        df2 = add_key_column(df)
        flagged = df2.filter(
            pl.col(s).cast(pl.Utf8, strict=False).is_in(list(suspect_nodes)) |
            pl.col(d).cast(pl.Utf8, strict=False).is_in(list(suspect_nodes))
        )
        scores = [
            PerRecordScore(r["_record_key"], 1.0,
                          f"member of tight cluster")
            for r in flagged.iter_rows(named=True)
        ]
        return DetectorResult(
            flagged=flagged,
            summary={
                "flagged_count": flagged.height,
                "community_count": len(big_communities),
                "communities": [list(c)[:30] for c in big_communities[:10]],
                "min_community_size": min_size,
            },
            per_record_scores=scores,
        )


register(TransactionGraphDetector())
register(CommunityDetectionDetector())
