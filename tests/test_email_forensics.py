from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import polars as pl
import pytest


# ---------------------------------------------------------------------------
# Ingest (mbox — no native deps needed)
# ---------------------------------------------------------------------------

def _make_mbox(path: Path) -> None:
    import mailbox
    from email.message import EmailMessage

    box = mailbox.mbox(str(path))
    m1 = EmailMessage()
    m1["From"] = "John Smith <j.smith@corp.com>"
    m1["To"] = "jsmith1984@gmail.com"
    m1["Subject"] = "FW: customer price list"
    m1["Date"] = "Fri, 06 Mar 2026 18:55:00 +0400"
    m1.set_content("forwarding confidential data")
    m1.add_attachment(b"x", maintype="application", subtype="octet-stream",
                      filename="prices.xlsx")
    m2 = EmailMessage()
    m2["From"] = "vendor@supplier.com"
    m2["To"] = "j.smith@corp.com"
    m2["Cc"] = "a.khan@corp.com"
    m2["Subject"] = "Invoice 100"
    m2["Date"] = "Mon, 02 Mar 2026 09:00:00 +0400"
    m2.set_content("invoice attached")
    box.add(mailbox.mboxMessage(m1))
    box.add(mailbox.mboxMessage(m2))
    box.flush()
    box.close()


def test_mbox_ingest(tmp_path):
    from backend.services import email_ingest

    p = tmp_path / "jsmith.mbox"
    _make_mbox(p)
    df = email_ingest.parse_mail_file(p)
    assert df.height == 2
    assert df["custodian"].to_list() == ["jsmith", "jsmith"]
    row = df.filter(pl.col("subject").str.contains("price list")).to_dicts()[0]
    assert row["sender_email"] == "j.smith@corp.com"
    assert row["all_recipients"] == "jsmith1984@gmail.com"
    assert row["has_attachments"] is True
    assert "prices.xlsx" in row["attachment_names"]
    cc_row = df.filter(pl.col("subject") == "Invoice 100").to_dicts()[0]
    assert "a.khan@corp.com" in cc_row["all_recipients"]
    assert cc_row["recipient_count"] == 2


def test_merge_multiple_files_keeps_custodians(tmp_path):
    from backend.services import email_ingest

    p1 = tmp_path / "a.mbox"
    p2 = tmp_path / "b.mbox"
    _make_mbox(p1)
    _make_mbox(p2)
    df = email_ingest.parse_mail_files([
        (p1, "jsmith.mbox", None),
        (p2, "akhan.mbox", "aisha"),
    ])
    assert df.height == 4
    assert set(df["custodian"].to_list()) == {"jsmith", "aisha"}


def test_pst_missing_lib_message(tmp_path):
    from backend.services import email_ingest

    pypff_present = True
    try:
        import pypff  # noqa: F401
    except ImportError:
        pypff_present = False
    if pypff_present:
        pytest.skip("pypff installed — error path not reachable")
    p = tmp_path / "box.pst"
    p.write_bytes(b"not a real pst")
    with pytest.raises(email_ingest.PstSupportMissing, match="libpff-python"):
        email_ingest.parse_mail_file(p)


# ---------------------------------------------------------------------------
# Detectors
# ---------------------------------------------------------------------------

def _email_df() -> pl.DataFrame:
    def t(day: int, hour: int) -> datetime:
        return datetime(2026, 3, day, hour, 0, tzinfo=timezone.utc)

    rows = [
        # 0: leak — own gmail + attachment + keyword (self-exfil)
        dict(custodian="jsmith", sender_name="John Smith",
             sender_email="j.smith@corp.com", sender_domain="corp.com",
             all_recipients="jsmith1984@gmail.com", recipient_domains="gmail.com",
             subject="FW: customer price list", body_excerpt="confidential pricing",
             has_attachments=True, attachment_names="prices.xlsx",
             sent_at=t(6, 18), is_after_hours=False),
        # 1: normal internal
        dict(custodian="jsmith", sender_name="John Smith",
             sender_email="j.smith@corp.com", sender_domain="corp.com",
             all_recipients="a.khan@corp.com", recipient_domains="corp.com",
             subject="forecast", body_excerpt="see numbers",
             has_attachments=False, attachment_names=None,
             sent_at=t(3, 11), is_after_hours=False),
        # 2: shared external contact — jsmith side
        dict(custodian="jsmith", sender_name="John Smith",
             sender_email="j.smith@corp.com", sender_domain="corp.com",
             all_recipients="rebate@gmail.com", recipient_domains="gmail.com",
             subject="arrangement", body_excerpt="2 percent as usual",
             has_attachments=False, attachment_names=None,
             sent_at=t(9, 21), is_after_hours=True),
        # 3: shared external contact — akhan side
        dict(custodian="akhan", sender_name="Aisha Khan",
             sender_email="a.khan@corp.com", sender_domain="corp.com",
             all_recipients="rebate@gmail.com", recipient_domains="gmail.com",
             subject="re: arrangement", body_excerpt="confirmed",
             has_attachments=False, attachment_names=None,
             sent_at=t(10, 22), is_after_hours=True),
        # 4: akhan normal
        dict(custodian="akhan", sender_name="Aisha Khan",
             sender_email="a.khan@corp.com", sender_domain="corp.com",
             all_recipients="finance@corp.com", recipient_domains="corp.com",
             subject="trial balance", body_excerpt="tb attached",
             has_attachments=True, attachment_names="tb.xlsx",
             sent_at=t(2, 10), is_after_hours=False),
    ]
    for i, r in enumerate(rows):
        r.update(
            record_id=f"M{i}", folder="Sent Items", direction="SENT",
            message_id=f"<{i}@corp.com>", in_reply_to=None,
            sent_hour=r["sent_at"].hour, is_weekend=False,
            recipients_to=r["all_recipients"], recipients_cc=None,
            recipients_bcc=None, recipient_count=1,
            body_length=len(r["body_excerpt"]),
            attachment_count=1 if r["has_attachments"] else 0,
        )
    return pl.DataFrame(rows)


def test_email_dlp_flags_personal_and_self_exfil(detector_catalog):
    det = detector_catalog.get("email_dlp")
    res = det.run(_email_df(), det.default_params)
    assert res.summary["flagged_count"] == 3  # rows 0, 2, 3 hit personal gmail
    by_key = {s.record_key: s for s in res.per_record_scores}
    self_exfil = [s for s in res.per_record_scores if "SELF-exfiltration" in s.reason]
    assert len(self_exfil) == 1
    assert self_exfil[0].score == 1.0
    assert "corp.com" in res.summary["corporate_domains_inferred"]
    assert len(by_key) == 3


def test_email_dlp_require_attachment(detector_catalog):
    det = detector_catalog.get("email_dlp")
    params = {**det.default_params, "require_attachment": True}
    res = det.run(_email_df(), params)
    assert res.summary["flagged_count"] == 1  # only row 0 has attachment + personal


def test_email_cross_custodian_finds_shared_contact(detector_catalog):
    det = detector_catalog.get("email_cross_custodian")
    res = det.run(_email_df(), det.default_params)
    assert res.summary["flagged_count"] == 2  # rows 2 + 3
    shared = res.summary["shared_contacts"]
    assert shared[0]["contact"] == "rebate@gmail.com"
    assert set(shared[0]["custodians"]) == {"jsmith", "akhan"}


def test_email_cross_custodian_needs_two_mailboxes(detector_catalog):
    det = detector_catalog.get("email_cross_custodian")
    single = _email_df().filter(pl.col("custodian") == "jsmith")
    res = det.run(single, det.default_params)
    assert res.summary["flagged_count"] == 0
    assert res.summary["reason"] == "needs_multiple_custodians"


def test_email_search_combined_criteria(detector_catalog):
    det = detector_catalog.get("email_search")
    params = {**det.default_params,
              "keywords": ["price list"], "recipient_contains": "gmail.com",
              "has_attachments": True}
    res = det.run(_email_df(), params)
    assert res.summary["flagged_count"] == 1
    assert "price list" in res.per_record_scores[0].reason


def test_email_search_date_window_and_after_hours(detector_catalog):
    det = detector_catalog.get("email_search")
    params = {**det.default_params, "after_hours_only": True,
              "date_from": "2026-03-09", "date_to": "2026-03-10"}
    res = det.run(_email_df(), params)
    assert res.summary["flagged_count"] == 2  # rows 2 and 3


def test_email_search_refuses_empty_criteria(detector_catalog):
    det = detector_catalog.get("email_search")
    res = det.run(_email_df(), det.default_params)
    assert res.summary["flagged_count"] == 0
    assert res.summary["reason"] == "no_search_criteria"
