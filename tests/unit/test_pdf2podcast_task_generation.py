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
from fastapi import HTTPException
from tasks import pdf2podcast_task
import json
from datetime import datetime
from uuid import uuid4
from database.schemas import PodcastStatus


def fake_generate_claude_prompt(text, language):
    return "dummy prompt"

async def fake_invoke_bedrock_model(prompt):
    # Return a response containing title and dialogue in expected format.
    return "~Test Podcast Title~```[{'speaker': 'A', 'text': 'Hello'}, {'speaker': 'B', 'text': 'World'}]```"

def fake_clean_dialogue(dialogue_str):
    # Return the parsed dialogue (simulate cleaning)
    return [{'speaker': 'A', 'text': 'Hello'}, {'speaker': 'B', 'text': 'World'}]

async def fake_generate_audio(dialogue, language):
    return "s3://audio"

async def fake_generate_podcast_image(transcript):
    return ("Test image prompt", "s3://image")

# Lists to record update calls
update_status_calls = []
update_podcast_calls = []

def fake_update_podcast_status(db, podcast_id, status):
    update_status_calls.append((podcast_id, status))

def fake_update_podcast(db, podcast_id, podcast_info):
    update_podcast_calls.append((podcast_id, podcast_info))


@pytest.mark.asyncio
async def test_process_generate_podcast_success(monkeypatch):
    # Clear call recording lists
    update_status_calls.clear()
    update_podcast_calls.clear()

    # Patch external dependencies with our fakes.
    monkeypatch.setattr(pdf2podcast_task, "generate_claude_prompt", fake_generate_claude_prompt)
    monkeypatch.setattr(pdf2podcast_task, "invoke_bedrock_model", fake_invoke_bedrock_model)
    monkeypatch.setattr(pdf2podcast_task, "clean_dialogue", fake_clean_dialogue)
    monkeypatch.setattr(pdf2podcast_task, "generate_audio", fake_generate_audio)
    monkeypatch.setattr(pdf2podcast_task, "generate_podcast_image", fake_generate_podcast_image)
    monkeypatch.setattr(pdf2podcast_task, "update_podcast_status", fake_update_podcast_status)
    monkeypatch.setattr(pdf2podcast_task, "update_podcast", fake_update_podcast)

    dummy_db = {}
    dummy_podcast_id = uuid4()
    text = "Some input text"
    language = "en"

    await pdf2podcast_task.process_generate_podcast(text, language, dummy_db, dummy_podcast_id)

    # Verify update_podcast_status was called in order with AUDIO then IMAGE status.
    assert len(update_status_calls) == 2
    assert update_status_calls[0] == (dummy_podcast_id, PodcastStatus.AUDIO)
    assert update_status_calls[1] == (dummy_podcast_id, PodcastStatus.IMAGE)

    # Verify update_podcast was called with a PodcastUpdate that has correct fields.
    # The last call to update_podcast should be with podcast_info.
    assert len(update_podcast_calls) == 1
    podcast_id_arg, podcast_info = update_podcast_calls[0]
    assert podcast_id_arg == dummy_podcast_id
    # Check that the title, audio and image URIs, image_prompt, and dialog are set correctly.
    assert podcast_info.title == "Test Podcast Title"
    # The dialogue was json dumped; parse it and compare.
    dialogue = json.loads(podcast_info.dialog)
    assert dialogue == [{'speaker': 'A', 'text': 'Hello'}, {'speaker': 'B', 'text': 'World'}]
    assert podcast_info.audio_s3_uri == "s3://audio"
    assert podcast_info.image_s3_uri == "s3://image"
    assert podcast_info.image_prompt == "Test image prompt"
    # completed_at should be a datetime instance.
    assert isinstance(podcast_info.completed_at, datetime)


@pytest.mark.asyncio
async def test_process_generate_podcast_failure(monkeypatch):
    # Clear call recording lists
    update_status_calls.clear()
    update_podcast_calls.clear()

    # Patch functions similar to success, except make generate_audio raise exception.
    monkeypatch.setattr(pdf2podcast_task, "generate_claude_prompt", fake_generate_claude_prompt)
    monkeypatch.setattr(pdf2podcast_task, "invoke_bedrock_model", fake_invoke_bedrock_model)
    monkeypatch.setattr(pdf2podcast_task, "clean_dialogue", fake_clean_dialogue)

    async def failing_generate_audio(dialogue, language):
        raise RuntimeError("Audio generation failed")

    monkeypatch.setattr(pdf2podcast_task, "generate_audio", failing_generate_audio)
    monkeypatch.setattr(pdf2podcast_task, "generate_podcast_image", fake_generate_podcast_image)
    monkeypatch.setattr(pdf2podcast_task, "update_podcast_status", fake_update_podcast_status)
    monkeypatch.setattr(pdf2podcast_task, "update_podcast", fake_update_podcast)

    # Patch cleanup_s3_files to record its call
    cleanup_calls = []
    async def fake_cleanup_s3_files(audio_uri, image_uri):
        cleanup_calls.append((audio_uri, image_uri))
    monkeypatch.setattr(pdf2podcast_task, "cleanup_s3_files", fake_cleanup_s3_files)

    dummy_db = {}
    dummy_podcast_id = uuid4()
    text = "Some input text"
    language = "en"

    with pytest.raises(HTTPException) as exc_info:
        await pdf2podcast_task.process_generate_podcast(text, language, dummy_db, dummy_podcast_id)
    assert exc_info.value.status_code == 500
    assert "Audio generation failed" in exc_info.value.detail

    # In failure case, update_podcast should have been called with an empty PodcastUpdate.
    # Since we don't know the inner details of PodcastUpdate, we check that a call was made.
    assert len(update_podcast_calls) >= 1

    # Ensure cleanup_s3_files was called.
    # At the time of exception, audio_s3_uri was not set (None) and image_s3_uri was not set.
    assert cleanup_calls == [(None, None)]