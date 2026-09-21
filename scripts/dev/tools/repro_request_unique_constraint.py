from cryptography.fernet import Fernet
import asyncio, os, tempfile
d=tempfile.mkdtemp()
os.environ.update(DATABASE_URL=f"sqlite+aiosqlite:///{d}/t.db", CHECKPOINT_DB_PATH=f"{d}/c.db", ENCRYPTION_KEY=Fernet.generate_key().decode(), MIGRATION_BACKUPS_KEEP="0")
from app.admin import service
from app.db.models import Channel
from app.db.session import init_db, session_scope
async def main():
    await init_db()
    async with session_scope() as s:
        r=await service.request_access(s, Channel.TELEGRAM,"9","hi"); await service.deny_request(s,r.id,resolved_by="api"); await s.commit()
    try:
        async with session_scope() as s:
            await service.request_access(s, Channel.TELEGRAM,"9","hi again"); await s.commit()
        print("second request accepted")
    except Exception as e:
        print("second request:", type(e).__name__)
asyncio.run(main())
