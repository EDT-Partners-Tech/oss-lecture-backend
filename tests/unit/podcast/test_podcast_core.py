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

import base64
import re
import tempfile
import pytest

from function.podcast_generator.podcast import (
    clean_dialogue,
    generate_claude_prompt,
    generate_claude_imagegen_prompt,
    generate_audio,
    generate_podcast_image,
)
from function.podcast_generator.utils import PodcastUtils, SupportedPodcastLanguage

# Test for clean_dialogue
def test_clean_dialogue_normal():
    text = "Alice: Hello there.\nBob: Hi, Alice!\nAlice: How are you?"
    dialogue = clean_dialogue(text)
    expected = [
        {"speaker": "Alice", "text": "Hello there."},
        {"speaker": "Bob", "text": "Hi, Alice!"},
        {"speaker": "Alice", "text": "How are you?"},
    ]
    assert dialogue == expected

def test_clean_dialogue_no_dialogue():
    text = "This is a text without any dialogue."
    dialogue = clean_dialogue(text)
    assert dialogue == []

def test_generate_claude_prompt():
    text = "Sample text for prompt"
    language = "english"
    result = generate_claude_prompt(text, language)
    # Assert that the prompt contains a known marker from the original template
    assert "Human:" in result
    assert text in result

def test_generate_claude_imagegen_prompt():
    transcript = "Sample transcript for image prompt"
    result = generate_claude_imagegen_prompt(transcript)
    # Assert that the prompt contains expected instructions (e.g., wrap the prompt output)
    assert "Wrap the generated prompt between backticks" in result or "```" in result

@pytest.mark.asyncio
async def test_generate_audio(monkeypatch):
    # Prepare a dummy voice list and dummy allowed speakers.
    dummy_language_code = "en-US"
    dummy_allowed = ["Alice", "Bob"]
    dummy_backup = ["Carol"]

    monkeypatch.setattr(PodcastUtils, "get_language_code", lambda lang: dummy_language_code)
    monkeypatch.setattr(PodcastUtils, "get_speakers", lambda lang: type("DummySpeakers", (), {
        "get_names": lambda self: dummy_allowed
    })())
    # Patch get_polly_voices to return allowed plus backup voices
    async def dummy_get_polly_voices(language_code):
        return dummy_allowed + dummy_backup
    monkeypatch.setattr("function.podcast_generator.podcast.get_polly_voices", dummy_get_polly_voices)
    
    # Dummy synthesize_speech returns a temporary file path with content.
    async def dummy_synthesize_speech(text, speaker, language_code):
        with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as tf:
            tf.write(b"audio")
            return tf.name
    monkeypatch.setattr("function.podcast_generator.podcast.synthesize_speech", dummy_synthesize_speech)

    # Patch upload_to_s3 to return a fake S3 URI.
    monkeypatch.setattr("function.podcast_generator.podcast.upload_to_s3", lambda bucket, file_path, key: f"s3://{bucket}/{key}")
    
    # Create a dialogue list including an allowed speaker and one not allowed.
    dialogue = [
        {"speaker": "Alice", "text": "Hello World!"},
        {"speaker": "Unknown", "text": "Fallback voice used."}
    ]
    # Call generate_audio
    s3_uri = await generate_audio(dialogue, SupportedPodcastLanguage.ENGLISH)
    assert s3_uri.startswith("s3://podcast/")

@pytest.mark.asyncio
async def test_generate_podcast_image(monkeypatch):
    dummy_prompt_response = "```Generated image prompt```"
    # Patch invoke_bedrock_claude_async to return a dummy response with triple backticks.
    async def dummy_invoke_bedrock(prompt):
        return dummy_prompt_response
    monkeypatch.setattr("function.podcast_generator.podcast.invoke_bedrock_model", dummy_invoke_bedrock)

    # Return dummy base64 encoded image (e.g., a small red dot PNG)
    dummy_base64 = base64.b64encode(b"fakeimagedata").decode("utf-8")
    async def dummy_invoke_titan_image_generator(prompt, width, height):
        return dummy_base64
    monkeypatch.setattr("function.podcast_generator.podcast.invoke_titan_image_generator", dummy_invoke_titan_image_generator)
    
    # Patch upload_to_s3 to return a fake S3 URI.
    monkeypatch.setattr("function.podcast_generator.podcast.upload_to_s3", lambda bucket, file_path, key: f"s3://{bucket}/{key}")

    transcript = "Dummy transcript for image generation."
    imagegen_prompt, s3_uri = await generate_podcast_image(transcript)
    
    # Validate that the prompt is extracted correctly.
    assert re.match(r'.+', imagegen_prompt)
    assert s3_uri.startswith("s3://podcast/")
