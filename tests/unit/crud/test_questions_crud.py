# © [2025] EDT&Partners. Licensed under CC BY 4.0.

import pytest
from uuid import uuid4
from datetime import datetime
from unittest.mock import MagicMock
from database.crud import (
    validate_questions_format,
    create_question,
    save_request_and_questions,
    get_questions_by_course_id,
    get_question_bank,
    get_questions_request,
    update_question_by_id,
    delete_question_by_id,
    get_question_by_id
)
from database.models import Question, Request, Course
from database.schemas import QuestionUpdate

@pytest.fixture
def db():
    # Return a MagicMock representing the DB session.
    return MagicMock()

def test_validate_questions_format_with_valid_json_string():
    questions_str = '[{"question": "What is 2+2?", "type": "open"}]'
    result = validate_questions_format(questions_str)
    assert isinstance(result, list)
    assert result[0]["question"] == "What is 2+2?"

def test_validate_questions_format_with_invalid_json_string():
    with pytest.raises(ValueError) as exc_info:
        validate_questions_format("not a json")
    assert "Questions field is not a valid JSON string" in str(exc_info.value)

def test_validate_questions_format_with_dict():
    questions_data = {"question": "Test?", "type": "open"}
    result = validate_questions_format(questions_data)
    assert result == questions_data

def test_create_question_non_dict(db):
    result = create_question(db, "not a dict", request_id=123)
    assert result is None

def test_create_question_unknown_type(db):
    q_data = {"question": "Test?", "type": "essay"}
    with pytest.raises(ValueError) as exc_info:
        create_question(db, q_data, request_id=1)
    assert "Unknown question type" in str(exc_info.value)

def test_create_question_missing_options_for_mcq(db):
    q_data = {"question": "What is 2+2?", "type": "mcq"}
    with pytest.raises(ValueError) as exc_info:
        create_question(db, q_data, request_id=1)
    # Check that error complains about missing options (case-insensitive)
    assert "MCQ" in str(exc_info.value).upper()

def test_create_question_success(db):
    # Prepare a dummy Question instance.
    dummy_question = Question(
        id=uuid4(), question="What is capital of France?",
        type="open", correct_answer="Paris", reason="Geography"
    )
    # Simulate db.refresh by setting the id.
    def fake_refresh(q):
        q.id = dummy_question.id
    db.refresh.side_effect = fake_refresh

    q_data = {
        "question": "What is capital of France?",
        "type": "open",
        "correct_answer": "Paris",
        "reason": "Geography"
    }
    result = create_question(db, q_data, request_id=1)
    assert str(dummy_question.id) == result["id"]

def test_create_question_missing_question_field(db):
    # Provide a dict missing the 'question' key; expect KeyError.
    q_data = {"type": "open", "correct_answer": "Answer", "reason": "Test"}
    with pytest.raises(KeyError):
        create_question(db, q_data, request_id=1)

def test_save_request_and_questions_success(db):
    # Create a dummy request to be returned
    dummy_request = Request(
        id=uuid4(), title="Test Request", user_id="user1",
        service_id=1, created_at=datetime.now()
    )
    # Patch save_request and create_question within the crud module.
    import database.crud as crud
    original_save_request = crud.save_request
    original_create_question = crud.create_question

    def fake_save_request(db, title, user_id, service_id):
        return dummy_request

    def fake_create_question(db, question_data, request_id, course_id=None):
        class Dummy:
            id = uuid4()
            question = question_data["question"]
            type = question_data["type"]
            correct_answer = question_data.get("correct_answer")
            reason = question_data.get("reason")
            options = question_data.get("options")
        return {
            "id": str(Dummy.id),
            "question": Dummy.question,
            "type": Dummy.type,
            "correct_answer": Dummy.correct_answer,
            "options": Dummy.options,
            "reason": Dummy.reason
        }

    crud.save_request = fake_save_request
    crud.create_question = fake_create_question

    data = {
        "title": "Test Request",
        "user_id": "user1",
        "service_id": 1,
        "questions": [{
            "question": "What is 2+2?",
            "type": "open",
            "correct_answer": "4",
            "reason": "Math"
        }]
    }
    result = save_request_and_questions(db, data)
    assert result["request"]["id"] == str(dummy_request.id)
    assert len(result["questions"]) == 1

    # Restore original functions.
    crud.save_request = original_save_request
    crud.create_question = original_create_question

def test_get_questions_by_course_id(db):
    # Create a dummy Question object.
    dummy_q = MagicMock()
    dummy_q.question = "Sample Question"
    # Configure execute chain: scalars().all() returns a list with our dummy.
    query_instance = MagicMock()
    query_instance.scalars.return_value.all.return_value = [dummy_q]
    db.execute.return_value = query_instance

    result = get_questions_by_course_id(db, "course1")
    assert "Sample Question" in result["questions"]

def test_get_question_bank_unauthorized(db):
    # Setup a dummy Course with teacher_id that does not match.
    dummy_course = Course(teacher_id="teacher1")
    db.query.return_value.filter.return_value.first.return_value = dummy_course
    result = get_question_bank(db, user_id="user2", course_id="course1")
    assert "Unauthorized" in result["detail"]

def test_get_questions_request_with_db_error(db):
    # Simulate a DB error on execute
    db.execute.side_effect = Exception("DB error")
    result = get_questions_request(db, request_id=1, user_id="user1")
    assert "detail" in result and "error" in result["detail"].lower()

def test_update_question_not_found(db):
    db.query.return_value.filter.return_value.first.return_value = None
    q_update = QuestionUpdate(
        id="1",
        question="Updated?",
        options=["a", "b"],
        correct_answer="a",
        reason="Testing",
        type="open"
    )
    result = update_question_by_id(db, "1", q_update)
    assert result is None

def test_update_question_success(db):
    # Prepare a dummy question for update.
    dummy_question = MagicMock()
    dummy_question.id = uuid4()
    dummy_question.question = "Old question?"
    dummy_question.options = '["a", "b"]'
    dummy_question.correct_answer = "a"
    dummy_question.reason = "Old Reason"
    dummy_question.type = "open"
    
    db.query.return_value.filter.return_value.first.return_value = dummy_question
    
    q_update = QuestionUpdate(
        id=str(dummy_question.id),
        question="New question?",
        options=["x", "y"],
        correct_answer="x",
        reason="New Reason",
        type="open"
    )
    updated = update_question_by_id(db, str(dummy_question.id), q_update)
    # Check updated fields in the returned dictionary.
    assert updated["question"] == "New question?"
    assert updated["options"] == ["x", "y"]

def test_delete_question_by_id_not_found(db):
    db.query.return_value.filter.return_value.first.return_value = None
    result = delete_question_by_id(db, uuid4())
    assert result is False

def test_delete_question_by_id_success(db):
    # Create a dummy question and simulate deletion.
    dummy_question = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = dummy_question
    result = delete_question_by_id(db, uuid4())
    assert result is True

def test_get_question_by_id_success(db):
    # Prepare a dummy question instance.
    dummy_question = MagicMock()
    dummy_question.id = uuid4()
    dummy_question.question = "Sample question text"
    
    # Configure the query chain to return the dummy question.
    db.query.return_value.filter.return_value.first.return_value = dummy_question
    
    result = get_question_by_id(db, dummy_question.id)
    assert result is dummy_question

def test_get_question_by_id_not_found(db):
    # Simulate no question found.
    db.query.return_value.filter.return_value.first.return_value = None
    result = get_question_by_id(db, uuid4())
    assert result is None

def test_get_questions_request_request_not_found(db):
    # Monkey-patch get_request_by_id to return None.
    import database.crud as crud
    original_get_request_by_id = crud.get_request_by_id
    crud.get_request_by_id = lambda db, req_id, user_id: None

    result = get_questions_request(db, request_id=1, user_id="user_test")
    assert result is None

    crud.get_request_by_id = original_get_request_by_id

def test_get_question_bank_invalid_options(db):
    # Setup a dummy course with matching teacher, but question.options as invalid JSON.
    dummy_course = MagicMock()
    dummy_course.teacher_id = "teacher1"
    db.query.return_value.filter.return_value.first.return_value = dummy_course
    
    # Create a dummy question with invalid JSON options.
    dummy_question = MagicMock()
    dummy_question.id = uuid4()
    dummy_question.question = "Question with bad options"
    dummy_question.options = "invalid json"
    dummy_question.type = "open"
    dummy_question.correct_answer = "None"
    dummy_question.reason = "Reason"
    dummy_question.request_id = uuid4()
    
    query_instance = MagicMock()
    query_instance.scalars.return_value.all.return_value = [dummy_question]
    db.execute.return_value = query_instance

    result = get_question_bank(db, user_id="teacher1", course_id="course1")
    # Options should be set to empty list upon JSONDecodeError.
    assert result["data"][0]["options"] == []
