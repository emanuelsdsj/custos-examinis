import uuid
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, UploadFile, status

from custos_examinis.api.deps import enforce_audit_rate_limit, get_job_store, get_model_router
from custos_examinis.api.schemas import AuditStatusResponse, AuditSubmitResponse, InlineFilesRequest
from custos_examinis.auth.jwt import CurrentUser, get_current_user
from custos_examinis.config import Settings, get_settings
from custos_examinis.ingest.models import FileSet
from custos_examinis.ingest.sandbox import IngestionError
from custos_examinis.ingest.sources import from_inline_files, from_zip_bytes
from custos_examinis.jobs.runner import run_audit
from custos_examinis.jobs.store import JobStore
from custos_examinis.llm.router import ModelRouter

router = APIRouter(prefix="/audits", tags=["audits"])


async def _schedule(
    file_set: FileSet,
    user: CurrentUser,
    store: JobStore,
    model_router: ModelRouter,
    background_tasks: BackgroundTasks,
) -> AuditSubmitResponse:
    audit_id = str(uuid.uuid4())
    job = await store.create(audit_id, owner=user.subject)
    background_tasks.add_task(run_audit, audit_id, file_set, model_router, store)
    return AuditSubmitResponse(audit_id=audit_id, status=job.status)


@router.post(
    "/zip",
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(enforce_audit_rate_limit)],
)
async def submit_zip_audit(
    background_tasks: BackgroundTasks,
    file: UploadFile,
    user: Annotated[CurrentUser, Depends(get_current_user)],
    store: Annotated[JobStore, Depends(get_job_store)],
    model_router: Annotated[ModelRouter, Depends(get_model_router)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> AuditSubmitResponse:
    data = await file.read()
    try:
        file_set = from_zip_bytes(data, settings)
    except IngestionError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    return await _schedule(file_set, user, store, model_router, background_tasks)


@router.post(
    "/inline",
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(enforce_audit_rate_limit)],
)
async def submit_inline_audit(
    background_tasks: BackgroundTasks,
    payload: InlineFilesRequest,
    user: Annotated[CurrentUser, Depends(get_current_user)],
    store: Annotated[JobStore, Depends(get_job_store)],
    model_router: Annotated[ModelRouter, Depends(get_model_router)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> AuditSubmitResponse:
    try:
        file_set = from_inline_files(payload.files, settings)
    except IngestionError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    return await _schedule(file_set, user, store, model_router, background_tasks)


@router.get("/{audit_id}")
async def get_audit(
    audit_id: str,
    user: Annotated[CurrentUser, Depends(get_current_user)],
    store: Annotated[JobStore, Depends(get_job_store)],
) -> AuditStatusResponse:
    job = await store.get(audit_id)
    if job is None or job.owner != user.subject:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="audit not found")

    return AuditStatusResponse(
        audit_id=job.audit_id, status=job.status, report=job.report, error=job.error
    )
