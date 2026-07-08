from custos_examinis.domain.state import initial_state
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
        result = await graph.ainvoke(initial_state(audit_id, file_set))
    except Exception as exc:  # noqa: BLE001 - surfaced to the caller via job status
        logger.error("audit_run_failed", audit_id=audit_id, error=str(exc))
        await store.mark_failed(audit_id, str(exc))
        return

    report = result.get("report")
    if report is None:
        await store.mark_failed(audit_id, "graph completed without producing a report")
        return

    await store.mark_completed(audit_id, report)
