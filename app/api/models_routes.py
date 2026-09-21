"""Models on disk (#104): list, delete, and later import and pull as jobs."""

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.admin import models, service
from app.admin.jobs import Job, JobError, registry
from app.api.actor import current_actor
from app.api.deps import get_db_session
from app.api.errors import error_responses
from app.api.schemas import JobOut, ModelImportIn, ModelOut, ModelPullIn
from app.api.scopes import Scope, require
from app.api.status import _engine as engine_status
from app.config import get_settings
from app.db.session import session_scope

router = APIRouter()


@router.get(
    "/models",
    dependencies=[require(Scope.READ)],
    response_model=list[ModelOut],
    tags=["models"],
    responses=error_responses(409),
)
async def list_models() -> list[ModelOut]:
    """The models in the models directory, and which one the running engine has loaded."""
    installed = models.list_installed()
    loaded = (await engine_status()).model
    configured = get_settings().model_file
    return [
        ModelOut(**m, loaded=m["name"] == loaded, configured=m["name"] == configured)
        for m in installed
    ]


@router.delete(
    "/models/{name}",
    dependencies=[require(Scope.ADMIN)],
    status_code=status.HTTP_204_NO_CONTENT,
    tags=["models"],
    responses=error_responses(404, 409),
)
async def delete_model(name: str, session: AsyncSession = Depends(get_db_session)) -> None:
    """Delete a model file and its recorded hash; the loaded or configured model is refused."""
    result = models.delete_model(name, (await engine_status()).model)
    await service.record_admin_event(
        session,
        actor=current_actor(),
        action="model.delete",
        target_type="model",
        details=result,
    )
    await session.commit()


@router.post(
    "/models/import",
    dependencies=[require(Scope.ADMIN)],
    response_model=JobOut,
    status_code=status.HTTP_202_ACCEPTED,
    tags=["models"],
    responses=error_responses(409),
)
async def import_model(body: ModelImportIn) -> Job:
    """Copy a local GGUF file into the models directory. Returns the job doing it."""
    plan = models.prepare_import(body.path, body.name, body.force)
    models.claim(plan["name"])
    actor = current_actor()

    async def run(job: Job) -> dict:
        try:
            result = await models.run_import(job, plan)
        except OSError as exc:
            raise JobError(f"The copy failed: {exc.strerror or 'input/output error'}") from exc
        async with session_scope() as session:
            await service.record_admin_event(
                session,
                actor=actor,
                action="model.import",
                target_type="model",
                details=result,
            )
            await session.commit()
        return result

    job = registry.start("model-import", run)
    # Whatever ends the job, done, failed or cancelled, the name is free again.
    job.task.add_done_callback(lambda _task, name=plan["name"]: models.release(name))
    return job


@router.post(
    "/models/pull",
    dependencies=[require(Scope.ADMIN)],
    response_model=JobOut,
    status_code=status.HTTP_202_ACCEPTED,
    tags=["models"],
    responses=error_responses(409),
)
async def pull_model(body: ModelPullIn) -> Job:
    """Download a model from the hub (<repo>[:quant]) or an https URL. Returns the job."""
    plan = await models.prepare_pull(
        body.spec, body.name, body.sha256.lower() if body.sha256 else None, body.force
    )
    actor = current_actor()

    async def run(job: Job) -> dict:
        result = await models.run_pull(job, plan)
        async with session_scope() as session:
            await service.record_admin_event(
                session,
                actor=actor,
                action="model.pull",
                target_type="model",
                details=result,
            )
            await session.commit()
        return result

    return registry.start("model-pull", run)
