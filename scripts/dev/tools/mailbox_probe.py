"""Read-only snapshot for the live email checks (#61 check 4): message counts of the INBOX,
the tagged unseen mail, and the agent folder, plus the access requests and the audit-trail
rows of the real database. Credentials come from .env and are never printed. Nothing is
flagged, moved or written (EXAMINE / STATUS / SEARCH only, SQLite opened read-only).

Usage: PYTHONPATH=. .venv/bin/python scripts/dev/tools/mailbox_probe.py
"""
import imaplib
import sqlite3

from app.config import get_settings

s = get_settings()
imap = imaplib.IMAP4_SSL(s.email_imap_host, s.email_imap_port)
imap.login(s.email_username, s.email_password)
tag, folder = s.email_trigger_tag, s.email_agent_folder
typ, data = imap.select("INBOX", readonly=True)
print("INBOX messages:", int(data[0]))
typ, data = imap.search(None, "UNSEEN", "SUBJECT", f'"{tag}"')
print(f"INBOX unseen with subject containing {tag!r}:", len(data[0].split()))
typ, data = imap.status(f'"{folder}"', "(MESSAGES)")
print(f"{folder}:", data[0].decode() if typ == "OK" else "missing")
imap.logout()
con = sqlite3.connect("file:data/channelagent.db?mode=ro", uri=True)
print("access_requests:", con.execute("select id, channel, status from access_requests order by id").fetchall())
print("last action_logs:", con.execute("select id, channel, direction, status, created_at from action_logs order by id desc limit 3").fetchall())
