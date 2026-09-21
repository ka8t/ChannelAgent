import asyncio, imaplib, os, re, sqlite3, time
# Live run against the real mailbox: SP is a scratch directory (any temp directory).
TMP = os.environ["SP"]
os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{TMP}/live51.db"
os.environ["LLAMA_SERVER_URL"] = "http://127.0.0.1:1"
import app.channels.email as em
from app.config import get_settings
from app.db.models import Channel, ChannelIdentity, PermissionKind, User
from app.db.session import init_db, session_scope
from app.security.auth import grant_permission
from app.security.hashing import channel_identifier_key

s = get_settings()
SUBJECT = "[agent] live failure test (#51)"
touched: list[tuple] = []

class LoggedIMAP(imaplib.IMAP4_SSL):
    def uid(self, command, *args):
        r = super().uid(command, *args)
        if command.upper() in ("STORE", "MOVE", "COPY", "EXPUNGE"):
            touched.append((command.upper(), args[0].decode() if isinstance(args[0], bytes) else args[0]))
        return r
em.imaplib.IMAP4_SSL = LoggedIMAP
RealIMAP = imaplib.IMAP4_SSL.__mro__[1]   # untouched class for our own inspection

def inspect():
    im = RealIMAP(s.email_imap_host, s.email_imap_port, timeout=15); im.login(s.email_username, s.email_password)
    def st(box):
        typ, d = im.status(f'"{box}"', "(MESSAGES UNSEEN)")
        if typ != "OK": return None
        m = re.search(rb"MESSAGES (\d+) UNSEEN (\d+)", d[0]); return (int(m.group(1)), int(m.group(2)))
    out = {"INBOX": st("INBOX"), "INBOX.Agent": st("INBOX.Agent"), "INBOX.Agent.Failed": st("INBOX.Agent.Failed")}
    im.select("INBOX", readonly=True)
    typ, d = im.uid("SEARCH", "SUBJECT", '"live failure test"'); out["test mail in INBOX"] = [u.decode() for u in d[0].split()]
    typ, d = im.uid("SEARCH", "UNSEEN", "SUBJECT", '"live failure test"'); out["...of which unseen"] = [u.decode() for u in d[0].split()]
    found_failed = []
    if out["INBOX.Agent.Failed"] is not None:
        im.select("INBOX.Agent.Failed", readonly=True)
        typ, d = im.uid("SEARCH", "SUBJECT", '"live failure test"'); found_failed = [u.decode() for u in d[0].split()]
        typ, fl = im.uid("FETCH", d[0].split()[0], "(FLAGS)") if found_failed else (None, [b""])
        out["test mail flags in .Failed"] = re.findall(r"FLAGS \(([^)]*)\)", fl[0].decode()) if found_failed else None
    out["test mail in .Failed"] = found_failed
    im.logout(); return out

def rows():
    c = sqlite3.connect(f"{TMP}/live51.db"); r = c.execute("select direction, status from action_logs order by id").fetchall(); c.close(); return r

async def main():
    await init_db()
    addr = s.email_username
    async with session_scope() as sess:
        u = User(display_name="live #51 test"); sess.add(u); await sess.flush()
        ident = ChannelIdentity(user_id=u.id, channel=Channel.EMAIL, external_id=channel_identifier_key(Channel.EMAIL, addr), raw_address=addr)
        sess.add(ident); await sess.flush(); await grant_permission(sess, ident, PermissionKind.CHAT); await sess.commit()
    print("BASELINE          :", inspect())
    await asyncio.to_thread(em._send_reply_sync, addr, SUBJECT, "please answer, this is a live failure test")
    for _ in range(60):
        if inspect()["...of which unseen"]: break
        await asyncio.sleep(2)
    print("MAIL ARRIVED      :", {k: v for k, v in inspect().items() if k.startswith("test") or k.startswith("...")})
    for n in (1, 2, 3):
        await em._poll_once()
        i = inspect()
        print(f"AFTER POLL {n} (LLM down): unseen in INBOX={i['...of which unseen']} | in .Failed={i['test mail in .Failed']} | attempts={dict((k.decode(), v) for k, v in em._attempts.items())} | audit rows={rows()}")
    i = inspect(); print("FINAL             :", i)
    print("IMAP mutating commands issued by the adapter (command, uid):", touched)
asyncio.run(main())
