import json
from collections.abc import AsyncIterator

from redis.asyncio import Redis

from custos_examinis.jobs.store import JobStatus, JobStore

_HEARTBEAT_SECONDS = 15.0
_TERMINAL_STATUSES = {JobStatus.COMPLETED, JobStatus.FAILED}


def _format(event: str, data: dict[str, object]) -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


async def stream_audit_events(audit_id: str, store: JobStore, redis: Redis) -> AsyncIterator[str]:
    """Yields Server-Sent Events for one audit's progress until it finishes.

    Subscribes to the job's pub/sub channel *before* reading its stored
    snapshot, so an event published in the gap between those two steps is
    still captured by the subscription rather than lost. Node names already
    present in the snapshot are then replayed as `progress` events and
    tracked in `seen`, so the same completion reported both in the snapshot
    and, moments later, on the channel is only ever emitted once.
    """
    pubsub = redis.pubsub()
    await pubsub.subscribe(store.channel(audit_id))
    try:
        await pubsub.get_message(timeout=1.0)  # consume the subscribe acknowledgement

        job = await store.get(audit_id)
        if job is None:
            return

        seen: set[str] = set(job.progress)
        for node in job.progress:
            yield _format("progress", {"node": node})

        if job.status in _TERMINAL_STATUSES:
            yield _format("status", {"status": job.status.value, "error": job.error})
            return

        while True:
            message = await pubsub.get_message(
                ignore_subscribe_messages=True, timeout=_HEARTBEAT_SECONDS
            )
            if message is None:
                yield ": heartbeat\n\n"
                continue

            payload = json.loads(message["data"])
            if payload["type"] == "progress":
                node = payload["node"]
                if node in seen:
                    continue
                seen.add(node)
                yield _format("progress", {"node": node})
            elif payload["status"] in (JobStatus.COMPLETED.value, JobStatus.FAILED.value):
                yield _format("status", payload)
                return
    finally:
        await pubsub.unsubscribe(store.channel(audit_id))
        await pubsub.aclose()  # type: ignore[no-untyped-call]
