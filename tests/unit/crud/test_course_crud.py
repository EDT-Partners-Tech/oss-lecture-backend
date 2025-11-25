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

import pytest
from uuid import uuid4
from unittest.mock import MagicMock
from database.crud import (
    get_teacher_courses,
    get_invite_by_code_email,
    create_student_user,
    enroll_user_in_course,
    get_course,
    get_material,
    get_materials_by_course,
    delete_materials_by_course,
    delete_material,
    get_materials_by_id,
    update_material_status,
    update_material_transcription_uri,
    delete_course,
    create_course_in_db,
    create_material,
    get_invitations_by_course,
    create_invite,
    get_invite_by_code,
    delete_invite,
    update_course_field,
    update_course_questions,
    generate_invite_code,
    get_course_by_id
)
from database.models import Course, Invite, User, Material
from database.schemas import CourseCreate, MaterialCreate


@pytest.fixture
def db():
    # Return a MagicMock representing the DB session.
    return MagicMock()

def test_get_teacher_courses_success(db):
    teacher_id = uuid4()
    dummy_course = MagicMock(spec=Course)
    dummy_course.teacher_id = teacher_id
    db.query.return_value.filter.return_value.all.return_value = [dummy_course]
    
    result = get_teacher_courses(db, teacher_id)
    assert result == [dummy_course]

def test_get_invite_by_code_email_success(db):
    invite_code = "ABC12345"
    email = "test@example.com"
    dummy_invite = MagicMock(spec=Invite)
    db.query.return_value.filter.return_value.first.return_value = dummy_invite
    
    result = get_invite_by_code_email(db, invite_code, email)
    assert result is dummy_invite

def test_create_student_user_success(db):
    email = "student@example.com"
    # Simulate setting user id on refresh.
    def fake_refresh(user):
        user.id = uuid4()
    db.refresh.side_effect = fake_refresh

    new_user = create_student_user(db, email)
    # Check that user was added and refreshed with an id.
    args, _ = db.add.call_args
    user_instance = args[0]
    assert hasattr(user_instance, "email")
    db.commit.assert_called_once()
    assert hasattr(new_user, "id")

def test_enroll_user_in_course_success(db):
    # Setup dummy course with empty students list.
    dummy_course = MagicMock(spec=Course)
    dummy_course.students = []
    course_id = uuid4()
    user_id = uuid4()
    # Course is found.
    db.query.return_value.filter.side_effect = [
        # First call: get course.
        MagicMock(first=MagicMock(return_value=dummy_course)),
        # Second call: get user.
        MagicMock(first=MagicMock(return_value=MagicMock(spec=User, id=user_id)))
    ]
    # Call enroll function.
    enroll_user_in_course(db, user_id, course_id)
    # Check that user got appended.
    assert any(u.id == user_id for u in dummy_course.students)
    db.commit.assert_called()

def test_enroll_user_in_course_course_not_found(db):
    course_id = uuid4()
    user_id = uuid4()
    # Simulate course not found.
    db.query.return_value.filter.return_value.first.return_value = None
    with pytest.raises(ValueError, match="Course not found"):
        enroll_user_in_course(db, user_id, course_id)

def test_enroll_user_in_course_user_not_found(db):
    dummy_course = MagicMock(spec=Course)
    dummy_course.students = []
    course_id = uuid4()
    user_id = uuid4()
    # First call returns course, second call returns None.
    db.query.return_value.filter.side_effect = [
        MagicMock(first=MagicMock(return_value=dummy_course)),
        MagicMock(first=MagicMock(return_value=None))
    ]
    with pytest.raises(ValueError, match="User not found"):
        enroll_user_in_course(db, user_id, course_id)

def test_enroll_user_in_course_already_enrolled(db):
    user_id = uuid4()
    # Create a dummy user already enrolled.
    dummy_user = MagicMock(spec=User, id=user_id)
    dummy_course = MagicMock(spec=Course)
    dummy_course.students = [dummy_user]
    course_id = uuid4()
    # First call: course found; second call: user found.
    db.query.return_value.filter.side_effect = [
        MagicMock(first=MagicMock(return_value=dummy_course)),
        MagicMock(first=MagicMock(return_value=dummy_user))
    ]
    # Should return without error and not add duplicate.
    enroll_user_in_course(db, user_id, course_id)
    # Confirm no duplicate entry.
    assert len(dummy_course.students) == 1

def test_get_course_success(db):
    course_id = uuid4()
    dummy_course = MagicMock(spec=Course)
    db.query.return_value.filter.return_value.first.return_value = dummy_course
    result = get_course(db, course_id)
    assert result is dummy_course

def test_get_material_success(db):
    material_id = uuid4()
    dummy_material = MagicMock(spec=Material)
    db.query.return_value.filter.return_value.first.return_value = dummy_material
    result = get_material(db, material_id)
    assert result is dummy_material

def test_get_materials_by_course_success(db):
    course_id = uuid4()
    dummy_material1 = MagicMock(spec=Material)
    dummy_material2 = MagicMock(spec=Material)
    db.query.return_value.filter.return_value.all.return_value = [dummy_material1, dummy_material2]
    result = get_materials_by_course(db, course_id)
    assert result == [dummy_material1, dummy_material2]

def test_delete_materials_by_course_success(db):
    course_id = uuid4()
    db.query.return_value.filter.return_value.delete.return_value = 3
    count = delete_materials_by_course(db, course_id)
    assert count == 3
    db.commit.assert_called()

def test_delete_material_success_found(db):
    material_id = uuid4()
    dummy_material = MagicMock(spec=Material)
    db.query.return_value.filter.return_value.first.return_value = dummy_material
    result = delete_material(db, material_id)
    assert result is True
    db.delete.assert_called_with(dummy_material)
    db.commit.assert_called()

def test_delete_material_success_not_found(db):
    material_id = uuid4()
    db.query.return_value.filter.return_value.first.return_value = None
    result = delete_material(db, material_id)
    assert result is False

def test_get_materials_by_id(db):
    material_ids = [uuid4(), uuid4()]
    dummy_material = MagicMock(spec=Material)
    db.query.return_value.filter.return_value.all.return_value = [dummy_material]
    result = get_materials_by_id(db, material_ids)
    assert result == [dummy_material]

def test_update_material_status(db):
    error_map = [
        {"file": "s3://file/audio1.mp3", "error": "Error A"},
        {"file": "s3://file/text1.txt", "error": "Error B"}
    ]
    # For first error: material type starts with audio and has transcription URI.
    dummy_material_audio = MagicMock(
        type="audio/mp3", 
        transcription_s3_uri="s3://transcribed/audio1.mp3",
        status=None
    )
    # For second: type not matching or missing transcription.
    dummy_material_text = MagicMock(
        type="text/plain", 
        transcription_s3_uri=None,
        status=None
    )
        
    db.query.return_value.filter.return_value.first.return_value = dummy_material_audio
    update_material_status(db, error_map)
    assert dummy_material_audio.status == "Transcribed version available"
    db.add.assert_any_call(dummy_material_audio)
    db.commit.assert_called()

    db.query.return_value.filter.return_value.first.return_value = dummy_material_text
    update_material_status(db, error_map)
    assert dummy_material_text.status == "Error B"
    db.add.assert_any_call(dummy_material_text)
    db.commit.assert_called()

def test_update_material_transcription_uri_success(db):
    material_id = uuid4()
    dummy_material = MagicMock(spec=Material)
    db.query.return_value.filter.return_value.first.return_value = dummy_material
    transcription_uri = "s3://transcribed/new.mp3"
    update_material_transcription_uri(db, material_id, transcription_uri)
    assert dummy_material.transcription_s3_uri == transcription_uri
    db.add.assert_called_with(dummy_material)
    db.commit.assert_called()

def test_update_material_transcription_uri_not_found(db):
    material_id = uuid4()
    db.query.return_value.filter.return_value.first.return_value = None
    with pytest.raises(ValueError, match="Material with ID"):
        update_material_transcription_uri(db, material_id, "s3://transcribed/new.mp3")

def test_delete_course_found(db):
    course_id = uuid4()
    dummy_course = MagicMock(spec=Course)
    db.query.return_value.filter.return_value.first.return_value = dummy_course
    result = delete_course(db, course_id)
    assert result is True
    db.delete.assert_called_with(dummy_course)
    db.commit.assert_called()

def test_delete_course_not_found(db):
    course_id = uuid4()
    db.query.return_value.filter.return_value.first.return_value = None
    result = delete_course(db, course_id)
    assert result is False

def test_create_course_in_db_success(db):
    teacher_id = uuid4()
    course_data = CourseCreate(title="Test Course", description="Desc")
    # Simulate refresh setting id.
    def fake_refresh(course):
        course.id = uuid4()
    db.refresh.side_effect = fake_refresh
    new_course = create_course_in_db(db, course_data, teacher_id)
    assert hasattr(new_course, "id")
    db.commit.assert_called()

def test_create_material_success(db):
    material_data = MaterialCreate(title="Mat 1", type="video/mp4", s3_uri="s3://video/uri", course_id=uuid4())
    def fake_refresh(mat):
        mat.id = uuid4()
    db.refresh.side_effect = fake_refresh
    new_mat = create_material(db, material_data)
    assert hasattr(new_mat, "id")
    db.commit.assert_called()

def test_generate_invite_code_default(db):
    # Invoke with default length (8)
    code = generate_invite_code()
    assert len(code) == 8
    assert code.isalnum()

def test_generate_invite_code_custom_length(db):
    custom_length = 16
    code = generate_invite_code(custom_length)
    assert len(code) == custom_length
    assert code.isalnum()

def test_generate_invite_code_too_short(db):
    with pytest.raises(ValueError, match="Invite code length must be between 8 and 32 characters"):
        generate_invite_code(5)

def test_generate_invite_code_too_long(db):
    with pytest.raises(ValueError, match="Invite code length must be between 8 and 32 characters"):
        generate_invite_code(40)

def test_get_invitations_by_course_success(db):
    course_id = uuid4()
    dummy_invite = MagicMock(spec=Invite)
    db.query.return_value.filter.return_value.all.return_value = [dummy_invite]
    invites = get_invitations_by_course(db, course_id)
    assert invites == [dummy_invite]

def test_create_invite_success(db):
    dummy_invite_data = MagicMock(spec=Invite)
    # Simulate refresh setting id.
    def fake_refresh(invite):
        invite.id = uuid4()
    db.refresh.side_effect = fake_refresh
    # Use create_invite passing an object with required attributes.
    class DummyInvite:
        invite_code = "INV1234"
        email = "invited@example.com"
        course_id = uuid4()
        expires_at = None
    new_invite = create_invite(db, DummyInvite())
    assert hasattr(new_invite, "id")
    db.commit.assert_called()

def test_get_invite_by_code_success(db):
    invite_code = "INV1234"
    dummy_invite = MagicMock(spec=Invite)
    db.query.return_value.filter.return_value.first.return_value = dummy_invite
    result = get_invite_by_code(db, invite_code)
    assert result is dummy_invite

def test_delete_invite_success(db):
    invite_code = "INV1234"
    dummy_invite = MagicMock(spec=Invite)
    db.query.return_value.filter.return_value.first.return_value = dummy_invite
    delete_invite(db, invite_code)
    db.delete.assert_called_with(dummy_invite)
    db.commit.assert_called()

def test_update_course_field_success(db):
    course_id = uuid4()
    dummy_course = MagicMock(spec=Course)
    setattr(dummy_course, "title", "Old Title")
    db.query.return_value.filter.return_value.first.return_value = dummy_course
    update_course_field(db, course_id, "title", "New Title")
    assert dummy_course.title == "New Title"
    db.commit.assert_called()

def test_update_course_questions_success(db):
    course_id = uuid4()
    dummy_course = MagicMock(spec=Course)
    # simulate course with existing sample_questions.
    dummy_course.sample_questions = ["q1", "q2"]
    db.query.return_value.filter.return_value.first.return_value = dummy_course
    new_questions = ["q3", "q4"]
    result = update_course_questions(db, str(course_id), new_questions)
    assert result.sample_questions == new_questions
    db.commit.assert_called()
    db.refresh.assert_called_with(dummy_course)

def test_update_course_questions_invalid_list(db):
    course_id = uuid4()
    dummy_course = MagicMock(spec=Course)
    dummy_course.sample_questions = ["q1"]
    db.query.return_value.filter.return_value.first.return_value = dummy_course
    with pytest.raises(ValueError, match="Questions must be a list of strings"):
        update_course_questions(db, str(course_id), "not a list")

def test_get_course_by_id_success(db):
    course_id = uuid4()
    dummy_course = MagicMock(spec=Course)
    db.query.return_value.filter.return_value.first.return_value = dummy_course
    result = get_course_by_id(db, course_id)
    assert result is dummy_course

def test_get_course_by_id_none(db):
    course_id = uuid4()
    db.query.return_value.filter.return_value.first.return_value = None
    result = get_course_by_id(db, course_id)
    assert result is None

