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

import os
import re
import uuid
import base64
import random
from io import BytesIO
from tempfile import NamedTemporaryFile
from typing import Dict, List, Tuple
from icecream import ic
from function.image_gen_models.titan_generator_invoke import invoke_titan_image_generator
from function.llms.bedrock_invoke import invoke_bedrock_model
from function.podcast_generator.utils import PodcastUtils
from utility.aws import synthesize_speech, upload_to_s3, get_polly_voices


def clean_dialogue(text: str) -> List[Dict[str, str]]:
    """
    Cleans and extracts dialogue from a given text.
    This function uses a regular expression to identify speakers and their corresponding lines of dialogue
    from the input text. It returns a list of dictionaries, each containing a speaker and their cleaned dialogue text.
    Args:
        text (str): The input text containing dialogue with speaker names.
    Returns:
        List[Dict[str, str]]: A list of dictionaries where each dictionary has two keys:
            - 'speaker' (str): The name of the speaker.
            - 'text' (str): The cleaned dialogue text associated with the speaker.
    """
    # Regex pattern to match speakers at start of lines only
    speaker_pattern = re.compile(r"(?m)^([A-Za-z]+):\s*(.*?)(?=\n[A-Za-z]+:|$)", re.DOTALL)
    
    dialogue = []
    
    # Find all matches of speaker names and their dialogue
    matches = speaker_pattern.findall(text)
    
    # Loop through the matches and clean the dialogue
    for speaker, dialogue_text in matches:
        # Clean the speaker name and dialogue text
        speaker = speaker.strip()
        dialogue_text = dialogue_text.strip().replace("\n", " ")

        # Add to the dialogue history
        dialogue.append({"speaker": speaker, "text": dialogue_text})
    
    return dialogue


async def generate_audio(dialogue: List[Dict[str, str]], language: str) -> str:
    """
    Generate a podcast audio file from a given dialogue.
    This function synthesizes speech for each dialogue item using Amazon Polly, combines the audio files, 
    and uploads the final audio to an S3 bucket.
    Args:
        dialogue (List[Dict[str, str]]): A list of dictionaries containing 'speaker' and 'text' keys.
        language (str): The language of the dialogue.
    Returns:
        str: The S3 URI of the generated podcast audio file.
    Raises:
        Exception: If there is an error during speech synthesis or file operations.
    """
    language_code = PodcastUtils.get_language_code(language)
    supported_voices = await get_polly_voices(language_code)
    ic("Using supported voices: ", supported_voices)

    allowed_speakers = PodcastUtils.get_speakers(language).get_names()
    backup_voices = [voice for voice in supported_voices if voice not in allowed_speakers]
    
    combined_audio = BytesIO()  # Start with an empty BytesIO stream

    for dialogue_item in dialogue:
        speaker = dialogue_item['speaker']
        text = dialogue_item['text']
        if speaker not in allowed_speakers:
            speaker = random.choice(backup_voices)  # Use a backup voice if the speaker is not allowed

        # Use the speaker's name directly as the voice input for Polly synthesis
        audio_file_path = await synthesize_speech(text, speaker, language_code)

        # Now open the file at audio_file_path and write its contents into combined_audio
        with open(audio_file_path, 'rb') as file_stream:
            combined_audio.write(file_stream.read())  # Write the file's content into the combined audio
            ic(audio_file_path)  # Log the file path

        # Optionally, you can delete the temporary file after it's used
        os.remove(audio_file_path)

    combined_audio.seek(0)  # Reset cursor for streaming response

    with NamedTemporaryFile(suffix=".mp3") as temp_audio_file:
        temp_audio_file.write(combined_audio.getvalue())
        temp_audio_file_path = temp_audio_file.name
        s3_key = f'audio/{uuid.uuid4()}.mp3'
        s3_uri = upload_to_s3("podcast", temp_audio_file_path, s3_key)
        ic("Uploading podcast audio to S3 bucket: ", s3_key, s3_uri)  # Log s3 key and uri

    # Return the audio file as an s3 uri
    return s3_uri

async def generate_podcast_image(podcast_transcript: str) -> Tuple[str, str]:
    """
    Generate a podcast image based on the transcript and upload it to S3.
    This async function generates an image for a podcast using Claude for prompt generation
    and Titan image generator for image creation. The generated image is then uploaded to S3.
    Args:
        podcast_transcript (str): The transcript text of the podcast to generate an image for.
    Returns:
        Tuple[str, str]: A tuple containing:
            - The generated image prompt used for Titan (str)
            - The S3 URI where the generated image was uploaded (str)
    """
    claude_imagegen_prompt = generate_claude_imagegen_prompt(podcast_transcript)
    response = await invoke_bedrock_model(claude_imagegen_prompt)
    # Extract prompt from response located inside triple backticks
    imagegen_prompt = re.search(r'```(.*?)```', response, re.DOTALL).group(1).strip()
    ic(imagegen_prompt)
    base64_image = await invoke_titan_image_generator(imagegen_prompt, 1280, 768)
    image_bytes = base64.b64decode(base64_image)
    
    with NamedTemporaryFile(suffix=".png") as temp_image_file:
        temp_image_file.write(image_bytes)
        temp_image_file_path = temp_image_file.name
        s3_key = f'images/{uuid.uuid4()}.png'
        s3_uri = upload_to_s3("podcast", temp_image_file_path, s3_key)
        ic("Uploading podcast image to S3 bucket: ", s3_key, s3_uri)

    return imagegen_prompt, s3_uri


def generate_claude_prompt(text: str, language: str) -> str:
    """
    Craft a prompt for Claude to generate a podcast dialogue from the given text.

    Arguments:
        text (str): The text to be transformed into a podcast dialogue.
        language (str): The language of the podcast dialogue.

    Returns:
        str: The formatted prompt for Claude.
    """
    speakers = PodcastUtils.get_speakers(language)
    prompt = PodcastUtils.get_podcast_prompt_template().format(
        text=text,
        speakers=str(speakers),
        language=language
    )
    
    return prompt


def generate_claude_imagegen_prompt(text: str) -> str:
    """
    Craft a prompt for Claude to generate a podcast image creation prompt from the given text.

    Arguments:
        text (str): The text to be transformed into a podcast image creation prompt.
    """
    prompt = PodcastUtils.get_podcast_image_prompt_template().format(
        transcript=text
    )

    return prompt
