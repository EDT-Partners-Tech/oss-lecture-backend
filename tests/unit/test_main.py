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

from io import BytesIO
import json
import uuid
import tempfile
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch, ANY
import pytest
from fastapi.testclient import TestClient
from main import app, get_db
from database.models import User, UserRole
from utility.auth import oauth2_scheme
from utility.tokens import CognitoTokenPayload

# Mock user data for testing
TEST_USER_ID = "test-user-id"
TEST_COGNITO_ID = "test-cognito-id"
TEST_USER = User(id=TEST_USER_ID, cognito_id=TEST_COGNITO_ID, name="Test User", email="test@example.com", role=UserRole.teacher)

@pytest.fixture
def client(mock_cognito_token_payload):
    # Create a mock database session
    mock_db = MagicMock()
    mock_db.execute = MagicMock(return_value=MagicMock())
    mock_db.commit = MagicMock()
    mock_db.rollback = MagicMock()
    mock_db.close = MagicMock()
    
    # Mock the database query results
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = []
    mock_db.execute.return_value = mock_result
    
    # Override both get_db and oauth2_scheme
    app.dependency_overrides[get_db] = lambda: mock_db
    app.dependency_overrides[oauth2_scheme] = lambda: "fake-jwt-token"
    
    # Mock the token validation functions to return our test data
    with patch("utility.auth.jose_jwt.get_unverified_claims") as mock_get_claims:
        
        # Mock the unverified claims to return cognito format
        mock_get_claims.return_value = {"cognito:username": "test-user"}
        
        # Mock the validator to return our test token data
        mock_validator = AsyncMock()
        mock_validator.validate_token.return_value = mock_cognito_token_payload
    
        with patch.dict("utility.auth.VALIDATOR_MAP", {"cognito": mock_validator}):
            # Create test client
            client = TestClient(app)
            yield client
    
    # Clean up
    app.dependency_overrides.clear()

# Test health endpoint - no auth needed
def test_health_check(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "healthy"}

# Test health endpoint with database error using dependency override
def test_health_check_db_error_with_override():
    # Create a DB session that raises an exception when execute is called
    failing_db = MagicMock()
    failing_db.execute = MagicMock(side_effect=Exception("Database connection error"))
    
    # Override the dependency with our failing database session
    app.dependency_overrides[get_db] = lambda: failing_db
    
    # Create a test client with our override
    test_client = TestClient(app)
    
    try:
        # Call the endpoint
        response = test_client.get("/health")
        
        # Verify it returns 500 error
        assert response.status_code == 500
        assert "error" in response.json()["detail"].lower()
    finally:
        # Clean up our override after test
        app.dependency_overrides = {}

# Test translate-text endpoint
def test_translate_text(client):
    input_data = {"text": "Hello", "source_lang": "en", "target_lang": "es"}

    # Mock the database session
    mock_db = MagicMock()
    
    with patch("main.generate_text_translation", return_value="Hola"), \
         patch("main.handle_save_request", return_value="req-123"), \
         patch("main.process_and_save_analytics") as mock_process_and_save_analytics, \
         patch("main.get_user_by_cognito_id", return_value=TEST_USER) as mock_get_user:

        response = client.post("/translate-text/", json=input_data)
        assert response.status_code == 200
        assert response.json() == {"source_text": "Hello", "translation": "Hola"}
        
        # Assert that process_and_save_analytics was called with expected arguments.
        mock_process_and_save_analytics.assert_called_once_with(
            ANY, "req-123", "translate", "Hello", "Hola", ANY
        )
        
        mock_get_user.assert_called_once()

# Test translate-file endpoint
def test_translate_file(client):
    with patch("main.extract_text_from_data", new_callable=AsyncMock, return_value="This is a test file"), \
         patch("main.generate_file_translation", new_callable=AsyncMock, return_value=b"Este es un archivo de prueba"), \
         patch("main.handle_save_request", return_value="req-123"), \
         patch("main.process_and_save_analytics") as mock_process_and_save_analytics, \
         patch("main.get_user_by_cognito_id", return_value=TEST_USER) as mock_get_user:
        
        response = client.post("/translate-file/", files={
            "source_lang": (None, "en"),
            "target_lang": (None, "es"),
            "file": ("test.txt", BytesIO(b"This is a test file"), "text/plain")
        })
        assert response.status_code == 200
        assert response.headers["content-type"] == "text/plain; charset=utf-8"
        assert "attachment; filename=''test.txt" in response.headers["content-disposition"]
        assert response.content == b"Este es un archivo de prueba"
        mock_process_and_save_analytics.assert_called_once()
        mock_get_user.assert_called_once()

# Test translate-file endpoint with extraction error
def test_translate_file_extraction_error(client):
    with patch("main.extract_text_from_data", new_callable=AsyncMock, return_value=None):
        response = client.post(
            "/translate-file/",
            files={"file": ("test.txt", b"This is a test file")},
            data={"source_lang": "en", "target_lang": "es"}
        )
        
        assert response.status_code == 400
        assert response.json()["detail"] == "Could not extract text from file"

# Test generate-exam endpoint
def test_generate_exam(client):
    try:
        with patch("main.extract_text_from_data", new_callable=AsyncMock, return_value="This is a test PDF"), \
             patch("main.clean_raw_data", return_value='[{"question": "Test?", "type": "mcq", "options": ["A", "B", "C"], "correct_answer": "A"}]'), \
             patch("main.get_service_id_by_code", return_value=1), \
             patch("main.save_request_and_questions", return_value={
                 "request": {"id": "req-123", "title": "Test Exam"},
                 "questions": [{"id": "q-1", "question": "Test?"}]
             }), \
            patch("main.get_default_model_ids", return_value={"claude": "anthropic.claude-v2"}), \
            patch("function.llms.bedrock_invoke.get_model_by_id", return_value=MagicMock(input_price=0.1, output_price=0.2, token_rate=6.0)), \
            patch("main.invoke_bedrock_model", side_effect=["Relevant content", '{"questions": [{"question": "Test?"}]}']), \
            patch("main.get_service_id_by_code", return_value=1), \
             patch("main.get_user_by_cognito_id", return_value=TEST_USER) as mock_get_user, \
             patch("main.process_and_save_analytics", new_callable=AsyncMock) as mock_process_analytics:
            
            response = client.post(
                "/generate-exam/",
                files={"file": ("test.pdf", b"This is a test PDF")},
                data={
                    "title": "Test Exam",
                    "number_mcq": "2",
                    "number_tfq": "2",
                    "number_open": "1",
                    "custom_instructions": "Make it challenging"
                }
            )
            
            assert response.status_code == 200
            assert response.json()["title"] == "Test Exam"
            assert len(response.json()["questions"]) == 1
            assert response.json()["questions"][0]["question"] == "Test?"
            mock_get_user.assert_called_once()
            mock_process_analytics.assert_called_once()
    finally:
        # Clean up the dependency override
        app.dependency_overrides.clear()

# Test generate-exam endpoint with extraction error
def test_generate_exam_extraction_error(client):
    with patch("main.extract_text_from_data", new_callable=AsyncMock, return_value=None):
        response = client.post(
            "/generate-exam/",
            files={"file": ("test.pdf", b"This is a test PDF")},
            data={
                "title": "Test Exam",
                "number_mcq": "2",
                "number_tfq": "2",
                "number_open": "1",
                "custom_instructions": "Make it challenging"
            }
        )
        
        assert response.status_code == 400
        assert response.json()["detail"] == "Could not extract text from file"

# Test get-exams endpoint
def test_get_exams(client):
    exams_data = {"data": [{"id": "exam-1", "title": "Test Exam"}]}
    
    with patch("main.get_service_id_by_code", return_value=1), \
         patch("main.get_requests_and_questions", return_value=exams_data), \
         patch("main.get_user_by_cognito_id", return_value=TEST_USER) as mock_get_user:
        
        response = client.get("/get-exams/")
        
        assert response.status_code == 200
        assert response.json() == exams_data
        mock_get_user.assert_called_once()

# Test get-exams endpoint with error
def test_get_exams_error_with_override(client):
    with patch("main.get_user_by_cognito_id", return_value=TEST_USER), \
         patch("main.get_service_id_by_code", return_value=1), \
         patch("main.get_requests_and_questions", side_effect=Exception("Database error")):
        
        # Call the endpoint
        response = client.get("/get-exams/")
        
        # Verify response
        assert response.status_code == 500
        assert "error" in response.json()["detail"].lower()

# Test get-question-bank endpoint
def test_get_question_bank(client):
    question_bank_data = {"data": [{"id": "q-1", "question": "Test Question?"}]}
    
    with patch("main.get_question_bank", return_value=question_bank_data), \
         patch("main.get_user_by_cognito_id", return_value=TEST_USER) as mock_get_user:
        
        course_id = str(uuid.uuid4())
        response = client.get(f"/get-question-bank/{course_id}")
        
        assert response.status_code == 200
        assert response.json() == question_bank_data
        mock_get_user.assert_called_once()

# Test get-request endpoint
def test_get_request(client):
    request_data = {"id": "req-1", "title": "Test Request", "questions": [{"id": "q-1", "question": "Test Question?"}]}
    
    with patch("main.get_questions_request", return_value=request_data), \
         patch("main.get_user_by_cognito_id", return_value=TEST_USER) as mock_get_user:
        
        request_id = str(uuid.uuid4())
        response = client.get(f"/get-request/{request_id}")
        
        assert response.status_code == 200
        assert response.json() == request_data
        mock_get_user.assert_called_once()

# Test get-request endpoint with not found using dependency override
def test_get_request_not_found_with_override(client):
    with patch("main.get_questions_request", return_value=None), \
         patch("main.get_user_by_cognito_id", return_value=TEST_USER):
        # Call the endpoint
        request_id = str(uuid.uuid4())
        response = client.get(f"/get-request/{request_id}")
        
        # Verify response
        assert response.status_code == 404
        assert response.json()["detail"] == "Request not found"

# Test questions/refresh endpoint
def test_refresh_question(client):
    mock_question = MagicMock()
    mock_question.course_id = "course-123"
    
    mock_course = MagicMock()
    mock_course.knowledge_base_id = "kb-123"
    
    question_data = {
        "id": "q-123",
        "question": "Old question?",
        "options": ["A", "B", "C"],
        "correct_answer": "A",
        "reason": "Because A is correct",
        "type": "mcq"
    }
    
    updated_question = {
        "id": "q-123",
        "question": "New question?",
        "options": ["X", "Y", "Z"],
        "correct_answer": "Y",
        "reason": "Because Y is correct",
        "type": "mcq"
    }
    
    refresh_request = {
        "question": question_data,
        "prompt": "Make this question better"
    }
    
    with patch("main.get_question_by_id", return_value=mock_question), \
         patch("main.get_course_by_id", return_value=mock_course), \
         patch("main.get_default_model_ids", return_value={"claude": "anthropic.claude-v2"}), \
         patch("function.llms.bedrock_invoke.get_model_by_id", return_value=MagicMock(input_price=0.1, output_price=0.2, token_rate=6.0)), \
         patch("main.retrieve_and_generate", return_value={"text": json.dumps(updated_question)}), \
         patch("main.invoke_bedrock_model", side_effect=["Relevant content", '{"questions": [{"question": "Test?"}]}']), \
         patch("main.update_question_by_id", return_value=updated_question), \
         patch("main.process_and_save_analytics", new_callable=AsyncMock) as mock_process_analytics:
        
        response = client.post("/questions/refresh/", json=refresh_request)
        
        assert response.status_code == 200
        assert response.json()["question"] == "New question?"
        assert response.json()["options"] == ["X", "Y", "Z"]
        mock_process_analytics.assert_called_once()

# Test questions/refresh endpoint with error
def test_refresh_question_error(client):
    question_data = {
        "id": "q-123",
        "question": "Old question?",
        "options": ["A", "B", "C"],
        "correct_answer": "A",
        "reason": "Because A is correct",
        "type": "mcq"
    }
    
    refresh_request = {
        "question": question_data,
        "prompt": "Make this question better"
    }
    
    with patch("main.get_question_by_id", side_effect=Exception("Too many requests")):
        response = client.post("/questions/refresh/", json=refresh_request)
        
        assert response.status_code == 429
        assert "too many requests" in response.json()["detail"].lower()

# Test update question endpoint with proper payload
def test_update_question(client):
    question_id = str(uuid.uuid4())
    updated_question = {
        "id": question_id,
        "question": "Updated question?",
        "options": ["X", "Y", "Z"],
        "correct_answer": "Y",
        "reason": "Because Y is correct",
        "type": "mcq"
    }
    
    with patch("main.update_question_by_id", return_value=updated_question):
        # Use the QuestionUpdate schema class to create the request payload
        from database.schemas import QuestionUpdate
        question_data = QuestionUpdate(**updated_question)
        
        response = client.put(
            f"/questions/{question_id}",
            json=question_data.model_dump()  # Use model_dump() for Pydantic v2 or dict() for v1
        )
        
        assert response.status_code == 200
        assert response.json()["question"] == "Updated question?"
        assert response.json()["options"] == ["X", "Y", "Z"]

# Test update question endpoint with not found
def test_update_question_not_found(client):
    with patch("main.update_question_by_id", return_value=None):
        question_id = str(uuid.uuid4())

        from database.schemas import QuestionUpdate
        question_data = QuestionUpdate(
            id=question_id,
            question="Updated question?",
            options=["X", "Y", "Z"],
            reason="Because Y is correct",
            type="mcq"
        )

        response = client.put(
            f"/questions/{question_id}",
            json=question_data.model_dump()
        )
        
        # Verify response
        assert response.status_code == 404
        assert response.json()["detail"] == "Question not found"

# Test delete question endpoint
def test_delete_question(client):
    question_id = str(uuid.uuid4())
    mock_question = MagicMock()
    
    with patch("main.get_question_by_id", return_value=mock_question), \
         patch("main.delete_question_by_id", return_value=True):
        
        response = client.delete(f"/questions/{question_id}")
        
        assert response.status_code == 200
        assert response.json()["message"] == "Question deleted successfully"

# Test delete question endpoint with not found
def test_delete_question_not_found(client):
    question_id = str(uuid.uuid4())
    
    with patch("main.get_question_by_id", return_value=None):
        response = client.delete(f"/questions/{question_id}")
        
        # Verify response
        assert response.status_code == 404
        assert response.json()["detail"] == "Question not found"

# Test upload-pdf endpoint
def test_upload_pdf(client):
    # Create a mock file content
    file_content = b"This is a test PDF"
    doc_id = str(uuid.uuid4())
    request_id = str(uuid.uuid4())
    
    with patch("main.extract_text_from_data", new_callable=AsyncMock, return_value="This is a test PDF"), \
         patch("main.store_parsed_document", return_value=doc_id), \
         patch("main.generate_summary_and_title", return_value=("Response text", "Summary text", "Test Title")), \
         patch("main.handle_save_request", return_value=request_id), \
         patch("main.save_summary"), \
         patch("main.get_session_data", return_value={}), \
         patch("main.get_user_by_cognito_id", return_value=TEST_USER), \
         patch("main.process_and_save_analytics", new_callable=AsyncMock) as mock_process_analytics, \
         patch("main.detect_language", return_value="en"):
        
        response = client.post(
            "/upload-pdf/",
            files={"file": ("test.pdf", file_content)}
        )
        
        assert response.status_code == 200
        assert response.json()["title"] == "Test Title"
        assert response.json()["doc_id"] == doc_id
        assert response.json()["request_id"] == request_id
        assert response.json()["summary"] == "Summary text"
        mock_process_analytics.assert_called_once()

# Test upload-url endpoint
def test_upload_url(client):
    doc_id = str(uuid.uuid4())
    request_id = str(uuid.uuid4())
    
    with patch("main.extract_text_from_url", new_callable=AsyncMock, return_value="Website content"), \
         patch("main.store_parsed_document", return_value=doc_id), \
         patch("main.generate_summary_and_title", return_value=("Response text", "Website summary", "Website Title")), \
         patch("main.handle_save_request", return_value=request_id), \
         patch("main.save_summary"), \
         patch("main.get_user_by_cognito_id", return_value=TEST_USER), \
         patch("main.process_and_save_analytics", new_callable=AsyncMock) as mock_process_analytics, \
         patch("main.detect_language", return_value="en"):
        
        response = client.post(
            "/upload-url/",
            json={"url": "https://example.com"}
        )
        
        assert response.status_code == 200
        assert response.json()["title"] == "Website Title"
        assert response.json()["doc_id"] == doc_id
        assert response.json()["request_id"] == request_id
        assert response.json()["summary"] == "Website summary"
        mock_process_analytics.assert_called_once()

# Test ask-question endpoint
def test_ask_question(client):
    doc_id = str(uuid.uuid4())
    request_id = str(uuid.uuid4())
    
    with patch("main.get_request_id_by_document", return_value=request_id), \
         patch("main.get_session_data", return_value={"document_summary": "Document summary"}), \
         patch("main.invoke_bedrock_model", return_value="Answer to the question"), \
         patch("main.process_and_save_analytics", new_callable=AsyncMock) as mock_process_analytics:
        
        response = client.post(
            f"/ask-question/{doc_id}/",
            data={"question": "What is in this document?"}
        )
        
        assert response.status_code == 200
        assert response.json()["question"] == "What is in this document?"
        assert response.json()["answer"] == "Answer to the question"
        mock_process_analytics.assert_called_once()

# Test ask-question endpoint with invalid doc_id
def test_ask_question_invalid_doc_id(client):
    with patch("main.get_user_by_cognito_id", return_value=TEST_USER):
        response = client.post(
            "/ask-question/invalid-uuid/",
            data={"question": "What is in this document?"}
        )
        
        assert response.status_code == 400
        assert response.json()["detail"] == "Invalid document ID format"

# Test ask-question endpoint with document not found
def test_ask_question_document_not_found(client):
    doc_id = str(uuid.uuid4())
    
    with patch("main.get_request_id_by_document", return_value=None), \
         patch("main.get_user_by_cognito_id", return_value=TEST_USER):
        
        response = client.post(
            f"/ask-question/{doc_id}/",
            data={"question": "What is in this document?"}
        )
        
        assert response.status_code == 404
        assert response.json()["detail"] == "Document not found"

# Test transcribe endpoint with YouTube URL
def test_transcribe_youtube(client):
    request_id = str(uuid.uuid4())
    mock_audio_path = "/tmp/mock_audio.mp3"
    
    # Create a mock file that exists
    with patch("pathlib.Path.exists", return_value=True), \
         patch("pathlib.Path.is_file", return_value=True), \
         patch("os.access", return_value=True), \
         patch("main.download_youtube_audio", new_callable=AsyncMock, return_value=(mock_audio_path, "YouTube Title")), \
         patch("main.get_audio_duration", return_value=120), \
         patch("main.upload_to_s3", return_value="s3://bucket/audio.mp3"), \
         patch("main.handle_save_request", return_value=request_id), \
         patch("main.start_transcription", return_value={"TranscriptionJob": {"TranscriptionJobStatus": "IN_PROGRESS"}}), \
         patch("main.save_transcription_to_db"), \
         patch("main.get_user_by_cognito_id", return_value=TEST_USER), \
         patch("main.process_and_save_analytics", new_callable=AsyncMock) as mock_analytics, \
         patch("ffmpeg.probe", return_value={"format": {"duration": "120.5"}}):
        
        response = client.post(
            "/transcribe",
            data={"youtube_url": "https://www.youtube.com/watch?v=123456", "language_code": "en-US"}
        )
        
        assert response.status_code == 200
        assert response.json()["title"] == "YouTube Title"
        assert response.json()["status"] == "IN_PROGRESS"
        
        # Verify that our mocks were called correctly
        mock_analytics.assert_called_once()

# Test transcribe endpoint with file upload
def test_transcribe_file(client):
    request_id = str(uuid.uuid4())
    
    with patch("main.handle_uploaded_file", new_callable=AsyncMock, return_value=("/tmp/mock_audio.mp3", "Uploaded Audio")), \
         patch("main.get_audio_duration", return_value=120), \
         patch("main.upload_to_s3", return_value="s3://bucket/audio.mp3"), \
         patch("main.handle_save_request", return_value=request_id), \
         patch("main.start_transcription", return_value={"TranscriptionJob": {"TranscriptionJobStatus": "IN_PROGRESS"}}), \
         patch("main.save_transcription_to_db"), \
         patch("main.get_user_by_cognito_id", return_value=TEST_USER), \
         patch("main.process_and_save_analytics", new_callable=AsyncMock) as mock_analytics:
        
        # Create a mock file content
        file_content = b"This is audio data"
        
        response = client.post(
            "/transcribe",
            files={"file": ("audio.mp3", file_content, "audio/mp3")},
            data={"language_code": "en-US"}
        )
        
        assert response.status_code == 200
        assert response.json()["title"] == "Uploaded Audio"
        assert response.json()["status"] == "IN_PROGRESS"
        mock_analytics.assert_called_once()

# Test transcribe endpoint with audio too long
def test_transcribe_audio_too_long(client):
    # Create a mock file content
    file_content = b"This is audio data"
    
    with tempfile.NamedTemporaryFile(suffix='.mp3') as tmp_file, \
         patch("main.handle_uploaded_file", new_callable=AsyncMock, return_value=(tmp_file, "Uploaded Audio")), \
         patch("main.get_audio_duration", return_value=1200), \
         patch("main.get_user_by_cognito_id", return_value=TEST_USER):
        
        response = client.post(
            "/transcribe",
            files={"file": ("audio.mp3", file_content)},
            data={"language_code": "en-US"}
        )
        
        assert response.status_code == 400
        assert "duration exceeds 10 minutes" in response.json()["detail"]

# Test transcribe endpoint with no input
def test_transcribe_no_input(client):
    with patch("main.get_user_by_cognito_id", return_value=TEST_USER):
        response = client.post(
            "/transcribe",
            data={"language_code": "en-US"}
        )
        
        assert response.status_code == 400
        assert "No valid input provided" in response.json()["detail"]

# Test transcription-status endpoint
def test_transcription_status(client):
    with patch("main.get_transcription_status", return_value={"status": "COMPLETED", "transcript_text": "Transcription text"}), \
         patch("main.get_user_by_cognito_id", return_value=TEST_USER):
        
        response = client.get("/transcription-status/job-123")
        
        assert response.status_code == 200
        assert response.json()["status"] == "COMPLETED"
        assert response.json()["transcript_text"] == "Transcription text"

# Test transcription-status endpoint with error
def test_transcription_status_error(client):
    with patch("main.get_transcription_status", side_effect=Exception("Job not found")), \
         patch("main.get_user_by_cognito_id", return_value=TEST_USER):
        
        response = client.get("/transcription-status/job-123")
        
        assert response.status_code == 404
        assert "Job not found" in response.json()["detail"]

# Test transcription-history endpoint
def test_transcription_history(client):
    # Create mock requests and transcripts
    mock_request = MagicMock(id="req-123", title="Test Transcript")
    mock_transcript = MagicMock(
        id="transcript-123",
        transcription_text="This is a test transcription",
        status="COMPLETED",
        completed_at=datetime.now()
    )
    
    with patch("main.get_user_by_cognito_id", return_value=TEST_USER), \
         patch("main.get_service_id_by_code", return_value=1), \
         patch("main.get_requests_by_user_service", return_value=[mock_request]), \
         patch("main.get_transcript_by_request_id", return_value=mock_transcript):
        
        response = client.get("/transcription-history")
        
        assert response.status_code == 200
        assert len(response.json()) == 1
        assert response.json()[0]["id"] == "transcript-123"
        assert response.json()[0]["title"] == "Test Transcript"
        assert response.json()[0]["status"] == "COMPLETED"

# Test transcription-history endpoint with no requests
def test_transcription_history_no_requests(client):
    with patch("main.get_user_by_cognito_id", return_value=TEST_USER), \
         patch("main.get_service_id_by_code", return_value=1), \
         patch("main.get_requests_by_user_service", return_value=[]):
        
        response = client.get("/transcription-history")
        
        assert response.status_code == 404
        assert response.json()["detail"] == "No requests found for this user."

# Test transcript/{id} endpoint
def test_get_transcript(client):
    # Create mock transcript and request
    transcript_id = str(uuid.uuid4())
    mock_transcript = MagicMock(
        id=transcript_id,
        transcription_text="Test transcription content",
        status="COMPLETED",
        job_name="job-123",
        completed_at=datetime.now(),
        s3_uri="s3://bucket/audio.mp3",
        language_code="en-US",
        summary="Test summary",
        request_id="req-123"
    )
    
    mock_request = MagicMock(title="Test Transcript", user_id=TEST_USER_ID)
    
    with patch("main.get_user_by_cognito_id", return_value=TEST_USER), \
         patch("main.get_transcript_by_id", return_value=mock_transcript), \
         patch("main.get_request_by_id", return_value=mock_request), \
         patch("main.generate_presigned_url", return_value="https://example.com/audio.mp3"):
        
        response = client.get(f"/transcript/{transcript_id}")
        
        assert response.status_code == 200
        assert response.json()["id"] == transcript_id
        assert response.json()["title"] == "Test Transcript"
        assert response.json()["transcription_text"] == "Test transcription content"
        assert response.json()["status"] == "COMPLETED"
        assert response.json()["audioUrl"] == "https://example.com/audio.mp3"
        assert response.json()["summary"] == "Test summary"

# Test transcript/{id} endpoint with not found
def test_get_transcript_not_found(client):     
    transcript_id = str(uuid.uuid4())
    
    with patch("main.get_user_by_cognito_id", return_value=TEST_USER), \
         patch("main.get_transcript_by_id", return_value=None):
        
        response = client.get(f"/transcript/{transcript_id}")
        
        # Verify response
        assert response.status_code == 404
        assert response.json()["detail"] == "Transcript not found."

# Test transcript/{id} endpoint with unauthorized access
def test_get_transcript_unauthorized(client):
    # Create mock transcript and request
    transcript_id = str(uuid.uuid4())
    mock_transcript = MagicMock(
        id=transcript_id,
        request_id="req-123"
    )

    with patch("main.get_user_by_cognito_id", return_value=TEST_USER), \
         patch("main.get_transcript_by_id", return_value=mock_transcript), \
         patch("main.get_request_by_id", return_value=None):
        
        response = client.get(f"/transcript/{transcript_id}")
        
        # Verify response
        assert response.status_code == 403
        assert "Access denied" in response.json()["detail"]

# Test summarize endpoint
def test_summarize(client):
    # Create mock transcript and request
    transcript_id = str(uuid.uuid4())
    mock_transcript = MagicMock(
        id=transcript_id,
        request_id="req-123"
    )
    
    mock_request = MagicMock(user_id=TEST_USER_ID)
    
    with patch("main.get_user_by_cognito_id", return_value=TEST_USER), \
         patch("main.get_transcript_by_id", return_value=mock_transcript), \
         patch("main.get_request_by_id", return_value=mock_request), \
         patch("main.get_default_model_ids", return_value={"claude": "anthropic.claude-v2"}), \
         patch("function.llms.bedrock_invoke.get_model_by_id", return_value=MagicMock(input_price=0.1, output_price=0.2, token_rate=6.0)), \
         patch("main.invoke_bedrock_model", return_value="This is a summary"), \
         patch("main.update_transcript_summary", return_value=mock_transcript), \
         patch("main.process_and_save_analytics", new_callable=AsyncMock) as mock_process_analytics:
        
        response = client.post(
            "/summarize",
            json={
                "transcript_id": transcript_id,
                "transcript": "This is the transcript to summarize",
                "language": "en"
            }
        )
        
        assert response.status_code == 200
        assert response.json()["data"] == "This is a summary"
        mock_process_analytics.assert_called_once()

# Test summarize endpoint with unauthorized access
def test_summarize_unauthorized(client):
    # Create mock transcript and request
    transcript_id = str(uuid.uuid4())
    mock_transcript = MagicMock(
        id=transcript_id,
        request_id="req-123"
    )
    
    mock_request = MagicMock(user_id="different-user-id")
    
    with patch("main.get_user_by_cognito_id", return_value=TEST_USER), \
         patch("main.get_transcript_by_id", return_value=mock_transcript), \
         patch("main.get_request_by_id", return_value=mock_request):
        
        response = client.post(
            "/summarize",
            json={
                "transcript_id": transcript_id,
                "transcript": "This is the transcript to summarize",
                "language": "en"
            }
        )
        
        assert response.status_code == 403
        assert response.json()["detail"] == "Access denied"

# Test agent-exam endpoint
def test_agent_exam(client):
    # Mock course and user
    course_id = str(uuid.uuid4())
    mock_course = MagicMock(
        id=course_id,
        knowledge_base_id="kb-123",
        teacher_id=TEST_USER_ID,
        title="Test Course"
    )
    
    # Create mock file content
    file_content = b"This is a test PDF"
    
    # Create a side_effect list for retrieve_and_generate
    retrieve_generate_responses = [
        {"text": "Relevant extracted text"},  # First call for key points
        {"text": "Generated questions content"}  # Second call for questions
    ]
    
    with patch("main.get_user_by_cognito_id", return_value=TEST_USER), \
         patch("main.get_course_by_id", return_value=mock_course), \
         patch("main.extract_text_from_pdf", return_value="This is the PDF text"), \
         patch("main.build_key_points_prompt", return_value="Prompt"), \
         patch("main.get_default_model_ids", return_value={"claude": "anthropic.claude-v2"}), \
         patch("function.llms.bedrock_invoke.get_model_by_id", return_value=MagicMock(input_price=0.1, output_price=0.2, token_rate=6.0)), \
         patch("main.retrieve_and_generate", side_effect=retrieve_generate_responses), \
         patch("main.get_questions_by_course_id", return_value={"questions": ["Question 1"]}), \
         patch("main.build_prompt_agent", return_value="Agent prompt"), \
         patch("main.clean_raw_data", return_value='[{"question": "Test?", "type": "mcq"}]'), \
         patch("main.get_service_id_by_code", return_value=1), \
         patch("main.save_request_and_questions", return_value={
            "request": {"id": "req-123", "title": "Knowledge base: kb-123"},
            "questions": [{"question": "Test?", "id": "q-1"}]
         }), \
         patch("main.process_and_save_analytics", new_callable=AsyncMock) as mock_process_analytics:
        
        response = client.post(
            "/agent-exam/",
            files={"file": ("test.pdf", file_content)},
            data={
                "course_id": course_id,
                "number_mcq": "2",
                "number_tfq": "2",
                "number_open": "1",
                "custom_instructions": "Make it challenging",
                "materials": None  # Explicitly handle materials parameter
            }
        )
        
        assert response.status_code == 200
        assert response.json()["title"] == "Knowledge base: kb-123"
        assert len(response.json()["questions"]) == 1
        assert response.json()["questions"][0]["question"] == "Test?"
        mock_process_analytics.assert_called()

# Test agent-exam endpoint with unauthorized access
def test_agent_exam_unauthorized(client):
    course_id = str(uuid.uuid4())
    mock_course = MagicMock(
        id=course_id,
        knowledge_base_id="kb-123",
        teacher_id="different-teacher-id",  # Different from TEST_USER_ID
        title="Test Course"
    )
    
    # Create mock file content
    file_content = b"This is a test PDF"
    
    with patch("main.get_user_by_cognito_id", return_value=TEST_USER), \
         patch("main.get_course_by_id", return_value=mock_course):
        
        response = client.post(
            "/agent-exam/",
            files={"file": ("test.pdf", file_content)},
            data={
                "course_id": course_id,
                "number_mcq": "2",
                "number_tfq": "2",
                "number_open": "1",
                "custom_instructions": "Make it challenging"
            }
        )
        
        # Verify response
        assert response.status_code == 403
        assert "Access denied" in response.json()["detail"]

# Test ask-agent endpoint
def test_ask_agent(client):
    # Mock course and user
    course_id = str(uuid.uuid4())
    mock_course = MagicMock(
        id=course_id,
        knowledge_base_id="kb-123",
        teacher_id=TEST_USER_ID,
        title="Test Course"
    )
    
    with patch("main.get_user_by_cognito_id", return_value=TEST_USER), \
         patch("main.get_course_by_id", return_value=mock_course), \
         patch("main.get_default_model_ids", return_value={"claude": "anthropic.claude-v2"}), \
         patch("function.llms.bedrock_invoke.get_model_by_id", return_value=MagicMock(input_price=0.1, output_price=0.2, token_rate=6.0)), \
         patch("main.retrieve_and_generate", return_value={
            "text": "Answer to the question",
            "contexts": ["context1", "context2"]
         }), \
         patch("main.process_and_save_analytics", new_callable=AsyncMock) as mock_process_analytics:
        
        response = client.post(
            f"/ask-agent/{course_id}/",
            data={"question": "What is this course about?"}
        )
        
        assert response.status_code == 200
        assert response.json()["question"] == "What is this course about?"
        assert response.json()["answer"] == "Answer to the question"
        assert response.json()["citation"] == ["context1", "context2"]
        mock_process_analytics.assert_called_once()

# Test ask-agent endpoint with unauthorized access
def test_ask_agent_unauthorized(client):
    course_id = str(uuid.uuid4())
    mock_course = MagicMock(
        id=course_id,
        knowledge_base_id="kb-123",
        teacher_id="different-teacher-id",  # Different from TEST_USER_ID
        title="Test Course"
    )
    
    with patch("main.get_user_by_cognito_id", return_value=TEST_USER), \
         patch("main.get_course_by_id", return_value=mock_course):
        
        response = client.post(
            f"/ask-agent/{course_id}/",
            data={"question": "What is this course about?"}
        )
        
        # Verify response
        assert response.status_code == 403
        assert "Access denied" in response.json()["detail"]

# Test process_text endpoint
def test_process_text(client):
    # Create a mock for the async operations
    mock_async = AsyncMock()
    mock_async.return_value = "<response>Processed text</response>"
    
    with patch("main.get_selected_text", return_value=None), \
         patch("main.build_text_processing_prompt", return_value="Processing prompt"), \
         patch("main.get_default_model_ids", return_value={"claude": "anthropic.claude-v2"}), \
         patch("function.llms.bedrock_invoke.get_model_by_id", return_value=MagicMock(input_price=0.1, output_price=0.2, token_rate=6.0)), \
         patch("main.invoke_bedrock_model", mock_async), \
         patch("main.get_user_by_cognito_id", return_value=TEST_USER), \
         patch("main.get_db", return_value=MagicMock()), \
         patch("main.process_and_save_analytics", new_callable=AsyncMock) as mock_process_analytics:
        
        response = client.post(
            "/process_text",
            json={
                "action": "summarize",
                "text": "This is a long text that needs to be processed.",
                "start_index": 10,
                "end_index": 30,
                "tones": ["formal"],
                "audiences": ["technical"]
            }
        )
        
        assert response.status_code == 200
        assert response.json()["response"] == "Processed text"
        mock_process_analytics.assert_called_once()

# Test process_text endpoint
def test_process_text_with_selected_text(client):
    # Create a mock for the async operations
    mock_async = AsyncMock()
    mock_async.return_value = "<response>has been processed</response>"
    
    with patch("main.get_selected_text", return_value="needs to be processed"), \
         patch("main.build_text_processing_prompt", return_value="Processing prompt"), \
         patch("main.get_default_model_ids", return_value={"claude": "anthropic.claude-v2"}), \
         patch("function.llms.bedrock_invoke.get_model_by_id", return_value=MagicMock(input_price=0.1, output_price=0.2, token_rate=6.0)), \
         patch("main.invoke_bedrock_model", mock_async), \
         patch("main.replace_selected_text", return_value="This is a long text that has been processed."), \
         patch("main.get_user_by_cognito_id", return_value=TEST_USER), \
         patch("main.get_db", return_value=MagicMock()), \
         patch("main.process_and_save_analytics", new_callable=AsyncMock) as mock_process_analytics:
        
        response = client.post(
            "/process_text",
            json={
                "action": "summarize",
                "text": "This is a long text that needs to be processed.",
                "start_index": 10,
                "end_index": 30,
                "tones": ["formal"],
                "audiences": ["technical"]
            }
        )
        
        assert response.status_code == 200
        assert response.json()["response"] == "This is a long text that has been processed."
        mock_process_analytics.assert_called_once()

# Test process_text endpoint with invalid action
def test_process_text_invalid_action(client):
    response = client.post(
        "/process_text",
        json={
            "action": "invalid_action",
            "text": "This is a text.",
            "start_index": 0,
            "end_index": 14,
            "tones": ["formal"],
            "audiences": ["general"]
        }
    )
    
    assert response.status_code == 400
    assert "Invalid action type" in response.json()["detail"]

# Test process_text endpoint with API error
def test_process_text_api_error(client):
    # Create a mock for the async operations that raises an exception
    mock_async = AsyncMock()
    mock_async.side_effect = Exception("Too many requests")
    
    with patch("main.get_selected_text", return_value="Selected text"), \
         patch("main.build_text_processing_prompt", return_value="Processing prompt"), \
         patch("main.get_default_model_ids", return_value={"claude": "anthropic.claude-v2"}), \
         patch("function.llms.bedrock_invoke.get_model_by_id", return_value=MagicMock(input_price=0.1, output_price=0.2, token_rate=6.0)), \
         patch("main.invoke_bedrock_model", mock_async), \
         patch("main.get_user_by_cognito_id", return_value=TEST_USER), \
         patch("main.process_and_save_analytics", new_callable=AsyncMock) as mock_process_analytics:
        
        response = client.post(
            "/process_text",
            json={
                "action": "summarize",
                "text": "This is a text.",
                "start_index": 0,
                "end_index": 14,
                "tones": ["formal"],
                "audiences": ["general"]
            }
        )
        
        assert response.status_code == 429
        assert "Too many requests" in response.json()["detail"]
        # We don't expect analytics to be processed when there's an API error
        mock_process_analytics.assert_not_called()