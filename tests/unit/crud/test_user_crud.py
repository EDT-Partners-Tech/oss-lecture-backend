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

from unittest.mock import MagicMock
from uuid import uuid4
import pytest
from database.models import User, UserRole
from database.crud import create_user, get_user_by_email, get_user, update_user, delete_user, get_users_by_course, get_user_by_cognito_id
from database.schemas import UserCreate, UserUpdate

@pytest.fixture
def db():
    # Create a mock session that simulates add, commit, refresh, and query.
    session = MagicMock()

    # Simulate session.add assigning an id on refresh.
    def fake_add(user):
        user.id = "dummy_id"
    session.add.side_effect = fake_add

    # Setup a fake query method that returns a chainable mock.
    query_mock = MagicMock()
    session.query.return_value = query_mock
    return session

def test_create_and_get_user(db):
    # Prepare dummy user object via create_user.
    user_data = UserCreate(
        cognito_id="test-cognito-id",
        name="Test User",
        email="test@example.com",
        role=UserRole.student
    )
    created_user = create_user(db, user_data)
    assert created_user.id == "dummy_id"

    # Configure query to return this dummy user when filtering by email.
    query_instance = MagicMock()
    query_instance.filter.return_value.first.return_value = created_user
    db.query.return_value = query_instance

    user_by_email = get_user_by_email(db, "test@example.com")
    assert user_by_email.id == created_user.id

def test_create_user_db_error(db):
    # Simulate DB commit error when creating user.
    user_data = UserCreate(
        cognito_id="error-cognito",
        name="Error User",
        email="error@example.com",
        role=UserRole.student
    )
    # Simulate error on commit
    db.commit.side_effect = Exception("DB commit error")
    with pytest.raises(Exception) as exc_info:
        create_user(db, user_data)
    assert "DB commit error" in str(exc_info.value)
    # Reset side_effect for subsequent tests
    db.commit.side_effect = None

def test_get_user(db):
    # Create a dummy user and return it for get_user.
    dummy_user = User(cognito_id="dummy", name="Dummy", email="dummy@example.com", role=UserRole.student)
    dummy_user.id = "dummy_id"
    query_instance = MagicMock()
    query_instance.filter.return_value.first.return_value = dummy_user
    db.query.return_value = query_instance

    db_user = get_user(db, "dummy_id")
    assert db_user.email == "dummy@example.com"

def test_get_user_by_email_not_found(db):
    # Configure query to return None
    query_instance = MagicMock()
    query_instance.filter.return_value.first.return_value = None
    db.query.return_value = query_instance

    user = get_user_by_email(db, "nonexistent@example.com")
    assert user is None

def test_get_user_by_id_not_found(db):
    # Configure query to return None for get_user
    query_instance = MagicMock()
    query_instance.filter.return_value.first.return_value = None
    db.query.return_value = query_instance

    user = get_user(db, "nonexistent_id")
    assert user is None

def test_get_user_by_cognito_id(db):
    # Prepare a dummy user with a specific cognito_id
    dummy_user = User(cognito_id="cognito_dummy", name="Dummy", email="dummy@example.com", role=UserRole.student)
    dummy_user.id = "dummy_id"
    query_instance = MagicMock()
    query_instance.filter.return_value.first.return_value = dummy_user
    db.query.return_value = query_instance

    found_user = get_user_by_cognito_id(db, "cognito_dummy")
    assert found_user.cognito_id == "cognito_dummy"

def test_get_users_by_course(db):
    # Prepare a dummy user list
    dummy_user = User(cognito_id="dummy", name="Dummy", email="dummy@example.com", role=UserRole.student)
    dummy_user.id = "user1"
    dummy_users = [dummy_user]
    
    # Configure chained mock calls: join -> filter -> all
    query_instance = MagicMock()
    query_instance.join.return_value = query_instance
    query_instance.filter.return_value = query_instance
    query_instance.all.return_value = dummy_users
    db.query.return_value = query_instance

    dummy_course_id = uuid4()
    users = get_users_by_course(db, dummy_course_id)
    assert len(users) == 1
    assert users[0].id == "user1"

def test_update_user(db):
    # Set up a dummy user to be updated.
    dummy_user = User(cognito_id="dummy", name="Dummy", email="dummy@example.com", role=UserRole.student)
    dummy_user.id = "dummy_id"
    query_instance = MagicMock()
    query_instance.filter.return_value.first.return_value = dummy_user
    db.query.return_value = query_instance

    update_data = UserUpdate(name="Updated Name")
    updated_user = update_user(db, "dummy_id", update_data)
    assert updated_user.name == "Updated Name"

def test_update_user_not_found(db):
    # Set the query to return None, simulating a non-existent user.
    query_instance = MagicMock()
    query_instance.filter.return_value.first.return_value = None
    db.query.return_value = query_instance

    update_data = UserUpdate(name="Nonexistent")
    result = update_user(db, "nonexistent_id", update_data)
    assert result is None

def test_update_user_db_exception(db):
    # Set up a dummy user for update.
    dummy_user = User(cognito_id="dummy", name="Dummy", email="dummy@example.com", role=UserRole.student)
    dummy_user.id = "dummy_id"
    query_instance = MagicMock()
    query_instance.filter.return_value.first.return_value = dummy_user
    db.query.return_value = query_instance

    # Simulate error on commit for update_user
    db.commit.side_effect = Exception("Commit failure")
    update_data = UserUpdate(name="Should Fail")
    with pytest.raises(Exception) as exc_info:
        update_user(db, "dummy_id", update_data)
    assert "Commit failure" in str(exc_info.value)
    db.commit.side_effect = None

def test_delete_user(db):
    # Set up a dummy user to be deleted.
    dummy_user = User(cognito_id="dummy", name="Dummy", email="dummy@example.com", role=UserRole.student)
    dummy_user.id = "dummy_id"
    query_instance = MagicMock()
    query_instance.filter.return_value.first.return_value = dummy_user
    db.query.return_value = query_instance

    deletion_result = delete_user(db, "dummy_id")
    assert deletion_result is True

    # After deletion, simulate query returning None.
    query_instance.filter.return_value.first.return_value = None
    assert get_user_by_email(db, "dummy@example.com") is None

def test_delete_user_not_found(db):
    # Simulate query returning None to represent a missing user.
    query_instance = MagicMock()
    query_instance.filter.return_value.first.return_value = None
    db.query.return_value = query_instance

    result = delete_user(db, "nonexistent_id")
    assert result is False
