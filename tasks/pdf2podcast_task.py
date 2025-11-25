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

import re
import json
from datetime import datetime
from uuid import UUID
from icecream import ic
from sqlalchemy.orm import Session
from fastapi import HTTPException

from utility.aws import delete_from_s3
from function.podcast_generator.podcast import generate_claude_prompt, generate_audio, generate_podcast_image, clean_dialogue
from function.llms.bedrock_invoke import invoke_bedrock_model
from database.schemas import PodcastUpdate, PodcastStatus
from database.crud import update_podcast, update_podcast_status


async def cleanup_s3_files(audio_s3_uri: str, image_s3_uri: str):
    """
    Asynchronously deletes audio and image files from S3 bucket after a failed podcast creation.

    Args:
        audio_s3_uri (str): S3 URI of the audio file to be deleted. If empty, no audio deletion is attempted.
        image_s3_uri (str): S3 URI of the image file to be deleted. If empty, no image deletion is attempted.
    """
    try:
        if audio_s3_uri:
            ic("Cleaning up audio file from failed podcast")
            await delete_from_s3('podcast', audio_s3_uri)
        if image_s3_uri:
            ic("Cleaning up image file from failed podcast")
            await delete_from_s3('podcast', image_s3_uri)
    except Exception as e:
        ic(f"Error in cleanup_s3_files function: {e}")
        raise HTTPException(status_code=500, detail=f"Internal Server Error: {str(e)}")


async def process_generate_podcast(text: str, language: str, db: Session, podcast_id: UUID):
    """
    Asynchronously processes text to generate a podcast with audio and image.
    This function orchestrates the podcast generation process by:
    1. Generating and processing dialogue using Claude AI
    2. Creating audio from the dialogue
    3. Generating a complementary image
    4. Updating the podcast status in the database throughout the process

    Args:
        text (str): The input text to be converted into a podcast
        language (str): The target language for the podcast
        db (Session): Database session for storing podcast information
        podcast_id (UUID): Unique identifier for the podcast
    
    Note:
        The function updates the podcast status in the database at various stages:
        - During audio generation (PodcastStatus.AUDIO)
        - During image generation (PodcastStatus.IMAGE)
        If an error occurs, it performs cleanup of any generated S3 files.
    """
    audio_s3_uri, image_s3_uri = None, None
    try:
        ic("Generating prompt for Claude")
        prompt = generate_claude_prompt(text, language)

        ic("Invoking Claude with the generated prompt")
        response = await invoke_bedrock_model(prompt)

        ic(f"Claude's response: {response}")

        ic("Extracting title & dialogue from Claude's response")
        podcast_title = re.search(r'~(.*?)~', response, re.DOTALL).group(1).strip()
        dialogue_stripped = re.search(r'```(.*?)```', response, re.DOTALL).group(1).strip()

        ic("Cleaning the dialogue")
        dialogue = clean_dialogue(dialogue_stripped)

        ic(f"Using title: {podcast_title}")
        ic(f"Using dialogue: {dialogue}")

        update_podcast_status(db, podcast_id, PodcastStatus.AUDIO)

        ic("Generating audio from the dialogue")
        audio_s3_uri = await generate_audio(dialogue, language)
        ic(f"Generated audio podcast at s3 uri: {audio_s3_uri}")

        update_podcast_status(db, podcast_id, PodcastStatus.IMAGE)

        ic("Generating image for the podcast")
        podcast_transcript = "\n".join([f"{item['speaker']}: {item['text']}" for item in dialogue])
        image_prompt, image_s3_uri = await generate_podcast_image(podcast_transcript)

        # Everything succeeded; update the podcast log
        podcast_info = PodcastUpdate(
            title=podcast_title,
            dialog=json.dumps(dialogue),
            audio_s3_uri=audio_s3_uri,
            image_s3_uri=image_s3_uri,
            image_prompt=image_prompt,
            completed_at=datetime.now()
        )
        update_podcast(db, podcast_id, podcast_info)
    
    except Exception as e:
        ic(f"Error in pdf_to_podcast function: {e}")
        # Update the podcast log with failure status
        update_podcast(db, podcast_id, PodcastUpdate())
        # Clean up bad files
        await cleanup_s3_files(audio_s3_uri, image_s3_uri)
        raise HTTPException(status_code=500, detail=f"Internal Server Error: {str(e)}")
