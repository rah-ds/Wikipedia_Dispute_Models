#!/usr/bin/env python3
"""Lightweight email sender for SLURM job notifications.

Tries UVA relay (out.mail.virginia.edu:25) first, then falls back to
localhost sendmail.  Always exits 0 — notification failure must never
crash a data-collection job.

Usage:
    python send_email.py --to rah5ff@virginia.edu \
                         --subject "[Rivanna] fetch_full — 50% complete" \
                         --body "plain-text body here"

    # Or pipe the body via stdin:
    echo "body" | python send_email.py --to rah5ff@virginia.edu \
                                       --subject "subject"

Environment:
    NOTIFY_EMAIL  — default recipient (overridden by --to)
"""

from __future__ import annotations

import argparse
import os
import smtplib
import subprocess
import sys
from email.mime.text import MIMEText

# UVA mail relay discovered via Rivanna postfix config
_RELAY_HOST = "out.mail.virginia.edu"
_RELAY_PORT = 25
_SENDER = "rah5ff@virginia.edu"
_TIMEOUT = 15


def send_via_smtp(to: str, subject: str, body: str) -> bool:
    """Send via UVA SMTP relay — preferred method."""
    msg = MIMEText(body, "plain", "utf-8")
    msg["Subject"] = subject
    msg["From"] = _SENDER
    msg["To"] = to
    try:
        with smtplib.SMTP(_RELAY_HOST, _RELAY_PORT, timeout=_TIMEOUT) as s:
            s.sendmail(_SENDER, [to], msg.as_string())
        return True
    except Exception:
        return False


def send_via_sendmail(to: str, subject: str, body: str) -> bool:
    """Fallback: pipe through /usr/sbin/sendmail."""
    raw = f"Subject: {subject}\nFrom: {_SENDER}\nTo: {to}\n\n{body}\n"
    try:
        result = subprocess.run(
            ["/usr/sbin/sendmail", "-t"],
            input=raw.encode(),
            capture_output=True,
            timeout=_TIMEOUT,
        )
        return result.returncode == 0
    except Exception:
        return False


def send_email(to: str, subject: str, body: str) -> bool:
    """Try all available methods; return True if any succeeds."""
    if send_via_smtp(to, subject, body):
        return True
    if send_via_sendmail(to, subject, body):
        return True
    return False


def main() -> None:
    parser = argparse.ArgumentParser(description="Send email notification")
    parser.add_argument("--to", default=os.environ.get("NOTIFY_EMAIL", ""))
    parser.add_argument("--subject", required=True)
    parser.add_argument("--body", default=None, help="Body text (or pass via stdin)")
    args = parser.parse_args()

    to = args.to
    if not to:
        print("No recipient (set --to or NOTIFY_EMAIL)", file=sys.stderr)
        sys.exit(0)  # exit 0 — never crash the caller

    body = args.body if args.body is not None else sys.stdin.read()

    ok = send_email(to, args.subject, body)
    if ok:
        print(f"Email sent to {to}", file=sys.stderr)
    else:
        print(f"Email send failed (all methods) to {to}", file=sys.stderr)

    # Always exit 0
    sys.exit(0)


if __name__ == "__main__":
    main()
