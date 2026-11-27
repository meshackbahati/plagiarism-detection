"""
End-to-end: upload -> process -> results -> exports -> delete, against a
real PostgreSQL with pgvector. Set TEST_DATABASE_URL to run, e.g.
postgresql+asyncpg://user@localhost:5432/plagiarism_test
"""
import io
import json
import os
import zipfile

import pytest

pytestmark = pytest.mark.skipif(not os.getenv("TEST_DATABASE_URL"), reason="TEST_DATABASE_URL not set")

from tests.helpers import essay, make_docx, make_pdf  # noqa: E402


@pytest.fixture
async def client(tmp_path, monkeypatch):
    monkeypatch.setenv("UPLOAD_DIR", str(tmp_path / "uploads"))
    from httpx import ASGITransport, AsyncClient
    from sqlalchemy import text

    from app.api.v1 import routes
    from app.core.db import async_engine
    from app.core.schema import ensure_schema

    async with async_engine.begin() as conn:
        await conn.execute(text("DROP SCHEMA public CASCADE"))
        await conn.execute(text("CREATE SCHEMA public"))
    await ensure_schema(async_engine)
    # Run ensure_schema twice: upgrades must be idempotent.
    await ensure_schema(async_engine)

    queued = []
    monkeypatch.setattr(routes.process_batch, "delay", lambda *a, **kw: queued.append((a, kw)))

    from app.main import app

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        c.queued = queued
        yield c
    await async_engine.dispose()


async def _run_queued(client):
    from app.services.batch_processing import _process_batch_async

    while client.queued:
        args, kw = client.queued.pop(0)
        await _process_batch_async(args[0], kw.get("provider", "local"), kw.get("ai_threshold", 0.5))


async def _upload(client, files, options=None, text=None):
    data = {"options": json.dumps(options or {"provider": "local", "check_plagiarism": True, "check_ai": True})}
    if text:
        data["text"] = text
    r = await client.post("/api/v1/analyze", files=[("files", f) for f in files], data=data)
    assert r.status_code == 200, r.text
    return r.json()


async def test_full_pipeline(client):
    source = essay(10, 500)
    copied = " ".join(source.split()[50:200])
    student = essay(11, 150) + " " + copied + " " + essay(12, 100)

    zbuf = io.BytesIO()
    with zipfile.ZipFile(zbuf, "w") as z:
        z.writestr("class/student.docx", make_docx([student]))
        z.writestr("../escape.txt", "should be ignored")
        z.writestr("notes.exe", "ignored")
    files = [
        ("source & ref.pdf", make_pdf(source), "application/pdf"),
        ("submissions.zip", zbuf.getvalue(), "application/zip"),
        ("locked.pdf", make_pdf("secret " * 50, encrypt="pw"), "application/pdf"),
        ("dup.txt", b"same text " * 30, "text/plain"),
        ("dup copy.txt", b"same text " * 30, "text/plain"),
    ]
    resp = await _upload(client, files)
    assert resp["documents"] == 5
    assert resp["failed_documents"] == 1
    assert any("notes.exe" in s for s in resp["skipped"])
    batch_id = resp["batch_id"]

    await _run_queued(client)
    r = await client.get(f"/api/v1/batches/{batch_id}/results")
    body = r.json()
    assert body["batch"]["status"] == "completed_with_errors"
    assert body["batch"]["processed_docs"] == 5
    docs = {d["filename"]: d for d in body["data"]}

    locked = docs["locked.pdf"]
    assert locked["status"] == "failed" and "password" in locked["error"]

    stu = docs["submissions.zip/class/student.docx"]
    assert stu["status"] == "completed"
    assert stu["ai_analysis"]["label"]
    best = stu["plagiarism_analysis"][0]
    assert best["similar_document"] == "source & ref.pdf"
    assert best["cross_batch"] is False
    assert abs(best["similarity"] - 150 / 400) < 0.03  # 150 copied words of 400
    assert best["matches"][0]["type"] == "exact"
    assert best["matches"][0]["words"] >= 100

    dup = docs["dup.txt"]["plagiarism_analysis"][0]
    assert dup["similar_document"] == "dup copy.txt" and dup["similarity"] == 1.0

    # Exports
    pdf = await client.get(f"/api/v1/batches/{batch_id}/export/pdf")
    assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF")
    csv = await client.get(f"/api/v1/batches/{batch_id}/export/csv")
    assert "source & ref.pdf" in csv.text

    # Re-processing is idempotent (no duplicate comparisons).
    client.queued.append(((batch_id,), {}))
    await _run_queued(client)
    again = (await client.get(f"/api/v1/batches/{batch_id}/results")).json()
    again_stu = next(d for d in again["data"] if d["filename"].endswith("student.docx"))
    assert len(again_stu["plagiarism_analysis"]) == len(stu["plagiarism_analysis"])

    # Second batch copies from the first: cross-batch match.
    resp2 = await _upload(client, [], {"provider": "local", "check_plagiarism": True, "check_ai": False},
                          text=essay(13, 80) + " " + " ".join(source.split()[300:420]))
    await _run_queued(client)
    body2 = (await client.get(f"/api/v1/batches/{resp2['batch_id']}/results")).json()
    match = body2["data"][0]["plagiarism_analysis"][0]
    assert match["cross_batch"] is True and match["similar_document"] == "source & ref.pdf"
    assert body2["data"][0]["ai_analysis"]["label"] is None  # AI check was off

    # Listing
    listing = (await client.get("/api/v1/batches")).json()
    assert listing["total"] == 2
    assert listing["data"][0]["name"] == "Pasted text"

    # Delete
    d = await client.delete(f"/api/v1/batches/{batch_id}")
    assert d.status_code == 200 and d.json()["deleted_documents"] == 5
    assert (await client.get(f"/api/v1/batches/{batch_id}/results")).status_code == 404
    assert (await client.get("/api/v1/batches")).json()["total"] == 1


async def test_vector_candidate_query_runs(client):
    """The pgvector query used in full mode (was broken by ':embedding::vector')."""
    import uuid

    from sqlalchemy import update

    from app.core.db import AsyncSessionLocal
    from app.models import Batch, Document
    from app.services.plagiarism import PlagiarismService

    async with AsyncSessionLocal() as s:
        user_id = (await client.get("/api/v1/users/me")).json()["id"]
        old_batch, new_batch = uuid.uuid4(), uuid.uuid4()
        s.add_all([Batch(id=old_batch, user_id=user_id, status="completed"),
                   Batch(id=new_batch, user_id=user_id, status="processing")])
        await s.flush()
        vec = [0.0] * 384
        vec[0] = 1.0
        s.add(Document(id=uuid.uuid4(), batch_id=old_batch, filename="old.txt", text_content="old text",
                       status="completed", embedding=vec))
        await s.commit()
        cands = await PlagiarismService(s).cross_batch_candidates(str(new_batch), [vec], [])
        assert [c["filename"] for c in cands] == ["old.txt"]
        assert cands[0]["semantic"] is True


async def test_validation_errors(client):
    r = await client.post("/api/v1/analyze", data={"options": "{}"})
    assert r.status_code == 400
    r = await client.post("/api/v1/analyze", files=[("files", ("x.exe", b"MZ", "application/octet-stream"))],
                          data={"options": "{}"})
    assert r.status_code == 400 and "not a supported file type" in r.json()["detail"]
    r = await client.post("/api/v1/analyze", data={"text": "hello", "options": json.dumps({"provider": "openai"})})
    assert r.status_code == 400 and "OPENAI_API_KEY" in r.json()["detail"]
    r = await client.post("/api/v1/analyze", data={"text": "hello", "options": json.dumps({"check_ai": False, "check_plagiarism": False})})
    assert r.status_code == 400
