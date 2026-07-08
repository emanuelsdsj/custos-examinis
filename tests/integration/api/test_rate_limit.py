from httpx import AsyncClient

from custos_examinis.config import get_settings


async def test_audit_submission_is_rate_limited_per_user(client: AsyncClient) -> None:
    limit = get_settings().audit_rate_limit_per_hour

    for _ in range(limit):
        response = await client.post("/audits/inline", json={"files": {"a.py": "x = 1\n"}})
        assert response.status_code == 202

    limited_response = await client.post("/audits/inline", json={"files": {"a.py": "x = 1\n"}})

    assert limited_response.status_code == 429
    assert "Retry-After" in limited_response.headers
