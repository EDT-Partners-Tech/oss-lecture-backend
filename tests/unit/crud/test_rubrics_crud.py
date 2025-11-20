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
import pytest
from unittest.mock import MagicMock, call, ANY

from database.crud import save_rubric, update_rubric, delete_rubric, get_rubrics, get_rubric_by_id
from database.schemas import RubricCreate, RubricUpdate, PerformanceIndicator

# Dummy rubric object used for update/delete tests
class DummyRubric:
    def __init__(self, id, name, description, created_by, indicators=None):
        self.id = id
        self.name = name
        self.description = description
        self.created_by = created_by
        self.indicators = indicators or []

# Pytest fixture for the db mock
@pytest.fixture
def db():
    return MagicMock()

def test_save_rubric_calls_db_methods(db):
    # Setup
    dummy_id = uuid.uuid4()
    indicators = [PerformanceIndicator(name="Quality", weight=1.0, criteria={"min": 0, "max": 10})]
    rubric_data = RubricCreate(name="Test Rubric", description="Desc", indicators=indicators)
    
    # Simulate refresh: assign id to rubric
    def refresh_side_effect(obj):
        obj.id = dummy_id
    db.refresh.side_effect = refresh_side_effect

    # Call function
    returned = save_rubric(db, rubric_data, user_id=str(uuid.uuid4()))
    
    # Assertions for rubric creation and indicators
    assert returned.id == dummy_id
    assert db.commit.call_count == 2
    expected_add_calls = [call(returned)] + [call(ANY) for _ in rubric_data.indicators]
    assert db.add.call_count >= len(expected_add_calls)

def test_get_rubrics(db):
    dummy_rubric = DummyRubric(id=uuid.uuid4(), name="Test Rubric", description="desc", created_by="user1")
    # Setup execute().scalars().all() to return a list with our dummy rubric
    db.execute().scalars().all.return_value = [dummy_rubric]
    
    rubrics = get_rubrics(db, "user1")
    assert len(rubrics) == 1
    assert rubrics[0].name == "Test Rubric"

def test_get_rubric_by_id_found(db):
    dummy_rubric = DummyRubric(id=uuid.uuid4(), name="Found Rubric", description="desc", created_by="user1")
    db.query().filter().first.return_value = dummy_rubric
    
    rub = get_rubric_by_id(db, dummy_rubric.id)
    assert rub.name == "Found Rubric"

def test_update_rubric_rubric_not_found(db):
    db.query().filter().first.return_value = None
    result = update_rubric(db, uuid.uuid4(), RubricUpdate(name="New Name"))
    assert result is None

def test_update_rubric_success(db):
    dummy_id = uuid.uuid4()
    original_rubric = DummyRubric(id=dummy_id, name="Old Name", description="Old Desc", created_by="user1")
    db.query().filter().first.return_value = original_rubric

    new_indicator = PerformanceIndicator(name="Updated Indicator", weight=2.0, criteria={"min": 1, "max": 5})
    update_data = RubricUpdate(name="New Name", description="New Desc", indicators=[new_indicator])
    
    updated = update_rubric(db, dummy_id, update_data)
    
    assert updated.name == "New Name"
    assert updated.description == "New Desc"
    db.query().filter.assert_called()
    assert db.commit.call_count >= 1
    db.refresh.assert_called_with(updated)

def test_delete_rubric_success(db):
    dummy_id = uuid.uuid4()
    dummy_rub = DummyRubric(id=dummy_id, name="Test", description="desc", created_by="user2")
    db.query().filter().first.return_value = dummy_rub

    deleted_id = delete_rubric(db, dummy_id)
    assert deleted_id == dummy_id
    db.delete.assert_called_with(dummy_rub)
    db.commit.assert_called()

def test_delete_rubric_not_found(db):
    db.query().filter().first.return_value = None
    result = delete_rubric(db, uuid.uuid4())
    assert result is None
