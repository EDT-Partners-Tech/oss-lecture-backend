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
from datetime import datetime, timedelta, timezone
from fastapi import FastAPI
from fastapi.testclient import TestClient
from unittest.mock import MagicMock, AsyncMock, patch
import pytest

from routers import courses
from routers.courses import router, get_db
from database.models import UserRole
from utility.auth import oauth2_scheme

# Create test app with courses router
app = FastAPI()
app.include_router(router)

@pytest.fixture(scope="function")
def client(mock_cognito_token_payload):
    app.dependency_overrides[get_db] = lambda: MagicMock()
    app.dependency_overrides[oauth2_scheme] = lambda: "fake-jwt-token"

    with patch("utility.auth.jose_jwt.get_unverified_claims") as mock_get_claims:
    
        mock_get_claims.return_value = {"cognito:username": "dummy_user_id"}

        mock_validator = AsyncMock()
        mock_validator.validate_token.return_value = mock_cognito_token_payload
    
        with patch.dict("utility.auth.VALIDATOR_MAP", {"cognito": mock_validator}):
            client = TestClient(app)
            yield client

    app.dependency_overrides.clear()

# Common test fixtures
@pytest.fixture
def mock_teacher():
    teacher = MagicMock()
    teacher.id = str(uuid.uuid4())
    teacher.cognito_id = "mock_user_id"
    teacher.role = UserRole.teacher
    teacher.name = "Test Teacher"
    teacher.email = "teacher@example.com"
    return teacher

@pytest.fixture
def mock_course(mock_teacher):
    course = MagicMock()
    course.id = str(uuid.uuid4())
    course.title = "Test Course"
    course.description = "Test Description"
    course.teacher_id = mock_teacher.id
    course.created_at = datetime.now()
    course.knowledge_base_id = "kb_123"
    course.data_source_id = "ds_123"
    course.ingestion_job_id = "ing_job_123"
    course.execution_arn = "arn:aws:state-machine:123"
    course.sample_questions = ["Question 1?", "Question 2?"]
    course.ingestion_status = "COMPLETE"
    course.settings = {"knowledge_base_filter_structure": ["type", "category", "level"]}
    return course

@pytest.fixture
def mock_material():
    material = MagicMock()
    material.id = str(uuid.uuid4())
    material.title = "Test Material"
    material.type = "application/pdf"
    material.s3_uri = "s3://bucket/path/to/material.pdf"
    material.transcription_s3_uri = None
    material.status = "Uploaded"
    material.course_id = "mock_course_id"
    return material

@pytest.fixture
def mock_invite():
    invite = MagicMock()
    invite.invite_code = "mock_invite_code"
    invite.email = "student@example.com"
    invite.course_id = "mock_course_id"
    invite.expires_at = datetime.now(timezone.utc) + timedelta(days=7)
    invite.created_at = datetime.now()
    return invite

# Tests for GET / - Get courses by teacher
def test_get_courses_by_teacher_success(client, monkeypatch, mock_teacher, mock_course):
    monkeypatch.setattr(courses, "get_user_by_cognito_id", lambda db, user_id: mock_teacher)
    monkeypatch.setattr(courses, "get_teacher_courses", lambda db, teacher_id: [mock_course])
    
    # Por defecto is_kbm es False, así que el curso debe tener settings=None
    mock_course.settings = None
    
    response = client.get("/")
    
    assert response.status_code == 200
    assert len(response.json()) == 1
    assert response.json()[0]["title"] == mock_course.title

def test_get_courses_by_teacher_kbm_success(client, monkeypatch, mock_teacher, mock_course):
    monkeypatch.setattr(courses, "get_user_by_cognito_id", lambda db, user_id: mock_teacher)
    monkeypatch.setattr(courses, "get_teacher_courses", lambda db, teacher_id: [mock_course])
    
    # Para is_kbm=True, el curso debe tener settings no nulo
    mock_course.settings = {"some_setting": "value"}
    
    response = client.get("/?is_kbm=true")
    
    assert response.status_code == 200
    assert len(response.json()) == 1
    assert response.json()[0]["title"] == mock_course.title

def test_get_courses_by_teacher_empty(client, monkeypatch, mock_teacher):
    monkeypatch.setattr(courses, "get_user_by_cognito_id", lambda db, user_id: mock_teacher)
    monkeypatch.setattr(courses, "get_teacher_courses", lambda db, teacher_id: [])
    
    response = client.get("/")
    
    assert response.status_code == 200
    assert response.json() == []

def test_get_courses_by_teacher_not_found(client, monkeypatch):
    monkeypatch.setattr(courses, "get_user_by_cognito_id", lambda db, user_id: None)
    
    response = client.get("/")
    
    assert response.status_code == 404
    assert "not found" in response.json()["detail"]

# Tests for POST /{course_id}/invite - Invite students
def test_invite_students_success(client, monkeypatch, mock_course, mock_teacher):
    course_id = mock_course.id
    student_emails = ["student1@example.com", "student2@example.com"]
    
    # Create mock student users
    student1 = MagicMock(id="student1_id", cognito_id="cognito_1_id", email=student_emails[0])
    student2 = MagicMock(id="student2_id", cognito_id="cognito_2_id", email=student_emails[1])

    student1.name = "John Doe"
    student2.name = "Jane Doe"
    
    monkeypatch.setattr(courses, "get_user_by_cognito_id", lambda db, user_id: mock_teacher)
    monkeypatch.setattr(courses, "get_user_by_email", lambda db, email: None if email == student_emails[0] else student2)
    monkeypatch.setattr(courses, "create_user", lambda db, user: student1)
    monkeypatch.setattr(courses, "enroll_user_in_course", lambda db, user_id, course_id: None)
    
    response = client.post(f"/{course_id}/invite", json=student_emails)
    
    assert response.status_code == 201
    assert len(response.json()) == 2
    assert response.json()[0]["id"] == "student1_id"
    assert response.json()[1]["id"] == "student2_id"

# Tests for DELETE /{course_id}/ - Delete course resources
def test_delete_course_success(client, monkeypatch, mock_course):
    course_id = mock_course.id
    
    monkeypatch.setattr(courses, "verify_user_owner", lambda db, user, course_id: None)
    monkeypatch.setattr(courses, "delete_materials_by_course", lambda db, course_id: 2)
    monkeypatch.setattr(courses, "delete_resources", AsyncMock())
    monkeypatch.setattr(courses, "delete_course", lambda db, course_id: True)
    
    response = client.delete(f"/{course_id}/")
    
    assert response.status_code == 204

def test_delete_course_not_found(client, monkeypatch):
    course_id = str(uuid.uuid4())
    
    monkeypatch.setattr(courses, "verify_user_owner", lambda db, user, course_id: None)
    monkeypatch.setattr(courses, "delete_materials_by_course", lambda db, course_id: 0)
    monkeypatch.setattr(courses, "delete_resources", AsyncMock())
    monkeypatch.setattr(courses, "delete_course", lambda db, course_id: False)
    
    response = client.delete(f"/{course_id}/")
    
    assert response.status_code == 204  # Still returns 204 even if course not found

def test_delete_course_unauthorized(client, monkeypatch):
    course_id = str(uuid.uuid4())
    
    def mock_verify_user_owner(db, user, course_id):
        from fastapi import HTTPException
        raise HTTPException(status_code=403, detail="Not authorized")
    
    monkeypatch.setattr(courses, "verify_user_owner", mock_verify_user_owner)
    
    response = client.delete(f"/{course_id}/")
    
    assert response.status_code == 403
    assert "Not authorized" in response.json()["detail"]

# Tests for POST / - Create course
def test_create_course_success(client, monkeypatch, mock_teacher):
    course_data = {"title": "New Course", "description": "New Description"}
    
    # Create a mock course that FastAPI can actually serialize
    course_id = str(uuid.uuid4())
    # Use a custom class instead of MagicMock to avoid serialization issues
    class CourseModel:
        def __init__(self, id, title, description, teacher_id):
            self.id = id
            self.title = title
            self.description = description
            self.teacher_id = teacher_id
    
    new_course = CourseModel(
        id=course_id,
        title=course_data["title"],
        description=course_data["description"],
        teacher_id=mock_teacher.id
    )
    
    monkeypatch.setattr(courses, "verify_user_permission", lambda db, user: None)
    monkeypatch.setattr(courses, "get_user_by_cognito_id", lambda db, user_id: mock_teacher)
    monkeypatch.setattr(courses, "create_course_in_db", lambda db, course, teacher_id: new_course)
    monkeypatch.setattr(courses, "setup_s3_directory", AsyncMock())
    
    response = client.post("/", json=course_data)
    
    assert response.status_code == 201
    assert response.json()["title"] == course_data["title"]
    assert response.json()["description"] == course_data["description"]

def test_create_course_teacher_not_found(client, monkeypatch):
    course_data = {"title": "New Course", "description": "New Description"}
    
    monkeypatch.setattr(courses, "verify_user_permission", lambda db, user: None)
    monkeypatch.setattr(courses, "get_user_by_cognito_id", lambda db, user_id: None)
    
    response = client.post("/", json=course_data)
    
    assert response.status_code == 404
    assert "Teacher not found" in response.json()["detail"]

# Tests for POST /{course_id}/state_machine - Start knowledge base state machine
def test_knowledgebase_state_machine_success(client, monkeypatch, mock_course):
    course_id = mock_course.id
    execution_arn = "arn:aws:states:us-west-2:123456789012:execution:state-machine:execution-id"
    
    monkeypatch.setattr(courses, "verify_user_owner", lambda db, user, course_id: None)
    monkeypatch.setattr(courses, "start_step_function", 
                       lambda input_data: {"executionArn": execution_arn})
    monkeypatch.setattr(courses, "update_course_field", lambda db, course_id, field, value: None)
    
    response = client.post(f"/{course_id}/state_machine")
    
    assert response.status_code == 201
    assert response.json()["executionArn"] == execution_arn

def test_knowledgebase_state_machine_unauthorized(client, monkeypatch):
    course_id = str(uuid.uuid4())
    
    def mock_verify_user_owner(db, user, course_id):
        from fastapi import HTTPException
        raise HTTPException(status_code=403, detail="Not authorized")
    
    monkeypatch.setattr(courses, "verify_user_owner", mock_verify_user_owner)
    
    response = client.post(f"/{course_id}/state_machine")
    
    assert response.status_code == 403
    assert "Not authorized" in response.json()["detail"]

# Tests for POST /{course_id}/poll_state_machine - Poll step function
def test_poll_step_function_success(client, monkeypatch, mock_course):
    course_id = mock_course.id
    execution_arn = "arn:aws:states:us-west-2:123456789012:execution:state-machine:execution-id"
    
    request_data = {"execution_arn": execution_arn}
    execution_output = {
        "state_status": "SUCCEEDED",
        "execution_output": {"knowledge_base_id": "kb_123", "data_source_id": "ds_123"}
    }
    
    monkeypatch.setattr(courses, "verify_user_owner", lambda db, user, course_id: None)
    monkeypatch.setattr(courses, "get_execution_details", lambda arn: execution_output)
    monkeypatch.setattr(courses, "update_course_field", lambda db, course_id, field, value: None)
    
    response = client.post(f"/{course_id}/poll_state_machine", json=request_data)
    
    assert response.status_code == 200
    assert response.json() == execution_output

def test_poll_step_function_no_execution_arn(client, monkeypatch, mock_course):
    course_id = mock_course.id
    execution_arn = "arn:aws:states:us-west-2:123456789012:execution:state-machine:execution-id"
    
    execution_output = {
        "state_status": "RUNNING",
        "execution_output": {}
    }
    
    monkeypatch.setattr(courses, "verify_user_owner", lambda db, user, course_id: None)
    monkeypatch.setattr(courses, "get_course", lambda db, course_id: mock_course)
    monkeypatch.setattr(courses, "get_execution_details", lambda arn: execution_output)
    
    # Request with no execution_arn
    request_data = {"execution_arn": ""}
    
    response = client.post(f"/{course_id}/poll_state_machine", json=request_data)
    
    assert response.status_code == 200
    assert response.json() == execution_output

# Tests for GET /{course_id}/ingestion - Start ingestion
def test_start_ingestion_success(client, monkeypatch, mock_course):
    course_id = mock_course.id
    ingestion_job_id = "ingestion_job_123"
    
    monkeypatch.setattr(courses, "verify_user_permission", lambda db, user: None)
    monkeypatch.setattr(courses, "get_course", lambda db, course_id: mock_course)
    monkeypatch.setattr(courses, "start_ingestion_job", 
                       AsyncMock(return_value={"ingestionJobId": ingestion_job_id}))
    monkeypatch.setattr(courses, "update_course_field", lambda db, course_id, field, value: None)
    
    response = client.get(f"/{course_id}/ingestion")
    
    assert response.status_code == 200
    assert response.json()["message"] == "Ingestion job started"

def test_start_ingestion_course_not_found(client, monkeypatch):
    course_id = str(uuid.uuid4())
    
    monkeypatch.setattr(courses, "verify_user_permission", lambda db, user: None)
    monkeypatch.setattr(courses, "get_course", lambda db, course_id: None)
    
    response = client.get(f"/{course_id}/ingestion")
    
    assert response.status_code == 404
    assert "Course not found" in response.json()["detail"]

def test_start_ingestion_no_kb_id(client, monkeypatch):
    course = MagicMock(knowledge_base_id=None, data_source_id=None)
    course_id = str(uuid.uuid4())
    
    monkeypatch.setattr(courses, "verify_user_permission", lambda db, user: None)
    monkeypatch.setattr(courses, "get_course", lambda db, course_id: course)
    
    response = client.get(f"/{course_id}/ingestion")
    
    assert response.status_code == 400
    assert "Knowledge base or data source not set" in response.json()["detail"]

# Tests for GET /{course_id}/ingestion_status - Get materials summary
def test_get_materials_summary_success(client, monkeypatch, mock_course):
    course_id = mock_course.id
    ingestion_summary = {
        "status": "COMPLETE",
        "statistics": {
            "numberOfDocumentsAdded": 10,
            "numberOfDocumentsFailed": 0
        },
        "failureReasons": []
    }
    
    monkeypatch.setattr(courses, "verify_user_permission", lambda db, user: None)
    monkeypatch.setattr(courses, "get_course", lambda db, course_id: mock_course)
    monkeypatch.setattr(courses, "get_ingestion_summary", 
                       AsyncMock(return_value=ingestion_summary))
    monkeypatch.setattr(courses, "update_course_field", lambda db, course_id, field, value: None)
    
    response = client.get(f"/{course_id}/ingestion_status")
    
    assert response.status_code == 200
    assert response.json() == ingestion_summary

def test_get_materials_summary_with_failures(client, monkeypatch, mock_course):
    course_id = mock_course.id
    ingestion_summary = {
        "status": "COMPLETE",
        "statistics": {
            "numberOfDocumentsAdded": 8,
            "numberOfDocumentsFailed": 2
        },
        "failureReasons": ["Encountered error: Invalid file format [Files: s3://bucket/file1.pdf]"]
    }
    
    monkeypatch.setattr(courses, "verify_user_permission", lambda db, user: None)
    monkeypatch.setattr(courses, "get_course", lambda db, course_id: mock_course)
    monkeypatch.setattr(courses, "get_ingestion_summary", 
                       AsyncMock(return_value=ingestion_summary))
    monkeypatch.setattr(courses, "parse_failure_reasons", 
                       lambda reasons: [{"file": "s3://bucket/file1.pdf", "error": "Invalid file format"}])
    monkeypatch.setattr(courses, "update_material_status", lambda db, error_map: None)
    monkeypatch.setattr(courses, "update_course_field", lambda db, course_id, field, value: None)
    
    response = client.get(f"/{course_id}/ingestion_status")
    
    assert response.status_code == 200
    assert response.json() == ingestion_summary

# Tests for GET /{course_id}/analyze_knowledge_base - Analyze knowledge base
def test_analyze_knowledge_base_success(client, monkeypatch, mock_course):
    course_id = mock_course.id
    
    monkeypatch.setattr(courses, "verify_user_permission", lambda db, user: None)
    monkeypatch.setattr(courses, "get_course", lambda db, course_id: mock_course)
    
    response = client.get(f"/{course_id}/analyze_knowledge_base")
    
    assert response.status_code == 200
    assert "summary" in response.json()
    assert "questions" in response.json()

def test_analyze_knowledge_base_generate_questions(client, monkeypatch, mock_course):
    # Modified course with no sample questions
    course = MagicMock(
        id=mock_course.id,
        knowledge_base_id=mock_course.knowledge_base_id,
        sample_questions=None,
        description="Some description"
    )
    
    sample_questions = ["Generated question 1?", "Generated question 2?"]
    
    # Create an async mock that returns the sample questions
    async def mock_generate_questions(*args, **kwargs):
        return sample_questions
    
    monkeypatch.setattr(courses, "verify_user_permission", lambda db, user: None)
    monkeypatch.setattr(courses, "get_course", lambda db, course_id: course)
    monkeypatch.setattr(courses, "generate_course_questions", mock_generate_questions)
    
    response = client.get(f"/{course.id}/analyze_knowledge_base")
    
    assert response.status_code == 200
    assert response.json()["questions"] == sample_questions

def test_analyze_knowledge_base_generate_summary(client, monkeypatch, mock_course):
    # Modified course with no description
    course = MagicMock(
        id=mock_course.id,
        knowledge_base_id=mock_course.knowledge_base_id,
        sample_questions=["Question 1?"],
        description=None
    )
    
    summary = "Generated course summary"
    
    monkeypatch.setattr(courses, "verify_user_permission", lambda db, user: None)
    monkeypatch.setattr(courses, "get_course", lambda db, course_id: course)
    monkeypatch.setattr(courses, "generate_course_summary", 
                       AsyncMock(return_value=summary))
    
    response = client.get(f"/{course.id}/analyze_knowledge_base")
    
    assert response.status_code == 200
    assert response.json()["summary"] == summary

def test_analyze_knowledge_base_no_kb_id(client, monkeypatch):
    course = MagicMock(knowledge_base_id=None)
    course_id = str(uuid.uuid4())
    
    monkeypatch.setattr(courses, "verify_user_permission", lambda db, user: None)
    monkeypatch.setattr(courses, "get_course", lambda db, course_id: course)
    
    response = client.get(f"/{course_id}/analyze_knowledge_base")
    
    assert response.status_code == 400
    assert "Knowledge base not set" in response.json()["detail"]

# Tests for POST /{course_id}/materials/ - Upload materials
def test_upload_materials_success(client, monkeypatch, mock_course, mock_teacher, mock_material):
    course_id = mock_course.id
    file_content = b"PDF content"
    material_id = str(uuid.uuid4())
    
    # Create a mock Material object that can be serialized
    class SerializableMaterial:
        def __init__(self, id, title, type, s3_uri, status, course_id):
            self.id = id
            self.title = title
            self.type = type
            self.s3_uri = s3_uri
            self.status = status
            self.course_id = course_id
            
        def dict(self):
            return {
                "id": self.id,
                "title": self.title,
                "type": self.type,
                "s3_uri": self.s3_uri,
                "status": self.status,
                "course_id": self.course_id
            }
    
    mock_material = SerializableMaterial(
        id=material_id,
        title="Test Material",
        type="application/pdf",
        s3_uri="s3://bucket/path/to/material.pdf",
        status="Uploaded",
        course_id=str(course_id)
    )
    
    # Mock the PDFDocumentProcessor
    mock_processor = MagicMock()
    mock_processor.process_and_upload_to_s3 = AsyncMock(return_value={
        "status": "success",
        "s3_uri": f"s3://materials/{course_id}/{material_id}.md",
        "s3_uri_metadata": f"s3://materials/{course_id}/{material_id}.md.metadata.json",
        "s3_path": f"materials/{course_id}",
        "processed_data": {
            "chatbot_name": "Test Material",
            "markdown_content": ["Test content"]
        }
    })
    
    # Mock the ChatbotCreate class
    mock_chatbot_create = MagicMock()
    mock_chatbot_create.name = "Test Material"
    mock_chatbot_create.id = str(course_id)
    
    monkeypatch.setattr(courses, "get_course", lambda db, cid: mock_course)
    monkeypatch.setattr(courses, "get_user_by_cognito_id", lambda db, uid: mock_teacher)
    monkeypatch.setattr(courses, "PDFDocumentProcessor", lambda *args, **kwargs: mock_processor)
    monkeypatch.setattr(courses, "ChatbotCreate", lambda **kwargs: mock_chatbot_create)
    
    with monkeypatch.context() as m:
        m.setattr(courses, "sanitize_filename", lambda filename: filename)
        m.setattr(courses, "upload_to_s3", lambda b, s, d: f"s3://{d}")
        m.setattr(courses, "process_epub_file", AsyncMock(return_value=None))
        m.setattr(courses, "create_material", lambda db, material: mock_material)
        m.setattr(courses, "update_course_field", lambda db, cid, f, v: None)
        
        response = client.post(
            f"/{course_id}/materials/",
            data={"extra_processing": "true"},
            files={"files": ("test.pdf", file_content, "application/pdf")}
        )
        
        assert response.status_code == 201
        assert len(response.json()) == 1
        assert response.json()[0]["id"] == material_id
        
        # Verify that PDFDocumentProcessor was called with the correct parameters
        mock_processor.process_and_upload_to_s3.assert_called_once()
        call_args = mock_processor.process_and_upload_to_s3.call_args[0]
        assert call_args[0] == f"materials/{course_id}"

def test_upload_materials_course_not_found(client, monkeypatch):
    course_id = str(uuid.uuid4())
    file_content = b"PDF content"

    monkeypatch.setattr(courses, "get_course", lambda db, course_id: None)

    response = client.post(
        f"/{course_id}/materials/",
        files={"files": ("test.pdf", file_content, "application/pdf")},
        data={"extra_processing": "true"}
    )

    assert response.status_code == 404

def test_upload_materials_unauthorized(client, monkeypatch, mock_course):
    course_id = mock_course.id
    file_content = b"PDF content"
    
    monkeypatch.setattr(courses, "get_course", lambda db, course_id: mock_course)
    monkeypatch.setattr(courses, "get_user_by_cognito_id",
                       lambda db, user_id: MagicMock(id="other_user_id"))

    response = client.post(
        f"/{course_id}/materials/",
        files={"files": ("test.pdf", file_content, "application/pdf")},
        data={"extra_processing": "true"}
    )

    assert response.status_code == 403
    assert "Not authorized" in response.json()["detail"]

def test_upload_materials_epub_processing(client, monkeypatch, mock_course, mock_teacher):
    course_id = mock_course.id
    file_content = b"EPUB content"
    
    # Create a dictionary that can be properly serialized instead of using mock_material directly
    material_dict = {
        "id": str(uuid.uuid4()),
        "title": "Test EPUB Material",
        "type": "application/epub+zip",
        "s3_uri": "s3://bucket/path/to/material.epub",
        "transcription_s3_uri": "s3://transcribed_content_uri",
        "status": "Processed",
        "course_id": str(course_id)
    }
    
    monkeypatch.setattr(courses, "get_course", lambda db, course_id: mock_course)
    monkeypatch.setattr(courses, "get_user_by_cognito_id", lambda db, user_id: mock_teacher)
    
    with monkeypatch.context() as m:
        m.setattr(courses, "sanitize_filename", lambda filename: filename)
        m.setattr(courses, "upload_to_s3", lambda bucket, src, dst: f"s3://{dst}")
        m.setattr(courses, "process_epub_file", AsyncMock(return_value="s3://transcribed_content_uri"))
        # Return the dictionary instead of the mock object
        m.setattr(courses, "create_material", lambda db, material: material_dict)
        m.setattr(courses, "update_course_field", lambda db, course_id, field, value: None)
        
        response = client.post(
            f"/{course_id}/materials/",
            files={"files": ("test.epub", file_content, "application/epub+zip")},
            data={"extra_processing": "true"}
        )
        
        assert response.status_code == 201
        assert len(response.json()) == 1
        assert response.json()[0]["id"] == material_dict["id"]

# Tests for DELETE /{course_id}/materials/ - Delete materials
def test_delete_materials_success(client, monkeypatch, mock_material):
    course_id = str(uuid.uuid4())
    material_ids = [str(uuid.uuid4()), str(uuid.uuid4())]
    
    monkeypatch.setattr(courses, "verify_user_owner", lambda db, user, course_id: None)
    monkeypatch.setattr(courses, "get_material", lambda db, material_id: mock_material)
    monkeypatch.setattr(courses, "delete_from_s3", AsyncMock())
    monkeypatch.setattr(courses, "delete_material", lambda db, material_id: True)
    
    # Use the request method with the proper method and json parameters
    response = client.request(
        "DELETE",
        f"/{course_id}/materials/", 
        json=material_ids
    )
    
    assert response.status_code == 200

def test_delete_materials_not_found(client, monkeypatch):
    course_id = str(uuid.uuid4())
    material_ids = [str(uuid.uuid4())]
    
    monkeypatch.setattr(courses, "verify_user_owner", lambda db, user, course_id: None)
    monkeypatch.setattr(courses, "get_material", lambda db, material_id: None)
    
    # Use the request method with the proper method and json parameters
    response = client.request(
        "DELETE",
        f"/{course_id}/materials/", 
        json=material_ids
    )
    
    assert response.status_code == 404
    assert "Material not found" in response.json()["detail"]

# Tests for GET /{course_id}/materials/preprocess - Preprocess materials
def test_preprocess_materials_success(client, monkeypatch, mock_course):
    course_id = mock_course.id
    
    # Create mock materials with audio/video types
    material1 = MagicMock(id=str(uuid.uuid4()), type="audio/mp3", transcription_s3_uri=None, s3_uri="s3://content/audio1.mp3")
    material2 = MagicMock(id=str(uuid.uuid4()), type="video/mp4", transcription_s3_uri=None, s3_uri="s3://content/video1.mp4")
    
    monkeypatch.setattr(courses, "get_course", lambda db, course_id: mock_course)
    monkeypatch.setattr(courses, "verify_user_owner", lambda db, user, course_id: None)
    monkeypatch.setattr(courses, "get_materials_by_course", lambda db, course_id: [material1, material2])
    monkeypatch.setattr(courses, "run_preprocessing_job", 
                       AsyncMock(return_value=[
                           {"materialId": material1.id, "transcribedFileUri": "s3://transcribed/audio1.txt"},
                           {"materialId": material2.id, "transcribedFileUri": "s3://transcribed/video1.txt"}
                       ]))
    monkeypatch.setattr(courses, "update_material_transcription_uri", lambda db, mid, uri: None)
    
    response = client.get(f"/{course_id}/materials/preprocess")
    
    assert response.status_code == 200
    assert "Preprocessing completed" in response.json()["message"]

def test_preprocess_materials_no_transcriptable_materials(client, monkeypatch, mock_course):
    course_id = mock_course.id
    
    # Create mock materials with non-audio/video types
    material = MagicMock(id=str(uuid.uuid4()), type="application/pdf", transcription_s3_uri=None)
    
    monkeypatch.setattr(courses, "get_course", lambda db, course_id: mock_course)
    monkeypatch.setattr(courses, "verify_user_owner", lambda db, user, course_id: None)
    monkeypatch.setattr(courses, "get_materials_by_course", lambda db, course_id: [material])
    
    response = client.get(f"/{course_id}/materials/preprocess")
    
    assert response.status_code == 200
    assert "No audio/video materials found" in response.json()["message"]

def test_preprocess_materials_course_not_found(client, monkeypatch):
    course_id = str(uuid.uuid4())
    
    monkeypatch.setattr(courses, "get_course", lambda db, course_id: None)
    
    response = client.get(f"/{course_id}/materials/preprocess")
    
    assert response.status_code == 404
    assert "Course not found" in response.json()["detail"]

# Tests for GET /{course_id}/sample_questions - Get sample questions
def test_get_sample_questions_success(client, monkeypatch, mock_course):
    course_id = mock_course.id
    
    monkeypatch.setattr(courses, "verify_user_owner", lambda db, user, course_id: None)
    monkeypatch.setattr(courses, "get_course", lambda db, course_id: mock_course)
    
    response = client.get(f"/{course_id}/sample_questions")
    
    assert response.status_code == 200
    assert response.json()["questions"] == mock_course.sample_questions

def test_get_sample_questions_empty(client, monkeypatch):
    course = MagicMock(id=str(uuid.uuid4()), sample_questions=None)
    
    monkeypatch.setattr(courses, "verify_user_owner", lambda db, user, course_id: None)
    monkeypatch.setattr(courses, "get_course", lambda db, course_id: course)
    
    response = client.get(f"/{course.id}/sample_questions")
    
    assert response.status_code == 200
    assert response.json()["questions"] == []

def test_get_sample_questions_not_found(client, monkeypatch):
    course_id = str(uuid.uuid4())
    
    monkeypatch.setattr(courses, "verify_user_owner", lambda db, user, course_id: None)
    monkeypatch.setattr(courses, "get_course", lambda db, course_id: None)
    
    response = client.get(f"/{course_id}/sample_questions")
    
    assert response.status_code == 404
    assert "Course not found" in response.json()["detail"]

# Tests for GET /{course_id}/materials/ - Get course with materials
def test_get_course_with_materials_success(client, monkeypatch, mock_course):
    course_id = mock_course.id
    
    # Create mock materials
    material1 = MagicMock(id=str(uuid.uuid4()), title="Material 1", type="application/pdf", 
                         s3_uri="s3://content/file1.pdf", status="Uploaded")
    material2 = MagicMock(id=str(uuid.uuid4()), title="Material 2", type="audio/mp3", 
                         s3_uri="s3://content/file2.mp3", status="Transcribed")
    materials = [material1, material2]
    
    monkeypatch.setattr(courses, "get_course", lambda db, course_id: mock_course)
    monkeypatch.setattr(courses, "get_materials_by_course", lambda db, course_id: materials)
    monkeypatch.setattr(courses, "generate_presigned_url", lambda bucket, s3_uri: f"https://presigned-url/{s3_uri}")
    
    response = client.get(f"/{course_id}/materials/")
    
    assert response.status_code == 200
    assert response.json()["id"] == mock_course.id
    assert response.json()["title"] == mock_course.title
    assert len(response.json()["materials"]) == 2
    assert response.json()["materials"][0]["id"] == material1.id
    assert response.json()["materials"][1]["id"] == material2.id

def test_get_course_with_materials_not_found(client, monkeypatch):
    course_id = str(uuid.uuid4())
    
    monkeypatch.setattr(courses, "get_course", lambda db, course_id: None)
    
    response = client.get(f"/{course_id}/materials/")
    
    assert response.status_code == 404
    assert "Course not found" in response.json()["detail"]

# Tests for POST /invites/ - Invite user
def test_invite_user_success(client, monkeypatch, mock_course):
    invite_data = {"email": "student@example.com", "course_id": str(mock_course.id)}
    invite_code = "mock_invite_code"
    
    # Create a mock invite with the invite_code attribute
    mock_invite = MagicMock()
    mock_invite.invite_code = invite_code
    
    with patch("uuid.uuid4") as mock_uuid:
        mock_uuid.return_value.hex = invite_code
        monkeypatch.setattr(courses, "create_invite", lambda db, invite_data: mock_invite)
        monkeypatch.setattr(courses, "get_course", lambda db, course_id: mock_course)
        monkeypatch.setattr(courses, "send_invite_email", lambda email, url, title: None)
        
        response = client.post("/invites/", json=invite_data)
        
        assert response.status_code == 200
        assert response.json()["invite_code"] == invite_code
        assert response.json()["message"] == "Invite sent"

def test_invite_user_error(client, monkeypatch):
    invite_data = {"email": "student@example.com", "course_id": str(uuid.uuid4())}
    
    with patch("uuid.uuid4") as mock_uuid:
        mock_uuid.return_value.hex = "mock_invite_code"
        monkeypatch.setattr(courses, "create_invite", lambda db, invite_data: 
                            exec('raise Exception("Invite creation failed")'))
        
        response = client.post("/invites/", json=invite_data)
        
        assert response.status_code == 400
        assert "Invite creation failed" in response.json()["detail"]

# Tests for GET /invites/{course_id} - Get invitations by course
def test_get_invitations_by_course_success(client, monkeypatch, mock_course):
    course_id = str(uuid.uuid4())
    
    # Create a proper invite object with string values instead of MagicMock objects
    invite_id = str(uuid.uuid4())
    proper_invite = MagicMock()
    proper_invite.id = invite_id
    proper_invite.invite_code = "test_invite_code"
    proper_invite.email = "test_student@example.com"
    proper_invite.course_id = course_id  # Use the same UUID string
    proper_invite.expires_at = datetime.now(timezone.utc) + timedelta(days=7)
    proper_invite.created_at = datetime.now()
    proper_invite.status = "pending"  # Add a status field
    
    # Use the proper invite object
    monkeypatch.setattr(courses, "get_invitations_by_course", lambda db, cid: [proper_invite])
    
    response = client.get(f"/invites/{course_id}")
    
    assert response.status_code == 200
    assert len(response.json()) == 1
    assert response.json()[0]["invite_code"] == proper_invite.invite_code
    assert response.json()[0]["email"] == proper_invite.email
    assert response.json()[0]["id"] == proper_invite.id
    assert response.json()[0]["course_id"] == course_id

def test_get_invitations_by_course_empty(client, monkeypatch):
    course_id = str(uuid.uuid4())
    
    monkeypatch.setattr(courses, "get_invitations_by_course", lambda db, course_id: [])
    
    response = client.get(f"/invites/{course_id}")
    
    assert response.status_code == 200
    assert response.json() == []

# Tests for POST /invites/confirm - Confirm invite
def test_confirm_invite_success(client, monkeypatch, mock_invite):
    # Prepare the confirmation data
    confirm_data = {
        "invite_code": mock_invite.invite_code,
        "password": "Password123!",
        "given_name": "Test",
        "family_name": "Student",
        "locale": "en-US"
    }
    
    # Make the mock invite's expiry date valid (future date)
    mock_invite.expires_at = datetime.now(timezone.utc) + timedelta(days=1)
    
    monkeypatch.setattr(courses, "get_invite_by_code", lambda db, code: mock_invite)
    monkeypatch.setattr(courses, "create_cognito_and_db_user", lambda user, db: {"id": "new_user_id"})
    monkeypatch.setattr(courses, "delete_invite", lambda db, code: None)
    
    response = client.post("/invites/confirm", json=confirm_data)
    
    assert response.status_code == 200
    assert response.json()["message"] == "User created in Cognito and database"
    assert response.json()["email"] == mock_invite.email

def test_confirm_invite_expired(client, monkeypatch, mock_invite):
    # Prepare the confirmation data
    confirm_data = {
        "invite_code": mock_invite.invite_code,
        "password": "Password123!",
        "given_name": "Test",
        "family_name": "Student",
        "locale": "en-US"
    }
    
    # Make the mock invite's expiry date invalid (past date)
    mock_invite.expires_at = datetime.now(timezone.utc) - timedelta(days=1)
    
    monkeypatch.setattr(courses, "get_invite_by_code", lambda db, code: mock_invite)
    
    response = client.post("/invites/confirm", json=confirm_data)
    
    assert response.status_code == 400
    assert "Invalid or expired invite" in response.json()["detail"]

def test_confirm_invite_not_found(client, monkeypatch):
    # Prepare the confirmation data
    confirm_data = {
        "invite_code": "invalid_code",
        "password": "Password123!",
        "given_name": "Test",
        "family_name": "Student",
        "locale": "en-US"
    }
    
    monkeypatch.setattr(courses, "get_invite_by_code", lambda db, code: None)
    
    response = client.post("/invites/confirm", json=confirm_data)
    
    assert response.status_code == 400
    assert "Invalid or expired invite" in response.json()["detail"]