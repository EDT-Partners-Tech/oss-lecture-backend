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

import uuid
import json
import pytest
import asyncio
from database.schemas import PodcastStatus, PodcastUpdate

from tasks.pdf2podcast_task import process_generate_podcast, cleanup_s3_files

# Variables to capture DB update calls.
dummy_updates = {}

def dummy_update_podcast(db, podcast_id, podcast_update: PodcastUpdate):
    dummy_update_podcast_status(db, podcast_id, PodcastStatus.COMPLETED)
    dummy_updates[podcast_id] = dummy_updates.get(podcast_id, {})
    dummy_updates[podcast_id]["update"] = podcast_update

def dummy_update_podcast_status(db, podcast_id, status: PodcastStatus):
    dummy_updates[podcast_id] = dummy_updates.get(podcast_id, {})
    dummy_updates[podcast_id]["status"] = status

# Variables to capture generated S3 URIs.
audio_s3_uri, image_s3_uri = None, None

# Tear down fixture to cleanup any residual S3 files.
@pytest.fixture(autouse=True)
def clear_residual_s3_files():
    yield
    asyncio.run(cleanup_s3_files(audio_s3_uri, image_s3_uri))

# Minimal dummy DB session. We don't want to interfere with prod DB.
class DummyDB:
    def commit(self): 
        # Empty method mocking commit
        pass
    def refresh(self, obj):
        # Empty method mocking refresh
        pass
    def add(self, obj):
        # Empty method mocking add
        pass

@pytest.mark.integration
@pytest.mark.asyncio
async def test_process_generate_podcast_success(monkeypatch):
    # Prepare the correct environment variables
    global audio_s3_uri, image_s3_uri

    input_text = """Photosynthesis is the process through which plants, algae, and some bacteria convert sunlight into chemical energy.
    It takes place in the chloroplasts, where chlorophyll captures light energy. This energy is used to transform water and carbon 
    dioxide into glucose and oxygen. The oxygen is released into the atmosphere, supporting life on Earth. Photosynthesis is essential 
    for maintaining the balance of oxygen and carbon dioxide in the environment."""
    language = "english"
    podcast_id = uuid.uuid4()
    
    # Patch DB update calls.
    monkeypatch.setattr("tasks.pdf2podcast_task.update_podcast", dummy_update_podcast)
    monkeypatch.setattr("tasks.pdf2podcast_task.update_podcast_status", dummy_update_podcast_status)
    
    # Use a dummy DB instance
    dummy_db = DummyDB()
    
    # Call the integration task using real external services.
    await process_generate_podcast(input_text, language, dummy_db, podcast_id)
    
    # Validate that dummy_updates captured expected values.
    updated: PodcastUpdate = dummy_updates.get(podcast_id, {}).get("update")

    # First of all, populate s3 files for teardown.
    audio_s3_uri = updated.audio_s3_uri
    image_s3_uri = updated.image_s3_uri
    assert updated.audio_s3_uri is not None
    assert updated.image_s3_uri is not None

    # Check the other fields.
    assert updated is not None, "Podcast update was not recorded"
    assert updated.title != ""
    assert updated.dialog != ""
    try:
        json.loads(updated.dialog)
    except Exception as e:
        pytest.fail(f"Podcast dialogue is not a valid JSON. Error: {e}")
    assert updated.image_prompt != ""
    assert updated.completed_at is not None
    status = dummy_updates.get(podcast_id, {}).get("status")
    assert status == PodcastStatus.COMPLETED
