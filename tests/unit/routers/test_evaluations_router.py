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

import json
import uuid
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from unittest.mock import MagicMock, AsyncMock, patch

# Import the router and dependencies
from routers import evaluations
from routers.evaluations import router, get_db
from utility.auth import oauth2_scheme

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

# --- Test Rubric Endpoints ---

def test_create_rubric_with_data(client, monkeypatch):
    """Test creating a rubric with provided data"""
    # Mock rubric data and user
    rubric_data = json.dumps({
        "name": "Test Rubric",
        "description": "A test rubric",
        "indicators": [
            {
                "name": "Quality",
                "weight": 60,
                "criteria": [
                    {"key": "1", "description": "Poor"},
                    {"key": "3", "description": "Average"},
                    {"key": "5", "description": "Excellent"}
                ]
            }
        ]
    })
    
    # Mock db operations
    FakeUser = type("FakeUser", (), {"id": "user123"})
    FakeRubric = type("FakeRubric", (), {"id": uuid.uuid4(), "name": "Test Rubric", "description": "A test rubric"})
    monkeypatch.setattr(evaluations, "get_user_by_cognito_id", lambda db, sub: FakeUser())
    monkeypatch.setattr(evaluations, "save_rubric", lambda db, data, user_id: FakeRubric())
    
    # Call the endpoint
    response = client.post("/rubrics/", data={"rubric_data": rubric_data})
    
    # Verify response
    assert response.status_code == 200
    assert "id" in response.json()
    assert response.json()["name"] == "Test Rubric"
    assert response.json()["description"] == "A test rubric"

def test_create_rubric_with_file_and_ai(client, monkeypatch):
    """Test creating a rubric with an uploaded file and AI generation"""
    # Mock file handling and AI response
    source_text = "This is a sample rubric text"
    ai_generated_rubric = {
        "name": "AI Generated Rubric",
        "description": "An AI-generated rubric",
        "indicators": [
            {
                "name": "Quality", 
                "weight": 100, 
                "criteria": {"1": "Bad", "5": "Good"}
            }
        ]
    }
    
    # Setup mocks
    FakeUser = type("FakeUser", (), {"id": "user123"})
    FakeRubric = type("FakeRubric", (), {
        "id": uuid.uuid4(), 
        "name": "AI Generated Rubric", 
        "description": "An AI-generated rubric"
    })
    
    # Mock async functions to return immediately
    async def mock_process_files(files, flag=False, ai=True):
        return source_text
    
    async def mock_get_text_from_material_id(db, materials_id):
        return source_text
    
    async def mock_invoke_bedrock_model(prompt):
        return json.dumps(ai_generated_rubric)
    
    async def mock_process_analytics(*args, **kwargs):
        pass
        
    monkeypatch.setattr(evaluations, "process_uploaded_files", mock_process_files)
    monkeypatch.setattr(evaluations, "get_text_from_material_id", mock_get_text_from_material_id)
    monkeypatch.setattr(evaluations, "detect_language", lambda text: "English")
    monkeypatch.setattr(evaluations, "invoke_bedrock_model", mock_invoke_bedrock_model)
    monkeypatch.setattr(evaluations, "get_user_by_cognito_id", lambda db, sub: FakeUser())
    monkeypatch.setattr(evaluations, "save_rubric", lambda db, data, user_id: FakeRubric())
    monkeypatch.setattr(evaluations, "_clean_formatted_text", lambda text: text)
    monkeypatch.setattr(evaluations, "process_and_save_analytics", mock_process_analytics)
    monkeypatch.setattr(evaluations, "handle_save_request", lambda db, title, user_id, code: uuid.uuid4())
    
    # Call the endpoint with a file
    test_file = ("test.pdf", b"%PDF-1.5\n%\xE2\xE3\xCF\xD3\n" + b"dummy pdf content", "application/pdf")
    response = client.post(
        "/rubrics/",
        files={"files[]": test_file}
    )
    
    # Verify response
    assert response.status_code == 200
    assert "id" in response.json()
    assert response.json()["name"] == "AI Generated Rubric"

def test_create_rubric_invalid_data(client, monkeypatch):
    """Test creating a rubric with invalid data"""
    # Pass invalid JSON data
    response = client.post("/rubrics/", data={"rubric_data": "invalid json"})
    
    assert response.status_code == 400
    assert "Invalid rubric data format" in response.json()["detail"]

def test_get_rubrics_list(client, monkeypatch):
    """Test getting a list of rubrics"""
    # Mock user and rubrics
    FakeUser = type("FakeUser", (), {"id": "user123"})
    FakeRubric = type("FakeRubric", (), {})
    rubric1 = FakeRubric()
    rubric1.id = str(uuid.uuid4())
    rubric1.name = "Rubric 1"
    rubric1.description = "First test rubric"
    
    rubric2 = FakeRubric()
    rubric2.id = str(uuid.uuid4())
    rubric2.name = "Rubric 2"
    rubric2.description = "Second test rubric"
    
    # Setup mocks
    monkeypatch.setattr(evaluations, "get_user_by_cognito_id", lambda db, sub: FakeUser())
    monkeypatch.setattr(evaluations, "get_rubrics", lambda db, user_id: [rubric1, rubric2])
    
    # Call the endpoint
    response = client.get("/rubrics/")
    
    # Verify response
    assert response.status_code == 200
    assert len(response.json()) == 2
    assert response.json()[0]["name"] == "Rubric 1"
    assert response.json()[1]["name"] == "Rubric 2"

def test_get_rubric_by_id(client, monkeypatch):
    """Test getting a specific rubric by ID"""
    # Create mock rubric with indicators
    rubric_id = str(uuid.uuid4())
    FakeRubric = type("FakeRubric", (), {})
    fake_rubric = FakeRubric()
    fake_rubric.id = rubric_id
    fake_rubric.name = "Test Rubric"
    fake_rubric.description = "A test rubric description"
    fake_rubric.created_by = "user123"
    
    # Create indicator
    FakeIndicator = type("FakeIndicator", (), {})
    indicator = FakeIndicator()
    indicator.name = "Quality"
    indicator.weight = 100
    # Update format of the criteria to match the array approach
    indicator.criteria = json.dumps({"1": "Poor", "5": "Excellent"})
    
    fake_rubric.indicators = [indicator]
    
    # Setup mocks
    monkeypatch.setattr(evaluations, "get_rubric_by_id", lambda db, rid: fake_rubric)
    
    # Call the endpoint
    response = client.get(f"/rubrics/{rubric_id}")
    
    # Verify response
    assert response.status_code == 200
    assert response.json()["id"] == rubric_id
    assert response.json()["name"] == "Test Rubric"
    assert len(response.json()["indicators"]) == 1
    assert response.json()["indicators"][0]["name"] == "Quality"

def test_get_rubric_not_found(client, monkeypatch):
    """Test getting a non-existent rubric"""
    # Setup mock to return None
    monkeypatch.setattr(evaluations, "get_rubric_by_id", lambda db, rid: None)
    
    # Call with random UUID
    response = client.get(f"/rubrics/{uuid.uuid4()}")
    
    # Verify response
    assert response.status_code == 404

def test_update_rubric(client, monkeypatch):
    """Test updating a rubric"""
    # Setup test data
    rubric_id = uuid.uuid4()
    update_data = {
        "name": "Updated Rubric",
        "description": "Updated description",
        "indicators": [
            {
                "name": "Quality",
                "weight": 75,
                "criteria": {"1": "Poor", "3": "Good", "5": "Excellent"}
            }
        ]
    }
    
    # Mock user and rubric
    FakeUser = type("FakeUser", (), {"id": "user123"})
    FakeRubric = type("FakeRubric", (), {
        "id": rubric_id,
        "name": "Updated Rubric",
        "description": "Updated description",
        "created_by": "user123"
    })
    
    monkeypatch.setattr(evaluations, "get_user_by_cognito_id", lambda db, sub: FakeUser())
    monkeypatch.setattr(evaluations, "get_rubric_by_id", lambda db, rid: FakeRubric)
    monkeypatch.setattr(evaluations, "update_rubric", lambda db, rid, data: FakeRubric)
    
    # Call the endpoint
    response = client.put(f"/rubrics/{rubric_id}", json=update_data)
    
    # Verify response
    assert response.status_code == 200
    assert response.json()["name"] == "Updated Rubric"
    assert response.json()["description"] == "Updated description"

def test_update_rubric_unauthorized(client, monkeypatch):
    """Test unauthorized rubric update"""
    # Setup test data with different user
    rubric_id = uuid.uuid4()
    
    # Mock user and rubric with different user IDs
    FakeUser = type("FakeUser", (), {"id": "user123"})
    FakeRubric = type("FakeRubric", (), {"created_by": "different_user"})
    
    monkeypatch.setattr(evaluations, "get_user_by_cognito_id", lambda db, sub: FakeUser())
    monkeypatch.setattr(evaluations, "get_rubric_by_id", lambda db, rid: FakeRubric)
    
    # Call the endpoint
    response = client.put(
        f"/rubrics/{rubric_id}",
        json={"name": "Updated Rubric"}
    )
    
    # Verify response
    assert response.status_code == 403
    assert "not authorized" in response.json()["detail"]

def test_delete_rubric(client, monkeypatch):
    """Test deleting a rubric"""
    rubric_id = str(uuid.uuid4())
    
    # Mock delete operation
    monkeypatch.setattr(evaluations, "delete_rubric", lambda db, rid: rubric_id)
    
    # Call the endpoint
    response = client.delete(f"/rubrics/{rubric_id}")
    
    # Verify response
    assert response.status_code == 200
    assert response.json()["id"] == rubric_id

def test_delete_rubric_not_found(client, monkeypatch):
    """Test deleting a non-existent rubric"""
    # Mock delete to return None (not found)
    monkeypatch.setattr(evaluations, "delete_rubric", lambda db, rid: None)
    
    # Call the endpoint with random UUID
    response = client.delete(f"/rubrics/{uuid.uuid4()}")
    
    # Verify response
    assert response.status_code == 404

# --- Test Evaluation Endpoints ---

def test_evaluate_exam(client, monkeypatch):
    """Test successful exam evaluation"""
    # Setup test data
    rubric_id = str(uuid.uuid4())
    evaluation_id = 12345
    
    # Mock file content and processing
    source_text = "This is the exam text to evaluate"
    
    # Mock async functions to return immediately
    async def mock_process_files(files):
        return source_text
    
    async def mock_invoke_bedrock_model(prompt, llm_id=None):
        return json.dumps({
            "feedback": "Good work overall",
            "criteria_evaluation": [
                {"name": "Quality", "score": 4, "comments": "Well done"}
            ],
            "overall_comments": "Very good submission"
        })
    
    async def mock_process_analytics(*args, **kwargs):
        pass

    # Mock rubric
    FakeRubric = type("FakeRubric", (), {"name": "Test Rubric"})
    FakeRubric.id = rubric_id
    FakeRubric.indicators = []
    
    # Mock evaluation
    FakeEvaluation = type("FakeEvaluation", (), {})
    fake_eval = FakeEvaluation()
    fake_eval.id = evaluation_id
    fake_eval.rubric_id = rubric_id
    fake_eval.course_name = "Test Course"
    fake_eval.student_name = "John"
    fake_eval.student_surname = "Doe"
    fake_eval.exam_description = "Midterm"
    fake_eval.feedback = "Good work overall"
    fake_eval.criteria_evaluation = [{"name": "Quality", "score": 4}]
    fake_eval.overall_comments = "Very good submission"
    fake_eval.source_text = source_text
    
    # Mock evaluation prompt builder
    mock_prompt = "This is a mocked evaluation prompt"
    monkeypatch.setattr(evaluations, "build_evaluation_prompt", lambda text, rubric, lang, custom: mock_prompt)
    
    # Setup mocks
    monkeypatch.setattr(evaluations, "process_uploaded_files", mock_process_files)
    monkeypatch.setattr(evaluations, "detect_language", lambda text: "English")
    monkeypatch.setattr(evaluations, "get_rubric_by_id", lambda db, rid: FakeRubric)
    monkeypatch.setattr(evaluations, "invoke_bedrock_model", mock_invoke_bedrock_model)
    monkeypatch.setattr(evaluations, "get_user_by_cognito_id", lambda db, sub: type("FakeUser", (), {"id": "user123"})())
    monkeypatch.setattr(evaluations, "save_evaluation", lambda db, data, user_id: fake_eval)
    monkeypatch.setattr(evaluations, "process_and_save_analytics", mock_process_analytics)
    monkeypatch.setattr(evaluations, "handle_save_request", lambda db, title, user_id, code: uuid.uuid4())
    
    # Call the endpoint
    test_file = ("exam.pdf", b"%PDF-1.5\n%\xE2\xE3\xCF\xD3\n" + b"dummy pdf content", "application/pdf")
    response = client.post(
        "/evaluate-exam/",
        files={"files[]": test_file},
        data={
            "rubric_id": rubric_id,
            "course_name": "Test Course",
            "student_name": "John",
            "student_surname": "Doe",
            "exam_description": "Midterm"
        }
    )
    
    # Verify response
    assert response.status_code == 200
    assert response.json()["evaluation"]["id"] == evaluation_id
    assert response.json()["evaluation"]["rubric_id"] == rubric_id
    assert response.json()["evaluation"]["student_name"] == "John"

def test_evaluate_exam_no_files(client, monkeypatch):
    """Test exam evaluation without files"""
    # Call endpoint without files
    response = client.post(
        "/evaluate-exam/",
        data={
            "rubric_id": str(uuid.uuid4()),
            "course_name": "Test Course",
            "student_name": "John",
            "student_surname": "Doe",
            "exam_description": "Midterm"
        }
    )
    
    # Verify response
    assert response.status_code == 400
    assert "At least one file must be provided" in response.json()["detail"]

def test_evaluate_exam_rubric_not_found(client, monkeypatch):
    """Test exam evaluation with non-existent rubric"""
    # Mock process_uploaded_files
    async def mock_process_files(files):
        return "Sample text"
        
    monkeypatch.setattr(evaluations, "process_uploaded_files", mock_process_files)
    monkeypatch.setattr(evaluations, "detect_language", lambda text: "English")
    monkeypatch.setattr(evaluations, "get_user_by_cognito_id", lambda db, sub: type("FakeUser", (), {"id": "user123"})())
    
    # Return None for rubric
    monkeypatch.setattr(evaluations, "get_rubric_by_id", lambda db, rid: None)
    
    # Call the endpoint
    test_file = ("exam.pdf", b"dummy content", "application/pdf")
    response = client.post(
        "/evaluate-exam/",
        files={"files[]": test_file},
        data={
            "rubric_id": str(uuid.uuid4()),
            "course_name": "Test Course",
            "student_name": "John",
            "student_surname": "Doe",
            "exam_description": "Midterm"
        }
    )
    
    # Verify response
    assert response.status_code == 404
    assert "Rubric not found" in response.json()["detail"]

def test_create_evaluation_manually(client, monkeypatch):
    """Test creating an evaluation manually"""
    # Setup test data
    rubric_id = str(uuid.uuid4())
    evaluation_id = 12345
    criteria_eval = json.dumps([{"name": "Quality", "score": 4}])
    
    # Mock evaluation
    FakeEvaluation = type("FakeEvaluation", (), {})
    fake_eval = FakeEvaluation()
    fake_eval.id = evaluation_id
    fake_eval.rubric_id = rubric_id
    fake_eval.course_name = "Test Course"
    fake_eval.student_name = "John"
    fake_eval.student_surname = "Doe"
    fake_eval.exam_description = "Midterm"
    fake_eval.feedback = "Good work"
    fake_eval.criteria_evaluation = [{"name": "Quality", "score": 4}]
    fake_eval.overall_comments = "Nice job"
    fake_eval.source_text = "Exam content"
    
    # Setup mocks
    monkeypatch.setattr(evaluations, "get_user_by_cognito_id", lambda db, sub: type("FakeUser", (), {"id": "user123"})())
    monkeypatch.setattr(evaluations, "save_evaluation", lambda db, data, user_id: fake_eval)
    
    # Call the endpoint
    response = client.post(
        "/",
        data={
            "rubric_id": rubric_id,
            "course_name": "Test Course",
            "student_name": "John",
            "student_surname": "Doe",
            "exam_description": "Midterm",
            "feedback": "Good work",
            "criteria_evaluation": criteria_eval,
            "overall_comments": "Nice job",
            "source_text": "Exam content"
        }
    )
    
    # Verify response
    assert response.status_code == 200
    assert response.json()["id"] == evaluation_id
    assert response.json()["rubric_id"] == rubric_id
    assert response.json()["student_name"] == "John"

def test_list_evaluations(client, monkeypatch):
    """Test listing all evaluations"""
    # Create mock evaluations
    FakeEvaluation = type("FakeEvaluation", (), {})
    eval1 = FakeEvaluation()
    eval1.id = 1
    eval1.rubric_id = str(uuid.uuid4())
    eval1.course_name = "Course 1"
    eval1.student_name = "John"
    eval1.student_surname = "Doe"
    eval1.exam_description = "Midterm"
    eval1.feedback = "Good"
    eval1.criteria_evaluation = [{"name": "Quality", "score": 4}]
    eval1.overall_comments = "Nice job"
    eval1.source_text = "Content 1"
    
    eval2 = FakeEvaluation()
    eval2.id = 2
    eval2.rubric_id = str(uuid.uuid4())
    eval2.course_name = "Course 2"
    eval2.student_name = "Jane"
    eval2.student_surname = "Doe"
    eval2.exam_description = "Midterm"
    eval2.feedback = "Bad"
    eval2.criteria_evaluation = [{"name": "Quality", "score": 1}]
    eval2.overall_comments = "Bad job"
    eval2.source_text = "Content 2"
    
    # Setup mocks
    monkeypatch.setattr(evaluations, "get_user_by_cognito_id", lambda db, sub: type("FakeUser", (), {"id": "user123"})())
    monkeypatch.setattr(evaluations, "get_evaluations", lambda db, uid: [eval1, eval2])
    
    # Call the endpoint
    response = client.get("/")
    
    # Verify response
    assert response.status_code == 200
    assert len(response.json()) == 2
    assert response.json()[0]["id"] == 1
    assert response.json()[0]["student_name"] == "John"
    assert response.json()[1]["id"] == 2
    assert response.json()[1]["student_name"] == "Jane"

def test_get_evaluation_by_id(client, monkeypatch):
    """Test getting a specific evaluation"""
    # Setup test data
    evaluation_id = str(uuid.uuid4())
    rubric_id = str(uuid.uuid4())
    
    # Mock evaluation
    FakeEvaluation = type("FakeEvaluation", (), {})
    fake_eval = FakeEvaluation()
    fake_eval.id = evaluation_id
    fake_eval.rubric_id = rubric_id
    fake_eval.course_name = "Test Course"
    fake_eval.student_name = "John"
    fake_eval.student_surname = "Doe"
    fake_eval.exam_description = "Midterm"
    fake_eval.feedback = "Good work"
    fake_eval.criteria_evaluation = json.dumps([{"name": "Quality", "score": 4}])
    fake_eval.overall_comments = "Nice job"
    fake_eval.source_text = "Exam content"
    
    # Mock rubric
    FakeRubric = type("FakeRubric", (), {"indicators": []})
    FakeIndicator = type("FakeIndicator", (), {"name": "Quality", "weight": 70})
    FakeRubric.indicators = [FakeIndicator]
    
    # Setup mocks
    monkeypatch.setattr(evaluations, "get_evaluation_by_id", lambda db, eid: fake_eval)
    monkeypatch.setattr(evaluations, "get_rubric_by_id", lambda db, rid: FakeRubric)
    
    # Call the endpoint
    response = client.get(f"/{evaluation_id}")
    
    # Verify response
    assert response.status_code == 200
    assert response.json()["id"] == evaluation_id
    assert response.json()["student_name"] == "John"
    assert response.json()["criteria_evaluation"][0]["name"] == "Quality"
    assert response.json()["criteria_evaluation"][0]["weight"] == 70

def test_get_evaluation_not_found(client, monkeypatch):
    """Test getting a non-existent evaluation"""
    # Setup mock to return None
    monkeypatch.setattr(evaluations, "get_evaluation_by_id", lambda db, eid: None)
    
    # Call with random UUID
    response = client.get(f"/{uuid.uuid4()}")
    
    # Verify response
    assert response.status_code == 404
    assert "Evaluation not found" in response.json()["detail"]

def test_update_evaluation(client, monkeypatch):
    """Test updating an evaluation"""
    # Setup test data
    evaluation_id = str(uuid.uuid4())
    
    # Mock updated evaluation
    FakeEvaluation = type("FakeEvaluation", (), {})
    fake_eval = FakeEvaluation()
    fake_eval.id = evaluation_id
    fake_eval.rubric_id = str(uuid.uuid4())
    fake_eval.course_name = "Updated Course"
    fake_eval.student_name = "John"
    fake_eval.student_surname = "Doe"
    fake_eval.exam_description = "Updated Exam"
    fake_eval.feedback = "Updated feedback"
    fake_eval.criteria_evaluation = [{"name": "Quality", "score": 5}]
    fake_eval.overall_comments = "Updated comments"
    fake_eval.source_text = "Updated content"
    
    # Setup mocks
    monkeypatch.setattr(evaluations, "update_evaluation", lambda db, eid, data: fake_eval)
    
    # Call the endpoint
    criteria_eval = json.dumps([{"name": "Quality", "score": 5}])
    response = client.put(
        f"/{evaluation_id}",
        data={
            "course_name": "Updated Course",
            "exam_description": "Updated Exam",
            "feedback": "Updated feedback",
            "criteria_evaluation": criteria_eval,
            "overall_comments": "Updated comments"
        }
    )
    
    # Verify response
    assert response.status_code == 200
    assert response.json()["id"] == evaluation_id
    assert response.json()["course_name"] == "Updated Course"
    assert response.json()["feedback"] == "Updated feedback"

def test_update_evaluation_not_found(client, monkeypatch):
    """Test updating a non-existent evaluation"""
    # Setup mock to return None
    monkeypatch.setattr(evaluations, "update_evaluation", lambda db, eid, data: None)
    
    # Call with random UUID
    evaluation_id = str(uuid.uuid4())
    criteria_eval = json.dumps([{"name": "Quality", "score": 5}])
    response = client.put(
        f"/{evaluation_id}",
        data={
            "course_name": "Updated Course",
            "criteria_evaluation": criteria_eval
        }
    )
    
    # Verify response
    assert response.status_code == 404
    assert "Evaluation not found" in response.json()["detail"]

def test_delete_evaluation(client, monkeypatch):
    """Test deleting an evaluation"""
    evaluation_id = str(uuid.uuid4())
    
    # Mock delete operation
    monkeypatch.setattr(evaluations, "delete_evaluation_by_id", lambda db, eid: evaluation_id)
    
    # Call the endpoint
    response = client.delete(f"/{evaluation_id}")
    
    # Verify response
    assert response.status_code == 200
    assert response.json()["id"] == evaluation_id

def test_delete_evaluation_not_found(client, monkeypatch):
    """Test deleting a non-existent evaluation"""
    # Mock delete to return None
    monkeypatch.setattr(evaluations, "delete_evaluation_by_id", lambda db, eid: None)
    
    # Call the endpoint with random UUID
    response = client.delete(f"/{uuid.uuid4()}")
    
    # Verify response
    assert response.status_code == 404
    assert "Evaluation not found" in response.json()["detail"]
