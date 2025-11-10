# © [2025] EDT&Partners. Licensed under CC BY 4.0.

import pytest
from fastapi import HTTPException
from tasks import pdf2podcast_task
from unittest.mock import AsyncMock

@pytest.mark.asyncio
async def test_cleanup_s3_files_both_present(monkeypatch):
    calls = []

    fake_delete_from_s3 = AsyncMock(side_effect=lambda bucket, uri: calls.append((bucket, uri)))

    monkeypatch.setattr(pdf2podcast_task, "delete_from_s3", fake_delete_from_s3)
    await pdf2podcast_task.cleanup_s3_files("s3://test_audio", "s3://test_image")
    assert calls == [("podcast", "s3://test_audio"), ("podcast", "s3://test_image")]

@pytest.mark.asyncio
async def test_cleanup_s3_files_audio_only(monkeypatch):
    calls = []

    async def fake_delete_from_s3(bucket, uri):
        calls.append((bucket, uri))

    monkeypatch.setattr(pdf2podcast_task, "delete_from_s3", fake_delete_from_s3)
    await pdf2podcast_task.cleanup_s3_files("s3://test_audio", "")
    assert calls == [("podcast", "s3://test_audio")]

@pytest.mark.asyncio
async def test_cleanup_s3_files_image_only(monkeypatch):
    calls = []

    async def fake_delete_from_s3(bucket, uri):
        calls.append((bucket, uri))

    monkeypatch.setattr(pdf2podcast_task, "delete_from_s3", fake_delete_from_s3)
    await pdf2podcast_task.cleanup_s3_files("", "s3://test_image")
    assert calls == [("podcast", "s3://test_image")]

@pytest.mark.asyncio
async def test_cleanup_s3_files_exception(monkeypatch):
    async def fake_delete_from_s3(bucket, uri):
        raise Exception("Fake deletion error")

    monkeypatch.setattr(pdf2podcast_task, "delete_from_s3", fake_delete_from_s3)
    with pytest.raises(HTTPException) as exc_info:
        await pdf2podcast_task.cleanup_s3_files("s3://test_audio", "s3://test_image")
    assert exc_info.value.status_code == 500