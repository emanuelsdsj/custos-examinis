from typing import Any, cast

from custos_examinis.domain.state import AuditState, initial_state
from custos_examinis.graph.build import build_audit_graph
from custos_examinis.ingest.models import FileSet
from custos_examinis.jobs.store import JobStore
from custos_examinis.llm.router import ModelRouter
from custos_examinis.logging import get_logger

logger = get_logger(__name__)


async def run_audit(
    audit_id: str,
    file_set: FileSet,
    router: ModelRouter,
    store: JobStore,
) -> None:
    await store.mark_running(audit_id)

    try:
        graph = build_audit_graph(router)
        final_state: AuditState | None = None
        async for event in graph.astream(
            initial_state(audit_id, file_set), stream_mode=["updates", "values"]
        ):
            mode, chunk = cast(tuple[str, Any], event)
            if mode == "updates":
                for node_name in chunk:
                    await store.append_progress(audit_id, node_name)
            else:
                final_state = cast(AuditState, chunk)
    except Exception as exc:  # noqa: BLE001 - surfaced to the caller via job status
        logger.error("audit_run_failed", audit_id=audit_id, error=str(exc))
        await store.mark_failed(audit_id, str(exc))
        return

    report = final_state.get("report") if final_state else None
    if report is None:
        await store.mark_failed(audit_id, "graph completed without producing a report")
        return

    await store.mark_completed(audit_id, report)
