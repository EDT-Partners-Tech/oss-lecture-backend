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

import pytest
from uuid import uuid4
from datetime import datetime
from unittest.mock import MagicMock

from database.crud import (
    save_podcast_to_db,
    update_podcast,
    update_podcast_status,
    get_podcast_status,
    get_podcast_details,
    find_podcast_by_request_id
)
from database.schemas import PodcastCreate, PodcastUpdate, PodcastStatus


# Patch refresh to assign an id if missing.
@pytest.fixture
def db_session():
    session = MagicMock()
    def fake_refresh(instance):
        if not getattr(instance, "id", None):
            instance.id = str(uuid4())
    session.refresh.side_effect = fake_refresh
    return session

def test_save_podcast_to_db(db_session):
    podcast_create = PodcastCreate(language="en", request_id=str(uuid4()))
    new_id = save_podcast_to_db(db_session, podcast_create)
    # The patched refresh should have assigned an id:
    assert new_id is not None
    db_session.add.assert_called()

def test_save_podcast_to_db_commit_error(db_session):
    # Simulate exception on commit.
    podcast_create = PodcastCreate(language="en", request_id=str(uuid4()))
    db_session.commit.side_effect = Exception("Commit error")
    with pytest.raises(Exception) as exc_info:
        save_podcast_to_db(db_session, podcast_create)
    assert "Commit error" in str(exc_info.value)
    db_session.commit.side_effect = None  # Reset side effect for subsequent tests

def test_update_podcast(db_session):
    podcast_id = str(uuid4())
    fake_podcast = MagicMock()
    fake_podcast.id = podcast_id
    fake_podcast.status = PodcastStatus.PROCESSING
    # Setup the query chain.
    db_session.query.return_value.filter.return_value.first.return_value = fake_podcast
    
    podcast_update = PodcastUpdate(
        title="New Title",
        dialog="Dialog content",
        audio_s3_uri="s3://audio.mp3",
        image_s3_uri="s3://image.jpg",
        image_prompt="Prompt",
        completed_at=datetime(2023, 10, 10)
    )
    update_podcast(db_session, podcast_id, podcast_update)
    
    assert fake_podcast.title == "New Title"
    assert fake_podcast.dialog == "Dialog content"
    assert fake_podcast.audio_s3_uri == "s3://audio.mp3"
    assert fake_podcast.image_s3_uri == "s3://image.jpg"
    assert fake_podcast.image_prompt == "Prompt"
    assert fake_podcast.completed_at == datetime(2023, 10, 10)
    assert fake_podcast.status == PodcastStatus.COMPLETED

def test_update_podcast_not_found(db_session):
    podcast_id = str(uuid4())
    # Configure query chain to return None, simulating missing podcast.
    db_session.query.return_value.filter.return_value.first.return_value = None
    podcast_update = PodcastUpdate(
        title="Nonexistent", dialog="No dialog", audio_s3_uri="",
        image_s3_uri="", image_prompt="None", completed_at=datetime(2023, 10, 10)
    )
    with pytest.raises(ValueError) as exc_info:
        update_podcast(db_session, podcast_id, podcast_update)
    assert f"Podcast with ID {podcast_id} not found." in str(exc_info.value)

def test_update_podcast_status(db_session):
    podcast_id = str(uuid4())
    fake_podcast = MagicMock()
    fake_podcast.status = PodcastStatus.PROCESSING
    db_session.query.return_value.filter.return_value.first.return_value = fake_podcast
    update_podcast_status(db_session, podcast_id, PodcastStatus.ERROR)
    assert fake_podcast.status == PodcastStatus.ERROR

def test_update_podcast_status_not_found(db_session):
    podcast_id = str(uuid4())
    db_session.query.return_value.filter.return_value.first.return_value = None
    with pytest.raises(ValueError) as exc_info:
        update_podcast_status(db_session, podcast_id, PodcastStatus.ERROR)
    assert f"Podcast with ID {podcast_id} not found." in str(exc_info.value)

def test_get_podcast_status(db_session):
    podcast_id = str(uuid4())
    fake_podcast = MagicMock()
    fake_podcast.status = PodcastStatus.PROCESSING
    db_session.query.return_value.filter.return_value.first.return_value = fake_podcast
    status = get_podcast_status(db_session, podcast_id)
    assert status == PodcastStatus.PROCESSING

def test_get_podcast_status_not_found(db_session):
    podcast_id = str(uuid4())
    db_session.query.return_value.filter.return_value.first.return_value = None
    with pytest.raises(ValueError) as exc_info:
        get_podcast_status(db_session, podcast_id)
    assert f"Podcast with ID {podcast_id} not found." in str(exc_info.value)

def test_get_podcast_details(db_session):
    podcast_id = str(uuid4())
    fake_podcast = MagicMock()
    fake_podcast.id = podcast_id
    fake_podcast.title = "Test"
    db_session.query.return_value.filter.return_value.first.return_value = fake_podcast
    details = get_podcast_details(db_session, podcast_id)
    assert details.id == podcast_id
    assert details.title == "Test"

def test_get_podcast_details_not_found(db_session):
    podcast_id = str(uuid4())
    db_session.query.return_value.filter.return_value.first.return_value = None
    with pytest.raises(ValueError) as exc_info:
        get_podcast_details(db_session, podcast_id)
    assert f"Podcast with ID {podcast_id} not found." in str(exc_info.value)

def test_find_podcast_by_request_id(db_session):
    request_id = str(uuid4())
    fake_podcast = MagicMock()
    fake_podcast.id = str(uuid4())
    db_session.query.return_value.filter.return_value.first.return_value = fake_podcast
    found = find_podcast_by_request_id(db_session, request_id)
    assert found.id == fake_podcast.id

def test_find_podcast_by_request_id_not_found(db_session):
    request_id = str(uuid4())
    db_session.query.return_value.filter.return_value.first.return_value = None
    with pytest.raises(ValueError) as exc_info:
        find_podcast_by_request_id(db_session, request_id)
    assert f"Podcast with request ID {request_id} not found." in str(exc_info.value)