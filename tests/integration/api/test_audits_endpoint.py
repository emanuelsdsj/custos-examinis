import io
import zipfile

from httpx import AsyncClient


async def test_submit_inline_audit_and_poll_until_completed(client: AsyncClient) -> None:
    submit_response = await client.post(
        "/audits/inline", json={"files": {"app.py": "print('hello')\n"}}
    )
    assert submit_response.status_code == 202
    audit_id = submit_response.json()["audit_id"]

    status_response = await client.get(f"/audits/{audit_id}")
    assert status_response.status_code == 200
    body = status_response.json()
    assert body["status"] == "completed"
    assert body["report"]["audit_id"] == audit_id


async def test_submit_zip_audit_is_accepted(client: AsyncClient) -> None:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("app.py", "print('hi')\n")

    response = await client.post(
        "/audits/zip",
        files={"file": ("sample.zip", buffer.getvalue(), "application/zip")},
    )

    assert response.status_code == 202


async def test_submit_inline_audit_rejects_path_traversal(client: AsyncClient) -> None:
    response = await client.post(
        "/audits/inline", json={"files": {"../../etc/passwd.py": "evil = True\n"}}
    )

    assert response.status_code == 400


async def test_get_audit_returns_404_for_unknown_id(client: AsyncClient) -> None:
    response = await client.get("/audits/does-not-exist")

    assert response.status_code == 404


async def test_get_audit_requires_authentication(client: AsyncClient) -> None:
    from custos_examinis.auth.jwt import get_current_user
    from custos_examinis.main import app

    del app.dependency_overrides[get_current_user]
    try:
        response = await client.get("/audits/some-id")
    finally:
        from tests.integration.api.conftest import TEST_USER

        app.dependency_overrides[get_current_user] = lambda: TEST_USER

    assert response.status_code == 401
