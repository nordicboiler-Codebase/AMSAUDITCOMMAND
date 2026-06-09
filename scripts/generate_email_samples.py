#!/usr/bin/env python3
"""Generate two sample mailbox files (mbox) with planted DLP / collusion signals.

Run:  python3 scripts/generate_email_samples.py
Writes samples/email_jsmith.mbox and samples/email_akhan.mbox.

Planted signals (so the EMAIL_INVESTIGATION pack lights up immediately):
  - j.smith forwards "Customer price list" with attachment to jsmith1984@gmail.com
    (self-exfiltration: localpart resembles sender)            → EM01/EM02/EM03
  - a.khan sends payroll extract to akhan.personal@yahoo.com   → EM01/EM02/EM03
  - BOTH custodians email rebatekickbacks@gmail.com            → EM04 (shared contact)
  - j.smith mails a competitor at 23:40                        → EM06 (after hours)
  - plenty of normal corporate traffic as background noise
"""
from __future__ import annotations

import mailbox
from email.message import EmailMessage
from pathlib import Path

SAMPLES = Path(__file__).resolve().parents[1] / "samples"

CORP = "nordicboiler.com"


def msg(frm: str, to: str, subject: str, body: str, date: str,
        cc: str = "", attachment: str = "") -> EmailMessage:
    m = EmailMessage()
    m["From"] = frm
    m["To"] = to
    if cc:
        m["Cc"] = cc
    m["Subject"] = subject
    m["Date"] = date
    m["Message-ID"] = f"<{abs(hash((frm, to, subject, date)))}@{CORP}>"
    m.set_content(body)
    if attachment:
        m.add_attachment(b"sample-bytes", maintype="application",
                         subtype="octet-stream", filename=attachment)
    return m


def build_jsmith() -> list[EmailMessage]:
    f = f"John Smith <j.smith@{CORP}>"
    return [
        msg(f, f"procurement@{CORP}", "PO 4471 approval",
            "Please approve PO 4471 for boiler plates.", "Mon, 02 Mar 2026 09:15:00 +0400"),
        msg(f, f"a.khan@{CORP}", "Q1 forecast review",
            "Numbers attached look fine, minor variance in line 4.",
            "Tue, 03 Mar 2026 11:02:00 +0400"),
        msg(f, "jsmith1984@gmail.com", "FW: Customer price list 2026",
            "Forwarding for weekend work. Keep confidential.",
            "Fri, 06 Mar 2026 18:55:00 +0400", attachment="customer_price_list_2026.xlsx"),
        msg(f, "rebatekickbacks@gmail.com", "March arrangement",
            "Same as last month. 2% on invoiced totals, settle via the usual route.",
            "Mon, 09 Mar 2026 21:30:00 +0400"),
        msg(f, "sales@rivalboilers.com", "Pricing discussion",
            "As discussed, our floor price for the GCC tender is 18% below list.",
            "Wed, 11 Mar 2026 23:40:00 +0400"),
        msg(f, f"hr@{CORP}", "Leave request",
            "Requesting annual leave 20-24 March.", "Thu, 12 Mar 2026 08:20:00 +0400"),
    ]


def build_akhan() -> list[EmailMessage]:
    f = f"Aisha Khan <a.khan@{CORP}>"
    return [
        msg(f, f"finance@{CORP}", "Trial balance Feb close",
            "TB attached for review.", "Mon, 02 Mar 2026 10:05:00 +0400",
            attachment="tb_feb_2026.xlsx"),
        msg(f, "akhan.personal@yahoo.com", "payroll extract",
            "Backing this up to my personal email just in case. Salary data for managers.",
            "Wed, 04 Mar 2026 19:45:00 +0400", attachment="payroll_mgrs_feb.csv"),
        msg(f, "rebatekickbacks@gmail.com", "Re: March arrangement",
            "Confirmed. Will route through the new vendor account.",
            "Tue, 10 Mar 2026 22:10:00 +0400"),
        msg(f, f"j.smith@{CORP}", "Re: Q1 forecast review",
            "Agreed, fixing line 4 today.", "Tue, 03 Mar 2026 12:30:00 +0400"),
        msg(f, f"it-helpdesk@{CORP}", "VPN token reset",
            "My VPN token expired, please reset.", "Thu, 05 Mar 2026 09:40:00 +0400"),
    ]


def write(name: str, messages: list[EmailMessage]) -> None:
    path = SAMPLES / name
    path.unlink(missing_ok=True)
    box = mailbox.mbox(str(path))
    try:
        for m in messages:
            box.add(mailbox.mboxMessage(m))
        box.flush()
    finally:
        box.close()
    print(f"wrote {path} ({path.stat().st_size} bytes, {len(messages)} messages)")


if __name__ == "__main__":
    write("email_jsmith.mbox", build_jsmith())
    write("email_akhan.mbox", build_akhan())
