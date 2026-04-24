from __future__ import annotations

import json
import uuid
from io import BytesIO

import polars as pl
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.models import Dataset, PackRun, Project, RiskScore, TestRun
from backend.services import charts


def _html_safe(s: str | None) -> str:
    if s is None:
        return ""
    return (str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


def generate_template_report(db: Session, test_run_id: uuid.UUID) -> bytes:
    from weasyprint import HTML

    run = db.get(TestRun, test_run_id)
    if not run:
        raise ValueError("Run not found")
    dataset = db.get(Dataset, run.dataset_id)

    findings_html = ""
    try:
        if run.output_parquet_path:
            findings = pl.read_parquet(run.output_parquet_path).head(100)
            if findings.height > 0:
                cols = [c for c in findings.columns if c != "_record_key"][:10]
                rows = []
                for r in findings.to_dicts():
                    rows.append("<tr>" + "".join(f"<td>{_html_safe(r.get(c))}</td>" for c in cols) + "</tr>")
                findings_html = (
                    "<table><thead><tr>"
                    + "".join(f"<th>{_html_safe(c)}</th>" for c in cols)
                    + "</tr></thead><tbody>"
                    + "".join(rows)
                    + "</tbody></table>"
                )
    except Exception as e:
        findings_html = f"<p>Could not render findings: {_html_safe(str(e))}</p>"

    params_html = "<table>" + "".join(
        f"<tr><td class='k'>{_html_safe(k)}</td><td>{_html_safe(json.dumps(v))}</td></tr>"
        for k, v in (run.params or {}).items()
    ) + "</table>"

    chart_uri = charts.render_chart_for_summary(run.detector_name, run.summary or {})
    chart_html = f'<img src="{chart_uri}" style="max-width:100%;"/>' if chart_uri else ""

    html = f"""
    <html><head><style>
      body {{ font-family: DejaVu Sans, sans-serif; font-size: 10pt; color: #222; }}
      h1 {{ color: #0b2a4a; }}
      h2 {{ color: #0b2a4a; border-bottom: 1px solid #ccc; padding-bottom: 2px; }}
      .cover {{ padding: 40px 0; border-bottom: 3px solid #0b2a4a; }}
      .metric {{ font-size: 24pt; color: #0b2a4a; }}
      table {{ border-collapse: collapse; width: 100%; margin: 8px 0; }}
      th, td {{ border: 1px solid #ccc; padding: 3px 5px; text-align: left; }}
      th {{ background: #0b2a4a; color: white; }}
      td.k {{ font-weight: bold; width: 30%; }}
      .footer {{ margin-top: 30px; font-size: 8pt; color: #666; border-top: 1px solid #ccc; padding-top: 8px; }}
    </style></head><body>
      <div class="cover">
        <h1>TechSource Audit Report</h1>
        <p><strong>Template:</strong> {_html_safe(run.template_code)} — Detector: {_html_safe(run.detector_name)}</p>
        <p><strong>Dataset:</strong> {_html_safe(dataset.name if dataset else "")}</p>
        <p><strong>Run ID:</strong> {run.id}</p>
        <p><strong>Run Date:</strong> {run.started_at.isoformat() if run.started_at else ""}</p>
      </div>
      <h2>Executive Summary</h2>
      <p>The test produced <span class="metric">{run.findings_count}</span> findings.</p>
      <h2>Parameters</h2>
      {params_html}
      <h2>Visualisation</h2>
      {chart_html or "<p>No chart available for this detector.</p>"}
      <h2>Summary</h2>
      <pre>{_html_safe(json.dumps(run.summary or {}, indent=2)[:3000])}</pre>
      <h2>Findings (top 100)</h2>
      {findings_html or "<p>No findings.</p>"}
      <div class="footer">
        Input hash: {run.input_hash or ""}<br>
        Output hash: {run.output_hash or ""}<br>
        Run by: {run.run_by}
      </div>
    </body></html>
    """
    return HTML(string=html).write_pdf()


def generate_pack_report(db: Session, pack_run_id: uuid.UUID) -> bytes:
    from weasyprint import HTML

    pr = db.get(PackRun, pack_run_id)
    if not pr:
        raise ValueError("Pack run not found")
    dataset = db.get(Dataset, pr.dataset_id)
    runs = list(db.execute(select(TestRun).where(TestRun.pack_run_id == pr.id)).scalars())
    rows = "".join(
        f"<tr><td>{_html_safe(r.template_code)}</td>"
        f"<td>{_html_safe(r.detector_name)}</td>"
        f"<td>{r.findings_count}</td>"
        f"<td>{r.status.value if r.status else ''}</td></tr>"
        for r in runs
    )

    # Findings-count Pareto by template
    pareto_rows = [{"template": r.template_code or r.detector_name, "findings": r.findings_count}
                   for r in runs if r.findings_count]
    pareto_uri = charts.pareto_chart(pareto_rows, "template", "findings",
                                     title="Top Templates by Findings Count")
    pareto_html = f'<img src="{pareto_uri}" style="max-width:100%;"/>' if pareto_uri else ""

    # Risk score distribution for ensemble-scored records on this dataset
    score_html = ""
    if pr.ensemble_run_id:
        score_vals = [
            s for (s,) in db.execute(
                select(RiskScore.score).where(RiskScore.ensemble_run_id == pr.ensemble_run_id)
            ).all()
        ]
        score_uri = charts.score_histogram_chart([float(s) for s in score_vals])
        if score_uri:
            score_html = f'<img src="{score_uri}" style="max-width:100%;"/>'

    html = f"""
    <html><head><style>
      body {{ font-family: DejaVu Sans, sans-serif; font-size: 10pt; }}
      h1 {{ color: #0b2a4a; }}
      h2 {{ color: #0b2a4a; border-bottom: 1px solid #ccc; padding-bottom: 2px; }}
      table {{ border-collapse: collapse; width: 100%; }}
      th, td {{ border: 1px solid #ccc; padding: 4px 6px; }}
      th {{ background: #0b2a4a; color: white; }}
    </style></head><body>
      <h1>Pack Run Report — {_html_safe(pr.pack_code)}</h1>
      <p>Dataset: {_html_safe(dataset.name if dataset else "")}</p>
      <p>Templates run: {len(runs)} | Total findings: {sum(r.findings_count for r in runs)}</p>
      <h2>Findings by Template</h2>
      {pareto_html or "<p>No findings to chart.</p>"}
      {"<h2>Risk Score Distribution</h2>" + score_html if score_html else ""}
      <h2>Detail by Template</h2>
      <table><thead><tr><th>Template</th><th>Detector</th><th>Findings</th><th>Status</th></tr></thead>
      <tbody>{rows}</tbody></table>
    </body></html>
    """
    return HTML(string=html).write_pdf()


def generate_project_report(db: Session, project_id: uuid.UUID) -> bytes:
    from weasyprint import HTML

    project = db.get(Project, project_id)
    if not project:
        raise ValueError("Project not found")
    datasets = list(db.execute(select(Dataset).where(Dataset.project_id == project_id)).scalars())
    ds_rows = "".join(
        f"<tr><td>{_html_safe(d.name)}</td><td>{d.subledger_type.value}</td>"
        f"<td>{d.record_count}</td></tr>"
        for d in datasets
    )
    html = f"""
    <html><head><style>
      body {{ font-family: DejaVu Sans, sans-serif; font-size: 10pt; }}
      h1 {{ color: #0b2a4a; }}
      table {{ border-collapse: collapse; width: 100%; }}
      th, td {{ border: 1px solid #ccc; padding: 4px 6px; }}
      th {{ background: #0b2a4a; color: white; }}
    </style></head><body>
      <h1>Project Report — {_html_safe(project.name)}</h1>
      <p>{_html_safe(project.description or "")}</p>
      <p>Subsidiary: {_html_safe(project.subsidiary_code or "")}</p>
      <h2>Datasets</h2>
      <table><thead><tr><th>Name</th><th>Subledger</th><th>Records</th></tr></thead>
      <tbody>{ds_rows}</tbody></table>
    </body></html>
    """
    return HTML(string=html).write_pdf()


def generate_excel(db: Session, test_run_id: uuid.UUID) -> bytes:
    run = db.get(TestRun, test_run_id)
    if not run or not run.output_parquet_path:
        return b""
    df = pl.read_parquet(run.output_parquet_path)
    buf = BytesIO()
    df.write_excel(buf)
    return buf.getvalue()
