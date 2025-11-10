# © [2025] EDT&Partners. Licensed under CC BY 4.0.

from unittest.mock import MagicMock, patch
from datetime import datetime
import json
import pytest
from sqlalchemy.exc import SQLAlchemyError
import uuid
from database.models import Request, Question, Document
from database.crud import (
    save_request,
    save_request_and_questions,
    get_requests_and_questions,
    get_questions_request,
    get_request_by_id,
    get_request_id_by_document,
    create_question,
    validate_questions_format
)

@pytest.fixture
def db():
    # Create a mock session
    session = MagicMock()
    
    # Simulate session.add assigning an id
    def fake_add(obj):
        if isinstance(obj, Request):
            obj.id = uuid.uuid4()
            obj.created_at = datetime.now()
        elif isinstance(obj, Question):
            obj.id = uuid.uuid4()
        elif isinstance(obj, Document):
            obj.id = uuid.uuid4()
    session.add.side_effect = fake_add
    
    # Setup fake query method
    query_mock = MagicMock()
    session.query.return_value = query_mock
    
    # Setup fake execute method
    execute_mock = MagicMock()
    session.execute.return_value = execute_mock
    
    return session

def test_save_request(db):
    # Test data
    title = "Test Request"
    user_id = "user123"
    service_id = 1
    
    # Call function
    request = save_request(db, title, user_id, service_id)
    
    # Assertions
    assert request.title == title
    assert request.user_id == user_id
    assert request.service_id == service_id
    assert request.id is not None
    assert request.created_at is not None
    db.add.assert_called_once()
    db.commit.assert_called_once()
    db.refresh.assert_called_once()

def test_validate_questions_format_with_dict():
    # Test with a dictionary
    questions_dict = [{"question": "Q1", "type": "mcq", "options": ["A", "B"]}]
    result = validate_questions_format(questions_dict)
    assert result == questions_dict

def test_validate_questions_format_with_json_string():
    # Test with a JSON string
    questions_json = '[{"question": "Q1", "type": "mcq", "options": ["A", "B"]}]'
    result = validate_questions_format(questions_json)
    assert isinstance(result, list)
    assert result[0]["question"] == "Q1"

def test_validate_questions_format_with_invalid_json():
    # Test with invalid JSON
    with pytest.raises(ValueError) as excinfo:
        validate_questions_format('invalid json')
    assert "not a valid JSON string" in str(excinfo.value)

def test_create_question(db):
    # Test data
    question_data = {
        "question": "Test question?",
        "type": "mcq",
        "options": ["A", "B", "C"],
        "correct_answer": "A",
        "reason": "Because A is correct"
    }
    request_id = 123
    
    # Call function
    question = create_question(db, question_data, request_id)
    
    # Assertions
    assert question["question"] == "Test question?"
    assert question["type"] == "mcq"
    assert question["options"] == ["A", "B", "C"]
    assert question["correct_answer"] == "A"
    assert question["reason"] == "Because A is correct"
    assert "id" in question
    db.add.assert_called_once()
    db.commit.assert_called_once()
    db.refresh.assert_called_once()

def test_create_question_with_invalid_type(db):
    # Test data with invalid question type
    question_data = {
        "question": "Test question?",
        "type": "invalid",
        "options": ["A", "B", "C"],
        "correct_answer": "A"
    }
    request_id = 123
    
    # Call function and expect ValueError
    with pytest.raises(ValueError) as excinfo:
        create_question(db, question_data, request_id)
    assert "Unknown question type" in str(excinfo.value)

def test_create_question_mcq_missing_options(db):
    # Test MCQ without options
    question_data = {
        "question": "Test question?",
        "type": "mcq",
        "correct_answer": "A"
    }
    request_id = 123
    
    # Call function and expect ValueError
    with pytest.raises(ValueError) as excinfo:
        create_question(db, question_data, request_id)
    assert "missing 'options'" in str(excinfo.value)

def test_save_request_and_questions(db):
    # Test data
    data = {
        "title": "Test Request with Questions",
        "user_id": "user123",
        "service_id": 1,
        "questions": json.dumps([
            {
                "question": "Q1?",
                "type": "mcq",
                "options": ["A", "B", "C"],
                "correct_answer": "A",
                "reason": "Because A is correct"
            }
        ])
    }
    
    # Call function
    result = save_request_and_questions(db, data)
    
    # Assertions
    assert "request" in result
    assert "questions" in result
    assert result["request"]["title"] == "Test Request with Questions"
    assert len(result["questions"]) == 1
    assert result["questions"][0]["question"] == "Q1?"

def test_get_requests_and_questions(db):
    # Mock data
    user_id = "user123"
    service_id = 1
    
    # Create mock requests
    request1 = MagicMock(id=uuid.uuid4(), title="Request 1", user_id=user_id, service_id=service_id)
    request1.created_at = datetime.now()
    request2 = MagicMock(id=uuid.uuid4(), title="Request 2", user_id=user_id, service_id=service_id)
    request2.created_at = datetime.now()
    
    # Create mock questions
    question1 = MagicMock(request_id=request1.id, type="mcq")
    question2 = MagicMock(request_id=request1.id, type="mcq")
    question3 = MagicMock(request_id=request2.id, type="tf")
    question4 = MagicMock(request_id=request2.id, type="open")
    
    # First, create a new MagicMock for each execute call
    requests_execute_result = MagicMock()
    requests_execute_result.scalars.return_value.all.return_value = [request1, request2]
    
    questions_execute_result = MagicMock()
    questions_execute_result.scalars.return_value.all.return_value = [question1, question2, question3, question4]
    
    # Then patch the function that's being tested to use our mock results
    with patch('database.crud.select', autospec=True):
        # Set up db.execute to return our mocked results in sequence
        db.execute.side_effect = [requests_execute_result, questions_execute_result]
        
        # Call function
        result = get_requests_and_questions(db, user_id, service_id)
        
        # Assertions
        assert "data" in result
        assert len(result["data"]) == 2
        
        # Check first request
        request1_result = next((r for r in result["data"] if r["id"] == str(request1.id)), None)
        assert request1_result is not None
        assert request1_result["mcq_count"] == 2
        assert request1_result["tfq_count"] == 0
        assert request1_result["open_count"] == 0
        
        # Check second request
        request2_result = next((r for r in result["data"] if r["id"] == str(request2.id)), None)
        assert request2_result is not None
        assert request2_result["mcq_count"] == 0
        assert request2_result["tfq_count"] == 1
        assert request2_result["open_count"] == 1

def test_get_request_by_id(db):
    # Test data
    request_id = uuid.uuid4()
    user_id = "user123"
    
    # Mock request
    mock_request = MagicMock(id=request_id, title="Test Request", user_id=user_id)
    
    # Setup mock returns
    mock_result = MagicMock()
    mock_result.scalars.return_value.first.return_value = mock_request
    db.execute.return_value = mock_result
    
    # Call function
    result = get_request_by_id(db, request_id, user_id)
    
    # Assertions
    assert result == mock_request
    db.execute.assert_called_once()

def test_get_request_by_id_not_found(db):
    # Test data
    request_id = uuid.uuid4()
    user_id = "user123"
    
    # Setup mock returns for not found
    mock_result = MagicMock()
    mock_result.scalars.return_value.first.return_value = None
    db.execute.return_value = mock_result
    
    # Call function
    result = get_request_by_id(db, request_id, user_id)
    
    # Assertions
    assert result is None
    db.execute.assert_called_once()

def test_get_request_id_by_document(db):
    # Test data
    document_id = "doc123"
    request_id = uuid.uuid4()
    
    # Mock document
    mock_document = MagicMock(id=document_id, request_id=request_id)
    
    # Setup mock returns
    mock_result = MagicMock()
    mock_result.scalars.return_value.first.return_value = mock_document
    db.execute.return_value = mock_result
    
    # Call function
    result = get_request_id_by_document(db, document_id)
    
    # Assertions
    assert result == request_id
    db.execute.assert_called_once()

def test_get_questions_request(db):
    # Test data
    request_id = uuid.uuid4()
    user_id = "user123"
    
    # Mock request and questions
    mock_request = MagicMock(id=request_id, title="Test Request", created_at=datetime.now())
    
    mock_question1 = MagicMock(
        id="q1",
        question="Question 1?",
        options='["A", "B", "C"]',
        type="mcq",
        correct_answer="A",
        reason="Because A is correct"
    )
    
    mock_question2 = MagicMock(
        id="q2",
        question="Question 2?",
        options=["Yes", "No"],  # Test with Python list instead of JSON string
        type="tf",
        correct_answer="Yes",
        reason="Because Yes is correct"
    )
    
    # Patch get_request_by_id
    with patch('database.crud.get_request_by_id', return_value=mock_request):
        # Setup mock returns for questions
        mock_questions_result = MagicMock()
        mock_questions_result.scalars.return_value.all.return_value = [mock_question1, mock_question2]
        db.execute.return_value = mock_questions_result
        
        # Call function
        result = get_questions_request(db, request_id, user_id)
        
        # Assertions
        assert result["id"] == request_id
        assert result["title"] == "Test Request"
        assert len(result["questions"]) == 2
        
        # Check question details
        q1 = result["questions"][0]
        assert q1["id"] == "q1"
        assert q1["question"] == "Question 1?"
        assert q1["type"] == "mcq"
        assert q1["options"] == ["A", "B", "C"]
        
        q2 = result["questions"][1]
        assert q2["id"] == "q2"
        assert q2["question"] == "Question 2?"
        assert q2["type"] == "tf"
        assert q2["options"] == ["Yes", "No"]

def test_get_questions_request_not_found(db):
    # Test data
    request_id = uuid.uuid4()
    user_id = "user123"
    
    # Patch get_request_by_id to return None
    with patch('database.crud.get_request_by_id', return_value=None):
        # Call function
        result = get_questions_request(db, request_id, user_id)
        
        # Assertions
        assert result is None

def test_get_questions_request_sqlalchemy_error(db):
    # Test data
    request_id = uuid.uuid4()
    user_id = "user123"
    
    # Mock SQLAlchemyError
    db.execute.side_effect = SQLAlchemyError("Database connection failed")
    
    # Call function
    with patch('database.crud.ic') as mock_ic:  # Mock the ic logger
        result = get_questions_request(db, request_id, user_id)
        
        # Assertions
        assert "detail" in result
        assert "database" in result["detail"].lower()
        mock_ic.assert_called()  # Verify that the error was logged

def test_get_questions_request_json_decode_error(db):
    # Test data
    request_id = uuid.uuid4()
    user_id = "user123"
    
    # Mock request with invalid JSON in options
    mock_request = MagicMock(id=request_id, title="Test Request", created_at=datetime.now())
    
    # Mock question with invalid JSON
    mock_question = MagicMock(
        id="q1",
        question="Question 1?",
        options='{invalid json}',  # Invalid JSON that will cause JSONDecodeError
        type="mcq",
        correct_answer="A",
        reason="Because A is correct"
    )
    
    # Setup mocks
    with patch('database.crud.get_request_by_id', return_value=mock_request):
        mock_questions_result = MagicMock()
        mock_questions_result.scalars.return_value.all.return_value = [mock_question]
        db.execute.return_value = mock_questions_result
        
        # Call function with mock ic to verify logging
        with patch('database.crud.ic') as mock_ic:
            result = get_questions_request(db, request_id, user_id)
            
            # Assertions - per-question JSON errors are handled by setting options to []
            assert "id" in result
            assert "questions" in result
            assert len(result["questions"]) == 1
            assert result["questions"][0]["options"] == []  # Empty list due to error handling
            mock_ic.assert_called()  # Verify that the error was logged

def test_get_questions_request_json_decode_error_handled(db):
    # Test data
    request_id = uuid.uuid4()
    user_id = "user123"
    
    # Mock request with invalid JSON that should still work through error handling
    mock_request = MagicMock(id=request_id, title="Test Request", created_at=datetime.now())
    
    # First question with valid options
    mock_question1 = MagicMock(
        id="q1",
        question="Question 1?",
        options='["A", "B", "C"]',  # Valid JSON
        type="mcq",
        correct_answer="A",
        reason="Because A is correct"
    )
    
    # Second question with invalid JSON that will trigger exception handling
    mock_question2 = MagicMock(
        id="q2",
        question="Question 2?",
        options='{invalid json}',  # Invalid JSON
        type="mcq",
        correct_answer="B",
        reason="Because B is correct"
    )
    
    # Setup mocks
    with patch('database.crud.get_request_by_id', return_value=mock_request):
        mock_questions_result = MagicMock()
        mock_questions_result.scalars.return_value.all.return_value = [mock_question1, mock_question2]
        db.execute.return_value = mock_questions_result
        
        # The real function catches JSONDecodeError and assigns empty options
        with patch('json.loads', side_effect=[["A", "B", "C"], json.JSONDecodeError('Expecting value', '', 0)]):
            with patch('database.crud.ic') as mock_ic:
                result = get_questions_request(db, request_id, user_id)
                
                # Assertions
                assert "id" in result
                assert "questions" in result
                assert len(result["questions"]) == 2
                
                # First question should have parsed options
                assert result["questions"][0]["options"] == ["A", "B", "C"]
                
                # Second question should have empty options due to error handling
                assert result["questions"][1]["options"] == []
                
                mock_ic.assert_called()  # Verify that the error was logged

def test_get_questions_request_unexpected_error(db):
    # Test data
    request_id = uuid.uuid4()
    user_id = "user123"
    
    # Patch get_request_by_id to raise an unexpected exception
    with patch('database.crud.get_request_by_id', side_effect=Exception("Unexpected error")):
        with patch('database.crud.ic') as mock_ic:
            result = get_questions_request(db, request_id, user_id)
            
            # Assertions
            assert "detail" in result
            assert "unexpected" in result["detail"].lower()
            mock_ic.assert_called()  # Verify that the error was logged
