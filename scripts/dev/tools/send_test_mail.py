"""Sends one tagged test mail through the mailbox's own SMTP account (credentials from .env,
never printed), to the mailbox itself. The sender is the bot's own address, which is not a
registered user: used for the live check of an unknown tagged sender (#61 check 4).

Usage: PYTHONPATH=. .venv/bin/python scripts/dev/tools/send_test_mail.py "body text" [from-header]
"""
import smtplib
import sys
from email.mime.text import MIMEText

from app.config import get_settings

s = get_settings()
msg = MIMEText(sys.argv[1] if len(sys.argv) > 1 else "test")
msg["Subject"] = f"{s.email_trigger_tag} test"
# Optional second argument: a different From header (envelope sender stays the account), to
# play an unknown external sender.
msg["From"] = sys.argv[2] if len(sys.argv) > 2 else s.email_username
msg["To"] = s.email_username
with smtplib.SMTP_SSL(s.email_smtp_host, s.email_smtp_port, timeout=15) as smtp:
    smtp.login(s.email_username, s.email_password)
    smtp.send_message(msg, from_addr=s.email_username, to_addrs=[s.email_username])
print("sent: subject", repr(msg["Subject"]), "| header From is the mailbox address:", msg["From"] == s.email_username)
