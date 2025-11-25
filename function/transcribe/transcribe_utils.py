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
import uuid
import logging
import tempfile
import asyncio
from typing import Final, Tuple
from pathlib import Path
import aiofiles
import yt_dlp
import ffmpeg
import magic
from fastapi import UploadFile, HTTPException
from sqlalchemy.orm import Session
from database.models import Transcript
from utility.common import MAX_FILE_SIZE
from utility.aws import fetch_and_save_transcript, fetch_transcription_job, generate_presigned_url, update_transcription_status
from logging_config import setup_logging

# Constants
ALLOWED_AUDIO_TYPES: Final[set] = {'audio/mpeg', 'audio/mp3', 'audio/wav', 'audio/ogg'}
ALLOWED_VIDEO_TYPES: Final[set] = {'video/mp4', 'video/mpeg', 'video/webm'}
MAX_AUDIO_DURATION: Final[int] = 600  # 10 minutes
AUDIO_OUTPUT_FORMAT: Final[str] = 'mp3'
AUDIO_QUALITY: Final[str] = '192'

# Configure logging
logger = setup_logging()

def validate_media_type(file_data: bytes) -> bool:
    """Validate file type using magic numbers."""
    try:
        mime = magic.Magic(mime=True)
        actual_type = mime.from_buffer(file_data)
        return actual_type in ALLOWED_AUDIO_TYPES or actual_type in ALLOWED_VIDEO_TYPES
    except Exception as e:
        logger.error(f"Media type validation error: {str(e)}")
        return False

async def download_youtube_audio(youtube_url: str) -> Tuple[str, str]:
    """Download audio from YouTube URL with security checks."""
    try:
        ydl_opts = {
            'format': 'bestaudio/best',
            'outtmpl': str(Path(tempfile.gettempdir()) / '%(id)s.%(ext)s'),
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': AUDIO_OUTPUT_FORMAT,
                'preferredquality': AUDIO_QUALITY,
            }],
        }
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, _sync_download_youtube, youtube_url, ydl_opts)
    except Exception as e:
        logger.error(f"YouTube download error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to download YouTube audio: {str(e)}")

def _sync_download_youtube(url: str, opts: dict) -> Tuple[str, str]:
    """Synchronous YouTube download to run in thread pool."""
    with yt_dlp.YoutubeDL(opts) as ydl:
        info_dict = ydl.extract_info(url, download=True)
        audio_path = ydl.prepare_filename(info_dict).replace(".webm", ".mp3").replace(".m4a", ".mp3")
        return audio_path, info_dict['title']

async def handle_uploaded_file(file: UploadFile) -> tuple[str, str]:
    """Handle uploaded audio/video file with security checks."""
    temp_files = []  # Track temporary files for cleanup
    try:
        # Validate file size first
        file_data = await file.read()
        if len(file_data) > MAX_FILE_SIZE:
            raise HTTPException(status_code=400, detail="File size exceeds maximum limit")

        # Check content type and determine file extension
        content_type = file.content_type
        if content_type.startswith('audio/'):
            ext = '.mp3'
        elif content_type.startswith('video/'):
            ext = '.mp4'
        else:
            raise HTTPException(status_code=400, detail="Unsupported file type. Only audio and video files are allowed.")

        # Create temporary directory if it doesn't exist
        temp_dir = Path(tempfile.gettempdir()) / 'audio_processing'
        temp_dir.mkdir(exist_ok=True)

        # Generate secure filename and save file
        safe_filename = f"{uuid.uuid4()}{ext}"
        file_path = temp_dir / safe_filename
        
        # Save file with proper permissions
        async with aiofiles.open(file_path, 'wb') as f:
            await f.write(file_data)
        temp_files.append(file_path)

        # Convert video to audio if needed
        if content_type.startswith('video/'):
            audio_path = await convert_video_to_audio(str(file_path))
            temp_files.append(Path(audio_path))
            os.unlink(file_path)
            file_path = Path(audio_path)

        # Validate the resulting audio file
        if not file_path.exists():
            raise ValueError("Failed to create audio file")

        return str(file_path), file.filename

    except HTTPException as http_error:
        raise http_error
    except Exception as e:
        # Clean up any temporary files on error
        for temp_file in temp_files:
            try:
                if temp_file.exists():
                    os.unlink(temp_file)
            except Exception:
                pass
        logger.error(f"Error handling uploaded file: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to process uploaded file: {str(e)}")

async def convert_video_to_audio(file_path: str) -> str:
    """Convert video to audio asynchronously with security checks."""
    output_path = None
    try:
        input_path = Path(file_path)
        if not input_path.exists():
            raise ValueError(f"Input file not found: {file_path}")
        if not os.access(input_path, os.R_OK):
            raise ValueError(f"Input file not readable: {file_path}")

        # Create temporary file with specific extension
        temp_dir = Path(tempfile.gettempdir()) / 'audio_processing'
        temp_dir.mkdir(exist_ok=True)
        
        output_path = str(temp_dir / f"{uuid.uuid4()}.{AUDIO_OUTPUT_FORMAT}")

        # Run conversion in thread pool
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, _sync_convert_video, str(input_path), output_path)

        return output_path

    except Exception as e:
        # Clean up output file if conversion failed
        if output_path and os.path.exists(output_path):
            try:
                os.unlink(output_path)
            except Exception as cleanup_error:
                logger.error(f"Failed to cleanup output file: {cleanup_error}")
                
        logger.error(f"Video conversion error: {str(e)}")
        raise RuntimeError(f"Failed to convert video to audio: {str(e)}")

def _sync_convert_video(input_path: str, output_path: str) -> None:
    """Synchronous video conversion to run in thread pool."""
    try:
        # Get input file information
        probe = ffmpeg.probe(input_path)
        if not probe.get('streams'):
            raise ValueError("No streams found in input file")

        # Setup ffmpeg command with specific codec and quality settings
        stream = ffmpeg.input(input_path)
        stream = ffmpeg.output(
            stream,
            output_path,
            format=AUDIO_OUTPUT_FORMAT,
            acodec='libmp3lame',
            ab='192k',  # Audio bitrate
            ac=2,       # Audio channels
            ar='44100', # Audio sample rate
            loglevel='warning'  # Increase log level for debugging
        )

        # Run the conversion with proper error capture
        ffmpeg.run(
            stream,
            capture_stdout=True,
            capture_stderr=True,
            overwrite_output=True
        )
        
        # Verify the output file
        if not os.path.exists(output_path) or os.path.getsize(output_path) == 0:
            raise RuntimeError("Output file is empty or missing")
            
    except ffmpeg.Error as e:
        error_message = e.stderr.decode() if e.stderr else str(e)
        logger.error(f"FFmpeg conversion error: {error_message}")
        raise RuntimeError(f"FFmpeg conversion failed: {error_message}")
    except Exception as e:
        logger.error(f"Video conversion error: {str(e)}")
        raise RuntimeError(f"Video conversion failed: {str(e)}")

def get_audio_duration(file_path: str) -> int:
    """Get audio duration with validation."""
    try:
        path = Path(file_path)
        if not path.exists():
            raise ValueError(f"Audio file not found at: {file_path}")
        if not path.is_file():
            raise ValueError("Path exists but is not a file")
        if not os.access(path, os.R_OK):
            raise ValueError("File exists but is not readable")
            
        probe = ffmpeg.probe(str(path))
        if 'format' not in probe or 'duration' not in probe['format']:
            raise ValueError("Invalid audio file format")
            
        duration = float(probe['format']['duration'])
        if duration <= 0:
            raise ValueError("Invalid audio duration")
            
        return int(duration)
    except Exception as e:
        logger.error(f"Duration check error for {file_path}: {str(e)}")
        raise ValueError(f"Failed to get audio duration: {str(e)}")

async def get_transcription_status(db: Session, job_name: str) -> dict:
    transcription = db.query(Transcript).filter(Transcript.job_name == job_name).first()
    
    if not transcription:
        raise FileNotFoundError("Transcription job not found")
    
    if transcription.status == "COMPLETED":
        audio_url = generate_presigned_url('audio', transcription.s3_uri)
        return {
            "request_id": transcription.request_id,
            "status": transcription.status,
            "transcript_id": transcription.id,
            "language_code": transcription.language_code,
            "transcript": transcription.transcription_text,
            "completed_at": transcription.completed_at.isoformat() if transcription.completed_at else None,
            "audioUrl": audio_url
        }

    job_details = await fetch_transcription_job(job_name)
    current_status = job_details['TranscriptionJobStatus']
    
    if transcription.status != current_status:
        await update_transcription_status(transcription, current_status)
        db.commit()

    if current_status == "COMPLETED" and not transcription.transcription_text:
        transcript_uri = job_details['Transcript']['TranscriptFileUri']
        await fetch_and_save_transcript(transcription, transcript_uri, db)
        audio_url = generate_presigned_url('audio', transcription.s3_uri)
        result = {
            "request_id": transcription.request_id,
            "status": transcription.status,
            "transcript_id": transcription.id,
            "language_code": transcription.language_code,
            "transcript": transcription.transcription_text,
            "completed_at": transcription.completed_at.isoformat() if transcription.completed_at else None,
            "audioUrl": audio_url
        }
    else:
        result = {
            "request_id": transcription.request_id,
            "status": transcription.status,
            "transcript": transcription.transcription_text if transcription.status == "COMPLETED" else None,
        }

    return result
