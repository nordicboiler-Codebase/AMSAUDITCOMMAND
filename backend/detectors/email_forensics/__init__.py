"""Email-forensics detectors — run on datasets produced by the PST/mbox
importer (`backend.services.email_ingest`), i.e. one row per message with the
standard columns: custodian, sender_email, all_recipients, recipient_domains,
subject, body_excerpt, has_attachments, attachment_names, sent_at, ...

Three engines:
  - email_dlp              data leakage to personal/free email accounts
  - email_cross_custodian  shared external contacts across employees (multi-PST)
  - email_search           parameterised search — the target for plain-English
                           "Ask AI" questions over mailboxes
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from typing import Any

import polars as pl
from rapidfuzz import fuzz

from backend.detectors.base import Detector, DetectorResult, PerRecordScore, add_key_column
from backend.detectors.catalog import register
from backend.models.enums import DetectorCategory, SubledgerType
from backend.services.email_ingest import PERSONAL_EMAIL_DOMAINS

SENSITIVE_KEYWORDS_DEFAULT = [
    "confidential", "internal only", "do not share", "do not forward", "nda",
    "password", "credentials", "login", "vpn", "salary", "payroll", "bonus",
    "appraisal", "termination", "customer list", "client list", "price list",
    "pricing", "quotation", "tender", "bid", "contract", "agreement",
    "bank account", "iban", "swift", "statement", "invoice", "p&l",
    "trial balance", "forecast", "budget", "source code", "database dump",
    "backup", "export", "personal data", "passport", "emirates id", "visa",
]


def _split(values: str | None) -> list[str]:
    if not values:
        return []
    return [v.strip().lower() for v in values.split(";") if v.strip()]


def _localpart(addr: str) -> str:
    return addr.split("@", 1)[0].lower()


def _name_tokens(s: str | None) -> list[str]:
    if not s:
        return []
    return [t for t in re.split(r"[^a-z]+", s.lower()) if len(t) >= 3]


def _infer_corporate_domains(df: pl.DataFrame) -> set[str]:
    """Corporate domains = the domains the custodians themselves send from.

    Any sender_domain that accounts for a meaningful share of SENT traffic is
    treated as corporate; personal providers are never corporate.
    """
    corp: set[str] = set()
    if "sender_domain" not in df.columns:
        return corp
    counts = (
        df.filter(pl.col("sender_domain").is_not_null())
        .group_by("sender_domain").len()
    )
    total = int(counts["len"].sum() or 0)
    if not total:
        return corp
    personal = set(PERSONAL_EMAIL_DOMAINS)
    for dom, n in zip(counts["sender_domain"].to_list(), counts["len"].to_list()):
        if dom and dom not in personal and (n / total >= 0.05 or n >= 10):
            corp.add(dom)
    return corp


@dataclass
class EmailDlpDetector:
    """Flags messages that leak content to personal/free email accounts.

    Signals (combined into the per-record score):
      - any recipient on a personal/free provider          (base signal)
      - attachments included                               (+)
      - sensitive keyword in subject/body/attachment name  (+)
      - self-exfiltration: recipient local-part resembles the sender's own
        name or the custodian (sending company data to your private account)
    """
    name: str = "email_dlp"
    category: DetectorCategory = DetectorCategory.TEXT
    description: str = "Data leakage to personal email accounts (DLP over PST/mailbox datasets)"
    default_weight: float = 2.0
    default_params: dict[str, Any] = field(
        default_factory=lambda: {
            "recipient_field": "all_recipients",
            "sender_field": "sender_email",
            "subject_field": "subject",
            "body_field": "body_excerpt",
            "attachment_field": "attachment_names",
            "personal_domains": list(PERSONAL_EMAIL_DOMAINS),
            "sensitive_keywords": list(SENSITIVE_KEYWORDS_DEFAULT),
            "corporate_domains": [],          # empty → inferred from senders
            "require_attachment": False,
            "require_keyword": False,
            "check_self_exfiltration": True,
            "name_similarity_threshold": 80,
        }
    )
    supported_subledgers: list[SubledgerType] | None = field(
        default_factory=lambda: [SubledgerType.EMAIL, SubledgerType.OTHER]
    )

    def run(self, df: pl.DataFrame, params: dict[str, Any]) -> DetectorResult:
        rf = params.get("recipient_field", "all_recipients")
        sf = params.get("sender_field", "sender_email")
        if rf not in df.columns:
            return DetectorResult(flagged=df.head(0),
                                  summary={"flagged_count": 0, "reason": f"field_not_found:{rf}"})
        subject_f = params.get("subject_field", "subject")
        body_f = params.get("body_field", "body_excerpt")
        att_f = params.get("attachment_field", "attachment_names")
        personal = {d.lower() for d in (params.get("personal_domains") or PERSONAL_EMAIL_DOMAINS)}
        keywords = [k.lower() for k in (params.get("sensitive_keywords") or SENSITIVE_KEYWORDS_DEFAULT)]
        corporate = {d.lower() for d in (params.get("corporate_domains") or [])} or _infer_corporate_domains(df)
        require_att = bool(params.get("require_attachment", False))
        require_kw = bool(params.get("require_keyword", False))
        self_exfil = bool(params.get("check_self_exfiltration", True))
        sim_threshold = float(params.get("name_similarity_threshold", 80))

        df2 = add_key_column(df)
        keys = df2["_record_key"].to_list()
        recipients = df2[rf].cast(pl.Utf8, strict=False).to_list()
        senders = df2[sf].cast(pl.Utf8, strict=False).to_list() if sf in df2.columns else [None] * df2.height
        sender_names = (df2["sender_name"].cast(pl.Utf8, strict=False).to_list()
                        if "sender_name" in df2.columns else [None] * df2.height)
        custodians = (df2["custodian"].cast(pl.Utf8, strict=False).to_list()
                      if "custodian" in df2.columns else [None] * df2.height)
        subjects = df2[subject_f].cast(pl.Utf8, strict=False).to_list() if subject_f in df2.columns else [None] * df2.height
        bodies = df2[body_f].cast(pl.Utf8, strict=False).to_list() if body_f in df2.columns else [None] * df2.height
        atts = df2[att_f].cast(pl.Utf8, strict=False).to_list() if att_f in df2.columns else [None] * df2.height
        has_att_col = (df2["has_attachments"].to_list()
                       if "has_attachments" in df2.columns else [bool(a) for a in atts])

        flagged_idx: list[int] = []
        scores: list[PerRecordScore] = []
        by_domain: dict[str, int] = {}
        for i in range(df2.height):
            rcpts = _split(recipients[i])
            personal_rcpts = [r for r in rcpts if r.split("@")[-1] in personal]
            if not personal_rcpts:
                continue
            # Internal-to-internal noise guard: when the sender is already a
            # personal account (e.g. imported personal mailbox), still relevant
            # only if it talks to corporate content — keep it simple and flag.
            has_att = bool(has_att_col[i])
            text = " ".join(filter(None, [subjects[i], bodies[i], atts[i]])).lower()
            kw_hits = [k for k in keywords if k in text][:5]
            if require_att and not has_att:
                continue
            if require_kw and not kw_hits:
                continue

            score = 0.5
            reasons = [f"sent to personal account(s): {', '.join(personal_rcpts[:3])}"]
            if has_att:
                score += 0.2
                reasons.append("with attachment(s)")
            if kw_hits:
                score += 0.2
                reasons.append(f"sensitive keywords: {', '.join(kw_hits)}")
            if self_exfil:
                sender = (senders[i] or "").lower()
                own_tokens = set(
                    _name_tokens(sender_names[i]) + _name_tokens(custodians[i])
                    + ([_localpart(sender)] if sender else [])
                )
                for r in personal_rcpts:
                    lp = _localpart(r)
                    if any(
                        fuzz.partial_ratio(tok, lp) >= sim_threshold
                        for tok in own_tokens if tok
                    ):
                        score = 1.0
                        reasons.append(f"likely SELF-exfiltration → {r}")
                        break
            # corporate-origin check: leak only counts if sender is corporate
            # (or unknown). Personal→personal chat is lower signal.
            sender_dom = (senders[i] or "").split("@")[-1].lower()
            if corporate and sender_dom and sender_dom in personal:
                score = max(0.3, score - 0.3)
                reasons.append("(sender is also a personal account)")
            flagged_idx.append(i)
            scores.append(PerRecordScore(keys[i], min(score, 1.0), "; ".join(reasons)))
            for r in personal_rcpts:
                by_domain[r.split("@")[-1]] = by_domain.get(r.split("@")[-1], 0) + 1

        mask = pl.Series(values=[i in set(flagged_idx) for i in range(df2.height)])
        flagged = df2.filter(mask)
        return DetectorResult(
            flagged=flagged,
            summary={
                "flagged_count": flagged.height,
                "personal_domains_hit": dict(sorted(by_domain.items(), key=lambda x: -x[1])[:20]),
                "corporate_domains_inferred": sorted(corporate)[:10],
                "require_attachment": require_att,
                "require_keyword": require_kw,
            },
            per_record_scores=scores,
        )


@dataclass
class EmailCrossCustodianDetector:
    """Cross-mailbox patterns — needs ≥2 custodians (multiple PSTs merged).

    Finds external addresses that multiple employees both communicate with,
    which is the classic collusion / shared-conduit signal. Optionally limits
    to personal/free providers (the default — corporate counterparties writing
    to many employees is normal business).
    """
    name: str = "email_cross_custodian"
    category: DetectorCategory = DetectorCategory.RELATIONAL
    description: str = "Shared external contacts across multiple employee mailboxes"
    default_weight: float = 2.0
    default_params: dict[str, Any] = field(
        default_factory=lambda: {
            "custodian_field": "custodian",
            "recipient_field": "all_recipients",
            "sender_field": "sender_email",
            "min_custodians": 2,
            "personal_domains_only": True,
            "personal_domains": list(PERSONAL_EMAIL_DOMAINS),
            "min_messages": 2,
        }
    )
    supported_subledgers: list[SubledgerType] | None = field(
        default_factory=lambda: [SubledgerType.EMAIL, SubledgerType.OTHER]
    )

    def run(self, df: pl.DataFrame, params: dict[str, Any]) -> DetectorResult:
        cf = params.get("custodian_field", "custodian")
        rf = params.get("recipient_field", "all_recipients")
        sf = params.get("sender_field", "sender_email")
        min_cust = int(params.get("min_custodians", 2))
        min_msgs = int(params.get("min_messages", 2))
        personal_only = bool(params.get("personal_domains_only", True))
        personal = {d.lower() for d in (params.get("personal_domains") or PERSONAL_EMAIL_DOMAINS)}
        for needed in (cf, rf):
            if needed not in df.columns:
                return DetectorResult(flagged=df.head(0),
                                      summary={"flagged_count": 0, "reason": f"field_not_found:{needed}"})
        df2 = add_key_column(df)
        custodians = df2[cf].cast(pl.Utf8, strict=False).to_list()
        n_custodians = len({c for c in custodians if c})
        if n_custodians < min_cust:
            return DetectorResult(
                flagged=df.head(0),
                summary={"flagged_count": 0, "reason": "needs_multiple_custodians",
                         "custodians_found": n_custodians,
                         "hint": "Import 2+ PST files into one dataset to correlate employees."},
            )
        corporate = _infer_corporate_domains(df2)
        recipients = df2[rf].cast(pl.Utf8, strict=False).to_list()
        senders = (df2[sf].cast(pl.Utf8, strict=False).to_list()
                   if sf in df2.columns else [None] * df2.height)
        keys = df2["_record_key"].to_list()

        def _externals(i: int) -> list[str]:
            """External counterparties for row i, both directions."""
            out = []
            for a in _split(recipients[i]) + ([senders[i].lower()] if senders[i] else []):
                dom = a.split("@")[-1]
                if dom in corporate:
                    continue
                if personal_only and dom not in personal:
                    continue
                out.append(a)
            return out

        contact_custodians: dict[str, set[str]] = {}
        contact_msgs: dict[str, list[int]] = {}
        for i in range(df2.height):
            cust = custodians[i]
            if not cust:
                continue
            for addr in _externals(i):
                contact_custodians.setdefault(addr, set()).add(cust)
                contact_msgs.setdefault(addr, []).append(i)

        shared = {
            addr: custs for addr, custs in contact_custodians.items()
            if len(custs) >= min_cust and len(contact_msgs[addr]) >= min_msgs
        }
        flagged_idx: set[int] = set()
        reasons: dict[str, str] = {}
        for addr, custs in shared.items():
            for i in contact_msgs[addr]:
                flagged_idx.add(i)
                reasons.setdefault(
                    keys[i],
                    f"external contact {addr} appears in {len(custs)} mailboxes: "
                    f"{', '.join(sorted(custs))}",
                )
        mask = pl.Series(values=[i in flagged_idx for i in range(df2.height)])
        flagged = df2.filter(mask)
        scores = [
            PerRecordScore(k, 1.0, reasons.get(k, "shared external contact"))
            for k in flagged["_record_key"].to_list()
        ]
        shared_summary = sorted(
            (
                {"contact": addr, "custodians": sorted(custs),
                 "message_count": len(contact_msgs[addr])}
                for addr, custs in shared.items()
            ),
            key=lambda d: (-len(d["custodians"]), -d["message_count"]),
        )[:100]
        return DetectorResult(
            flagged=flagged,
            summary={
                "flagged_count": flagged.height,
                "custodians_found": n_custodians,
                "shared_contacts": shared_summary,
                "shared_contact_count": len(shared),
                "personal_domains_only": personal_only,
            },
            per_record_scores=scores,
        )


@dataclass
class EmailSearchDetector:
    """Parameterised mailbox search — the workhorse behind plain-English
    questions on email datasets ("find mails from X to gmail with attachments
    about pricing in March"). Every criterion is optional; criteria combine
    with AND, while the keyword list matches ANY (or ALL with match_all)."""
    name: str = "email_search"
    category: DetectorCategory = DetectorCategory.TEXT
    description: str = "Search mailbox dataset by sender/recipient/keywords/dates/attachments"
    default_weight: float = 0.5
    default_params: dict[str, Any] = field(
        default_factory=lambda: {
            "keywords": [],              # ANY of these in subject/body/attachment names
            "match_all_keywords": False,
            "sender_contains": "",
            "recipient_contains": "",     # substring OR domain (e.g. "gmail.com")
            "subject_contains": "",
            "custodian": "",
            "folder_contains": "",
            "date_from": "",             # YYYY-MM-DD
            "date_to": "",
            "has_attachments": None,      # true / false / null = any
            "attachment_name_contains": "",
            "after_hours_only": False,
            "external_only": False,       # recipient domain differs from sender's
            "regex": "",                 # applied to subject + body
            "case_sensitive": False,
        }
    )
    supported_subledgers: list[SubledgerType] | None = field(
        default_factory=lambda: [SubledgerType.EMAIL, SubledgerType.OTHER]
    )

    def run(self, df: pl.DataFrame, params: dict[str, Any]) -> DetectorResult:
        cs = bool(params.get("case_sensitive", False))

        def norm(s: str | None) -> str:
            s = s or ""
            return s if cs else s.lower()

        keywords = [norm(k) for k in (params.get("keywords") or []) if str(k).strip()]
        match_all = bool(params.get("match_all_keywords", False))
        sender_q = norm(str(params.get("sender_contains") or ""))
        rcpt_q = norm(str(params.get("recipient_contains") or ""))
        subj_q = norm(str(params.get("subject_contains") or ""))
        cust_q = norm(str(params.get("custodian") or ""))
        folder_q = norm(str(params.get("folder_contains") or ""))
        att_q = norm(str(params.get("attachment_name_contains") or ""))
        regex_q = str(params.get("regex") or "")
        has_att = params.get("has_attachments", None)
        after_hours = bool(params.get("after_hours_only", False))
        external_only = bool(params.get("external_only", False))
        date_from = str(params.get("date_from") or "")
        date_to = str(params.get("date_to") or "")

        rx = None
        if regex_q:
            try:
                rx = re.compile(regex_q, 0 if cs else re.IGNORECASE)
            except re.error as e:
                return DetectorResult(flagged=df.head(0),
                                      summary={"flagged_count": 0, "reason": f"bad_regex:{e}"})

        def parse_date(s: str) -> datetime | None:
            try:
                return datetime.combine(date.fromisoformat(s), datetime.min.time(),
                                        tzinfo=timezone.utc)
            except ValueError:
                return None

        dt_from = parse_date(date_from) if date_from else None
        dt_to = parse_date(date_to) if date_to else None

        df2 = add_key_column(df)

        def col(name: str) -> list:
            return (df2[name].cast(pl.Utf8, strict=False).to_list()
                    if name in df2.columns else [None] * df2.height)

        senders = col("sender_email")
        rcpts = col("all_recipients")
        subjects = col("subject")
        bodies = col("body_excerpt")
        custs = col("custodian")
        folders = col("folder")
        atts = col("attachment_names")
        sender_doms = col("sender_domain")
        rcpt_doms = col("recipient_domains")
        has_att_col = (df2["has_attachments"].to_list()
                       if "has_attachments" in df2.columns else [None] * df2.height)
        after_col = (df2["is_after_hours"].to_list()
                     if "is_after_hours" in df2.columns else [None] * df2.height)
        sent_col = (df2["sent_at"].to_list()
                    if "sent_at" in df2.columns else [None] * df2.height)
        keys = df2["_record_key"].to_list()

        flagged_idx: list[int] = []
        scores: list[PerRecordScore] = []
        for i in range(df2.height):
            crit_hits: list[str] = []
            if sender_q:
                if sender_q not in norm(senders[i]):
                    continue
                crit_hits.append(f"sender~{sender_q}")
            if rcpt_q:
                if rcpt_q not in norm(rcpts[i]) and rcpt_q not in norm(rcpt_doms[i]):
                    continue
                crit_hits.append(f"recipient~{rcpt_q}")
            if subj_q:
                if subj_q not in norm(subjects[i]):
                    continue
                crit_hits.append(f"subject~{subj_q}")
            if cust_q:
                if cust_q not in norm(custs[i]):
                    continue
                crit_hits.append(f"custodian~{cust_q}")
            if folder_q:
                if folder_q not in norm(folders[i]):
                    continue
                crit_hits.append(f"folder~{folder_q}")
            if att_q:
                if att_q not in norm(atts[i]):
                    continue
                crit_hits.append(f"attachment~{att_q}")
            if has_att is not None and bool(has_att) != bool(has_att_col[i]):
                continue
            if after_hours and not after_col[i]:
                continue
            if external_only:
                sd = (sender_doms[i] or "").lower()
                rds = _split(rcpt_doms[i])
                if not sd or not rds or all(rd == sd for rd in rds):
                    continue
                crit_hits.append("external")
            sent = sent_col[i]
            if dt_from or dt_to:
                if sent is None:
                    continue
                sent_cmp = sent if sent.tzinfo else sent.replace(tzinfo=timezone.utc)
                if dt_from and sent_cmp < dt_from:
                    continue
                if dt_to and sent_cmp > dt_to.replace(hour=23, minute=59, second=59):
                    continue
            text = " ".join(filter(None, [
                norm(subjects[i]), norm(bodies[i]), norm(atts[i]),
            ]))
            if keywords:
                hits = [k for k in keywords if k in text]
                if match_all and len(hits) != len(keywords):
                    continue
                if not match_all and not hits:
                    continue
                crit_hits.append(f"keywords: {', '.join(hits[:5])}")
            if rx:
                raw_text = " ".join(filter(None, [subjects[i], bodies[i]]))
                if not rx.search(raw_text):
                    continue
                crit_hits.append(f"regex:{regex_q}")
            if not (keywords or sender_q or rcpt_q or subj_q or cust_q or folder_q
                    or att_q or rx or has_att is not None or after_hours
                    or external_only or dt_from or dt_to):
                # No criteria at all — refuse to dump the whole mailbox.
                return DetectorResult(
                    flagged=df.head(0),
                    summary={"flagged_count": 0, "reason": "no_search_criteria"},
                )
            flagged_idx.append(i)
            scores.append(PerRecordScore(keys[i], 1.0,
                                         "matched " + ("; ".join(crit_hits) or "filters")))

        mask = pl.Series(values=[i in set(flagged_idx) for i in range(df2.height)])
        flagged = df2.filter(mask)
        return DetectorResult(
            flagged=flagged,
            summary={
                "flagged_count": flagged.height,
                "criteria": {
                    k: v for k, v in {
                        "keywords": keywords, "match_all_keywords": match_all,
                        "sender_contains": sender_q, "recipient_contains": rcpt_q,
                        "subject_contains": subj_q, "custodian": cust_q,
                        "folder_contains": folder_q, "date_from": date_from,
                        "date_to": date_to, "has_attachments": has_att,
                        "attachment_name_contains": att_q,
                        "after_hours_only": after_hours,
                        "external_only": external_only, "regex": regex_q,
                    }.items() if v not in ("", [], None, False)
                },
            },
            per_record_scores=scores,
        )


register(EmailDlpDetector())
register(EmailCrossCustodianDetector())
register(EmailSearchDetector())
