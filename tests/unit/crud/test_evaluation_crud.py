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
import json
import pytest
from unittest.mock import MagicMock

from database.crud import (
    save_evaluation,
    get_evaluations,
    get_evaluation_by_id,
    update_evaluation,
    delete_evaluation_by_id
)
from database.schemas import EvaluationCreate, EvaluationUpdate

# Dummy evaluation to simulate DB query returns
class DummyEvaluation:
    def __init__(self, id, rubric_id, course_name, student_name, student_surname,
                 exam_description, feedback, criteria_evaluation, overall_comments, source_text):
        self.id = id
        self.rubric_id = rubric_id
        self.course_name = course_name
        self.student_name = student_name
        self.student_surname = student_surname
        self.exam_description = exam_description
        self.feedback = feedback
        self.criteria_evaluation = criteria_evaluation
        self.overall_comments = overall_comments
        self.source_text = source_text

# Fixture for the db mock
@pytest.fixture
def db():
    return MagicMock()

def test_save_evaluation_calls_db_methods(db):
    dummy_id = uuid.uuid4()
    rubric_id = uuid.uuid4()
    eval_data = EvaluationCreate(
        rubric_id=rubric_id,
        course_name="Test Course",
        student_name="John",
        student_surname="Doe",
        exam_description="Final Exam",
        feedback="Good Job",
        criteria_evaluation=[{"score": 5}],
        overall_comments="Well done",
        source_text="Original text"
    )
    user_id = str(uuid.uuid4())
    
    def refresh_side_effect(obj):
        obj.id = dummy_id
    db.refresh.side_effect = refresh_side_effect

    result = save_evaluation(db, eval_data, user_id)
    
    assert result.id == dummy_id
    # One commit for evaluation saving
    db.commit.assert_called()
    db.add.assert_called_with(result)

def test_get_evaluations(db):
    dummy_eval = DummyEvaluation(
        id=uuid.uuid4(),
        rubric_id=uuid.uuid4(),
        course_name="Test Course",
        student_name="John",
        student_surname="Doe",
        exam_description="Exam",
        feedback="Feedback",
        criteria_evaluation=json.dumps([{"score": 10}]),
        overall_comments="Ok",
        source_text="Text"
    )
    # Simulate execute().scalars().all()
    db.execute().scalars().all.return_value = [dummy_eval]
    
    evals = get_evaluations(db, "some_user_id")
    assert len(evals) == 1
    assert evals[0].course_name == "Test Course"

def test_get_evaluation_by_id_found(db):
    dummy_eval = DummyEvaluation(
        id=uuid.uuid4(),
        rubric_id=uuid.uuid4(),
        course_name="Found Course",
        student_name="Alice",
        student_surname="Smith",
        exam_description="Midterm",
        feedback="Excellent",
        criteria_evaluation=json.dumps([{"score": 8}]),
        overall_comments="Nice work",
        source_text="Some text"
    )
    db.query().filter().first.return_value = dummy_eval
    found = get_evaluation_by_id(db, dummy_eval.id)
    assert found.course_name == "Found Course"

def test_update_evaluation_not_found(db):
    db.query().filter().first.return_value = None
    update_data = EvaluationUpdate(
        feedback="Updated feedback",
        criteria_evaluation=[{"score": 7}],
        overall_comments="Updated comments",
        source_text="Updated text"
    )
    result = update_evaluation(db, uuid.uuid4(), update_data)
    assert result is None

def test_update_evaluation_success(db):
    dummy_id = uuid.uuid4()
    original_eval = DummyEvaluation(
        id=dummy_id,
        rubric_id=uuid.uuid4(),
        course_name="Course A",
        student_name="Bob",
        student_surname="Jones",
        exam_description="Exam 1",
        feedback="Initial",
        criteria_evaluation=json.dumps([{"score": 5}]),
        overall_comments="Initial comments",
        source_text="Original text"
    )
    db.query().filter().first.return_value = original_eval
    
    update_data = EvaluationUpdate(
        course_name="Updated Course",
        student_name="Sam",
        student_surname="Taylor",
        exam_description="Updated exam",
        feedback="Updated feedback",
        criteria_evaluation=[{"score": 9}],
        overall_comments="Updated comments",
        source_text="Updated text"
    )
    updated = update_evaluation(db, dummy_id, update_data)
    assert updated.feedback == "Updated feedback"
    # Ensure criteria is updated as JSON string
    assert updated.criteria_evaluation == json.dumps([{"score": 9}])
    db.commit.assert_called()
    db.refresh.assert_called_with(updated)

def test_delete_evaluation_success(db):
    dummy_id = uuid.uuid4()
    dummy_eval = DummyEvaluation(
        id=dummy_id,
        rubric_id=uuid.uuid4(),
        course_name="Del Course",
        student_name="Sam",
        student_surname="Taylor",
        exam_description="Exam delete",
        feedback="Feedback",
        criteria_evaluation=json.dumps([{"score": 4}]),
        overall_comments="Ok",
        source_text="Text"
    )
    db.query().filter().first.return_value = dummy_eval
    ret_id = delete_evaluation_by_id(db, dummy_id)
    assert ret_id == dummy_id
    db.delete.assert_called_with(dummy_eval)
    db.commit.assert_called()

def test_delete_evaluation_not_found(db):
    db.query().filter().first.return_value = None
    ret = delete_evaluation_by_id(db, uuid.uuid4())
    assert ret is None
