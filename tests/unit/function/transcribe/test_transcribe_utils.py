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

import asyncio
import os
import uuid
import tempfile
import pytest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch, MagicMock, AsyncMock
from fastapi import HTTPException, UploadFile
from sqlalchemy.orm import Session

from function.transcribe.transcribe_utils import (
    validate_media_type,
    download_youtube_audio,
    handle_uploaded_file,
    convert_video_to_audio,
    get_audio_duration,
    get_transcription_status
)
from database.models import Transcript


# --- Fixtures ---

@pytest.fixture
def mock_file():
    """Mock an uploaded file"""
    file = MagicMock(spec=UploadFile)
    file.filename = "test_audio.mp3"
    file.content_type = "audio/mp3"
    # Create a read method that returns bytes
    file.read = AsyncMock(return_value=b"mock audio data")
    return file

@pytest.fixture
def mock_video_file():
    """Mock an uploaded video file"""
    file = MagicMock(spec=UploadFile)
    file.filename = "test_video.mp4"
    file.content_type = "video/mp4"
    file.read = AsyncMock(return_value=b"mock video data")
    return file

@pytest.fixture
def mock_db_session():
    """Create a mock database session"""
    return MagicMock(spec=Session)

@pytest.fixture
def mock_transcript_record():
    """Create a mock transcript record"""
    transcript = MagicMock(spec=Transcript)
    transcript.id = 1
    transcript.job_name = "test-job-123"
    transcript.language_code = "en-US"
    transcript.status = "IN_PROGRESS"
    transcript.transcription_text = None
    transcript.s3_uri = "s3://test-audio-bucket/test-audio.mp3"
    transcript.completed_at = None
    return transcript

@pytest.fixture
def mock_completed_transcript():
    """Create a mock completed transcript"""
    transcript = MagicMock(spec=Transcript)
    transcript.id = 2
    transcript.job_name = "completed-job-123"
    transcript.language_code = "en-US"
    transcript.status = "COMPLETED"
    transcript.transcription_text = "This is a test transcription"
    transcript.s3_uri = "s3://test-audio-bucket/completed-audio.mp3"
    transcript.completed_at = datetime.now(timezone.utc)
    return transcript


# --- Tests for validate_media_type ---

def test_validate_media_type_audio_success():
    """Test validation of audio file type"""
    with patch('magic.Magic') as mock_magic:
        mock_magic_instance = mock_magic.return_value
        mock_magic_instance.from_buffer.return_value = "audio/mp3"
        
        result = validate_media_type(b"mock audio data")
        assert result is True
        mock_magic_instance.from_buffer.assert_called_once_with(b"mock audio data")

def test_validate_media_type_video_success():
    """Test validation of video file type"""
    with patch('magic.Magic') as mock_magic:
        mock_magic_instance = mock_magic.return_value
        mock_magic_instance.from_buffer.return_value = "video/mp4"
        
        result = validate_media_type(b"mock video data")
        assert result is True

def test_validate_media_type_invalid():
    """Test validation of invalid file type"""
    with patch('magic.Magic') as mock_magic:
        mock_magic_instance = mock_magic.return_value
        mock_magic_instance.from_buffer.return_value = "application/pdf"
        
        result = validate_media_type(b"mock pdf data")
        assert result is False

def test_validate_media_type_exception():
    """Test error handling in file type validation"""
    with patch('magic.Magic') as mock_magic:
        mock_magic_instance = mock_magic.return_value
        mock_magic_instance.from_buffer.side_effect = Exception("Magic library error")
        
        result = validate_media_type(b"corrupt data")
        assert result is False


# --- Tests for download_youtube_audio ---

@pytest.mark.asyncio
async def test_download_youtube_audio_success():
    """Test successful YouTube audio download"""
    youtube_url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
    expected_title = "Rick Astley - Never Gonna Give You Up"
    
    # Mock the underlying thread execution
    with tempfile.NamedTemporaryFile(suffix="mp3") as expected_audio_file:
        expected_audio_path = Path(expected_audio_file.name)
        with patch('asyncio.get_event_loop') as mock_loop:
            mock_executor = AsyncMock()
            mock_executor.return_value = (expected_audio_path, expected_title)
            mock_loop.return_value.run_in_executor = mock_executor
            
            audio_path, title = await download_youtube_audio(youtube_url)
            
            assert audio_path == expected_audio_path
            assert title == expected_title
            # Verify the executor was called with the right parameters
            mock_executor.assert_called_once()

@pytest.mark.asyncio
async def test_download_youtube_audio_error():
    """Test error handling in YouTube download"""
    youtube_url = "https://www.youtube.com/watch?v=invalid"
    
    # Mock the underlying thread execution to raise an exception
    with patch('asyncio.get_event_loop') as mock_loop:
        mock_executor = AsyncMock(side_effect=Exception("YouTube download failed"))
        mock_loop.return_value.run_in_executor = mock_executor
        
        with pytest.raises(HTTPException) as exc_info:
            await download_youtube_audio(youtube_url)
        
        assert exc_info.value.status_code == 500
        assert "Failed to download YouTube audio" in str(exc_info.value.detail)
        mock_executor.assert_called_once()


# --- Tests for handle_uploaded_file ---

@pytest.mark.asyncio
async def test_handle_uploaded_file_audio_success(mock_file):
    """Test successful handling of uploaded audio file"""
    with patch('uuid.uuid4', return_value=uuid.UUID('12345678-1234-5678-1234-567812345678')):
        # Call the function
        result_path, result_filename = await handle_uploaded_file(mock_file)
        
        # Verify results
        assert result_filename == "test_audio.mp3"
        assert result_path.endswith("12345678-1234-5678-1234-567812345678.mp3")
        with open(result_path, 'rb') as f:
            assert f.read() == b"mock audio data"
        os.unlink(result_path)

@pytest.mark.asyncio
async def test_handle_uploaded_file_video_success(mock_video_file):
    """Test successful handling of uploaded video file with conversion"""
    # Setup mocks for file operations and video conversion
    # Use actual temp directories to ensure Path operations work correctly
    temp_dir = Path(tempfile.gettempdir()) / "audio_processing"
    temp_dir.mkdir(exist_ok=True)
    
    video_path = Path(tempfile.gettempdir()) / "12345678-1234-5678-1234-567812345678.mp4"
    converted_audio_path = temp_dir / "12345678-1234-5678-1234-567812345678.mp3"
    
    try:
        # Create the audio file that convert_video_to_audio would create
        with open(converted_audio_path, 'wb') as f:
            f.write(b"mock converted audio data")
        
        with patch('uuid.uuid4', return_value=uuid.UUID('12345678-1234-5678-1234-567812345678')), \
             patch('function.transcribe.transcribe_utils.convert_video_to_audio',
                   AsyncMock(return_value=str(converted_audio_path))) as mock_convert:
            
            # Call the function
            result_path, result_filename = await handle_uploaded_file(mock_video_file)
            
            # Verify results
            assert result_filename == "test_video.mp4"
            assert result_path == str(converted_audio_path)
            assert Path(result_path).exists()  # This should now pass
            
            # Verify conversion was called with the temporary video path
            mock_convert.assert_called_once()
            call_arg = mock_convert.call_args[0][0]
            assert "12345678-1234-5678-1234-567812345678.mp4" in call_arg
    
    finally:
        # Clean up temporary files
        if converted_audio_path.exists():
            os.unlink(converted_audio_path)
        if video_path.exists():
            os.unlink(video_path)

@pytest.mark.asyncio
async def test_handle_uploaded_file_size_exceeded(mock_file):
    """Test handling of file exceeding size limit"""
    # Create a large file that exceeds the limit
    mock_file.read = AsyncMock(return_value=b"x" * (10 * 1024 * 1024 + 1))  # Assuming MAX_FILE_SIZE is 10MB
    
    with pytest.raises(HTTPException) as exc_info:
        await handle_uploaded_file(mock_file)
    
    assert exc_info.value.status_code == 400
    assert "File size exceeds maximum limit" in str(exc_info.value.detail)

@pytest.mark.asyncio
async def test_handle_uploaded_file_invalid_type():
    """Test handling of file with unsupported type"""
    # Create a mock file with unsupported content type
    invalid_file = MagicMock(spec=UploadFile)
    invalid_file.filename = "test_document.pdf"
    invalid_file.content_type = "application/pdf"
    invalid_file.read = AsyncMock(return_value=b"mock pdf data")
    
    with pytest.raises(HTTPException) as exc_info:
        await handle_uploaded_file(invalid_file)
    
    assert exc_info.value.status_code == 400
    assert "Unsupported file type" in str(exc_info.value.detail)


# --- Tests for convert_video_to_audio ---

@pytest.mark.asyncio
async def test_convert_video_to_audio_success():
    """Test successful video to audio conversion"""
    with tempfile.NamedTemporaryFile(suffix=".mp4") as input_file:
        # Mock the run_in_executor function that calls _sync_convert_video
        with patch('uuid.uuid4', return_value=uuid.UUID('12345678-1234-5678-1234-567812345678')), \
            patch('asyncio.get_event_loop') as mock_loop:
            
            mock_executor = AsyncMock()
            mock_loop.return_value.run_in_executor = mock_executor
            
            output_path = await convert_video_to_audio(input_file.name)
            
            assert "12345678-1234-5678-1234-567812345678.mp3" in output_path
            mock_executor.assert_called_once()

@pytest.mark.asyncio
async def test_convert_video_to_audio_file_not_found():
    """Test handling of missing input file"""
    with tempfile.NamedTemporaryFile(suffix=".mp4") as input_file, \
         patch('pathlib.Path.exists', return_value=False):
        
        with pytest.raises(RuntimeError) as exc_info:
            await convert_video_to_audio(input_file.name)
        
        assert "Failed to convert video to audio" in str(exc_info.value)
        assert "Input file not found" in str(exc_info.value)

@pytest.mark.asyncio
async def test_convert_video_to_audio_permission_error():
    """Test handling of input file with no read permission"""
    with tempfile.NamedTemporaryFile(suffix=".mp4") as input_file, \
         patch('os.access', return_value=False):
            
        with pytest.raises(RuntimeError) as exc_info:
            await convert_video_to_audio(input_file.name)
        
        assert "Failed to convert video to audio" in str(exc_info.value)
        assert "Input file not readable" in str(exc_info.value)

@pytest.mark.asyncio
async def test_convert_video_to_audio_conversion_error():
    """Test handling of error during conversion"""
    with tempfile.NamedTemporaryFile(suffix=".mp4") as input_file, \
         patch('asyncio.get_event_loop') as mock_loop:
        
        mock_executor = AsyncMock(side_effect=Exception("Conversion failed"))
        mock_loop.return_value.run_in_executor = mock_executor
        
        with pytest.raises(RuntimeError) as exc_info:
            await convert_video_to_audio(input_file.name)
        
        assert "Failed to convert video to audio" in str(exc_info.value)
        mock_executor.assert_called_once()


# --- Tests for get_audio_duration ---

def test_get_audio_duration_success():
    """Test successful audio duration check"""
    expected_duration = 120  # 2 minutes
    
    # Mock ffmpeg.probe response
    probe_result = {
        "format": {
            "duration": "120.5"  # Should return 120 (int)
        }
    }
    
    with tempfile.NamedTemporaryFile(suffix=".mp3") as audio_file, \
         patch('ffmpeg.probe', return_value=probe_result):
        
        duration = get_audio_duration(audio_file.name)
        assert duration == expected_duration

def test_get_audio_duration_file_not_found():
    """Test handling of missing audio file"""
    with tempfile.NamedTemporaryFile(suffix=".mp3") as audio_file, \
         patch('pathlib.Path.exists', return_value=False):
        
        with pytest.raises(ValueError) as exc_info:
            get_audio_duration(audio_file.name)
        
        assert "Audio file not found" in str(exc_info.value)

def test_get_audio_duration_not_a_file():
    """Test handling of a path that's not a file"""
    with tempfile.TemporaryDirectory() as temp_dir:
        with pytest.raises(ValueError) as exc_info:
            get_audio_duration(temp_dir)
        
        assert "Path exists but is not a file" in str(exc_info.value)

def test_get_audio_duration_permission_error():
    """Test handling of file with no read permission"""
    with tempfile.NamedTemporaryFile(suffix=".mp3") as audio_file, \
         patch('os.access', return_value=False):
        
        with pytest.raises(ValueError) as exc_info:
            get_audio_duration(audio_file.name)
            
        assert "File exists but is not readable" in str(exc_info.value)

def test_get_audio_duration_invalid_format():
    """Test handling of invalid audio format"""
    # Missing duration in response
    probe_result = {
        "format": {}
    }
    
    with tempfile.NamedTemporaryFile(suffix=".mp3") as audio_file, \
         patch('ffmpeg.probe', return_value=probe_result):
            
        with pytest.raises(ValueError) as exc_info:
            get_audio_duration(audio_file.name)
            
        assert "Invalid audio file format" in str(exc_info.value)

def test_get_audio_duration_negative_duration():
    """Test handling of negative audio duration"""
    # Negative duration in response
    probe_result = {
        "format": {
            "duration": "-10.5"
        }
    }
    
    with tempfile.NamedTemporaryFile(suffix=".mp3") as audio_file, \
         patch('ffmpeg.probe', return_value=probe_result):
        
        with pytest.raises(ValueError) as exc_info:
            get_audio_duration(audio_file.name)
        
        assert "Invalid audio duration" in str(exc_info.value)


# --- Tests for get_transcription_status ---

def test_get_transcription_status_completed(mock_db_session, mock_completed_transcript):
    """Test getting status for a completed transcription job"""
    # Setup mock query results
    mock_db_session.query.return_value.filter.return_value.first.return_value = mock_completed_transcript
    
    with patch('function.transcribe.transcribe_utils.generate_presigned_url', 
               return_value="https://presigned-url.com/audio.mp3"):
        
        # Call the async function
        result = asyncio.run(get_transcription_status(mock_db_session, "completed-job-123"))
        
        # Verify results
        assert result["status"] == "COMPLETED"
        assert result["transcript_id"] == 2
        assert result["transcript"] == "This is a test transcription"
        assert result["audioUrl"] == "https://presigned-url.com/audio.mp3"

def test_get_transcription_status_in_progress(mock_db_session, mock_transcript_record):
    """Test getting status for an in-progress transcription job"""
    # Setup mock query results and AWS response
    mock_db_session.query.return_value.filter.return_value.first.return_value = mock_transcript_record
    
    job_details = {
        'TranscriptionJobStatus': 'IN_PROGRESS'
    }
    
    with patch('function.transcribe.transcribe_utils.fetch_transcription_job', 
               return_value=job_details):
        
        # Call the async function
        result = asyncio.run(get_transcription_status(mock_db_session, "test-job-123"))
        
        # Verify results
        assert result["status"] == "IN_PROGRESS"
        assert result["transcript"] is None

@pytest.mark.asyncio
async def test_get_transcription_status_just_completed(mock_db_session, mock_transcript_record):
    """Test getting status for a transcription job that just completed"""
    # Setup mock query results and AWS response
    mock_db_session.query.return_value.filter.return_value.first.return_value = mock_transcript_record
    
    job_details = {
        'TranscriptionJobStatus': 'COMPLETED',
        'Transcript': {
            'TranscriptFileUri': 'https://s3.amazonaws.com/bucket/transcript.json'
        }
    }
    
    transcript_text = "This is the newly completed transcript"
    
    with patch('function.transcribe.transcribe_utils.fetch_transcription_job', 
               return_value=job_details), \
         patch('function.transcribe.transcribe_utils.update_transcription_status', AsyncMock()) as mock_update_status, \
         patch('function.transcribe.transcribe_utils.fetch_and_save_transcript', AsyncMock()) as mock_fetch_transcript, \
         patch('function.transcribe.transcribe_utils.generate_presigned_url', 
               return_value="https://presigned-url.com/audio.mp3"):
        
        # Set up the mock transcript to have the text after fetch_and_save_transcript is called
        def set_transcript_text(*args, **kwargs):
            mock_transcript_record.transcription_text = transcript_text
            mock_transcript_record.status = "COMPLETED"
        
        mock_fetch_transcript.side_effect = set_transcript_text
        
        # Call the async function
        result = await get_transcription_status(mock_db_session, "test-job-123")
        
        # Verify results and method calls
        mock_update_status.assert_called_once_with(mock_transcript_record, "COMPLETED")
        mock_fetch_transcript.assert_called_once()
        mock_db_session.commit.assert_called()
        
        assert result["status"] == "COMPLETED"
        assert result["transcript"] == transcript_text
        assert result["audioUrl"] == "https://presigned-url.com/audio.mp3"

@pytest.mark.asyncio
async def test_get_transcription_status_not_found(mock_db_session):
    """Test getting status for a non-existent transcription job"""
    # Ensure the mock returns None
    mock_db_session.query.return_value.filter.return_value.first.return_value = None
    
    try:
        await get_transcription_status(mock_db_session, "nonexistent-job")
    except FileNotFoundError as e:
        assert str(e) == "Transcription job not found"
        return  # Test passes if this is raised

    pytest.fail("Expected FileNotFoundError was not raised.")
