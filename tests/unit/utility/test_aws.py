# © [2025] EDT&Partners. Licensed under CC BY 4.0.

import json
import pytest
import boto3
import tempfile
import botocore
import io
from io import BytesIO
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock, ANY, AsyncMock
from botocore.exceptions import ClientError
from botocore.stub import Stubber
from fastapi import HTTPException
import requests
from sqlalchemy.orm import Session

# Import the module under test
import utility.aws as aws_module
from utility.exceptions import StepFunctionExecutionError, StepFunctionTimeoutError

@pytest.fixture(autouse=True, scope="module")
def mock_aws_config():
    with patch.object(aws_module, 'region_name', 'us-east-1'), \
         patch.object(aws_module, 'polly_speech_engine', 'neural'), \
         patch.object(aws_module, 'lecture_buckets', {
            "audio": "test-audio-bucket",
            "podcast": "test-podcast-bucket",
            "content": "lecture-content"
         }):
        yield

# Fixtures for common AWS services
@pytest.fixture
def translate_client():
    client = boto3.client("translate", region_name="us-east-1")
    return client

@pytest.fixture
def translate_stubber(translate_client):
    return Stubber(translate_client)

@pytest.fixture
def s3_client():
    client = boto3.client("s3", region_name="us-east-1")
    return client

@pytest.fixture
def s3_stubber(s3_client):
    return Stubber(s3_client)

@pytest.fixture
def transcribe_client():
    client = boto3.client("transcribe", region_name="us-east-1")
    return client

@pytest.fixture
def transcribe_stubber(transcribe_client):
    return Stubber(transcribe_client)

@pytest.fixture
def cognito_client():
    client = boto3.client("cognito-idp", region_name="us-east-1")
    return client

@pytest.fixture
def cognito_stubber(cognito_client):
    return Stubber(cognito_client)

@pytest.fixture
def ses_client():
    client = boto3.client("ses", region_name="us-east-1")
    return client

@pytest.fixture
def ses_stubber(ses_client):
    return Stubber(ses_client)

@pytest.fixture
def bedrock_agent_client():
    client = boto3.client("bedrock-agent", region_name="us-east-1")
    return client

@pytest.fixture
def bedrock_agent_stubber(bedrock_agent_client):
    return Stubber(bedrock_agent_client)

@pytest.fixture
def sf_client():
    client = boto3.client("stepfunctions", region_name="us-east-1")
    return client

@pytest.fixture
def sf_stubber(sf_client):
    return Stubber(sf_client)

@pytest.fixture
def iam_client():
    client = boto3.client("iam", region_name="us-east-1")
    return client

@pytest.fixture
def iam_stubber(iam_client):
    return Stubber(iam_client)

@pytest.fixture
def opensearch_client():
    client = boto3.client("opensearchserverless", region_name="us-east-1")
    return client

@pytest.fixture
def opensearch_stubber(opensearch_client):
    return Stubber(opensearch_client)

@pytest.fixture
def polly_client():
    client = boto3.client("polly", region_name="us-east-1")
    return client

@pytest.fixture
def polly_stubber(polly_client):
    return Stubber(polly_client)

@pytest.fixture
def textract_client():
    client = boto3.client("textract", region_name="us-east-1")
    return client

@pytest.fixture
def textract_stubber(textract_client):
    return Stubber(textract_client)

@pytest.fixture
def comprehend_client():
    client = boto3.client("comprehend", region_name="us-east-1")
    return client

@pytest.fixture
def comprehend_stubber(comprehend_client):
    return Stubber(comprehend_client)

@pytest.fixture
def sts_client():
    client = boto3.client("sts", region_name="us-east-1")
    return client

@pytest.fixture
def sts_stubber(sts_client):
    return Stubber(sts_client)

@pytest.fixture
def mock_db():
    """Create a mock database session"""
    db = MagicMock(spec=Session)
    return db

# Tests for translate functionality
class TestTranslate:
    def test_generate_text_translation_success(self, translate_client, translate_stubber):
        # Test parameters
        text = "Hello, world!"
        source_lang = "en"
        target_lang = "es"
        
        # Expected response from AWS Translate
        response = {
            'TranslatedText': 'Hola, mundo!',
            'SourceLanguageCode': source_lang,
            'TargetLanguageCode': target_lang
        }
        
        # Setup stubber with expected params and response
        expected_params = {
            'Text': text,
            'SourceLanguageCode': source_lang,
            'TargetLanguageCode': target_lang
        }
        translate_stubber.add_response('translate_text', response, expected_params)
        
        # Patch the boto3 client to use our stubbed client
        with patch.object(aws_module, 'translate_client', translate_client):
            with translate_stubber:
                # Call function and verify result
                result = aws_module.generate_text_translation(text, source_lang, target_lang)
                assert result == 'Hola, mundo!'
    
    def test_generate_text_translation_error(self, translate_client, translate_stubber):
        # Test parameters
        text = "Hello, world!"
        source_lang = "en"
        target_lang = "invalid-lang"
        
        # Setup stubber with expected params and error response
        expected_params = {
            'Text': text,
            'SourceLanguageCode': source_lang,
            'TargetLanguageCode': target_lang
        }
        translate_stubber.add_client_error(
            'translate_text',
            service_error_code='UnsupportedLanguagePairException',
            service_message='Language pair not supported',
            expected_params=expected_params
        )
        
        # Patch the boto3 client to use our stubbed client
        with patch.object(aws_module, 'translate_client', translate_client):
            with translate_stubber:
                # Call function and verify exception
                with pytest.raises(HTTPException) as excinfo:
                    aws_module.generate_text_translation(text, source_lang, target_lang)
                
                assert excinfo.value.status_code == 500
                assert "Failed to translate text" in str(excinfo.value.detail)


# Tests for S3 functionality
class TestS3:
    def test_generate_presigned_url_success(self, s3_client, s3_stubber, monkeypatch):
        # Test parameters
        bucket = "audio"
        object_key = "s3://test-audio-bucket/test.mp3"
        expected_clean_key = "test.mp3"
    
        # Mock response for generate_presigned_url
        mock_url = "https://test-audio-bucket.s3.amazonaws.com/test.mp3?AWSAccessKeyId=..."
        mock_generate_url = MagicMock(return_value=mock_url)

        monkeypatch.setattr(s3_client, 'generate_presigned_url', mock_generate_url)
        monkeypatch.setattr(aws_module, 's3_client', s3_client)

        with s3_stubber:
            # Call function
            result = aws_module.generate_presigned_url(bucket, object_key)
            
            # Verify results
            assert result == mock_url
            mock_generate_url.assert_called_once_with(
                'get_object',
                Params={'Bucket': 'test-audio-bucket', 'Key': expected_clean_key},
                ExpiresIn=3600
            )
    
    def test_generate_presigned_url_error(self, s3_client):
        # Test parameters
        bucket = "audio"
        object_key = "s3://test-audio-bucket/test.mp3"
        
        # Mock generate_presigned_url to raise an exception
        with patch.object(s3_client, 'generate_presigned_url', side_effect=Exception("Connection error")):
            with patch.object(aws_module, 's3_client', s3_client):
                # Call function and verify exception
                with pytest.raises(HTTPException) as excinfo:
                    aws_module.generate_presigned_url(bucket, object_key)
                
                assert excinfo.value.status_code == 500
                assert "Failed to generate presigned URL" in str(excinfo.value.detail)
    
    def test_create_s3_subdirectory_success(self, s3_client, s3_stubber):
        # Test parameters
        bucket_name = "lecture-content"
        directory = "materials/test-course/"
        
        # Expected params for put_object call
        expected_params = {
            'Bucket': bucket_name,
            'Key': directory
        }
        
        # Add response to stubber
        s3_stubber.add_response('put_object', {}, expected_params)
        
        # Call function with stubbed client
        with patch.object(aws_module, 's3_client', s3_client):
            with s3_stubber:
                aws_module.create_s3_subdirectory(bucket_name, directory)
                # No assertion needed - function succeeds if no exception
    
    def test_create_s3_subdirectory_no_credentials(self, s3_client, s3_stubber):
        # Test parameters
        bucket_name = "lecture-content"
        directory = "materials/test-course/"

        from botocore.exceptions import NoCredentialsError
        s3_client.put_object = MagicMock(side_effect=NoCredentialsError)
        
        # Call function with stubbed client
        with patch.object(aws_module, 's3_client', s3_client):
            with pytest.raises(HTTPException) as excinfo:
                aws_module.create_s3_subdirectory(bucket_name, directory)
            
            assert excinfo.value.status_code == 403
            assert "S3 credentials are not available" in str(excinfo.value.detail)
    
    @pytest.mark.asyncio
    async def test_setup_s3_directory_success(self, s3_client, s3_stubber):
        # Test parameters
        s3_bucket = 'test-bucket'
        course_id = "test-course-id"
        directory = f"materials/{course_id}/"
        
        # Expected params for put_object call
        expected_params = {
            'Bucket': s3_bucket,
            'Key': directory
        }
        
        # Add response to stubber
        s3_stubber.add_response('put_object', {}, expected_params)
        
        # Call function with stubbed client and patched ic
        with patch.object(aws_module, 's3_client', s3_client):
            with s3_stubber:
                await aws_module.setup_s3_directory(course_id, s3_bucket)
    
    @pytest.mark.asyncio
    async def test_setup_s3_directory_error(self, s3_client, s3_stubber):
        # Test parameters
        s3_bucket = 'test-bucket'
        course_id = "test-course-id"
        directory = f"materials/{course_id}/"
        
        # Expected params for put_object call
        expected_params = {
            'Bucket': s3_bucket,
            'Key': directory
        }
        
        # Add error to stubber
        s3_stubber.add_client_error(
            'put_object',
            service_error_code='InternalError',
            service_message='Internal S3 error',
            expected_params=expected_params
        )
        
        # Call function with stubbed client and patched ic
        with patch.object(aws_module, 's3_client', s3_client):
            with s3_stubber:
                with pytest.raises(HTTPException) as excinfo:
                    await aws_module.setup_s3_directory(course_id, s3_bucket)
                
                assert excinfo.value.status_code == 500
                assert "Error creating S3 subdirectory" in str(excinfo.value.detail)
    
    def test_upload_to_s3_success(self, s3_client, s3_stubber):
        # Test parameters
        bucket = "audio"
        object_name = "test-dir/test.mp3"
        bucket_name = "test-audio-bucket"
        
        # Mock the upload_file method directly since it's not an API call that can be stubbed
        with tempfile.NamedTemporaryFile(suffix=".mp3") as audio_file, \
             patch.object(aws_module, 's3_client', s3_client), \
             patch.object(s3_client, 'upload_file') as mock_upload_file:
            file_path = audio_file.name
            # Call function
            result = aws_module.upload_to_s3(bucket, file_path, object_name)
            
            # Verify results
            mock_upload_file.assert_called_once_with(
                file_path,
                bucket_name,
                object_name
            )
            assert result == f's3://{bucket_name}/{object_name}'
    
    def test_upload_to_s3_type_error(self, s3_client):
        # Test parameters
        bucket = "audio"
        file_path = 123  # Should be string
        object_name = "test.mp3"
        
        # Call function
        with patch.object(aws_module, 's3_client', s3_client):
            with pytest.raises(TypeError) as excinfo:
                aws_module.upload_to_s3(bucket, file_path, object_name)
            
            assert "Expected string for file_path" in str(excinfo.value)
    
    @pytest.mark.asyncio
    async def test_delete_from_s3_success(self, s3_client, s3_stubber):
        # Test parameters
        bucket = "audio"
        s3_uri = "s3://test-audio-bucket/test.mp3"
        object_key = "test.mp3"
        
        # Expected params for delete_object call
        expected_params = {
            'Bucket': "test-audio-bucket",
            'Key': object_key
        }
        
        # Add response to stubber
        s3_stubber.add_response('delete_object', {}, expected_params)
        
        # Call function with stubbed client
        with patch.object(aws_module, 's3_client', s3_client):
            with s3_stubber:
                await aws_module.delete_from_s3(bucket, s3_uri)
                # No assertion needed - function succeeds if no exception
    
    @pytest.mark.asyncio
    async def test_delete_from_s3_error(self, s3_client, s3_stubber):
        # Test parameters
        bucket = "audio"
        s3_uri = "s3://test-audio-bucket/test.mp3"
        object_key = "test.mp3"
        
        # Expected params for delete_object call
        expected_params = {
            'Bucket': "test-audio-bucket",
            'Key': object_key
        }
        
        # Add error to stubber
        s3_stubber.add_client_error(
            'delete_object',
            service_error_code='NoSuchKey',
            service_message='The specified key does not exist',
            expected_params=expected_params
        )
        
        # Call function with stubbed client
        with patch.object(aws_module, 's3_client', s3_client):
            with s3_stubber:
                with pytest.raises(HTTPException) as excinfo:
                    await aws_module.delete_from_s3(bucket, s3_uri)
                
                assert excinfo.value.status_code == 500
                assert "Failed to delete file from S3" in str(excinfo.value.detail)


# Tests for Polly functionality
class TestPolly:
    @pytest.mark.asyncio
    async def test_synthesize_speech_success(self, polly_client, polly_stubber):
        # Test parameters
        text = "Hello, world!"
        voice_id = "Joanna"
        language_code = "en-US"
        
        # Create mock audio stream data
        audio_data = b"fake audio data"
        audio_stream = io.BytesIO(audio_data)
        
        # Expected params for synthesize_speech call
        expected_params = {
            'Text': text,
            'VoiceId': voice_id,
            'OutputFormat': 'mp3',
            'LanguageCode': language_code,
            'Engine': 'neural'
        }
        
        # Create response with streaming body
        response = {
            'AudioStream': botocore.response.StreamingBody(
                raw_stream=audio_stream,
                content_length=len(audio_data)
            ),
            'ContentType': 'audio/mp3'
        }
        
        # Add response to stubber
        polly_stubber.add_response('synthesize_speech', response, expected_params)
        
        # This is the key part - we need to mock the actual iteration of AudioStream chunks
        # In the real code it's likely using .iter_chunks() on the AudioStream
        mock_audio_stream = MagicMock()
        mock_audio_stream.iter_chunks.return_value = [audio_data]
        mock_response = {
            'AudioStream': mock_audio_stream, 
            'ContentType': 'audio/mp3'
        }
        
        # Mock NamedTemporaryFile to return our mock object when used as a context manager
        with patch.object(aws_module, 'polly_client', polly_client), \
             patch('asyncio.to_thread', return_value=mock_response):
            
            with polly_stubber:
                temp_audio_file_path = await aws_module.synthesize_speech(text, voice_id, language_code)
                
                # Verify that temp file was written to with our audio data
                with open(temp_audio_file_path, 'rb') as f:
                    assert f.read() == audio_data

    @pytest.mark.asyncio
    async def test_get_polly_voices_success(self, polly_client, polly_stubber):
        # Test parameters
        language_code = "en-US"
        
        # Expected params for describe_voices call
        expected_params = {
            'Engine': 'neural',
            'LanguageCode': language_code
        }
        
        # Create response with voice list
        response = {
            'Voices': [
                {'Id': 'Joanna', 'Name': 'Joanna'},
                {'Id': 'Matthew', 'Name': 'Matthew'}
            ]
        }
        
        # Add response to stubber
        polly_stubber.add_response('describe_voices', response, expected_params)
        
        # Create an async mock for asyncio.to_thread
        async_mock = AsyncMock(return_value=response)
        
        # Call function with stubbed client
        with patch.object(aws_module, 'polly_client', polly_client), \
             patch('asyncio.to_thread', async_mock):
            with polly_stubber:
                result = await aws_module.get_polly_voices(language_code)
                
                # Verify results
                assert result == ['Joanna', 'Matthew']
                
                # Verify that asyncio.to_thread was called with the right parameters
                async_mock.assert_called_once_with(
                    polly_client.describe_voices,
                    Engine='neural',
                    LanguageCode=language_code
                )


# Tests for Transcribe functionality
class TestTranscribe:
    def test_start_transcription_success(self, transcribe_client, transcribe_stubber):
        # Test parameters
        s3_uri = "s3://test-audio-bucket/test.mp3"
        job_name = "test-job-123"
        language_code = "en-US"
        
        # Expected params for start_transcription_job call
        expected_params = {
            'TranscriptionJobName': job_name,
            'Media': {'MediaFileUri': s3_uri},
            'MediaFormat': 'mp3',
            'LanguageCode': language_code
        }
        
        # Create response
        response = {
            'TranscriptionJob': {
                'TranscriptionJobName': job_name,
                'TranscriptionJobStatus': 'IN_PROGRESS'
            }
        }
        
        # Add response to stubber
        transcribe_stubber.add_response('start_transcription_job', response, expected_params)
        
        # Call function with stubbed client
        with patch.object(aws_module, 'transcribe_client', transcribe_client):
            with transcribe_stubber:
                result = aws_module.start_transcription(s3_uri, job_name, language_code)
                
                # Verify response is returned correctly
                assert result == response
    
    @pytest.mark.asyncio
    async def test_fetch_transcription_job_success(self, transcribe_client, transcribe_stubber):
        # Test parameters
        job_name = "test-job-123"
        
        # Expected params for get_transcription_job call
        expected_params = {
            'TranscriptionJobName': job_name
        }
        
        # Create response
        response = {
            'TranscriptionJob': {
                'TranscriptionJobName': job_name,
                'TranscriptionJobStatus': 'COMPLETED',
                'Transcript': {
                    'TranscriptFileUri': 'https://s3.amazonaws.com/bucket/transcript.json'
                }
            }
        }
        
        # Add response to stubber
        transcribe_stubber.add_response('get_transcription_job', response, expected_params)
        
        # Call function with stubbed client
        with patch.object(aws_module, 'transcribe_client', transcribe_client):
            with transcribe_stubber:
                result = await aws_module.fetch_transcription_job(job_name)
                
                # Verify response is returned correctly
                assert result == response['TranscriptionJob']
    
    @pytest.mark.asyncio
    async def test_update_transcription_status_completed(self):
        # Create mock transcription object
        mock_transcription = MagicMock()
        mock_transcription.status = None
        mock_transcription.completed_at = None
        
        # Test with COMPLETED status
        await aws_module.update_transcription_status(mock_transcription, "COMPLETED")
        
        # Verify status and completed_at were updated
        assert mock_transcription.status == "COMPLETED"
        assert isinstance(mock_transcription.completed_at, datetime)
    
    @pytest.mark.asyncio
    async def test_update_transcription_status_other(self):
        # Create mock transcription object
        mock_transcription = MagicMock()
        mock_transcription.status = None
        mock_transcription.completed_at = None
        
        # Test with IN_PROGRESS status
        await aws_module.update_transcription_status(mock_transcription, "IN_PROGRESS")
        
        # Verify status was updated but not completed_at
        assert mock_transcription.status == "IN_PROGRESS"
        assert mock_transcription.completed_at is None
    
    @pytest.mark.asyncio
    async def test_fetch_and_save_transcript_success(self, mock_db):
        # Mock data
        mock_transcription = MagicMock()
        mock_transcription.transcription_text = None  # Ensure the attribute is writable
        transcript_uri = "https://s3.amazonaws.com/bucket/transcript.json"

        # Mock transcription JSON data
        transcript_json = {
            'results': {
                'transcripts': [
                    {'transcript': 'This is the transcribed text.'}
                ]
            }
        }

        # Mock the requests.get call
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = transcript_json

        # Call function with patched requests.get
        with patch.object(requests, 'get', return_value=mock_response):
            # Call function
            await aws_module.fetch_and_save_transcript(mock_transcription, transcript_uri, mock_db)
            
            # Verify that the transcription_text attribute was updated
            assert mock_transcription.transcription_text == 'This is the transcribed text.'
            # Verify that commit was called on the database
            mock_db.commit.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_fetch_and_save_transcript_error(self, mock_db):
        # Mock data
        mock_transcription = MagicMock()
        transcript_uri = "https://s3.amazonaws.com/bucket/transcript.json"
        
        # Mock the requests.get call with error status code
        mock_response = MagicMock()
        mock_response.status_code = 404
        
        # Call function with patched requests.get
        with patch.object(requests, 'get', return_value=mock_response):
            with pytest.raises(RuntimeError) as excinfo:
                await aws_module.fetch_and_save_transcript(mock_transcription, transcript_uri, mock_db)
            
            # Verify error message
            assert "Failed to fetch transcript: 404" in str(excinfo.value)

# Tests for Cognito functionality
class TestCognito:
    def test_create_cognito_and_db_user_success(self, cognito_client, cognito_stubber, mock_db):
        # Test parameters
        user_data = {
            "email": "test@example.com",
            "password": "Password123!",
            "given_name": "Test",
            "family_name": "User",
            "locale": "en-US",
            "role": "student"
        }
        
        # Expected params and responses for Cognito API calls
        create_params = {
            'UserPoolId': ANY,  # We don't know the exact value, use ANY matcher
            'Username': user_data["email"],
            'UserAttributes': [
                {"Name": "email", "Value": user_data["email"]},
                {"Name": "given_name", "Value": user_data["given_name"]},
                {"Name": "family_name", "Value": user_data["family_name"]},
                {"Name": "locale", "Value": user_data["locale"]},
                {"Name": "email_verified", "Value": "true"}
            ],
            'MessageAction': 'SUPPRESS',
            'DesiredDeliveryMediums': ['EMAIL']
        }
        
        create_response = {
            'User': {
                'Username': 'cognito-user-id',
                'Attributes': [
                    {'Name': 'email', 'Value': user_data["email"]}
                ]
            }
        }
        
        password_params = {
            'UserPoolId': ANY,
            'Username': user_data["email"],
            'Password': user_data["password"],
            'Permanent': True
        }
        
        password_response = {}
        
        # Add responses to stubber
        cognito_stubber.add_response('admin_create_user', create_response, create_params)
        cognito_stubber.add_response('admin_set_user_password', password_response, password_params)
        
        # Patch the user pool ID
        with patch.object(aws_module, 'cognito_client', cognito_client), \
             patch.object(aws_module, 'user_pool_id', 'test-user-pool-id'), \
             patch('utility.aws.create_user', return_value=MagicMock()) as mock_create_user:
            with cognito_stubber:
                result = aws_module.create_cognito_and_db_user(user_data, mock_db)
                
                # Verify results
                assert "User created successfully" in result
                mock_create_user.assert_called_once()

    def test_create_cognito_and_db_user_error(self, cognito_client, cognito_stubber, mock_db):
        """Test error handling in Cognito user creation"""
        # Test parameters
        user_data = {
            "email": "test@example.com",
            "password": "Password123!",
            "given_name": "Test",
            "family_name": "User",
            "locale": "en-US",
            "role": "student"
        }
        
        # Expected params for the Cognito API call
        create_params = {
            'UserPoolId': ANY,
            'Username': user_data["email"],
            'UserAttributes': [
                {"Name": "email", "Value": user_data["email"]},
                {"Name": "given_name", "Value": user_data["given_name"]},
                {"Name": "family_name", "Value": user_data["family_name"]},
                {"Name": "locale", "Value": user_data["locale"]},
                {"Name": "email_verified", "Value": "true"}
            ],
            'MessageAction': 'SUPPRESS',
            'DesiredDeliveryMediums': ['EMAIL']
        }
        
        # Add client error response
        cognito_stubber.add_client_error(
            'admin_create_user',
            service_error_code='UsernameExistsException',
            service_message='User already exists',
            expected_params=create_params
        )
        
        # Call function with stubbed client
        with patch.object(aws_module, 'cognito_client', cognito_client), \
             patch.object(aws_module, 'user_pool_id', 'test-user-pool-id'):
            with cognito_stubber, pytest.raises(ClientError) as excinfo:
                aws_module.create_cognito_and_db_user(user_data, mock_db)
            
            # Verify error was caught with proper message
            assert "UsernameExistsException" in str(excinfo.value)
            assert "User already exists" in str(excinfo.value)


# Tests for SES email functionality
class TestSES:
    def test_send_invite_email_success(self, ses_client, ses_stubber):
        """Test successful invite email sending"""
        # Test parameters
        email = "student@example.com"
        invite_url = "https://example.com/invite/123456"
        course_name = "Test Course"
        
        # Expected params for send_email call (partial matching)
        expected_params = {
            'Source': ANY,
            'Destination': {
                'ToAddresses': [email],
            },
            'Message': {
                'Subject': {
                    'Data': f"Invitation to join {course_name}",
                    'Charset': 'UTF-8'
                },
                'Body': {
                    'Html': {
                        'Data': ANY,
                        'Charset': 'UTF-8'
                    }
                }
            }
        }
        
        # Response for send_email
        response = {
            'MessageId': 'message-id-123456'
        }
        
        # Add response to stubber
        ses_stubber.add_response('send_email', response, expected_params)
        
        # Call function with stubbed client
        with patch.object(aws_module, 'ses_client', ses_client):
            with ses_stubber:
                aws_module.send_invite_email(email, invite_url, course_name)
    
    def test_send_invite_email_error(self, ses_client, ses_stubber):
        """Test error handling in invite email sending"""
        # Test parameters
        email = "invalid@example.com"
        invite_url = "https://example.com/invite/123456"
        course_name = "Test Course"
        
        # Expected params for send_email call (partial matching)
        expected_params = {
            'Source': ANY,
            'Destination': {
                'ToAddresses': [email],
            },
            'Message': ANY
        }
        
        # Add client error response
        ses_stubber.add_client_error(
            'send_email',
            service_error_code='MessageRejected',
            service_message='Email address not verified',
            expected_params=expected_params
        )
        
        # Call function with stubbed client
        with patch.object(aws_module, 'ses_client', ses_client):
            with ses_stubber, pytest.raises(ClientError) as excinfo:
                aws_module.send_invite_email(email, invite_url, course_name)
            
            # Verify error message
            assert "MessageRejected" in str(excinfo.value)
            assert "Email address not verified" in str(excinfo.value)


# Tests for Step Function operations
class TestStepFunctions:
    def test_start_step_function_success(self, sf_client, sf_stubber, sts_stubber):
        """Test successful step function execution start"""
        # Test parameters
        input_data = {"course_id": "test-course-id"}
        
        # Mock STS get_caller_identity response
        sts_stubber.add_response(
            'get_caller_identity',
            {'Account': '123456789012'},
            {}
        )
        
        # Expected params for start_execution call
        expected_params = {
            'stateMachineArn': 'arn:aws:states:us-east-1:123456789012:stateMachine:CreateKnowledgeBaseInfrastructure',
            'input': json.dumps(input_data)
        }
        
        # Response for start_execution
        response = {
            'executionArn': 'arn:aws:states:us-east-1:123456789012:execution:StateMachine:execution-id',
            'startDate': datetime.now()
        }
        
        # Add response to stubber
        sf_stubber.add_response('start_execution', response, expected_params)
        
        # Call function with stubbed clients
        with patch.object(aws_module, 'sf_client', sf_client), \
             patch.object(aws_module, 'sts_client', sts_stubber.client), \
             patch.object(aws_module, 'region_name', 'us-east-1'):
            with sf_stubber, sts_stubber:
                result = aws_module.start_step_function(input_data)
                
                # Verify results
                assert result is not None
                assert result['executionArn'] == response['executionArn']
    
    def test_start_step_function_error(self, sf_client, sf_stubber):
        """Test error handling in step function execution start"""
        # Test parameters
        input_data = {"course_id": "test-course-id"}
        account_number = '123456789012'
        
        # Mock STS get_caller_identity response
        mock_sts_client = MagicMock()
        mock_sts_client.get_caller_identity.return_value = {'Account': account_number}
        
        # Expected params for start_execution call
        expected_params = {
            'stateMachineArn': f'arn:aws:states:us-east-1:{account_number}:stateMachine:CreateKnowledgeBaseInfrastructure',
            'input': json.dumps(input_data)
        }
        
        # Add client error response
        sf_stubber.add_client_error(
            'start_execution',
            service_error_code='StateMachineDoesNotExist',
            service_message='State machine does not exist',
            expected_params=expected_params
        )
        
        # Call function with stubbed client
        with patch.object(aws_module, 'sf_client', sf_client), \
             patch.object(aws_module, 'region_name', 'us-east-1'), \
             patch('boto3.client', return_value=mock_sts_client):
            with sf_stubber:
                result = aws_module.start_step_function(input_data)
                
                # Verify result is None on error
                assert result is None

    def test_get_execution_details_success(self, sf_client, sf_stubber):
        """Test successful retrieval of step function execution details"""
        # Test parameters
        execution_arn = "arn:aws:states:us-east-1:123456789012:execution:state-machine:execution-id"
        
        # Expected params for describe_execution call
        describe_params = {
            'executionArn': execution_arn
        }
        
        # Response for describe_execution
        describe_response = {
            'executionArn': execution_arn,
            'stateMachineArn': 'arn:aws:states:us-east-1:123456789012:stateMachine:state-machine',
            'name': 'execution-id',
            'status': 'SUCCEEDED',
            'startDate': datetime.now(),
            'stopDate': datetime.now(),
            'input': '{"course_id":"test-course-id"}',
            'output': '{"knowledge_base_id":"kb-123", "data_source_id":"ds-123"}'
        }
        
        # Expected params for get_execution_history call
        history_params = {
            'executionArn': execution_arn,
            'maxResults': 100,
            'reverseOrder': True
        }
        
        # Response for get_execution_history
        history_response = {
            'events': [
                {
                    'timestamp': datetime.now(),
                    'type': 'ExecutionSucceeded',
                    'id': 1,
                    'previousEventId': 0,
                },
                {
                    'timestamp': datetime.now() - timedelta(seconds=5),
                    'type': 'StateExited',
                    'id': 2,
                    'previousEventId': 1,
                    'stateExitedEventDetails': {
                        'name': 'FinalState',
                        'output': '{"result":"success"}'
                    }
                }
            ]
        }
        
        # Add responses to stubber
        sf_stubber.add_response('describe_execution', describe_response, describe_params)
        sf_stubber.add_response('get_execution_history', history_response, history_params)
        
        # Call function with stubbed client
        with patch.object(aws_module, 'sf_client', sf_client):
            with sf_stubber:
                result = aws_module.get_execution_details(execution_arn)
                
                # Verify results
                assert result["execution_status"] == "SUCCEEDED"
                assert result["current_state"] == "FinalState"
                assert result["state_status"] == "SUCCEEDED"
                assert result["execution_output"] == {"knowledge_base_id":"kb-123", "data_source_id":"ds-123"}
    
    def test_get_execution_details_error(self, sf_client, sf_stubber):
        """Test error handling in step function execution details retrieval"""
        # Test parameters
        execution_arn = "arn:aws:states:us-east-1:123456789012:execution:state-machine:invalid-id"
        
        # Expected params for describe_execution call
        describe_params = {
            'executionArn': execution_arn
        }
        
        # Add client error response
        sf_stubber.add_client_error(
            'describe_execution',
            service_error_code='ExecutionDoesNotExist',
            service_message='Execution does not exist',
            expected_params=describe_params
        )
        
        # Call function with stubbed client
        with patch.object(aws_module, 'sf_client', sf_client):
            with sf_stubber, pytest.raises(ClientError) as excinfo:
                aws_module.get_execution_details(execution_arn)
            
            # Verify error was passed through
            assert "ExecutionDoesNotExist" in str(excinfo.value)


# Tests for Knowledge Base operations
class TestKnowledgeBase:
    @pytest.mark.asyncio
    async def test_generate_course_summary_success(self, mock_db):
        """Test successful course summary generation"""
        # Test parameters
        course_id = "test-course-id"
        knowledge_base_id = "kb-123"
        
        # Sample response from retrieve_and_generate
        response = {
            "text": """<summary_output>
            This course covers the fundamentals of machine learning algorithms.
            </summary_output>"""
        }
        
        # Call function with patched dependencies
        with patch('utility.aws.retrieve_and_generate', return_value=response), \
             patch('utility.aws.update_course_field') as mock_update_course_field:
            result = await aws_module.generate_course_summary(mock_db, course_id, knowledge_base_id)
            
            # Verify results
            assert result.strip() == "This course covers the fundamentals of machine learning algorithms."
            mock_update_course_field.assert_called_once_with(
                mock_db, course_id, "description", result
            )
    
    @pytest.mark.asyncio
    async def test_generate_course_summary_no_tags(self, mock_db):
        """Test course summary generation when response doesn't have summary tags"""
        # Test parameters
        course_id = "test-course-id"
        knowledge_base_id = "kb-123"
        
        # Sample response without tags
        response = {
            "text": "This course covers the fundamentals of machine learning algorithms."
        }
        
        # Call function with patched dependencies
        with patch('utility.aws.retrieve_and_generate', return_value=response), \
             patch('utility.aws.update_course_field') as mock_update_course_field:
            result = await aws_module.generate_course_summary(mock_db, course_id, knowledge_base_id)
            
            # Verify results - should use the full text if no tags found
            assert result == "This course covers the fundamentals of machine learning algorithms."
            mock_update_course_field.assert_called_once_with(
                mock_db, course_id, "description", result
            )
    
    @pytest.mark.asyncio
    async def test_generate_course_summary_error(self, mock_db, capsys):
        """Test error handling in course summary generation"""
        # Test parameters
        course_id = "test-course-id"
        knowledge_base_id = "kb-123"
        
        # Call function with patched dependencies to raise an error
        with patch('utility.aws.retrieve_and_generate', side_effect=Exception("API error")):
            with pytest.raises(Exception) as excinfo:
                await aws_module.generate_course_summary(mock_db, course_id, knowledge_base_id)
            
            # Verify error was passed through
            assert "API error" in str(excinfo.value)
            capture = capsys.readouterr()
            assert "Error generating course summary" in capture.out
    
    @pytest.mark.asyncio
    async def test_generate_course_questions_success(self, mock_db):
        """Test successful course questions generation"""
        # Test parameters
        course_id = "test-course-id"
        knowledge_base_id = "kb-123"
        
        # Sample response from retrieve_and_generate
        response = {
            "text": """<questions_output>
            1. What are the key machine learning algorithms?
            2. How does backpropagation work?
            3. What is gradient descent?
            4. Explain overfitting
            5. What are support vector machines?
            </questions_output>"""
        }
        
        expected_questions = [
            "What are the key machine learning algorithms?",
            "How does backpropagation work?",
            "What is gradient descent?",
            "Explain overfitting?",
            "What are support vector machines?"
        ]
        
        # Call function with patched dependencies
        with patch('utility.aws.retrieve_and_generate', return_value=response), \
             patch('utility.aws.update_course_questions') as mock_update_course_questions:
            result = await aws_module.generate_course_questions(mock_db, course_id, knowledge_base_id)
            
            # Verify results - clean questions with numbers removed
            assert len(result) == 5
            assert all(q in expected_questions for q in result)
            mock_update_course_questions.assert_called_once_with(mock_db, course_id, result)
    
    @pytest.mark.asyncio
    async def test_generate_course_questions_no_valid_questions(self, mock_db):
        """Test error handling when no valid questions are generated"""
        # Test parameters
        course_id = "test-course-id"
        knowledge_base_id = "kb-123"
        
        # Sample response with no proper questions
        response = {
            "text": """<questions_output>
            - -^^
            - %&$
            </questions_output>"""
        }
        
        # Call function with patched dependencies
        with patch('utility.aws.retrieve_and_generate', return_value=response):
            with pytest.raises(ValueError) as excinfo:
                await aws_module.generate_course_questions(mock_db, course_id, knowledge_base_id)
            
            # Verify error message
            assert "No valid questions were generated" in str(excinfo.value)


# Tests for Ingestion Job operations
class TestIngestionJobs:
    @pytest.mark.asyncio
    async def test_start_ingestion_job_success(self, bedrock_agent_client, bedrock_agent_stubber):
        """Test successful start of ingestion job"""
        # Test parameters
        knowledge_base_id = "kb-123"
        data_source_id = "ds-456"
        
        # Expected params for start_ingestion_job call
        expected_params = {
            'clientToken': ANY,  # Using ANY since this is a UUID that changes
            'dataSourceId': data_source_id,
            'knowledgeBaseId': knowledge_base_id,
            'description': 'Ingesting data for knowledge base synchronization'
        }
        
        # Response for start_ingestion_job
        response = {
            'ingestionJob': {
                'ingestionJobId': 'job-123',
                'dataSourceId': data_source_id,
                'knowledgeBaseId': knowledge_base_id,
                'status': 'STARTING',
                'startedAt': datetime(2021, 9, 1, 12, 0, 0),
                'updatedAt': datetime(2021, 9, 1, 12, 0, 0)
            }
        }
        
        # Add response to stubber
        bedrock_agent_stubber.add_response('start_ingestion_job', response, expected_params)
        
        # Call function with stubbed client
        with patch.object(aws_module, 'bedrock_agent_client', bedrock_agent_client):
            with bedrock_agent_stubber:
                result = await aws_module.start_ingestion_job(knowledge_base_id, data_source_id)
                
                # Verify results
                assert result == response['ingestionJob']
    
    @pytest.mark.asyncio
    async def test_start_ingestion_job_error(self, bedrock_agent_client, bedrock_agent_stubber):
        """Test error handling for ingestion job start"""
        # Test parameters
        knowledge_base_id = "kb-123"
        data_source_id = "invalid-ds"
        
        # Expected params for start_ingestion_job call
        expected_params = {
            'clientToken': ANY,
            'dataSourceId': data_source_id,
            'knowledgeBaseId': knowledge_base_id,
            'description': 'Ingesting data for knowledge base synchronization'
        }
        
        # Add client error response
        bedrock_agent_stubber.add_client_error(
            'start_ingestion_job',
            service_error_code='ResourceNotFoundException',
            service_message='Data source not found',
            expected_params=expected_params
        )
        
        # Call function with stubbed client
        with patch.object(aws_module, 'bedrock_agent_client', bedrock_agent_client):
            with bedrock_agent_stubber, pytest.raises(HTTPException) as excinfo:
                await aws_module.start_ingestion_job(knowledge_base_id, data_source_id)
            
            # Verify error was caught and transformed to HTTPException
            assert excinfo.value.status_code == 500
            assert "Error starting ingestion job" in str(excinfo.value.detail)
            assert "ResourceNotFoundException" in str(excinfo.value.detail)
    
    @pytest.mark.asyncio
    async def test_get_ingestion_summary_success(self, bedrock_agent_client, bedrock_agent_stubber):
        """Test successful retrieval of ingestion summary"""
        # Test parameters
        knowledge_base_id = "kb-123"
        data_source_id = "ds-456"
        ingestion_job_id = "job-123"
        
        # Expected params for get_ingestion_job call
        expected_params = {
            'knowledgeBaseId': knowledge_base_id,
            'dataSourceId': data_source_id,
            'ingestionJobId': ingestion_job_id
        }
        
        # Response for get_ingestion_job
        response = {
            'ingestionJob': {
                'ingestionJobId': ingestion_job_id,
                'dataSourceId': data_source_id,
                'knowledgeBaseId': knowledge_base_id,
                'status': 'COMPLETE',
                'statistics': {
                    'numberOfDocumentsScanned': 10,
                    'numberOfDocumentsFailed': 0
                },
                'startedAt': datetime(2021, 9, 1, 12, 0, 0),
                'updatedAt': datetime(2021, 9, 1, 12, 0, 0)
            }
        }
        
        # Add response to stubber
        bedrock_agent_stubber.add_response('get_ingestion_job', response, expected_params)
        
        # Call function with stubbed client
        with patch.object(aws_module, 'bedrock_agent_client', bedrock_agent_client):
            with bedrock_agent_stubber:
                result = await aws_module.get_ingestion_summary(knowledge_base_id, data_source_id, ingestion_job_id)
                
                # Verify results
                assert result == response['ingestionJob']
    
    @pytest.mark.asyncio
    async def test_get_ingestion_summary_error(self, bedrock_agent_client, bedrock_agent_stubber):
        """Test error handling for ingestion summary retrieval"""
        # Test parameters
        knowledge_base_id = "kb-123"
        data_source_id = "ds-456"
        ingestion_job_id = "invalid-job"
        
        # Expected params for get_ingestion_job call
        expected_params = {
            'knowledgeBaseId': knowledge_base_id,
            'dataSourceId': data_source_id,
            'ingestionJobId': ingestion_job_id
        }
        
        # Add client error response
        bedrock_agent_stubber.add_client_error(
            'get_ingestion_job',
            service_error_code='ResourceNotFoundException',
            service_message='Ingestion job not found',
            expected_params=expected_params
        )
        
        # Call function with stubbed client
        with patch.object(aws_module, 'bedrock_agent_client', bedrock_agent_client):
            with bedrock_agent_stubber, pytest.raises(ClientError) as excinfo:
                await aws_module.get_ingestion_summary(knowledge_base_id, data_source_id, ingestion_job_id)
            
            # Verify error was passed through
            assert "ResourceNotFoundException" in str(excinfo.value)
            assert "Ingestion job not found" in str(excinfo.value)


# Tests for Preprocessing Jobs
@pytest.mark.asyncio
class TestPreprocessingJobs:
    @pytest.mark.asyncio
    async def test_run_preprocessing_job_success(self, sf_client, sf_stubber, sts_stubber):
        """Test successful run of preprocessing job"""
        # Test parameters
        input_data = {
            "files": [
                {"materialId": "mat-1", "s3Uri": "s3://bucket/file1.mp3"},
                {"materialId": "mat-2", "s3Uri": "s3://bucket/file2.mp4"}
            ]
        }
        execution_arn = "arn:aws:states:us-east-1:123456789012:execution:TestPreprocessingTranscriptions:execution-id"
        
        # Mock STS get_caller_identity response
        sts_stubber.add_response(
            'get_caller_identity',
            {'Account': '123456789012'},
            {}
        )
        
        # Expected params for start_execution call
        start_params = {
            'stateMachineArn': f"arn:aws:states:us-east-1:123456789012:stateMachine:TestPreprocessingTranscriptions",
            'input': json.dumps(input_data)
        }
        
        # Response for start_execution
        start_response = {
            'executionArn': execution_arn,
            'startDate': datetime.now()
        }
        
        # Expected params for describe_execution call (from wait_for_preprocessing_job)
        describe_params = {
            'executionArn': execution_arn
        }
        
        # Response for describe_execution
        describe_response = {
            'executionArn': execution_arn,
            'stateMachineArn': "arn:aws:states:us-east-1:123456789012:stateMachine:TestPreprocessingTranscriptions",
            'name': 'execution-id',
            'status': 'SUCCEEDED',
            'startDate': datetime.now(),
            'stopDate': datetime.now(),
            'output': json.dumps([
                {"materialId": "mat-1", "transcribedFileUri": "s3://bucket/file1.txt"},
                {"materialId": "mat-2", "transcribedFileUri": "s3://bucket/file2.txt"}
            ])
        }
        
        # Add responses to stubber
        sf_stubber.add_response('start_execution', start_response, start_params)
        sf_stubber.add_response('describe_execution', describe_response, describe_params)
        
        # Call function with stubbed clients and patched sleep
        with patch.object(aws_module, 'sf_client', sf_client), \
             patch.object(aws_module, 'sts_client', sts_stubber.client), \
             patch.object(aws_module, 'region_name', 'us-east-1'), \
             patch('utility.aws.get_execution_details', return_value={
                 'execution_status': 'SUCCEEDED',
                 'execution_output': [
                     {"materialId": "mat-1", "transcribedFileUri": "s3://bucket/file1.txt"},
                     {"materialId": "mat-2", "transcribedFileUri": "s3://bucket/file2.txt"}
                 ]
             }), \
             patch('asyncio.sleep'):
            with sf_stubber, sts_stubber:
                result = await aws_module.run_preprocessing_job(input_data)
                
                # Verify results
                assert len(result) == 2
                assert result[0]["materialId"] == "mat-1"
                assert result[1]["materialId"] == "mat-2"
                assert result[0]["transcribedFileUri"] == "s3://bucket/file1.txt"
    
    @pytest.mark.asyncio
    async def test_wait_for_preprocessing_job_timeout(self):
        """Test timeout in preprocessing job execution"""
        # Test parameters
        execution_arn = "arn:aws:states:us-east-1:123456789012:execution:TestPreprocessingTranscriptions:execution-id"
        n_of_jobs = 1  # Small number to make the test faster
        heartbeat_minutes = 1  # Use smallest integer value
        
        # Call function with patched get_execution_details to simulate RUNNING status
        with patch('utility.aws.get_execution_details', return_value={
                'execution_status': 'RUNNING'
             }), \
             patch('asyncio.sleep', new_callable=AsyncMock) as mock_sleep:  # Mock sleep to avoid actual waiting
            with pytest.raises(StepFunctionTimeoutError):
                await aws_module.wait_for_preprocessing_job(execution_arn, n_of_jobs, heartbeat_minutes)
            
            # Verify sleep was called with the expected delay
            assert mock_sleep.call_count > 0
            mock_sleep.assert_called_with(15)
    
    @pytest.mark.asyncio
    async def test_wait_for_preprocessing_job_failure(self):
        """Test failure in preprocessing job execution"""
        # Test parameters
        execution_arn = "arn:aws:states:us-east-1:123456789012:execution:TestPreprocessingTranscriptions:execution-id"
        n_of_jobs = 2
        
        # Call function with patched get_execution_details to simulate FAILED status
        # AND patch asyncio.sleep to avoid waiting
        with patch('utility.aws.get_execution_details', return_value={
                'execution_status': 'FAILED'
             }), \
             patch('asyncio.sleep', new_callable=AsyncMock) as mock_sleep:  # Mock asyncio.sleep
            
            # The test should raise StepFunctionExecutionError immediately
            with pytest.raises(StepFunctionExecutionError):
                await aws_module.wait_for_preprocessing_job(execution_arn, n_of_jobs)
                
            # Verify sleep was not called (execution should fail immediately)
            mock_sleep.assert_not_called()


# Tests for Text Extraction and Language Detection
class TestTextExtraction:
    def test_extract_text_from_image_success(self, textract_client, textract_stubber):
        """Test successful text extraction from image"""
        # Create mock image bytes
        image_bytes = BytesIO(b"mock image data")
        
        # Expected params for detect_document_text call
        expected_params = {
            'Document': {
                'Bytes': image_bytes.getvalue()
            }
        }
        
        # Response for detect_document_text
        response = {
            'Blocks': [
                {
                    'BlockType': 'LINE',
                    'Text': 'This is line 1'
                },
                {
                    'BlockType': 'LINE',
                    'Text': 'This is line 2'
                },
                {
                    'BlockType': 'WORD',  # Should be ignored
                    'Text': 'Word'
                }
            ]
        }
        
        # Add response to stubber
        textract_stubber.add_response('detect_document_text', response, expected_params)
        
        # Call function with stubbed client
        with patch.object(aws_module, 'textract_client', textract_client):
            with textract_stubber:
                result = aws_module.extract_text_from_image(image_bytes)
                
                # Verify results
                assert result == "This is line 1\nThis is line 2"
    
    def test_extract_text_from_image_error(self, textract_client, textract_stubber):
        """Test error handling in text extraction from image"""
        # Create mock image bytes
        image_bytes = BytesIO(b"invalid image data")
        
        # Expected params for detect_document_text call
        expected_params = {
            'Document': {
                'Bytes': image_bytes.getvalue()
            }
        }
        
        # Add client error response
        textract_stubber.add_client_error(
            'detect_document_text',
            service_error_code='InvalidImageFormatException',
            service_message='The provided image format is not supported',
            expected_params=expected_params
        )
        
        # Call function with stubbed client
        with patch.object(aws_module, 'textract_client', textract_client):
            with textract_stubber:
                with pytest.raises(HTTPException) as excinfo:
                    aws_module.extract_text_from_image(image_bytes)
                
                # Verify the error was transformed into HTTPException
                assert excinfo.value.status_code == 500
                assert "Failed to extract text from image" in str(excinfo.value.detail)
    
    def test_extract_text_from_image_no_text(self, textract_client, textract_stubber):
        """Test extraction with no text found in the image"""
        # Create mock image bytes
        image_bytes = BytesIO(b"image with no text")
        
        # Expected params for detect_document_text call
        expected_params = {
            'Document': {
                'Bytes': image_bytes.getvalue()
            }
        }
        
        # Response for detect_document_text with no LINE blocks
        response = {
            'Blocks': [
                {
                    'BlockType': 'PAGE',  # Not a LINE type
                    'Text': ''
                }
            ]
        }
        
        # Add response to stubber
        textract_stubber.add_response('detect_document_text', response, expected_params)
        
        # Call function with stubbed client
        with patch.object(aws_module, 'textract_client', textract_client):
            with textract_stubber:
                result = aws_module.extract_text_from_image(image_bytes)
                
                # Verify results - should be an empty string
                assert result == ""


# Tests for Language Detection
class TestLanguageDetection:
    def test_detect_language_success(self, comprehend_client, comprehend_stubber):
        """Test successful language detection"""
        # Test parameters
        text = "Hello, this is a sample English text for language detection"
        
        # Expected params for detect_dominant_language call
        expected_params = {
            'Text': "Hello this is a sample English text for language detection"
        }
        
        # Response for detect_dominant_language
        response = {
            'Languages': [
                {
                    'LanguageCode': 'en',
                    'Score': 0.99
                },
                {
                    'LanguageCode': 'fr',
                    'Score': 0.01
                }
            ]
        }
        
        # Add response to stubber
        comprehend_stubber.add_response('detect_dominant_language', response, expected_params)
        
        # Call function with stubbed client and mocked langcodes
        with patch.object(aws_module, 'comprehend_client', comprehend_client), \
             patch('utility.aws.langcodes.Language.get') as mock_lang_get:
            
            # Mock langcodes.Language.get().display_name() to return "English"
            mock_lang = MagicMock()
            mock_lang.display_name.return_value = "English"
            mock_lang_get.return_value = mock_lang
            
            with comprehend_stubber:
                result = aws_module.detect_language(text)
                
                # Verify results
                assert result == "English"
                mock_lang_get.assert_called_once_with('en')
    
    def test_detect_language_with_special_chars(self, comprehend_client, comprehend_stubber):
        """Test language detection with text containing special characters"""
        # Test with text containing special characters
        text = "Hello, this is a test! With 123 numbers & special @#$% characters."
        expected_cleaned_text = "Hello this is a test With numbers special characters"
        
        # Expected params for detect_dominant_language call (after cleaning)
        # Note: Only first 30 words will be used
        expected_params = {
            'Text': expected_cleaned_text
        }
        
        # Response for detect_dominant_language
        response = {
            'Languages': [
                {
                    'LanguageCode': 'en',
                    'Score': 0.98
                }
            ]
        }
        
        # Add response to stubber
        comprehend_stubber.add_response('detect_dominant_language', response, expected_params)
        
        # Call function with stubbed client and mocked langcodes
        with patch.object(aws_module, 'comprehend_client', comprehend_client), \
             patch('utility.aws.langcodes.Language.get') as mock_lang_get:
            
            # Mock langcodes.Language.get().display_name() to return "English"
            mock_lang = MagicMock()
            mock_lang.display_name.return_value = "English"
            mock_lang_get.return_value = mock_lang
            
            with comprehend_stubber:
                result = aws_module.detect_language(text)
                
                # Verify results
                assert result == "English"
    
    def test_detect_language_error(self, comprehend_client, comprehend_stubber):
        """Test error handling in language detection"""
        # Test parameters
        text = "Text for testing error handling"
        
        # Expected params for detect_dominant_language call
        expected_params = {
            'Text': ANY  # Use ANY matcher since the text will be cleaned
        }
        
        # Add client error response
        comprehend_stubber.add_client_error(
            'detect_dominant_language',
            service_error_code='InternalServerException',
            service_message='Internal server error',
            expected_params=expected_params
        )
        
        # Call function with stubbed client
        with patch.object(aws_module, 'comprehend_client', comprehend_client):
            with comprehend_stubber, pytest.raises(HTTPException) as excinfo:
                aws_module.detect_language(text)
                
            # Verify the error was transformed to HTTPException
            assert excinfo.value.status_code == 500
            assert "Failed to detect language" in str(excinfo.value.detail)
    
    def test_detect_language_empty_text(self, comprehend_client, comprehend_stubber):
        """Test language detection with empty text"""
        # Test with very short text that becomes empty after cleaning
        text = "123!@#"  # This will become empty after removing non-alphabetic chars
        
        # Even with empty text, AWS SDK might still make the API call with whatever is provided
        # Expected params for detect_dominant_language call
        expected_params = {
            'Text': ANY  # Use ANY to match whatever text is sent
        }
        
        # Mock response with no detected languages
        response = {
            'Languages': []  # Empty languages list
        }
        
        # Add response to stubber
        comprehend_stubber.add_response('detect_dominant_language', response, expected_params)
        
        # Call function with stubbed client
        with patch.object(aws_module, 'comprehend_client', comprehend_client), \
             patch('utility.aws.langcodes.Language.get') as mock_lang_get:
            
            # Mock langcodes.Language.get().display_name() to not be called
            mock_lang_get.side_effect = Exception("This should not be called")
            
            with comprehend_stubber, pytest.raises(HTTPException) as excinfo:
                aws_module.detect_language(text)
            
            # Verify the error was raised
            assert excinfo.value.status_code == 500
            assert "Failed to detect language" in str(excinfo.value.detail)


# Tests for resource cleanup operations
class TestResourceCleanup:
    @pytest.mark.asyncio
    async def test_delete_resources_success(self, mock_db):
        """Test successful deletion of all AWS resources for a course"""
        # Test parameters
        course_id = "test-course-id"
        mock_course = MagicMock()
        mock_course.knowledge_base_id = "kb-123"
        
        # Create mock methods to verify they're called
        mock_delete_data_sources = MagicMock()
        mock_delete_iam_resources = MagicMock()
        mock_delete_opensearch_resources = MagicMock()
        mock_delete_s3_directory = MagicMock()
        
        # Call function with patched methods
        with patch('utility.aws.get_course', return_value=mock_course), \
             patch('utility.aws._delete_data_sources', mock_delete_data_sources), \
             patch('utility.aws._delete_iam_resources', mock_delete_iam_resources), \
             patch('utility.aws._delete_opensearch_resources', mock_delete_opensearch_resources), \
             patch('utility.aws._delete_s3_directory', mock_delete_s3_directory), \
             patch('utility.aws._generate_resource_names', return_value={
                'suffix': 'testcours', 
                'truncated_course_id': 'test-course-id', 
                'iam_policies': ['policy1', 'policy2'], 
                'execution_role': 'role1',
                'encryption_policy': 'encryption-policy',
                'network_policy': 'network-policy',
                'access_policy': 'access-policy',
                'vector_store': 'vector-store',
                's3_directory': f'materials/{course_id}/'
             }), \
             patch.object(aws_module, 'bedrock_agent_client') as mock_bedrock_agent:
            
            await aws_module.delete_resources(mock_db, course_id)
            
            # Verify all cleanup methods were called
            mock_delete_data_sources.assert_called_once_with("kb-123")
            mock_delete_iam_resources.assert_called_once_with('role1', ['policy1', 'policy2'])
            mock_delete_opensearch_resources.assert_called_once()
            mock_bedrock_agent.delete_knowledge_base.assert_called_once_with(knowledgeBaseId="kb-123")
            mock_delete_s3_directory.assert_called_once_with(f'materials/{course_id}/')
    
    @pytest.mark.asyncio
    async def test_delete_resources_with_errors(self, mock_db):
        """Test resource deletion with errors that are handled"""
        # Test parameters
        course_id = "test-course-id"
        mock_course = MagicMock()
        mock_course.knowledge_base_id = "kb-123"
        
        # Create a ClientError for knowledge base deletion
        kb_error = ClientError(
            error_response={"Error": {"Code": "ResourceNotFoundException", "Message": "KB not found"}},
            operation_name="DeleteKnowledgeBase"
        )
        
        # Call function with patched methods
        with patch('utility.aws.get_course', return_value=mock_course), \
             patch('utility.aws._delete_data_sources'), \
             patch('utility.aws._delete_iam_resources'), \
             patch('utility.aws._delete_opensearch_resources'), \
             patch('utility.aws._delete_s3_directory'), \
             patch('utility.aws._generate_resource_names', return_value={
                'suffix': 'testcours', 
                'truncated_course_id': 'test-course-id', 
                'iam_policies': ['policy1', 'policy2'], 
                'execution_role': 'role1',
                'encryption_policy': 'encryption-policy',
                'network_policy': 'network-policy',
                'access_policy': 'access-policy',
                'vector_store': 'vector-store',
                's3_directory': f'materials/{course_id}/'
             }), \
             patch.object(aws_module, 'bedrock_agent_client') as mock_bedrock_agent:
            
            # Set the delete_knowledge_base method to raise a ClientError
            mock_bedrock_agent.delete_knowledge_base.side_effect = kb_error
            
            # Should not raise exception even when knowledge base deletion fails
            await aws_module.delete_resources(mock_db, course_id)
            
            # Verify the delete was attempted
            mock_bedrock_agent.delete_knowledge_base.assert_called_once_with(knowledgeBaseId="kb-123")
    
    @pytest.mark.asyncio
    async def test_delete_resources_unexpected_error(self, mock_db):
        """Test resource deletion with an unexpected error that is propagated"""
        # Test parameters
        course_id = "test-course-id"
        
        # Call function with a patched method that raises an exception
        with patch('utility.aws.get_course', side_effect=Exception("Unexpected database error")):
            
            # Should propagate the exception
            with pytest.raises(Exception) as excinfo:
                await aws_module.delete_resources(mock_db, course_id)
            
            # Verify the error message
            assert "Unexpected database error" in str(excinfo.value)


# Add tests for helper private functions in aws.py
class TestHelperFunctions:
    def test_generate_resource_names(self):
        """Test the resource name generation helper"""
        # Test with a standard UUID
        course_id = "12345678-abcd-1234-5678-1234567890ab"
        
        # Call the function
        result = aws_module._generate_resource_names(course_id)
        
        # Verify results
        assert result['suffix'] == "12345678"  # First 8 chars of UUID without dashes
        assert result['truncated_course_id'] == "12345678-abcd"  # First 13 chars
        assert "AmazonBedrockFoundationModelPolicyForKnowledgeBase_12345678" in result['iam_policies']
        assert result['execution_role'] == "AmazonBedrockExecutionRoleForKnowledgeBase_12345678"
        assert result['encryption_policy'] == "bedrock-rag-sp-12345678"
        assert result['network_policy'] == "bedrock-rag-np-12345678"
        assert result['access_policy'] == "bedrock-rag-ap-12345678"
        assert result['vector_store'] == "bedrock-rag-12345678-abcd"
        assert result['s3_directory'] == f"materials/{course_id}/"