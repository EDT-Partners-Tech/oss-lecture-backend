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

# --- Test: GET /details/{podcast_id} ---
def test_get_podcast_details(client, monkeypatch):
    # Create a fake podcast object with needed attributes.
    FakePodcast = type("FakePodcast", (), {})  # simple dynamic object
    fake_podcast = FakePodcast()
    fake_podcast.id = str(uuid.uuid4())  # use a valid UUID string
    fake_podcast.request_id = "dummy_request_id"
    fake_podcast.title = "Fake Podcast"
    fake_podcast.dialog = json.dumps(["line 1", "line 2"])
    fake_podcast.audio_s3_uri = "dummy_audio"
    fake_podcast.image_s3_uri = "dummy_image"
    fake_podcast.status = PodcastStatus.COMPLETED
    
    monkeypatch.setattr(podcast, "get_podcast_details", lambda db, pid: fake_podcast)
    # get_request_by_id should return a dummy request to allow access.
    FakeRequest = type("FakeRequest", (), {"id": "dummy_request_id"})
    monkeypatch.setattr(podcast, "get_request_by_id", lambda db, rid, uid: FakeRequest())
    # Override functions generating URLs.
    monkeypatch.setattr(podcast, "generate_presigned_url", lambda bucket, key: f"https://fakeurl/{key}")
    FakeUser = type("FakeUser", (), {"id": "dummy_user_id"})
    monkeypatch.setattr(podcast, "get_user_by_cognito_id", lambda db, sub: FakeUser())
    
    test_id = fake_podcast.id  # use the valid UUID
    response = client.get(f"/details/{test_id}")
    assert response.status_code == 200
    data = response.json()
    assert data["title"] == "Fake Podcast"
    assert data["audioUrl"] == "https://fakeurl/dummy_audio"
    assert data["imageUrl"] == "https://fakeurl/dummy_image"
    assert data["dialog"] == ["line 1", "line 2"]

# --- Test: GET /history ---
def test_podcast_history(client, monkeypatch):
    # Fake request and podcast objects.
    FakeRequest = type("FakeRequest", (), {"id": "dummy_request_id"})
    monkeypatch.setattr(podcast, "get_requests_by_user_service", lambda db, uid, sid: [FakeRequest()])
    
    FakePodcast = type("FakePodcast", (), {}) 
    fake_podcast = FakePodcast()
    fake_podcast.id = "dummy_podcast_id"
    fake_podcast.title = "History Podcast"
    fake_podcast.audio_s3_uri = "audio_history"
    fake_podcast.image_s3_uri = "image_history"
    fake_podcast.completed_at = datetime(2023, 10, 10)
    fake_podcast.status = PodcastStatus.COMPLETED
    monkeypatch.setattr(podcast, "find_podcast_by_request_id", lambda db, rid: fake_podcast)
    # Override get_user_by_cognito_id and presigned URL generator.
    FakeUser = type("FakeUser", (), {"id": "dummy_user_id"})
    monkeypatch.setattr(podcast, "get_user_by_cognito_id", lambda db, sub: FakeUser())
    monkeypatch.setattr(podcast, "get_service_id_by_code", lambda db, code: "dummy_service_id")
    monkeypatch.setattr(podcast, "generate_presigned_url", lambda bucket, key: f"https://fakeurl/{key}")
    
    response = client.get("/history")
    assert response.status_code == 200
    data = response.json()
    assert "data" in data
    assert len(data["data"]) >= 1
    item = data["data"][0]
    assert item["id"] == "dummy_podcast_id"
    assert item["title"] == "History Podcast"
    assert item["audioUrl"] == "https://fakeurl/audio_history"
    assert item["imageUrl"] == "https://fakeurl/image_history"

# --- Test: GET /history with multiple podcasts ---
def test_podcast_history_multiple(client, monkeypatch):
    # Create fake request objects with unique ids.
    FakeRequest = type("FakeRequest", (), {})
    req1 = FakeRequest(); req1.id = "req1"
    req2 = FakeRequest(); req2.id = "req2"
    req3 = FakeRequest(); req3.id = "req3"
    requests = [req1, req2, req3]
    monkeypatch.setattr(podcast, "get_requests_by_user_service", lambda db, uid, sid: requests)
    
    # Create fake podcast objects with varying statuses.
    FakePodcast = type("FakePodcast", (), {})  
    podcast1 = FakePodcast()
    podcast1.id = "pod1"
    podcast1.title = "Completed Podcast"
    podcast1.audio_s3_uri = "audio1"
    podcast1.image_s3_uri = "image1"
    podcast1.completed_at = datetime(2023, 10, 10)
    podcast1.status = PodcastStatus.COMPLETED

    podcast2 = FakePodcast()
    podcast2.id = "pod2"
    podcast2.title = "Failed Podcast"
    podcast2.audio_s3_uri = "audio2"
    podcast2.image_s3_uri = "image2"
    podcast2.completed_at = datetime(2023, 9, 9)
    # Use a non-COMPLETED status (e.g., PROCESSING)
    podcast2.status = PodcastStatus.PROCESSING

    podcast3 = FakePodcast()
    podcast3.id = "pod3"
    podcast3.title = ""
    podcast3.audio_s3_uri = None
    podcast3.image_s3_uri = None
    podcast3.completed_at = datetime(2023, 8, 8)
    # Use a non-COMPLETED status (e.g., ERROR)
    podcast3.status = PodcastStatus.ERROR

    # Map request ids to fake podcasts.
    fake_podcasts = {"req1": podcast1, "req2": podcast2, "req3": podcast3}
    monkeypatch.setattr(podcast, "find_podcast_by_request_id", lambda db, rid: fake_podcasts.get(rid))
    # Override URL generator for consistency.
    monkeypatch.setattr(podcast, "generate_presigned_url", lambda bucket, key: f"https://fakeurl/{key}")
    # Override get_user_by_cognito_id and service id.
    FakeUser = type("FakeUser", (), {"id": "dummy_user_id"})
    monkeypatch.setattr(podcast, "get_user_by_cognito_id", lambda db, sub: FakeUser())
    monkeypatch.setattr(podcast, "get_service_id_by_code", lambda db, code: "dummy_service_id")
    
    response = client.get("/history")
    assert response.status_code == 200
    data = response.json()
    assert "data" in data
    assert len(data["data"]) == 3
    assert len([item for item in data["data"] if item["status"] == PodcastStatus.COMPLETED]) == 1
    item = data["data"][0]
    assert item["id"] == "pod1"
    assert item["title"] == "Completed Podcast"
    assert item["audioUrl"] == "https://fakeurl/audio1"
    assert item["imageUrl"] == "https://fakeurl/image1"

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

# Test: GET /details/{podcast_id} when podcast not completed (should return 400)
def test_get_details_not_completed(client, monkeypatch):
    FakePodcast = type("FakePodcast", (), {})  
    fake_podcast = FakePodcast()
    fake_podcast.id = str(uuid.uuid4())
    fake_podcast.request_id = "dummy_request_id"
    fake_podcast.status = PodcastStatus.PROCESSING  # Not completed
    monkeypatch.setattr(podcast, "get_podcast_details", lambda db, pid: fake_podcast)
    # get_request_by_id returns a valid request to bypass access check
    FakeRequest = type("FakeRequest", (), {"id": "dummy_request_id"})
    monkeypatch.setattr(podcast, "get_request_by_id", lambda db, rid, uid: FakeRequest())
    response = client.get(f"/details/{fake_podcast.id}")
    assert response.status_code == 400

# Test: GET /details/{podcast_id} when linked request is missing (should return 403)
def test_get_details_no_linked_request(client, monkeypatch):
    FakePodcast = type("FakePodcast", (), {})  
    fake_podcast = FakePodcast()
    fake_podcast.id = str(uuid.uuid4())
    fake_podcast.request_id = "dummy_request_id"
    fake_podcast.status = PodcastStatus.COMPLETED
    monkeypatch.setattr(podcast, "get_podcast_details", lambda db, pid: fake_podcast)
    # Simulate missing linked request
    monkeypatch.setattr(podcast, "get_request_by_id", lambda db, rid, uid: None)
    response = client.get(f"/details/{fake_podcast.id}")
    assert response.status_code == 403

# Test: GET /history when no requests are found (should return 404)
def test_history_no_requests(client, monkeypatch):
    # Configure user and service
    FakeUser = type("FakeUser", (), {"id": "dummy_user_id"})
    monkeypatch.setattr(podcast, "get_user_by_cognito_id", lambda db, sub: FakeUser())
    monkeypatch.setattr(podcast, "get_service_id_by_code", lambda db, code: "dummy_service_id")
    # Simulate no requests by returning None
    monkeypatch.setattr(podcast, "get_requests_by_user_service", lambda db, uid, sid: None)
    response = client.get("/history")
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
