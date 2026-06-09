"""Email / PST ingestion — turns Outlook PST archives (and mbox / .eml zips)
into a flat, analysable dataset: one row per message.

Why flat rows? The whole platform is built around tabular detectors. By
normalising mailboxes into a message table we get every existing capability
(NLQ "Ask AI" search, templates, packs, ensemble scoring, findings, reports)
for free on email evidence.

Supported inputs
  - .pst / .ost   — requires `libpff-python` (import name `pypff`). Optional
                    native dependency; a clear error tells the operator how to
                    install it if missing.
  - .mbox         — Python stdlib, no extra deps.
  - .eml          — single message, stdlib.
  - .zip of .eml  — stdlib.

Multiple files can be merged into ONE dataset; each message keeps a
`custodian` column (defaults to the file stem, e.g. "j.smith.pst" → "j.smith")
so cross-employee pattern detectors can correlate mailboxes.
"""
from __future__ import annotations

import mailbox
import re
import uuid
import zipfile
from datetime import datetime, timezone
from email import policy
from email.message import Message
from email.parser import BytesParser, Parser
from email.utils import getaddresses, parsedate_to_datetime
from pathlib import Path
from typing import Any, Iterator

import polars as pl

EMAIL_RE = re.compile(r"[A-Za-z0-9._%+\-']+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")

# Free / personal mail providers used as the default "personal account" list.
# Detectors take this as an overridable parameter; this is the single source.
PERSONAL_EMAIL_DOMAINS = [
    "gmail.com", "googlemail.com", "yahoo.com", "yahoo.co.uk", "yahoo.co.in",
    "ymail.com", "hotmail.com", "hotmail.co.uk", "outlook.com", "live.com",
    "msn.com", "icloud.com", "me.com", "mac.com", "aol.com", "proton.me",
    "protonmail.com", "pm.me", "tutanota.com", "tuta.io", "zoho.com",
    "zohomail.com", "mail.com", "gmx.com", "gmx.net", "yandex.com",
    "yandex.ru", "rediffmail.com", "qq.com", "163.com", "126.com",
    "naver.com", "daum.net", "fastmail.com", "hushmail.com", "mail.ru",
]

BODY_EXCERPT_CHARS = 4000


class PstSupportMissing(RuntimeError):
    """Raised when a .pst is uploaded but libpff-python isn't installed."""


def _addr_list(value: str | None) -> list[str]:
    if not value:
        return []
    out = []
    for _name, addr in getaddresses([value]):
        addr = addr.strip().lower()
        if addr and EMAIL_RE.fullmatch(addr):
            out.append(addr)
    # getaddresses can miss malformed headers; regex as safety net
    if not out:
        out = [m.group(0).lower() for m in EMAIL_RE.finditer(value)]
    return list(dict.fromkeys(out))


def _domain(addr: str) -> str:
    return addr.rsplit("@", 1)[-1].lower() if "@" in addr else ""


def _to_utc(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _row(
    *,
    custodian: str,
    folder: str,
    message_id: str | None,
    in_reply_to: str | None,
    sent_at: datetime | None,
    sender_name: str | None,
    sender_email: str | None,
    to: list[str],
    cc: list[str],
    bcc: list[str],
    subject: str | None,
    body: str | None,
    attachment_names: list[str],
) -> dict[str, Any]:
    # Hour-of-day / weekend are judged in the sender's LOCAL time (the original
    # Date header offset), then sent_at is normalised to UTC for storage.
    # PST archives expose naive UTC timestamps, so local == UTC there.
    local = sent_at
    sent_at = _to_utc(sent_at)
    all_rcpt = list(dict.fromkeys([*to, *cc, *bcc]))
    rcpt_domains = sorted({_domain(a) for a in all_rcpt if _domain(a)})
    body = (body or "").strip()
    sender_email = (sender_email or "").lower()
    folder_l = folder.lower()
    direction = "SENT" if ("sent" in folder_l or "outbox" in folder_l) else "RECEIVED"
    hour = local.hour if local else None
    return {
        "custodian": custodian,
        "folder": folder,
        "direction": direction,
        "message_id": (message_id or "").strip() or None,
        "in_reply_to": (in_reply_to or "").strip() or None,
        "sent_at": sent_at,
        "sent_hour": hour,
        "is_after_hours": (hour is not None and (hour < 7 or hour >= 20)),
        "is_weekend": (local.weekday() >= 5) if local else False,
        "sender_name": (sender_name or "").strip() or None,
        "sender_email": sender_email or None,
        "sender_domain": _domain(sender_email) or None,
        "recipients_to": "; ".join(to) or None,
        "recipients_cc": "; ".join(cc) or None,
        "recipients_bcc": "; ".join(bcc) or None,
        "all_recipients": "; ".join(all_rcpt) or None,
        "recipient_domains": "; ".join(rcpt_domains) or None,
        "recipient_count": len(all_rcpt),
        "subject": (subject or "").strip() or None,
        "body_excerpt": body[:BODY_EXCERPT_CHARS] or None,
        "body_length": len(body),
        "attachment_count": len(attachment_names),
        "has_attachments": bool(attachment_names),
        "attachment_names": "; ".join(attachment_names) or None,
    }


# ---------------------------------------------------------------------------
# stdlib email.message.Message → row
# ---------------------------------------------------------------------------

def _message_body(msg: Message) -> str:
    parts: list[str] = []
    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_type() == "text/plain" and not part.get_filename():
                payload = part.get_payload(decode=True)
                if payload:
                    charset = part.get_content_charset() or "utf-8"
                    parts.append(payload.decode(charset, errors="replace"))
    else:
        payload = msg.get_payload(decode=True)
        if payload:
            charset = msg.get_content_charset() or "utf-8"
            parts.append(payload.decode(charset, errors="replace"))
    return "\n".join(parts)


def _message_attachments(msg: Message) -> list[str]:
    names = []
    if msg.is_multipart():
        for part in msg.walk():
            fn = part.get_filename()
            if fn:
                names.append(fn)
    return names


def _stdlib_msg_to_row(msg: Message, *, custodian: str, folder: str) -> dict[str, Any]:
    sent_at = None
    if msg.get("Date"):
        try:
            sent_at = parsedate_to_datetime(msg["Date"])
        except (TypeError, ValueError):
            sent_at = None
    senders = _addr_list(msg.get("From"))
    sender_name = None
    if msg.get("From"):
        pairs = getaddresses([msg.get("From")])
        if pairs:
            sender_name = pairs[0][0] or None
    return _row(
        custodian=custodian,
        folder=folder,
        message_id=msg.get("Message-ID"),
        in_reply_to=msg.get("In-Reply-To"),
        sent_at=sent_at,
        sender_name=sender_name,
        sender_email=senders[0] if senders else None,
        to=_addr_list(msg.get("To")),
        cc=_addr_list(msg.get("Cc")),
        bcc=_addr_list(msg.get("Bcc")),
        subject=msg.get("Subject"),
        body=_message_body(msg),
        attachment_names=_message_attachments(msg),
    )


# ---------------------------------------------------------------------------
# PST (pypff)
# ---------------------------------------------------------------------------

def _pst_rows(path: Path, custodian: str) -> Iterator[dict[str, Any]]:
    try:
        import pypff  # type: ignore[import-not-found]
    except ImportError as e:
        raise PstSupportMissing(
            "PST parsing requires the optional native library libpff. "
            "Install it with: pip install libpff-python  "
            "(or convert the PST to mbox with `readpst -o out/ file.pst` "
            "and upload the .mbox instead)."
        ) from e

    pst = pypff.file()
    pst.open(str(path))
    try:
        root = pst.get_root_folder()
        yield from _pst_walk(root, custodian, [])
    finally:
        pst.close()


def _pst_walk(folder, custodian: str, crumbs: list[str]) -> Iterator[dict[str, Any]]:
    name = folder.name or ""
    path_parts = [*crumbs, name] if name else crumbs
    folder_path = "/".join(p for p in path_parts if p)
    for i in range(folder.number_of_sub_messages):
        try:
            msg = folder.get_sub_message(i)
            yield _pst_message_to_row(msg, custodian=custodian, folder=folder_path)
        except Exception:  # noqa: BLE001 — one corrupt message must not kill the import
            continue
    for j in range(folder.number_of_sub_folders):
        yield from _pst_walk(folder.get_sub_folder(j), custodian, path_parts)


def _pst_message_to_row(msg, *, custodian: str, folder: str) -> dict[str, Any]:
    headers_raw = msg.transport_headers or ""
    hdr = Parser(policy=policy.default).parsestr(headers_raw, headersonly=True) if headers_raw else None

    senders = _addr_list(hdr.get("From")) if hdr else []
    sender_email = senders[0] if senders else None
    sender_name = msg.sender_name or None
    if not sender_name and hdr and hdr.get("From"):
        pairs = getaddresses([hdr.get("From")])
        if pairs:
            sender_name = pairs[0][0] or None

    body = msg.plain_text_body
    if isinstance(body, bytes):
        body = body.decode("utf-8", errors="replace")
    if not body:
        html = msg.html_body
        if isinstance(html, bytes):
            html = html.decode("utf-8", errors="replace")
        if html:
            body = re.sub(r"<[^>]+>", " ", html)

    attachment_names = []
    for k in range(msg.number_of_attachments):
        try:
            att = msg.get_attachment(k)
            att_name = getattr(att, "name", None) or f"attachment_{k}"
            attachment_names.append(att_name)
        except Exception:  # noqa: BLE001
            attachment_names.append(f"attachment_{k}")

    sent_at = msg.client_submit_time or msg.delivery_time
    return _row(
        custodian=custodian,
        folder=folder,
        message_id=hdr.get("Message-ID") if hdr else None,
        in_reply_to=hdr.get("In-Reply-To") if hdr else None,
        sent_at=sent_at,
        sender_name=sender_name,
        sender_email=sender_email,
        to=_addr_list(hdr.get("To")) if hdr else [],
        cc=_addr_list(hdr.get("Cc")) if hdr else [],
        bcc=_addr_list(hdr.get("Bcc")) if hdr else [],
        subject=msg.subject,
        body=body,
        attachment_names=attachment_names,
    )


# ---------------------------------------------------------------------------
# mbox / eml / zip-of-eml
# ---------------------------------------------------------------------------

def _mbox_rows(path: Path, custodian: str) -> Iterator[dict[str, Any]]:
    box = mailbox.mbox(str(path))
    try:
        for msg in box:
            try:
                yield _stdlib_msg_to_row(msg, custodian=custodian, folder="mbox")
            except Exception:  # noqa: BLE001
                continue
    finally:
        box.close()


def _eml_rows(path: Path, custodian: str) -> Iterator[dict[str, Any]]:
    with open(path, "rb") as f:
        msg = BytesParser(policy=policy.compat32).parse(f)
    yield _stdlib_msg_to_row(msg, custodian=custodian, folder="eml")


def _zip_rows(path: Path, custodian: str) -> Iterator[dict[str, Any]]:
    with zipfile.ZipFile(path) as zf:
        for info in zf.infolist():
            if info.is_dir() or not info.filename.lower().endswith(".eml"):
                continue
            try:
                msg = BytesParser(policy=policy.compat32).parsebytes(zf.read(info))
                folder = str(Path(info.filename).parent) or "zip"
                yield _stdlib_msg_to_row(msg, custodian=custodian, folder=folder)
            except Exception:  # noqa: BLE001
                continue


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

SUPPORTED_SUFFIXES = (".pst", ".ost", ".mbox", ".eml", ".zip")

_SCHEMA: dict[str, pl.DataType] = {
    "custodian": pl.Utf8, "folder": pl.Utf8, "direction": pl.Utf8,
    "message_id": pl.Utf8, "in_reply_to": pl.Utf8,
    "sent_at": pl.Datetime(time_zone="UTC"), "sent_hour": pl.Int64,
    "is_after_hours": pl.Boolean, "is_weekend": pl.Boolean,
    "sender_name": pl.Utf8, "sender_email": pl.Utf8, "sender_domain": pl.Utf8,
    "recipients_to": pl.Utf8, "recipients_cc": pl.Utf8, "recipients_bcc": pl.Utf8,
    "all_recipients": pl.Utf8, "recipient_domains": pl.Utf8,
    "recipient_count": pl.Int64, "subject": pl.Utf8,
    "body_excerpt": pl.Utf8, "body_length": pl.Int64,
    "attachment_count": pl.Int64, "has_attachments": pl.Boolean,
    "attachment_names": pl.Utf8,
}


def parse_mail_file(path: Path, *, custodian: str | None = None,
                    source_name: str | None = None) -> pl.DataFrame:
    """Parse one mailbox file into a message DataFrame.

    `source_name` is the original upload filename (the staged temp file has a
    random prefix); custodian defaults to its stem.
    """
    display = source_name or path.name
    cust = (custodian or Path(display).stem).strip()
    suffix = Path(display).suffix.lower() or path.suffix.lower()
    if suffix in (".pst", ".ost"):
        rows = list(_pst_rows(path, cust))
    elif suffix == ".mbox":
        rows = list(_mbox_rows(path, cust))
    elif suffix == ".eml":
        rows = list(_eml_rows(path, cust))
    elif suffix == ".zip":
        rows = list(_zip_rows(path, cust))
    else:
        raise ValueError(
            f"Unsupported mailbox format '{suffix}'. "
            f"Supported: {', '.join(SUPPORTED_SUFFIXES)}"
        )
    return pl.DataFrame(rows, schema=_SCHEMA)


def parse_mail_files(
    files: list[tuple[Path, str, str | None]],
) -> pl.DataFrame:
    """Parse and merge multiple mailbox files.

    `files` is a list of (staged_path, original_filename, custodian_override).
    """
    frames = [
        parse_mail_file(p, custodian=cust, source_name=orig)
        for (p, orig, cust) in files
    ]
    df = pl.concat(frames, how="vertical")
    return df.sort("sent_at", descending=False, nulls_last=True)


def write_merged_parquet(df: pl.DataFrame, staging_dir: Path) -> Path:
    """Persist the merged message table to a temp parquet for import_dataset."""
    staging_dir.mkdir(parents=True, exist_ok=True)
    out = staging_dir / f"email_{uuid.uuid4()}.parquet"
    df.write_parquet(out)
    return out
