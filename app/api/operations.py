"""Jobs and backups (#109). Every long operation is a job: the route returns `202` and
the job, and `/jobs/{id}` says how it is going.
"""

import asyncio

from fastapi import APIRouter, status

from app.admin import service
from app.admin.jobs import Job, JobError, registry
from app.admin.restore import list_backups
from app.api.actor import current_actor
from app.api.errors import error_responses
from app.api.schemas import BackupOut, JobOut
from app.api.scopes import Scope, require
from app.config import get_settings
from app.db.backup import BackupError, make_backup
from app.db.session import session_scope, sqlite_file_path

router = APIRouter()


def _database_file():
    path = sqlite_file_path(get_settings().database_url)
    if path is None:
        raise service.ConflictError("Backups are only available for a SQLite database")
    return path


@router.get(
    "/jobs",
    dependencies=[require(Scope.ADMIN)],
    response_model=list[JobOut],
    tags=["jobs"],
    responses=error_responses(),
)
async def list_jobs() -> list[Job]:
    """The recent jobs, newest first."""
    return registry.list()


@router.get(
    "/jobs/{job_id}",
    dependencies=[require(Scope.ADMIN)],
    response_model=JobOut,
    tags=["jobs"],
    responses=error_responses(404),
)
async def get_job(job_id: str) -> Job:
    """One job: status, progress, result or error."""
    return registry.get(job_id)


@router.post(
    "/jobs/{job_id}/cancel",
    dependencies=[require(Scope.ADMIN)],
    response_model=JobOut,
    tags=["jobs"],
    responses=error_responses(404, 409),
)
async def cancel_job(job_id: str) -> Job:
    """Ask a running job to stop. A finished job cannot be cancelled (409)."""
    job = registry.cancel(job_id)
    await asyncio.sleep(0)  # let the cancellation reach the task before answering
    return job


@router.get(
    "/backups",
    dependencies=[require(Scope.ADMIN)],
    response_model=list[BackupOut],
    tags=["backups"],
    responses=error_responses(409),
)
async def list_database_backups() -> list[BackupOut]:
    """The backups of the database in `backups/`, newest first."""
    return [
        BackupOut(name=b.path.name, kind=b.kind, size_bytes=b.size, created_at=b.stamp)
        for b in list_backups(_database_file())
    ]


@router.post(
    "/backups",
    dependencies=[require(Scope.ADMIN)],
    response_model=JobOut,
    status_code=status.HTTP_202_ACCEPTED,
    tags=["backups"],
    responses=error_responses(409),
)
async def create_database_backup() -> Job:
    """Copy and verify the database into `backups/`. Returns the job doing it."""
    path = _database_file()
    actor = current_actor()

    async def run(job: Job) -> dict:
        job.update(0.1, "Copying the database")
        try:
            target = await asyncio.to_thread(make_backup, path, "manual")
        except BackupError as exc:
            raise JobError(str(exc)) from exc
        async with session_scope() as session:
            await service.record_admin_event(
                session,
                actor=actor,
                action="backup.create",
                target_type="backup",
                details={"name": target.name},
            )
            await session.commit()
        return {"name": target.name, "size_bytes": target.stat().st_size}

    return registry.start("backup", run)
