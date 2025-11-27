# 
# Copyright 2025 EDT&Partners
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
# 

import json
import uuid
import pytest
from datetime import datetime
from fastapi import FastAPI
from fastapi.testclient import TestClient
from unittest.mock import MagicMock, AsyncMock, patch

# Import the router and dependencies from the podcast module
from routers import podcast
from routers.podcast import router, get_db
from utility.auth import oauth2_scheme
from database.schemas import PodcastStatus

# Create a test app with the podcast router.
app = FastAPI()
app.include_router(router)

@pytest.fixture(scope="function")
def client(mock_cognito_token_payload):
    app.dependency_overrides[get_db] = lambda: MagicMock()
    app.dependency_overrides[oauth2_scheme] = lambda: "fake-jwt-token"

    with patch("utility.auth.jose_jwt.get_unverified_claims") as mock_get_claims:
    
        mock_get_claims.return_value = {"cognito:username": "dummy_user_id"}

        mock_validator = AsyncMock()
        mock_validator.validate_token.return_value = mock_cognito_token_payload
    
        with patch.dict("utility.auth.VALIDATOR_MAP", {"cognito": mock_validator}):
            client = TestClient(app)
            yield client

    app.dependency_overrides.clear()

# --- Test: POST /generate ---
def test_pdf_to_podcast(client, monkeypatch):
    # Override functions called in the endpoint.
    async def fake_extract_text_from_pdf_async(path):
        return "extracted fake text"
    monkeypatch.setattr(podcast, "extract_text_from_pdf", fake_extract_text_from_pdf_async)

    dummy_podcast_id = uuid.uuid4()
    monkeypatch.setattr(podcast, "handle_save_request", lambda db, title, user_id, code: uuid.uuid4())
    monkeypatch.setattr(podcast, "save_podcast_to_db", lambda db, podcast_create: dummy_podcast_id)
    
    # Mock the background task to run synchronously
    async def fake_process_generate_podcast(**kwargs):
        pass
    monkeypatch.setattr(podcast, "process_generate_podcast", fake_process_generate_podcast)
    
    # Override get_user_by_cognito_id to return fake user object.
    FakeUser = type("FakeUser", (), {"id": "dummy_user_id"})
    monkeypatch.setattr(podcast, "get_user_by_cognito_id", lambda db, sub: FakeUser())
    
    # Mock the analytics function to avoid any real processing
    async def fake_process_analytics(**kwargs):
        pass
    monkeypatch.setattr(podcast, "process_and_save_analytics", fake_process_analytics)
    
    # Make a request with a dummy file.
    response = client.post(
        "/generate",
        files={"file": ("dummy.pdf", b"%PDF-1.4 dummy pdf content", "application/pdf")},
        data={"language": "english"}
    )
    assert response.status_code == 202
    data = response.json()
    assert data["podcast_id"] == str(dummy_podcast_id)
    assert data["status"] == PodcastStatus.PROCESSING

# --- Test: GET /status/{podcast_id} ---
def test_get_podcast_status(client, monkeypatch):
    monkeypatch.setattr(podcast, "get_podcast_status", lambda db, pid: PodcastStatus.COMPLETED)
    test_id = str(uuid.uuid4())
    response = client.get(f"/status/{test_id}")
    assert response.status_code == 200
    data = response.json()
    assert data["podcast_id"] == test_id
    assert data["status"] == PodcastStatus.COMPLETED

# --- Test: DELETE /{podcast_id} ---
def test_delete_podcast(client, monkeypatch):
    # Fake podcast to be deleted.
    FakePodcast = type("FakePodcast", (), {}) 
    fake_podcast = FakePodcast()
    fake_podcast.id = str(uuid.uuid4())  # assign a valid UUID
    fake_podcast.request_id = "dummy_request_id"
    fake_podcast.audio_s3_uri = "audio_to_delete"
    fake_podcast.image_s3_uri = "image_to_delete"
    fake_podcast.status = PodcastStatus.COMPLETED

    # Override required functions.
    monkeypatch.setattr(podcast, "get_podcast_details", lambda db, pid: fake_podcast)
    FakeRequest = type("FakeRequest", (), {"id": "dummy_request_id"})
    monkeypatch.setattr(podcast, "get_request_by_id", lambda db, rid, uid: FakeRequest())
    async def fake_delete_from_s3(bucket, key):
        pass
    monkeypatch.setattr(podcast, "delete_from_s3", fake_delete_from_s3)
    FakeUser = type("FakeUser", (), {"id": "dummy_user_id"})
    monkeypatch.setattr(podcast, "get_user_by_cognito_id", lambda db, sub: FakeUser())

    response = client.delete(f"/{fake_podcast.id}")
    # Expect a 204 No Content response.
    assert response.status_code == 204

# --- Additional tests for error cases ---

# Test: POST /generate missing file (should return 422)
def test_generate_missing_file(client):
    response = client.post("/generate", data={"language": "english"})
    assert response.status_code == 422

# Test: POST /generate with extraction error (should return 400)
def test_generate_extraction_error(client, monkeypatch):
    async def fake_extract_text_error(path):
        raise ValueError("Extraction error")
    monkeypatch.setattr(podcast, "extract_text_from_pdf", fake_extract_text_error)
    monkeypatch.setattr(podcast, "handle_save_request", lambda db, title, user_id, code: uuid.uuid4())
    monkeypatch.setattr(podcast, "save_podcast_to_db", lambda db, podcast_create: uuid.uuid4())
    response = client.post(
        "/generate",
        files={"file": ("dummy.pdf", b"dummy content", "application/pdf")},
        data={"language": "english"}
    )
    assert response.status_code == 400

# Test: GET /status/{podcast_id} when podcast not found (should return 404)
def test_get_status_not_found(client, monkeypatch):
    monkeypatch.setattr(podcast, "get_podcast_status", lambda db, pid: None)
    test_id = str(uuid.uuid4())
    response = client.get(f"/status/{test_id}")
    assert response.status_code == 404

# Test: GET /details/{podcast_id} when podcast not found (should return 404)
def test_get_details_not_found(client, monkeypatch):
    monkeypatch.setattr(podcast, "get_podcast_details", lambda db, pid: None)
    test_id = str(uuid.uuid4())
    response = client.get(f"/details/{test_id}")
    assert response.status_code == 404


# Test: DELETE /{podcast_id} when podcast not found (should return 404)
def test_delete_podcast_not_found(client, monkeypatch):
    monkeypatch.setattr(podcast, "get_podcast_details", lambda db, pid: None)
    test_id = str(uuid.uuid4())
    response = client.delete(f"/{test_id}")
    assert response.status_code == 404

# Test: DELETE /{podcast_id} when linked request is missing (should return 403)
def test_delete_podcast_no_linked_request(client, monkeypatch):
    FakePodcast = type("FakePodcast", (), {}) 
    fake_podcast = FakePodcast()
    fake_podcast.id = str(uuid.uuid4())
    fake_podcast.request_id = "dummy_request_id"
    fake_podcast.audio_s3_uri = "audio_to_delete"
    fake_podcast.image_s3_uri = "image_to_delete"
    fake_podcast.status = PodcastStatus.COMPLETED
    monkeypatch.setattr(podcast, "get_podcast_details", lambda db, pid: fake_podcast)
    # Simulate missing linked request
    monkeypatch.setattr(podcast, "get_request_by_id", lambda db, rid, uid: None)
    response = client.delete(f"/{fake_podcast.id}")
    assert response.status_code == 403
