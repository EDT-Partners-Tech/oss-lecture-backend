# © [2025] EDT&Partners. Licensed under CC BY 4.0.

import pytest
from uuid import uuid4
from unittest.mock import MagicMock
from database.crud import (
    save_transcription_to_db,
    get_transcript_by_request_id,
    get_transcript_by_id,
    update_transcript_summary,
    save_analytics
)
from database.models import Transcript, Analytics

@pytest.fixture
def db():
    # Return a MagicMock representing the DB session.
    return MagicMock()

def test_save_transcription_to_db_success(db):
    # Simulate setting transcript id on refresh.
    def fake_refresh(transcript):
        transcript.id = uuid4()
    db.refresh.side_effect = fake_refresh

    job_name = "job123"
    s3_uri = "s3://bucket/uri"
    language_code = "en"
    status = "pending"
    request_id = 1

    new_transcript = save_transcription_to_db(db, job_name, s3_uri, language_code, status, request_id)
    # Verify that new transcript has an id assigned
    assert hasattr(new_transcript, "id")

def test_save_transcription_to_db_commit_failure(db):
    # Simulate commit failure when saving a transcription.
    def fake_refresh(transcript):
        transcript.id = uuid4()
    db.refresh.side_effect = fake_refresh
    db.commit.side_effect = Exception("Commit failed")
    
    with pytest.raises(Exception) as exc_info:
        save_transcription_to_db(db, "job_fail", "s3://fail/uri", "en", "pending", 1)
    assert "Commit failed" in str(exc_info.value)
    db.commit.side_effect = None  # Reset side effect

def test_get_transcript_by_request_id_success(db):
    # Prepare a dummy transcript to be returned.
    dummy_transcript = MagicMock(spec=Transcript)
    dummy_transcript.job_name = "job123"
    dummy_transcript.s3_uri = "s3://bucket/uri"
    # Configure query chain to return the dummy transcript.
    db.query.return_value.filter.return_value.first.return_value = dummy_transcript

    result = get_transcript_by_request_id(db, request_id=uuid4())
    assert result is dummy_transcript

def test_get_transcript_by_request_id_none(db):
    # Simulate no transcript found.
    db.query.return_value.filter.return_value.first.return_value = None
    result = get_transcript_by_request_id(db, request_id=uuid4())
    assert result is None

def test_get_transcript_by_id_success(db):
    dummy_transcript = MagicMock(spec=Transcript)
    dummy_transcript.id = uuid4()
    # Configure the query chain.
    db.query.return_value.filter.return_value.first.return_value = dummy_transcript

    result = get_transcript_by_id(db, dummy_transcript.id)
    assert result is dummy_transcript

def test_get_transcript_by_id_none(db):
    # Simulate no transcript found by id.
    db.query.return_value.filter.return_value.first.return_value = None
    result = get_transcript_by_id(db, uuid4())
    assert result is None

def test_update_transcript_summary_success(db):
    # Prepare a dummy transcript with initial summary.
    dummy_transcript = MagicMock(spec=Transcript)
    dummy_transcript.id = uuid4()
    dummy_transcript.summary = "Old summary"
    # Setup db query chain.
    db.query.return_value.filter.return_value.first.return_value = dummy_transcript

    new_summary = "New updated summary"
    updated_transcript = update_transcript_summary(db, transcript_id=dummy_transcript.id, summary=new_summary)
    assert updated_transcript.summary == new_summary

def test_update_transcript_summary_not_found(db):
    # Simulate transcript not found.
    db.query.return_value.filter.return_value.first.return_value = None
    result = update_transcript_summary(db, transcript_id=uuid4(), summary="Does not matter")
    assert result is None

def test_update_transcript_summary_commit_failure(db):
    # Setup a dummy transcript to update.
    dummy_transcript = MagicMock(spec=Transcript)
    dummy_transcript.id = uuid4()
    dummy_transcript.summary = "Old summary"
    db.query.return_value.filter.return_value.first.return_value = dummy_transcript
    # Simulate failure during commit in update.
    db.commit.side_effect = Exception("Update commit failed")
    
    with pytest.raises(Exception) as exc_info:
        update_transcript_summary(db, transcript_id=dummy_transcript.id, summary="New summary")
    assert "Update commit failed" in str(exc_info.value)
    db.commit.side_effect = None