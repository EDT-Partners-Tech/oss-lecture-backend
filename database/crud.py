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
import secrets
import string
from typing import List, Optional
from uuid import UUID
import uuid
from fastapi import HTTPException
from sqlalchemy import not_
from sqlalchemy.orm import Session
from sqlalchemy.future import select
from sqlalchemy.exc import SQLAlchemyError, NoResultFound
from sqlalchemy.dialects.postgresql import JSONB
from icecream import ic
from database.schemas import ChatbotMaterialCreate, ComparisonEngineDB, CourseCreate, CourseUpdateSettings, EvaluationCreate, EvaluationUpdate, InviteBase, MaterialCreate, QuestionUpdate, RubricCreate, RubricUpdate, UserCreate, UserUpdate, PodcastCreate, PodcastUpdate, PodcastStatus, GroupCreate, GroupUpdate, ChatbotCreate, ThirdPartyIntegrationUpdate, LTIPlatformCreate, LTIPlatformUpdate
from database.models import AIModel, Agent, Analytics, Chatbot, ChatbotMaterial, ComparisonConfig, ComparisonDocument, ComparisonEngine, ComparisonRule, Conversation, Course, Evaluation, Invite, Material, PerformanceIndicator, Request, Question, Document, Rubric, Transcript, User, Podcast, Service, Group, UserRole, Region, ThirdPartyIntegration, LTIPlatform, Notification, ETLTask, ETLTaskType, ETLTaskStatus, ETLTaskResult, ConversationTopics, ETLTaskConfiguration, ServiceToken
from datetime import datetime, timezone

def get_user_by_email(db: Session, email: str):
    return db.query(User).filter(User.email == email).first()

def create_user(db: Session, user: UserCreate):
    try:
        # Create the user without the group relationship first
        db_user = User(
            cognito_id=user.cognito_id,
            name=user.name,
            email=user.email,
            role=user.role,
            group_id=user.group_id
        )
        db.add(db_user)
        db.commit()
        db.refresh(db_user)
        return db_user
    except SQLAlchemyError as e:
        db.rollback()
        raise e

def get_user(db: Session, user_id: int) -> User:
    return db.query(User).filter(User.id == user_id).first()


def get_user_by_cognito_id(db: Session, cognito_id: UUID) -> User:
    return db.query(User).filter(User.cognito_id == cognito_id).first()

def get_users_by_course(db: Session, course_id: UUID):
    return db.query(User).join(Course.students).filter(Course.id == course_id).all()

def update_user(db: Session, user_id: int, user_update: UserUpdate):
    db_user = get_user(db, user_id=user_id)
    if db_user:
        for key, value in user_update.model_dump(exclude_unset=True).items():
            setattr(db_user, key, value)
        db.commit()
        db.refresh(db_user)
        return db_user
    return None

def delete_user(db: Session, user_id: int):
    db_user = get_user(db, user_id=user_id)
    if db_user:
        db.delete(db_user)
        db.commit()
        return True
    return False

def save_request(db: Session, title: str, user_id: str, service_id: int):
    request = Request(title=title, user_id=user_id, service_id=service_id)
    db.add(request)
    db.commit()
    db.refresh(request)
    return request

def get_request_by_title(db: Session, title: str):
    return db.query(Request).filter(Request.title == title).first()

def validate_questions_format(questions_data):
    """Validate and parse questions data."""
    if isinstance(questions_data, str):
        try:
            return json.loads(questions_data)
        except json.JSONDecodeError:
            raise ValueError("Questions field is not a valid JSON string")
    return questions_data

def create_question(db: Session, question_data: dict, request_id: int, course_id: str = None):
    """Create a single question record."""
    if not isinstance(question_data, dict):
        print(f"Skipping non-dictionary question: {question_data}")
        return None
        
    question_type = question_data.get('type')
    if question_type not in ['mcq', 'tf', 'open']:
        raise ValueError(f"Unknown question type: {question_type}")

    question_attributes = {
        'request_id': request_id,
        'question': question_data['question'],
        'type': question_type,
        'correct_answer': question_data.get('correct_answer'),
        'reason': question_data.get('reason')
    }
    
    if course_id:
        question_attributes['course_id'] = course_id
        
    if question_type in ['mcq', 'tf']:
        if 'options' not in question_data or not isinstance(question_data['options'], list):
            raise ValueError(f"{question_type.upper()} question missing 'options' or 'options' is not a list")
        question_attributes['options'] = question_data['options']

    question = Question(**question_attributes)
    db.add(question)
    db.commit()
    db.refresh(question)
    
    return {
        'id': str(question.id),
        'question': question.question,
        'type': question.type,
        'correct_answer': question.correct_answer,
        'options': question.options,
        'reason': question.reason
    }

def save_request_and_questions(db: Session, data):
    """Save the request and associated questions to the database."""
    questions = validate_questions_format(data['questions'])
    request = save_request(db, data['title'], data['user_id'], data['service_id'])
    
    if not isinstance(request, Request):
        raise TypeError("Expected 'request' to be a Request instance, but got a dict")

    saved_questions = []
    for q in questions:
        question = create_question(db, q, request.id, data.get('course_id'))
        if question:
            saved_questions.append(question)

    db.refresh(request)
    return {
        "request": {
            "id": str(request.id),
            "title": request.title,
            "user_id": str(request.user_id),
            "service_id": str(request.service_id),
            "created_at": request.created_at
        },
        "questions": saved_questions
    }

def save_questions_to_existing_request(db: Session, request_id: UUID, questions_data: list, course_id: str = None):
    """Save questions to an existing request."""
    questions = validate_questions_format(questions_data)
    
    saved_questions = []
    for q in questions:
        question = create_question(db, q, request_id, course_id)
        if question:
            saved_questions.append(question)

    return {
        "request_id": str(request_id),
        "questions": saved_questions
    }


def get_requests_and_questions(db: Session, user_id: str, service_id: int):
    request_query = (
        select(Request)
        .where(
            Request.user_id == user_id,
            Request.service_id == service_id,
            not_(Request.title.like("Knowledge base: %"))
        )
    )
    requests = db.execute(request_query).scalars().all()

    request_ids = [str(r.id) for r in requests]
    question_query = select(Question).where(Question.request_id.in_(request_ids))
    questions = db.execute(question_query).scalars().all()

    question_counts = {str(request_id): {"mcq_count": 0, "tfq_count": 0, "open_count": 0} for request_id in request_ids}
    for q in questions:
        if q.type == "mcq":
            question_counts[str(q.request_id)]["mcq_count"] += 1
        elif q.type == "tf":
            question_counts[str(q.request_id)]["tfq_count"] += 1
        elif q.type == "open":
            question_counts[str(q.request_id)]["open_count"] += 1

    exams = []
    for request in requests:
        counts = question_counts.get(str(request.id), {"mcq_count": 0, "tfq_count": 0, "open_count": 0})
        total_questions = counts["mcq_count"] + counts["tfq_count"] + counts["open_count"]
        exams.append({
            "id": str(request.id),
            "title": request.title,
            "created_at": request.created_at.isoformat(),
            "mcq_count": counts["mcq_count"],
            "tfq_count": counts["tfq_count"],
            "open_count": counts["open_count"],
            "status": "COMPLETED" if total_questions > 0 else "IN_PROGRESS"
        })

    return {"data": exams}

def get_questions_by_course_id(db: Session, course_id: str):
    question_query = select(Question).where(Question.course_id == course_id)
    questions = db.execute(question_query).scalars().all()
    
    questions_list = []
    for q in questions:
        questions_list.append(q.question)
    
    return {"questions": questions_list}

def get_question_bank(db: Session, user_id: str, course_id: str):
    course = db.query(Course).filter(Course.id == course_id).first()
    teacher_id = str(course.teacher_id)
    
    # print(user_id, teacher_id)
    
    if teacher_id != user_id:
        return {"detail": "Unauthorized access to course question bank"}
    
    question_query = select(Question).where(Question.course_id == course_id)
    questions = db.execute(question_query).scalars().all()
    
    question_bank = []
    for q in questions:
        try:
            options = json.loads(q.options) if isinstance(q.options, str) else q.options
        except json.JSONDecodeError as e:
            ic(f"JSONDecodeError: {e}")
            options = []

        question_bank.append({
            "id": str(q.id),
            "question": q.question,
            "options": options,
            "type": q.type,
            "correct_answer": q.correct_answer,
            "reason": q.reason,
            "request_id": str(q.request_id)
        })
        
        
    return {"data": question_bank}

def get_questions_request(db: Session, request_id: int, user_id: str):
    try:
        request = get_request_by_id(db, request_id, user_id)

        if not request:
            return None

        question_query = select(Question).where(Question.request_id == request_id)
        questions = db.execute(question_query).scalars().all()

        ic(f"Questions found: {questions}")

        formatted_questions = []
        for q in questions:
            try:
                options = json.loads(q.options) if isinstance(q.options, str) else q.options
            except json.JSONDecodeError as e:
                ic(f"JSONDecodeError: {e}")
                options = []

            formatted_questions.append({
                "id": q.id,
                "question": q.question,
                "options": options,
                "type": q.type,
                "correct_answer": q.correct_answer,
                "reason": q.reason,
            })

        return {
            "title": request.title,
            "id": request.id,
            "created_at": request.created_at.isoformat() if request.created_at else None,
            "questions": formatted_questions
        }
    except SQLAlchemyError as e:
        ic(f"Database error in get_questions_request function: {e}")
        return {"detail": "An error occurred while accessing the database"}
    except json.JSONDecodeError as e:
        ic(f"JSON decode error: {e}")
        return {"detail": "An error occurred while decoding JSON data"}
    except Exception as e:
        ic(f"Unexpected error in get_questions_request function: {e}")
        return {"detail": "An unexpected error occurred"}


def get_question_by_id(db: Session, question_id: UUID):
    return db.query(Question).filter(Question.id == question_id).first()

def get_questions_by_ids(db: Session, question_ids: List[UUID]) -> List[Question]:
    return db.query(Question).filter(Question.id.in_(question_ids)).all()

def update_question_by_id(db: Session, question_id: UUID, question_data: QuestionUpdate):
    question_id = str(question_id)
    question = db.query(Question).filter(Question.id == question_id).first()
    if question is None:
        return None

    # Update question fields
    question.question = question_data.question
    question.options = question_data.options if isinstance(question_data.options, str) else json.dumps(question_data.options)
    question.correct_answer = question_data.correct_answer
    question.reason = question_data.reason
    question.type = question_data.type

    db.commit()
    db.refresh(question)
    
    # If options are stored as JSON, ensure they are parsed correctly
    options = json.loads(question.options) if isinstance(question.options, str) else question.options
    
    # Return a dictionary with string ID
    return {
        "id": str(question.id),
        "question": question.question,
        "options": options,
        "correct_answer": question.correct_answer,
        "reason": question.reason,
        "type": question.type
    }

def delete_question_by_id(db: Session, question_id: UUID):
    question = db.query(Question).filter(Question.id == question_id).first()
    if question:
        db.delete(question)
        db.commit()
        return True
    return False

def get_request_by_id(db: Session, request_id: UUID, user_id: UUID):
    ic(f"Fetching request with ID: {request_id} for user: {user_id}")

    request_query = select(Request).where(Request.id == request_id, Request.user_id == user_id)
    request = db.execute(request_query).scalars().first()

    ic(f"Request found: {request}")
    return request


def get_request_id_by_document(db: Session, document_id: str):
    ic(f"Fetching request_id for Document with id: {document_id}")

    document_query = select(Document).where(Document.id == document_id)
    document = db.execute(document_query).scalars().first()

    ic(f"Request ID: {document.request_id}")
    return document.request_id

def save_summary(db: Session, request_id: int, doc_id: str, summary: str):
    document = Document(id=doc_id, text=summary, type="summary", request_id=request_id)
    db.add(document)
    db.commit()
    db.refresh(document)

def get_summary(db: Session, doc_id: str) -> str:
    doc = db.execute(select(Document).where(Document.id == doc_id)).scalars().first()

    if not doc:
        return ""

    return doc.text

def get_requests_by_user_service(db: Session, user_id: str, service_id: UUID):
    return db.query(Request).filter(Request.user_id == user_id, Request.service_id == service_id).all()


def get_transcript_by_request_id(db: Session, request_id: UUID):
    return db.query(Transcript).filter(Transcript.request_id == request_id).first()


def get_transcript_by_id(db: Session, transcript_id: UUID):
    return db.query(Transcript).filter(Transcript.id == transcript_id).first()

def update_transcript_summary(db: Session, transcript_id: UUID, summary: str):
    transcript = db.query(Transcript).filter(Transcript.id == transcript_id).first()

    if transcript:
        transcript.summary = summary
        db.commit()
        db.refresh(transcript)
        return transcript
    else:
        return None

def delete_transcript_by_id(db: Session, transcript_id: UUID) -> bool:
    transcript = db.query(Transcript).filter(Transcript.id == transcript_id).first()
    if transcript:
        db.delete(transcript)
        db.commit()
        return True
    return False

def delete_request_by_id(db: Session, request_id: UUID) -> bool:
    """
    Delete a request and all its associated questions, documents, transcripts, and analytics.
    Explicitly deletes related records first, then the request.
    """
    request = db.query(Request).filter(Request.id == request_id).first()
    if request:
        # 1. Delete all analytics related to this request_id
        analytics = db.query(Analytics).filter(Analytics.request_id == request_id).all()
        for analytic in analytics:
            db.delete(analytic)
        
        # 2. Delete all questions related to this request_id
        questions = db.query(Question).filter(Question.request_id == request_id).all()
        for question in questions:
            db.delete(question)
        
        # 3. Delete all documents related to this request_id
        documents = db.query(Document).filter(Document.request_id == request_id).all()
        for document in documents:
            db.delete(document)
        
        # 4. Delete all transcripts related to this request_id
        transcripts = db.query(Transcript).filter(Transcript.request_id == request_id).all()
        for transcript in transcripts:
            db.delete(transcript)
        
        # 5. Delete all podcasts related to this request_id
        podcasts = db.query(Podcast).filter(Podcast.request_id == request_id).all()
        for podcast in podcasts:
            db.delete(podcast)
        
        # 6. Delete the request record
        db.delete(request)
        db.commit()
        return True
    return False

def get_analytics_by_request_id(db: Session, request_id: UUID):
    return db.query(Analytics).filter_by(request_id=request_id).first()

def save_analytics(
    db: Session,
    request_id: UUID,
    model: str,
    request_token_count: int,
    response_token_count: int,
    processing_time: float = None,
    estimated_cost: float = None,
    error: str = None,
    model_parameters: dict = None,
    response_type: str = None,
    status: str = None,
    reference: str = None
):
    analytics_entry = Analytics(
        request_id=request_id,
        model=model,
        request_token_count=request_token_count,
        response_token_count=response_token_count,
        processing_time=processing_time,
        estimated_cost=estimated_cost,
        error=error,
        model_parameters=model_parameters,
        response_type=response_type,
        status=status,
        reference=reference
    )
    db.add(analytics_entry)
    db.commit()

def save_transcription_to_db(db: Session, job_name: str, s3_uri: str, language_code: str, status: str, request_id: int):
    new_transcript = Transcript(
        job_name=job_name,
        s3_uri=s3_uri,
        language_code=language_code,
        status=status,
        request_id=request_id
    )
    db.add(new_transcript)
    db.commit()
    db.refresh(new_transcript)
    return new_transcript

def save_podcast_to_db(db: Session, podcast_create: PodcastCreate) -> UUID:
    new_podcast = Podcast(
        language=podcast_create.language,
        status=PodcastStatus.PROCESSING,
        request_id=podcast_create.request_id
    )
    db.add(new_podcast)
    db.commit()
    db.refresh(new_podcast)
    return new_podcast.id

def update_podcast(db: Session, podcast_id: UUID, podcast_update: PodcastUpdate):
    try:
        podcast = db.query(Podcast).filter(Podcast.id == podcast_id).first()
        if podcast:
            podcast.title = podcast_update.title
            podcast.dialog = podcast_update.dialog
            podcast.audio_s3_uri = podcast_update.audio_s3_uri
            podcast.image_s3_uri = podcast_update.image_s3_uri
            podcast.image_prompt = podcast_update.image_prompt
            podcast.status = PodcastStatus.COMPLETED if podcast_update.audio_s3_uri else PodcastStatus.ERROR
            podcast.completed_at = podcast_update.completed_at
            db.commit()
            db.refresh(podcast)
        else:
            raise ValueError(f"Podcast with ID {podcast_id} not found.")
    except SQLAlchemyError as e:
        db.rollback()
        raise e
    
def update_podcast_status(db: Session, podcast_id: UUID, status: PodcastStatus):
    try:
        podcast = db.query(Podcast).filter(Podcast.id == podcast_id).first()
        if podcast:
            podcast.status = status
            db.commit()
            db.refresh(podcast)
        else:
            raise ValueError(f"Podcast with ID {podcast_id} not found.")
    except SQLAlchemyError as e:
        db.rollback()
        raise e
    
def get_podcast_status(db: Session, podcast_id: UUID) -> PodcastStatus:
    podcast = db.query(Podcast).filter(Podcast.id == podcast_id).first()
    if podcast:
        return podcast.status
    else:
        raise ValueError(f"Podcast with ID {podcast_id} not found.")
    
def get_podcast_details(db: Session, podcast_id: UUID) -> Podcast:
    podcast = db.query(Podcast).filter(Podcast.id == podcast_id).first()
    if podcast:
        return podcast
    else:
        raise ValueError(f"Podcast with ID {podcast_id} not found.")
    
def find_podcast_by_request_id(db: Session, request_id: UUID) -> Podcast:
    podcast = db.query(Podcast).filter(Podcast.request_id == request_id).first()
    if podcast:
        return podcast
    else:
        raise ValueError(f"Podcast with request ID {request_id} not found.")

def get_teacher_courses(db: Session, teacher_id: UUID):
    return db.query(Course).filter(Course.teacher_id == teacher_id).all()

def get_invite_by_code_email(db: Session, invite_code: str, email: str):
    return db.query(Invite).filter(Invite.invite_code == invite_code, Invite.email == email).first()

def create_student_user(db: Session, email: str, role: str = "student") -> User:
    new_user = User(email=email, role=role)
    
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    
    return new_user

def enroll_user_in_course(db: Session, user_id: int, course_id: UUID):
    # Function to enroll a user in a course
    course = db.query(Course).filter(Course.id == course_id).first()
    if not course:
        raise ValueError("Course not found")
    
    # Check if user is already enrolled
    if any(user.id == user_id for user in course.students):
        return
    
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise ValueError("User not found")
    
    course.students.append(user)
    db.commit()
    db.refresh(course)

def get_course(db: Session, course_id: UUID):
    return db.query(Course).filter(Course.id == course_id).first()

def get_courses_by_teacher_group(db: Session, group_id: UUID):
    """Get courses where the teacher belongs to the specified group"""
    return db.query(Course).join(User, Course.teacher_id == User.id).filter(User.group_id == group_id).all()

def get_material(db: Session, material_id: UUID):
    return db.query(Material).filter(Material.id == material_id).first()

def get_materials_by_course(db: Session, course_id: UUID):
    return db.query(Material).filter(Material.course_id == course_id).all()

def delete_materials_by_course(db: Session, course_id: UUID) -> int:
    deleted_count = db.query(Material).filter(Material.course_id == course_id).delete()
    db.commit()
    return deleted_count

def delete_material(db: Session, material_id: UUID) -> bool:
    material = db.query(Material).filter(Material.id == material_id).first()
    if material:
        db.delete(material)
        db.commit()
        return True
    return False

def get_materials_by_id(db: Session, material_id: list[UUID]):
    return db.query(Material).filter(Material.id.in_(material_id)).all()

def update_material_status(db: Session, error_map: list):
    for error_entry in error_map:
        s3_uri = error_entry.get("file")
        error_message = error_entry.get("error")
        
        material = db.query(Material).filter(Material.s3_uri == s3_uri).first()
        if material:
            if material.type.startswith(("audio", "video")) and material.transcription_s3_uri:
                material.status = "Transcribed version available"
            elif material.type == "application/epub+zip" and material.transcription_s3_uri:
                material.status = "Processed version available"
            else:
                material.status = error_message
            db.add(material)
    
    db.commit()

def update_material_transcription_uri(db: Session, material_id: UUID, transcription_uri: str):
    material = db.query(Material).filter(Material.id == material_id).first()
    if material:
        material.transcription_s3_uri = transcription_uri
        db.add(material)
    else:
        raise ValueError(f"Material with ID {material_id} not found.")
    db.commit()

def delete_course(db: Session, course_id: UUID) -> bool:
    course = db.query(Course).filter(Course.id == course_id).first()
    if course:
        db.delete(course)
        db.commit()
        return True
    return False

def create_course_in_db(db: Session, course: CourseCreate, teacher_id: UUID) -> Course:
    db_course = Course(
        title=course.title,
        description=course.description,
        teacher_id=teacher_id,
    )
    
    db.add(db_course)
    db.commit()    
    db.refresh(db_course)
    
    return db_course

def create_material(db: Session, material: MaterialCreate):
    db_material = Material(**material.model_dump())
    db.add(db_material)
    db.commit()
    db.refresh(db_material)
    return db_material

def generate_invite_code(length=8):
    if not 8 <= length <= 32:  # Reasonable limits for invite code length
        raise ValueError("Invite code length must be between 8 and 32 characters")
    # Use secrets instead of random for cryptographically strong tokens
    return ''.join(secrets.choice(string.ascii_letters + string.digits) for _ in range(length))

def get_invitations_by_course(db: Session, course_id: UUID):
    return db.query(Invite).filter(Invite.course_id == course_id).all()

def create_invite(db: Session, invite: InviteBase) -> Invite:
    new_invite = Invite(
        invite_code=invite.invite_code,
        email=invite.email,
        course_id=invite.course_id,
        expires_at=invite.expires_at
    )
    db.add(new_invite)
    db.commit()
    db.refresh(new_invite)
    return new_invite

def get_invite_by_code(db: Session, invite_code: str) -> Optional[Invite]:
    return db.query(Invite).filter(Invite.invite_code == invite_code).first()

def delete_invite(db: Session, invite_code: str) -> None:
    invite = get_invite_by_code(db, invite_code)
    if invite:
        db.delete(invite)
        db.commit()
        
def update_course_field(db: Session, course_id: UUID, field_name: str, value: str):
    try:
        # Dynamically access the field on the Course model
        course = db.query(Course).filter(Course.id == course_id).first()
        
        if course:
            setattr(course, field_name, value)  # Set the field dynamically
            db.commit()
        else:
            raise ValueError(f"Course with ID {course_id} not found.")
    
    except SQLAlchemyError as e:
        db.rollback()
        raise e

def update_course_questions(db: Session, course_id: str, questions: List[str]):
    try:
        course = get_course(db, course_id)
    except NoResultFound:
        raise NoResultFound(f"Course with ID {course_id} not found.")

    # Ensure that questions is a list of strings
    if not isinstance(questions, list) or not all(isinstance(q, str) for q in questions):
        raise ValueError("Questions must be a list of strings.")


    # Update the 'questions' field with the new list of questions
    course.sample_questions = questions

    # Commit the changes to the database
    db.commit()
    db.refresh(course)

    return course

def get_course_by_id(db: Session, course_id: UUID) -> Course:
    return db.query(Course).filter(Course.id == course_id).first()

def save_rubric(db: Session, rubric_data: RubricCreate, user_id: UUID):
    """
    Save a new rubric with its performance indicators and creator info.
    """
    # Create a new rubric
    rubric = Rubric(
        name=rubric_data.name,
        description=rubric_data.description,
        created_by=user_id
    )
    db.add(rubric)
    db.commit()
    db.refresh(rubric)

    # Add associated performance indicators
    for indicator_data in rubric_data.indicators:
        indicator = PerformanceIndicator(
            rubric_id=rubric.id,
            name=indicator_data.name,
            weight=indicator_data.weight,
            criteria=json.dumps(indicator_data.criteria)
        )
        db.add(indicator)
    db.commit()

    return rubric


def get_rubrics(db: Session, user_id: str):
    """
    Retrieve all rubrics created by a specific user.
    """
    rubric_query = select(Rubric).where(Rubric.created_by == user_id)  # Filter by created_by field
    rubrics = db.execute(rubric_query).scalars().all()
    return rubrics

def get_rubric_by_id(db: Session, rubric_id: UUID):
    """
    Retrieve a specific evaluation by its ID.
    """
    rubric = db.query(Rubric).filter(Rubric.id == rubric_id).first()
    return rubric


def update_rubric(db: Session, rubric_id: UUID, rubric_data: RubricUpdate):
    """
    Update an existing rubric's details and associated performance indicators.
    """
    rubric = db.query(Rubric).filter(Rubric.id == rubric_id).first()
    if not rubric:
        return None

    # Update name and description if provided
    if rubric_data.name:
        rubric.name = rubric_data.name
    if rubric_data.description:
        rubric.description = rubric_data.description

    # Update indicators if provided
    if rubric_data.indicators:
        # Clear existing indicators
        db.query(PerformanceIndicator).filter(PerformanceIndicator.rubric_id == rubric_id).delete()
        # Add new indicators
        for indicator_data in rubric_data.indicators:
            indicator = PerformanceIndicator(
                rubric_id=rubric.id,
                name=indicator_data.name,
                weight=indicator_data.weight,
                criteria=json.dumps(indicator_data.criteria)
            )
            db.add(indicator)

    db.commit()
    db.refresh(rubric)
    return rubric


def delete_rubric(db: Session, rubric_id: UUID):
    """
    Delete a rubric and its associated performance indicators.
    """
    rubric = db.query(Rubric).filter(Rubric.id == rubric_id).first()
    if not rubric:
        return None

    db.delete(rubric)
    db.commit()
    return rubric_id


def save_evaluation(db: Session, evaluation_data: EvaluationCreate, user_id: str):
    """
    Save a new evaluation for an exam with the associated rubric and feedback.
    """
    evaluation = Evaluation(
        rubric_id=evaluation_data.rubric_id,
        created_by=user_id,  # Assign the user ID to the created_by field
        course_name=evaluation_data.course_name,  # Save course name
        student_name=evaluation_data.student_name,  # Save student name
        student_surname=evaluation_data.student_surname,  # Save student surname
        exam_description=evaluation_data.exam_description,  # Save exam description
        feedback=evaluation_data.feedback,
        criteria_evaluation=json.dumps(evaluation_data.criteria_evaluation),
        overall_comments=evaluation_data.overall_comments,
        source_text=evaluation_data.source_text  # Save source_text
    )
    db.add(evaluation)
    db.commit()
    db.refresh(evaluation)
    return evaluation


def get_evaluations(db: Session, user_id: str):
    """
    Retrieve all evaluations from the database.
    """
    evaluations_query = select(Evaluation).where(Evaluation.created_by == user_id)  # Filter by created_by field
    evaluations = db.execute(evaluations_query).scalars().all()
    return evaluations


def get_evaluation_by_id(db: Session, evaluation_id: UUID):
    """
    Retrieve a specific evaluation by its ID.
    """
    evaluation = db.query(Evaluation).filter(Evaluation.id == evaluation_id).first()
    return evaluation


def update_evaluation(db: Session, evaluation_id: UUID, evaluation_data: EvaluationUpdate):
    """
    Update an existing evaluation's details.
    """
    evaluation = db.query(Evaluation).filter(Evaluation.id == evaluation_id).first()
    if not evaluation:
        return None

    # Dictionary mapping of fields to update
    field_updates = {
        'course_name': evaluation_data.course_name,
        'student_name': evaluation_data.student_name, 
        'student_surname': evaluation_data.student_surname,
        'exam_description': evaluation_data.exam_description,
        'feedback': evaluation_data.feedback,
        'overall_comments': evaluation_data.overall_comments,
        'source_text': evaluation_data.source_text
    }

    # Update fields if they have values
    for field, value in field_updates.items():
        if value:
            setattr(evaluation, field, value)

    # Special handling for criteria_evaluation since it needs json.dumps
    if evaluation_data.criteria_evaluation:
        evaluation.criteria_evaluation = json.dumps(evaluation_data.criteria_evaluation)

    db.commit()
    db.refresh(evaluation)
    return evaluation


def update_evaluation_content(db: Session, evaluation_id: UUID, feedback: str, criteria_evaluation: list, overall_comments: str, source_text: str):
    """
    Update only the content fields of an evaluation: feedback, criteria_evaluation, overall_comments, and source_text.
    """
    evaluation = db.query(Evaluation).filter(Evaluation.id == evaluation_id).first()
    if not evaluation:
        return None

    # Update only the content fields
    evaluation.feedback = feedback
    evaluation.criteria_evaluation = json.dumps(criteria_evaluation)
    evaluation.overall_comments = overall_comments
    evaluation.source_text = source_text
    
    db.commit()
    db.refresh(evaluation)
    return evaluation


def delete_evaluation_by_id(db: Session, evaluation_id: UUID):
    """
    Delete an evaluation by its ID.
    """
    evaluation = db.query(Evaluation).filter(Evaluation.id == evaluation_id).first()
    if not evaluation:
        return None

    db.delete(evaluation)
    db.commit()
    return evaluation_id

def get_all_ai_models(db: Session):
    """Get all AI models from the database."""
    return db.query(AIModel).all()

def get_default_ai_model(db: Session):
    """Get the default AI model."""
    return db.query(AIModel).filter(AIModel.is_default == True).first()

def get_ai_model_by_id(db: Session, model_id: str):
    """Get an AI model by its model_id."""
    return db.query(AIModel).filter(AIModel.identifier == model_id).first()

def get_ai_models_by_ids(db: Session, model_ids: List[int]):
    """Get AI models by a list of model IDs."""
    return db.query(AIModel).filter(AIModel.id.in_(model_ids)).all()

def get_ai_models_by_filters(
    db: Session,
    identifier: Optional[str] = None,
    input_modality: Optional[str] = None,
    output_modality: Optional[str] = None,
    supports_knowledge_base: Optional[bool] = None,
    category: Optional[str] = None,
    region: Optional[str] = None,
    provider: Optional[str] = None,
    inference: Optional[bool] = None,
):
    """Get AI models filtered by identifier, input/output modalities, category, region, and knowledge_base support."""
    query = db.query(AIModel)
    
    if identifier:
        query = query.filter(AIModel.identifier == identifier)
    
    if input_modality:
        query = query.filter(AIModel.input_modalities.cast(JSONB).contains(input_modality))
    
    if output_modality:
        query = query.filter(AIModel.output_modalities.cast(JSONB).contains([output_modality]))
    
    if supports_knowledge_base is not None:
        query = query.filter(AIModel.supports_knowledge_base == supports_knowledge_base)
    
    if category:
        query = query.filter(AIModel.category == category)

    if region:
        query = query.join(AIModel.region).filter(Region.name == region)

    if provider:
        query = query.filter(AIModel.provider == provider)
        
    if inference is not None:
        query = query.filter(AIModel.inference == inference)
        

    try:
        result = query.all()
        return result
    except Exception as e:
        print(f"Error in query execution: {e}")
        raise

def get_default_ai_model(db: Session, provider: str, region: str):
    """Get the default AI model for a specific provider"""
    return db.query(AIModel).join(AIModel.region).filter(
        AIModel.provider == provider,
        AIModel.is_default == True,
        Region.name == region
    ).first()
    
def update_ai_models_region(db: Session, region_id: UUID):
    """Update the region for all AI models in the database."""
    db.query(AIModel).update({AIModel.region_id: region_id})
    db.commit()

def set_user_role(db: Session, user: User, role: UserRole):
    try:
        user.role = role
        db.commit()
        db.refresh(user)
    except SQLAlchemyError as e:
        db.rollback()
        raise e

def get_available_services_for_user(db: Session, user: User) -> List[Service]:
    if user.role == UserRole.admin:
        available_services = db.query(Service).all()
    else:
        user_group = user.group
        available_services = user_group.available_services

    return available_services

def get_available_models_for_user(db: Session, user: User) -> List[AIModel]:
    user_group: Group = user.group
    group_region: Region = user_group.region

    if user.role == UserRole.admin:
        available_models = db.query(AIModel).join(AIModel.region).filter(
            Region.name == group_region.name
        ).all()
    else:
        user_group = user.group
        available_models = user_group.available_models

    return available_models

def get_services_by_ids(db: Session, services_ids: List[UUID]) -> List[Service]:
    return db.query(Service).filter(Service.id.in_(services_ids)).all()

def get_groups(db: Session) -> List[Group]:
    return db.query(Group).all()

def get_group_by_id(db: Session, group_id: UUID) -> Group:
    return db.query(Group).filter(Group.id == group_id).first()

def get_group_by_domain(db: Session, domain: str) -> Optional[Group]:
    return db.query(Group).filter(Group.domain == domain).first()

def save_group_to_db(db: Session, group_data: GroupCreate) -> Group:
    try:
        new_group = Group(
            domain=group_data.domain,
            name=group_data.name
        )
        region: Region = db.query(Region).filter(Region.name == group_data.region_name).first()
        if not region:
            raise ValueError(f"Region with name {group_data.region_name} not found.")
        new_group.region = region
        db.add(new_group)
        db.commit()
        db.refresh(new_group)
        return new_group
    except SQLAlchemyError as e:
        db.rollback()
        raise e
    
def update_group(db: Session, group_update: GroupUpdate, group: Group) -> Group:
    try:
        group.name = group_update.name
        db.commit()
        db.refresh(group)
        return group
    except SQLAlchemyError as e:
        db.rollback()
        raise e
    
def delete_group_from_db(db: Session, group: Group):
    try:
        db.delete(group)
        db.commit()
    except SQLAlchemyError as e:
        db.rollback()
        raise e

def set_group_available_services(db: Session, group_id: UUID, services: List[Service]) -> Group:
    group: Group = db.query(Group).filter(Group.id == group_id).first()
    if not group:
        raise ValueError(f"Group with ID {group_id} not found.")
    try:
        group.available_services = services
        db.commit()
        db.refresh(group)
        return group
    except SQLAlchemyError as e:
        db.rollback()
        raise e

def set_group_available_models(db: Session, group_id: UUID, models: List[AIModel]) -> Group:
    group: Group = db.query(Group).filter(Group.id == group_id).first()
    if not group:
        raise ValueError(f"Group with ID {group_id} not found.")
    try:
        group.available_models = models
        db.commit()
        db.refresh(group)
        return group
    except SQLAlchemyError as e:
        db.rollback()
        raise e
    
def get_regional_bucket(db: Session, region_name: str) -> str:
    region = db.query(Region).filter(Region.name == region_name).first()
    if region:
        return region.s3_bucket
    else:
        raise ValueError(f"Region with name {region_name} not found.")

async def get_comparison_engine_documents_by_user_id(db: Session, user_id: str, type: str):
    """
    Fetches the comparison engine for a given user ID.

    Args:
        db (Session): The database session.
        user_id (str): The ID of the user to fetch the comparison engine for.

    Returns:
        The comparison engine if found, None otherwise.
    """
    comparison_engine = db.query(ComparisonEngine).filter(ComparisonEngine.user_id == user_id, ComparisonEngine.type == type ).all()
    if comparison_engine:
        return comparison_engine
    else:
        return []

async def get_comparison_engine_document_by_id(db: Session, id: str):
    """
    Fetches the comparison engine for a given ID.

    Args:
        db (Session): The database session.
        id (str): The ID of the user to fetch the comparison engine for.

    Returns:
        The comparison engine if found, None otherwise.
    """
    comparison_engine = db.query(ComparisonEngine).filter(ComparisonEngine.id == id).first()
    if comparison_engine:
        return comparison_engine
    else:
        return []

async def update_comparison_engine(db: Session, comparison_engine_data: ComparisonEngineDB) -> UUID:
    """
    Update comparison engine data in the
    database.
    Args:
        db (Session): Database session.
        comparison_engine_data (dict): Dictionary containing engine data.
    """
    try:
        db_engine = db.query(ComparisonEngine).filter(ComparisonEngine.id == comparison_engine_data["id"]).first()
        if not db_engine:
            raise HTTPException(status_code=404, detail="Engine not found")
        
        db_engine.content = comparison_engine_data["content"]
        db_engine.status = comparison_engine_data["status"]

        db.commit()
        db.refresh(db_engine)
        return db_engine.id
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to update engine data: {str(e)}")


async def save_comparison_engine(db: Session, comparison_engine_data: ComparisonEngineDB) -> UUID:
    """
    Save comparison engine data to the database.

    Args:
        db (Session): Database session.
        comparison_engine_data (dict): Dictionary containing engine data.
    
    Returns:
        UUID: The UUID of the newly created engine.
    """
    try:
        db_engine = ComparisonEngine(
            id=comparison_engine_data["id"],
            name=comparison_engine_data["name"],
            description=comparison_engine_data["description"],
            type=comparison_engine_data["type"],
            content=comparison_engine_data["content"],
            user_id=comparison_engine_data["user_id"],
            status=comparison_engine_data["status"],
        )
        db.add(db_engine)
        db.commit()
        db.refresh(db_engine)
        return db_engine.id
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to save engine data: {str(e)}")

async def delete_comparison_engine_by_id(db: Session, id: str):
    """
    Deletes a comparison engine by its ID.

    Args:
        db (Session): The database session.
        id (str): The ID of the comparison engine to delete.

    Returns:
        bool: True if the engine was deleted, False otherwise.
    """
    engine = db.query(ComparisonEngine).filter(ComparisonEngine.id == id).first()
    if engine:
        db.delete(engine)
        db.commit()
        return True
    else:
        return False

async def delete_comparison_rule_by_id(db: Session, id: str):
    """
    Deletes a comparison rule by its ID.

    Args:
        db (Session): The database session.
        id (str): The ID of the comparison rule to delete.

    Returns:
        bool: True if the rule was deleted, False otherwise.
    """
    rule = db.query(ComparisonRule).filter(ComparisonRule.id == id).first()
    if rule:
        db.delete(rule)
        db.commit()
        return True
    else:
        return False

async def save_comparison_rule(db: Session, comparison_rule_data: ComparisonRule) -> UUID:
    """
    Save comparison rule data to the database.

    Args:
        db (Session): Database session.
        comparison_rule_data (dict): Dictionary containing rule data.
    
    Returns:
        UUID: The UUID of the newly created rule.
    """
    try:
        db_rule = ComparisonRule(
            name=comparison_rule_data['name'],
            description=comparison_rule_data['description'],
            data=comparison_rule_data['data'],
            type=comparison_rule_data['type'],
            user_id=comparison_rule_data['user_id']
        )
        db.add(db_rule)
        db.commit()
        db.refresh(db_rule)
        return db_rule.id
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to save rule data: {str(e)}")

async def get_comparison_document_by_document_id(db: Session, id: int, fields: list):
    """
    Fetches a specific field for a given document ID from the ComparisonDocument table.

    Args:
        db (Session): The database session.
        id (int): The ID of the document to fetch.
        field (str): The field to fetch.

    Returns:
        The value of the field if found, None otherwise.
    """
    document = db.query(ComparisonDocument).filter(ComparisonDocument.id == id).first()
    if document:
        return {field: getattr(document, field) for field in fields}
    else:
        return None

async def get_comparison_rule_by_id(db: Session, id: int):
    """
    Fetches a specific field for a given document ID from the S3Document table.

    Args:
        db (Session): The database session.
        id (int): The ID of the document to fetch.

    Returns:
        The value of the field if found, None otherwise.
    """
    document = db.query(ComparisonRule).filter(ComparisonRule.id == id).first()
    if document:
        return document
    else:
        return None
    
async def get_comparison_rules_by_user_id_and_type(db: Session, user_id: str, type: str):
    """
    Fetches the comparison rules for a given user ID and type.

    Args:
        db (Session): The database session.
        user_id (str): The ID of the user to fetch the comparison rules for.
        type (str): The type of the comparison rules to fetch.

    Returns:
        The comparison rules if found, None otherwise.
    """
    comparison_rules = db.query(ComparisonRule).filter(ComparisonRule.user_id == user_id, ComparisonRule.type == type).all()
    if comparison_rules:
        return comparison_rules
    else:
        return []
 
async def get_comparison_config_by_id(db: Session, id: int):
    """
    Fetches a specific field for a given document ID from the S3Document table.

    Args:
        db (Session): The database session.
        id (int): The ID of the document to fetch.

    Returns:
        The value of the field if found, None otherwise.
    """
    document = db.query(ComparisonConfig).filter(ComparisonConfig.id == id).first()
    if document:
        return document
    else:
        return None

async def save_comparison_document_data(db: Session, document_data: dict, user_id: UUID) -> UUID:
    """
    Save document data to the database.

    Args:
        db (Session): Database session.
        document_data (dict): Dictionary containing document data.
        user_id (UUID): ID of the user who uploaded the document.

    Returns:
        UUID: The UUID of the newly created document.
    """
    try:
        db_document = ComparisonDocument(
            title=document_data['title'],
            type=document_data['type'],
            s3_uri=document_data['s3_uri'],
            user_id=user_id,
            language=document_data.get('language', ''),
            comparison_engine_id=document_data.get('comparison_engine_id', None),
        )
        db.add(db_document)
        db.commit()
        db.refresh(db_document)
        return db_document.id
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to save document data: {str(e)}")

async def update_comparison_rule_by_id(db: Session, id: str, rule_data: ComparisonRule):
    """
    Update a comparison rule by its ID.
    """
    rule = db.query(ComparisonRule).filter(ComparisonRule.id == id).first()
    if rule:
        rule.name = rule_data.name
        rule.description = rule_data.description
        rule.data = rule_data.data
        db.commit()
        db.refresh(rule)
        return rule.id
    else:
        return None
    
async def db_upload_group_logo(db: Session, group_id: UUID, logo_s3_uri: str):
    group = db.query(Group).filter(Group.id == group_id).first()
    if group:
        group.logo_s3_uri = logo_s3_uri
        db.commit()
        db.refresh(group)
        return group.id
    else:
        return None

# Create a chatbot
async def create_chatbot(db: Session, chatbot_data: ChatbotCreate) -> UUID:
    """
    Create a chatbot in the database.
    """
    chatbot = Chatbot(
        id=chatbot_data.id,
        name=chatbot_data.name,
        system_prompt=chatbot_data.system_prompt,
        user_id=chatbot_data.user_id,
        status=chatbot_data.status,
        session_id=chatbot_data.session_id,
        memory_id=chatbot_data.memory_id,
        resource_data=chatbot_data.resource_data,
        lti_config=chatbot_data.lti_config
    )
    db.add(chatbot)
    db.commit()
    db.refresh(chatbot)
    return chatbot

async def update_chatbot_status(db: Session, id: str, status: str):
    """
    Update the status of a chatbot by its ID.
    """
    chatbot = db.query(Chatbot).filter(Chatbot.id == id).first()
    if chatbot:
        chatbot.status = status
        db.commit()
        db.refresh(chatbot)
        return chatbot.id
    else:
        return None


# Delete a chatbot by its ID
async def delete_chatbot_by_id(db: Session, id: str):
    """
    Delete a chatbot by its ID.
    1. Delete all chatbot materials
    2. Delete all chatbot messages
    3. Delete the chatbot
    """
    chatbot = db.query(Chatbot).filter(Chatbot.id == id).first()
    if chatbot:
        # Delete all chatbot materials
        materials = db.query(ChatbotMaterial).filter(ChatbotMaterial.chatbot_id == id).all()
        for material in materials:
            db.delete(material)
        db.commit()

        # Delete all chatbot messages
        messages = db.query(Conversation).filter(Conversation.chatbot_id == id).all()
        for message in messages:
            db.delete(message)
        db.commit()
        
        db.delete(chatbot)
        db.commit()
        return True
    else:
        return False

# Create a chatbot material
async def create_chatbot_material(db: Session, chatbot_material: ChatbotMaterialCreate) -> UUID:
    """
    Create a chatbot material in the database.
    """
    try:
        material = ChatbotMaterial(
            chatbot_id=chatbot_material["chatbot_id"],
            title=chatbot_material["title"],
            type=chatbot_material["type"],
            s3_uri=chatbot_material["s3_uri"],
            status=chatbot_material["status"],
            is_main=chatbot_material["is_main"]
        )
        db.add(material)
        db.commit()
        db.refresh(material)
        return material.id
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to create chatbot material: {str(e)}")

# Delete a chatbot material by its ID
async def delete_chatbot_material_by_id(db: Session, id: str):
    """
    Delete a chatbot material by its ID.
    """
    material = db.query(ChatbotMaterial).filter(ChatbotMaterial.id == id).first()
    if material:
        db.delete(material)
        db.commit()
        return True
    else:
        return False

# Get all chatbot materials by chatbot ID with "is_main" True
async def get_chatbot_materials_by_chatbot_id_with_is_main_true(db: Session, chatbot_id: UUID):
    """
    Get all chatbot materials by chatbot ID with "is_main" True.
    """
    materials = db.query(ChatbotMaterial).filter(ChatbotMaterial.chatbot_id == chatbot_id, ChatbotMaterial.is_main == True).all()
    return materials

async def get_chatbot_by_id(db: Session, chatbot_id: UUID):
    """
    Get a chatbot by its ID.
    """
    chatbot = db.query(Chatbot).filter(Chatbot.id == chatbot_id).first()
    return chatbot

# Get all chatbots by user ID
async def get_chatbots_by_user_id(db: Session, user_id: UUID):
    """
    Get all chatbots by user ID.
    """
    chatbots = db.query(Chatbot).filter(Chatbot.user_id == user_id).all()
    return chatbots

async def get_messages_by_chatbot_id(db: Session, chatbot_id: UUID):
    """
    Get all messages by chatbot ID.
    """
    messages = db.query(Conversation).filter(Conversation.chatbot_id == chatbot_id).order_by(Conversation.created_at.asc()).all()
    return messages

async def save_conversation(db: Session, conversation: Conversation):
    """
    Save a conversation in the database.
    """
    db.add(conversation)
    db.commit()
    db.refresh(conversation)
    return conversation

async def get_chatbot_material_by_id(db: Session, material_id: UUID):
    """
    Get a chatbot material by its ID.
    """
    material = db.query(ChatbotMaterial).filter(ChatbotMaterial.id == material_id).first()
    return material

async def update_chatbot_status(db: Session, chatbot_id: str, status: str):
    """
    Update the status of a chatbot by its ID.
    """
    chatbot = db.query(Chatbot).filter(Chatbot.id == chatbot_id).first()
    chatbot.status = status
    db.commit()
    db.refresh(chatbot)
    return chatbot

async def get_last_30_conversations(db: Session, chatbot_id: UUID):
    """
    Get the last 30 conversations for a chatbot.
    """
    conversations = db.query(Conversation).filter(Conversation.chatbot_id == chatbot_id).order_by(Conversation.created_at.asc()).limit(30).all()
    return conversations

async def update_course_settings(db: Session, course_id: UUID, settings: CourseUpdateSettings):
    """
    Update the settings for a course.
    """
    course = db.query(Course).filter(Course.id == course_id).first()
    course.settings = settings.settings
    db.commit()
    db.refresh(course)
    return course

async def update_course_conversation_access_token(db: Session, course_id: UUID, conversation_access_token: str):
    """
    Update the conversation access token for a course.
    """
    course = db.query(Course).filter(Course.id == course_id).first()
    course.conversation_access_token = conversation_access_token
    db.commit()
    db.refresh(course)
    return course

async def get_agents(db: Session):
    """
    Get all agents for a user.
    """
    agents = db.query(Agent).all()
    return agents

async def get_third_party_integration(db: Session, integration_id: UUID) -> Optional[ThirdPartyIntegration]:
    return db.query(ThirdPartyIntegration).filter(ThirdPartyIntegration.id == integration_id).first()

async def get_third_party_integrations(db: Session) -> List[ThirdPartyIntegration]:
    return db.query(ThirdPartyIntegration).all()

async def get_third_party_integration_by_service(db: Session, service_name: str) -> Optional[ThirdPartyIntegration]:
    return db.query(ThirdPartyIntegration).filter(
        ThirdPartyIntegration.service_name == service_name
    ).first()

async def update_third_party_integration(
    db: Session,
    integration_id: UUID,
    integration_update: ThirdPartyIntegrationUpdate
) -> Optional[ThirdPartyIntegration]:
    try:
        db_integration = await get_third_party_integration(db, integration_id)
        if db_integration:
            for key, value in integration_update.model_dump(exclude_unset=True).items():
                setattr(db_integration, key, value)
            db.commit()
            db.refresh(db_integration)
            return db_integration
        return None
    except SQLAlchemyError as e:
        db.rollback()
        raise e

async def delete_third_party_integration(db: Session, integration_id: UUID) -> bool:
    try:
        db_integration = await get_third_party_integration(db, integration_id)
        if db_integration:
            db.delete(db_integration)
            db.commit()
            return True
        return False
    except SQLAlchemyError as e:
        db.rollback()
        raise e

def create_user_with_domain_group(db: Session, user: UserCreate) -> User:
    """
    Create a new user and assign them to a group based on their email domain.
    If the domain doesn't exist, create a new group and assign all services and models.
    """
    try:
        # Check if user already exists
        db_user = get_user_by_email(db, email=user.email)
        if db_user:
            raise ValueError("Email already registered")

        # Get or create group based on domain
        user_domain = user.email.split('@')[-1]
        group_name = user_domain.split('.')[0].title()
        
        domain_group = get_group_by_domain(db, user_domain)
        
        if domain_group:
            # Domain already exists - assign as teacher
            user.role = UserRole.teacher
            user.group_id = domain_group.id
        else:
            # New domain - create group and assign as admin
            new_group_request = GroupCreate(domain=user_domain, name=group_name)
            created_group = save_group_to_db(db, new_group_request)
            user.role = UserRole.admin
            user.group_id = created_group.id
            
            # Get all services and models for the new group
            all_services = db.query(Service).all()
            set_group_available_services(db, created_group.id, all_services)
            
            # Get all models for the region
            region = created_group.region
            all_models = db.query(AIModel).join(AIModel.region).filter(
                Region.name == region.name
            ).all()
            set_group_available_models(db, created_group.id, all_models)

        # Create the user
        new_user = create_user(db=db, user=user)
        return new_user
    except SQLAlchemyError as e:
        db.rollback()
        raise e


def apply_date_filters(query, from_date, to_date):
    if from_date:
        ic(from_date)
        query = query.filter(Request.created_at >= from_date)
    if to_date:
        ic(to_date)
        query = query.filter(Request.created_at <= to_date)
    return query

def get_model_info(m):
    if not m:
        return None
    return {
        "name": m.name,
        "provider": m.provider,
        "category": m.category,
        "description": m.description
    }

def aggregate_request_data(a, r, m, u=None):
    data = {
        "request_id": str(r.id),
        "title": r.title,
        "created_at": r.created_at.isoformat(),
        "model": a.model,
        "model_info": get_model_info(m),
        "request_tokens": a.request_token_count,
        "response_tokens": a.response_token_count,
        "processing_time": a.processing_time,
        "estimated_cost": a.estimated_cost,
        "status": a.status,
        "response_type": a.response_type
    }
    if u:
        data["user_id"] = str(u.id)
        data["user_name"] = u.name
    return data

def process_analytics(analytics, include_user=False, include_group=False):
    unique_request_ids = set(a[1].id for a in analytics)
    result = {
        "total_requests": len(unique_request_ids),
        "total_tokens": sum((a[0].request_token_count or 0) + (a[0].response_token_count or 0) for a in analytics),
        "total_cost": sum(a[0].estimated_cost or 0 for a in analytics),
        "services": {},
    }

    if include_user:
        result["users"] = {}


    for entry in analytics:
        try:
            a, r, s = entry[:3]
            m = entry[-1]
            u = entry[3] if include_user else None
        except Exception as e:
            continue

        # Services
        if s.name not in result["services"]:
            result["services"][s.name] = {
                "service_code": getattr(s, "code", None),
                "total_requests": 0,
                "total_tokens": 0,
                "total_cost": 0,
                "requests": []
            }

        service = result["services"][s.name]
        service["total_requests"] += 1
        service["total_tokens"] += (a.request_token_count or 0) + (a.response_token_count or 0)
        service["total_cost"] += a.estimated_cost or 0
        service["requests"].append(aggregate_request_data(a, r, m, u))

        # Users (if needed)
        if include_user and u:
            user_id_str = str(u.id)
            if user_id_str not in result["users"]:
                result["users"][user_id_str] = {
                    "name": u.name,
                    "email": u.email,
                    "total_requests": 0,
                    "total_tokens": 0,
                    "total_cost": 0,
                    "services_used": set() if include_group else {},
                    **({ "services": {} } if not include_group else {})
                }


            user = result["users"][user_id_str]
            user["total_requests"] += 1
            user["total_tokens"] += (a.request_token_count or 0) + (a.response_token_count or 0)
            user["total_cost"] += a.estimated_cost or 0

            if include_group:
                user["services_used"].add(s.name)
            else:
                if s.name not in user["services"]:
                    user["services"][s.name] = {
                        "total_requests": 0,
                        "total_tokens": 0,
                        "total_cost": 0
                    }
                user_service = user["services"][s.name]
                user_service["total_requests"] += 1
                user_service["total_tokens"] += (a.request_token_count or 0) + (a.response_token_count or 0)
                user_service["total_cost"] += a.estimated_cost or 0

    # Convert sets to lists
    if include_user and include_group:
        for user in result["users"].values():
            user["services_used"] = list(user["services_used"])

    return result

def get_analytics_by_user_id(db: Session, user_id: UUID, from_date=None, to_date=None):
    query = db.query(Analytics, Request, Service, AIModel).join(
        Request, Analytics.request_id == Request.id
    ).join(
        Service, Request.service_id == Service.id
    ).outerjoin(
        AIModel, Analytics.model == AIModel.identifier
    ).filter(Request.user_id == user_id)

    analytics = apply_date_filters(query, from_date, to_date).all()
    return process_analytics(analytics)

def get_analytics_by_group_id(db: Session, group_id: UUID, from_date=None, to_date=None):
    query = db.query(Analytics, Request, Service, User, AIModel).join(
        Request, Analytics.request_id == Request.id
    ).join(
        Service, Request.service_id == Service.id
    ).join(
        User, Request.user_id == User.id
    ).outerjoin(
        AIModel, Analytics.model == AIModel.identifier
    ).filter(User.group_id == group_id)

    analytics = apply_date_filters(query, from_date, to_date).all()
    return process_analytics(analytics, include_user=True, include_group=True)

def get_all_analytics(db: Session, from_date=None, to_date=None, user_id=None):
    query = db.query(Analytics, Request, Service, User, AIModel).join(
        Request, Analytics.request_id == Request.id
    ).join(
        Service, Request.service_id == Service.id
    ).join(
        User, Request.user_id == User.id
    ).outerjoin(
        AIModel, Analytics.model == AIModel.identifier
    )

    if user_id:
        query = query.filter(Request.user_id == user_id)

    analytics = apply_date_filters(query, from_date, to_date).all()
    return process_analytics(analytics, include_user=True)


def update_analytics_processing_time(db: Session, request_id: int, processing_time: float) -> None:
    """Update the processing time in the analytics record.
    
    Args:
        db: Database session
        request_id: ID of the request to update
        processing_time: The processing time in seconds
    """
    analytics = db.query(Analytics).filter(Analytics.request_id == request_id).first()
    if analytics:
        analytics.processing_time = processing_time
        db.commit()

def get_course_by_knowledge_base_id(db: Session, kb_id: str):
    """
    Get a course by its knowledge base ID.
    """
    course = db.query(Course).filter(Course.knowledge_base_id == kb_id).first()
    return course

def get_region_by_name(db: Session, region_name: str) -> Optional[Region]:
    """Get a region by its name."""
    return db.query(Region).filter(Region.name == region_name).first()

def create_region(db: Session, region_name: str, region_suffix: str, s3_bucket: str) -> Region:
    """Create a new region."""
    new_region = Region(
        id=uuid.uuid4(),
        name=region_name,
        suffix=region_suffix,
        s3_bucket=s3_bucket
    )
    db.add(new_region)
    db.commit()
    db.refresh(new_region)
    return new_region

def update_region_s3_bucket(db: Session, region: Region, s3_bucket: str) -> Region:
    """Update the S3 bucket for a region."""
    region.s3_bucket = s3_bucket
    db.commit()
    db.refresh(region)
    return region

# LTI Platform CRUD operations
def get_lti_platform(db: Session, client_id: str) -> Optional[LTIPlatform]:
    """Get a specific LTI platform by client_id. client_id is unique for each LTI platform independent of the group."""
    return db.query(LTIPlatform).filter(LTIPlatform.client_id == client_id).first()

def get_lti_platforms_by_group(db: Session, group_id: UUID, active_only: bool = True) -> List[LTIPlatform]:
    """Get all LTI platforms for a group, optionally filtering by active status."""
    query = db.query(LTIPlatform).filter(LTIPlatform.group_id == group_id)
    if active_only:
        query = query.filter(LTIPlatform.is_active == True)
    return query.all()

def get_default_lti_platform(db: Session, group_id: UUID) -> Optional[LTIPlatform]:
    """Get the default LTI platform for a group."""
    return db.query(LTIPlatform).filter(
        LTIPlatform.group_id == group_id,
        LTIPlatform.is_default == True,
        LTIPlatform.is_active == True
    ).first()

def create_lti_platform(db: Session, platform_data: LTIPlatformCreate, group_id: UUID) -> LTIPlatform:
    """Create a new LTI platform."""
    try:
        # If this is set as default, unset any existing default for this group
        if platform_data.is_default:
            db.query(LTIPlatform).filter(
                LTIPlatform.group_id == group_id,
                LTIPlatform.is_default == True
            ).update({'is_default': False})
        
        platform = LTIPlatform(
            **platform_data.model_dump(),
            group_id=group_id
        )
        db.add(platform)
        db.commit()
        db.refresh(platform)
        return platform
    except SQLAlchemyError as e:
        db.rollback()
        raise e

def update_lti_platform(db: Session, client_id: str, group_id: UUID, platform_data: LTIPlatformUpdate) -> Optional[LTIPlatform]:
    """Update an existing LTI platform."""
    try:
        platform = get_lti_platform(db, client_id)
        if not platform:
            return None
            
        # If setting as default, unset any existing default
        if platform_data.is_default:
            db.query(LTIPlatform).filter(
                LTIPlatform.group_id == group_id,
                LTIPlatform.is_default == True,
                LTIPlatform.client_id != client_id
            ).update({'is_default': False})
        
        for key, value in platform_data.model_dump(exclude_unset=True).items():
            setattr(platform, key, value)
        
        db.commit()
        db.refresh(platform)
        return platform
    except SQLAlchemyError as e:
        db.rollback()
        raise e

def delete_lti_platform(db: Session, client_id: str) -> bool:
    """Delete an LTI platform."""
    try:
        platform = get_lti_platform(db, client_id)
        if platform:
            db.delete(platform)
            db.commit()
            return True
        return False
    except SQLAlchemyError as e:
        db.rollback()
        raise e

async def create_notification(db: Session, notification_data: dict) -> Notification:
    """
    Create a new notification in the database.
    
    Args:
        db: Database session
        notification_data: Dictionary with the notification data
        
    Returns:
        Notification: The created notification
    """
    try:
        # Convert actions to JSON if they are present
        actions = None
        if notification_data.get("actions"):
            actions = json.dumps([action.dict() if hasattr(action, 'dict') else action 
                                for action in notification_data["actions"]])
        
        notification = Notification(
            user_id=notification_data["user_id"],
            service_id=notification_data["service_id"],
            title=notification_data["title"],
            body=notification_data["body"],
            data=notification_data.get("data"),
            use_push_notification=notification_data.get("use_push_notification", True),
            actions=actions,
            notification_type=notification_data.get("notification_type", "info"),
            priority=notification_data.get("priority", "normal"),
            expires_at=notification_data.get("expires_at")
        )
        
        db.add(notification)
        db.commit()
        db.refresh(notification)
        return notification
    except SQLAlchemyError as e:
        db.rollback()
        raise e

async def get_notifications_by_user_id(
    db: Session, 
    user_id: UUID, 
    filters: dict = None,
    limit: int = 50,
    offset: int = 0
) -> List[Notification]:
    """
    Get notifications for a user with optional filters.
    
    Args:
        db: Database session
        user_id: User ID
        filters: Dictionary with optional filters
        limit: Result limit
        offset: Pagination offset
        
    Returns:
        List[Notification]: List of notifications
    """
    query = db.query(Notification).filter(Notification.user_id == user_id)
    
    if filters:
        if filters.get("is_read") is not None:
            query = query.filter(Notification.is_read == filters["is_read"])
        
        if filters.get("notification_type"):
            query = query.filter(Notification.notification_type == filters["notification_type"])
        
        if filters.get("priority"):
            query = query.filter(Notification.priority == filters["priority"])
        
        if filters.get("service_id"):
            query = query.filter(Notification.service_id == filters["service_id"])
    
    # Filter expired notifications
    query = query.filter(
        (Notification.expires_at.is_(None)) | 
        (Notification.expires_at > datetime.now(timezone.utc))
    )
    
    notifications = query.order_by(Notification.created_at.desc()).offset(offset).limit(limit).all()
    
    # Process actions for each notification
    for notification in notifications:
        if notification.actions:
            try:
                # If actions is already a list/dict, keep it as is
                if isinstance(notification.actions, (list, dict)):
                    continue
                # If it's a string, try to parse it as JSON
                elif isinstance(notification.actions, str):
                    notification.actions = json.loads(notification.actions)
            except (json.JSONDecodeError, TypeError) as e:
                # If parsing fails, set to None or empty list
                notification.actions = []
    
    return notifications

async def get_notification_by_id(db: Session, notification_id: UUID) -> Optional[Notification]:
    """
    Get a notification by its ID.
    
    Args:
        db: Database session
        notification_id: Notification ID
        
    Returns:
        Optional[Notification]: The notification if it exists, None otherwise
    """
    notification = db.query(Notification).filter(Notification.id == notification_id).first()
    
    # Process actions if notification exists
    if notification and notification.actions:
        try:
            # If actions is already a list/dict, keep it as is
            if isinstance(notification.actions, (list, dict)):
                pass
            # If it's a string, try to parse it as JSON
            elif isinstance(notification.actions, str):
                notification.actions = json.loads(notification.actions)
        except (json.JSONDecodeError, TypeError) as e:
            # If parsing fails, set to empty list
            notification.actions = []
    
    return notification

async def mark_notification_as_read(db: Session, notification_id: UUID) -> Optional[Notification]:
    """
    Mark a notification as read.
    
    Args:
        db: Database session
        notification_id: Notification ID
        
    Returns:
        Optional[Notification]: The updated notification if it exists
    """
    try:
        notification = await get_notification_by_id(db, notification_id)
        if notification:
            notification.is_read = True
            notification.read_at = datetime.now(timezone.utc)
            db.commit()
            db.refresh(notification)
        return notification
    except SQLAlchemyError as e:
        db.rollback()
        raise e

async def mark_all_notifications_as_read(db: Session, user_id: UUID) -> int:
    """
    Mark all notifications for a user as read.
    
    Args:
        db: Database session
        user_id: User ID
        
    Returns:
        int: Number of notifications marked as read
    """
    try:
        result = db.query(Notification).filter(
            Notification.user_id == user_id,
            Notification.is_read == False
        ).update({
            "is_read": True,
            "read_at": datetime.now(timezone.utc)
        })
        db.commit()
        return result
    except SQLAlchemyError as e:
        db.rollback()
        raise e

async def update_notification(
    db: Session, 
    notification_id: UUID, 
    notification_update: dict
) -> Optional[Notification]:
    """
    Update an existing notification.
    
    Args:
        db: Database session
        notification_id: Notification ID
        notification_update: Dictionary with the fields to update
        
    Returns:
        Optional[Notification]: The updated notification if it exists
    """
    try:
        notification = await get_notification_by_id(db, notification_id)
        if not notification:
            return None
        
        # Update fields if they are present
        if "is_read" in notification_update:
            notification.is_read = notification_update["is_read"]
            if notification_update["is_read"]:
                notification.read_at = datetime.now(timezone.utc)
        
        if "notification_type" in notification_update:
            notification.notification_type = notification_update["notification_type"]
        
        if "priority" in notification_update:
            notification.priority = notification_update["priority"]
        
        if "expires_at" in notification_update:
            notification.expires_at = notification_update["expires_at"]
        
        if "actions" in notification_update:
            actions = notification_update["actions"]
            if actions:
                notification.actions = json.dumps([action.dict() if hasattr(action, 'dict') else action 
                                                 for action in actions])
            else:
                notification.actions = None
        
        db.commit()
        db.refresh(notification)
        return notification
    except SQLAlchemyError as e:
        db.rollback()
        raise e

async def delete_notification(db: Session, notification_id: UUID) -> bool:
    """
    Delete a notification.
    
    Args:
        db: Database session
        notification_id: Notification ID
        
    Returns:
        bool: True if it was deleted correctly, False otherwise
    """
    try:
        notification = await get_notification_by_id(db, notification_id)
        if notification:
            db.delete(notification)
            db.commit()
            return True
        return False
    except SQLAlchemyError as e:
        db.rollback()
        raise e

async def delete_expired_notifications(db: Session) -> int:
    """
    Delete expired notifications.
    
    Args:
        db: Database session
        
    Returns:
        int: Number of notifications deleted
    """
    try:
        result = db.query(Notification).filter(
            Notification.expires_at.isnot(None),
            Notification.expires_at < datetime.now(timezone.utc)
        ).delete()
        db.commit()
        return result
    except SQLAlchemyError as e:
        db.rollback()
        raise e

async def get_unread_notifications_count(db: Session, user_id: UUID) -> int:
    """
    Get the number of unread notifications for a user.
    
    Args:
        db: Database session
        user_id: User ID
        
    Returns:
        int: Number of unread notifications
    """
    return db.query(Notification).filter(
        Notification.user_id == user_id,
        Notification.is_read == False,
        (Notification.expires_at.is_(None)) | 
        (Notification.expires_at > datetime.now(timezone.utc))
    ).count()

async def create_notification_from_event(
    db: Session,
    user_id: str,
    service_id: str,
    title: str,
    body: str,
    data: dict = None,
    use_push_notification: bool = True,
    actions: List[dict] = None,
    notification_type: str = "info",
    priority: str = "normal",
    expires_at: datetime = None
) -> Notification:
    """
    Create a notification from a system event.
    This function is compatible with the app_sync.send_event structure.
    
    Args:
        db: Database session
        user_id: User ID
        service_id: Service ID
        title: Notification title
        body: Notification body
        data: Additional data
        use_push_notification: If it should be sent as a push notification
        actions: List of actions/buttons
        notification_type: Notification type
        priority: Notification priority
        expires_at: Expiration date
        
    Returns:
        Notification: The created notification
    """
    notification_data = {
        "user_id": user_id,
        "service_id": service_id,
        "title": title,
        "body": body,
        "data": data,
        "use_push_notification": use_push_notification,
        "actions": actions,
        "notification_type": notification_type,
        "priority": priority,
        "expires_at": expires_at
    }
    
    return await create_notification(db, notification_data)

async def create_etl_task(
    db: Session,
    task_type: ETLTaskType,
    group_id: UUID,
    status: ETLTaskStatus
) -> ETLTask:
    """Create a new ETL task."""
    try:
        etl_task = ETLTask(
            type=task_type,
            group_id=group_id,
            status=status
        )
        db.add(etl_task)
        db.commit()
        db.refresh(etl_task)
        return etl_task
    except SQLAlchemyError as e:
        db.rollback()
        raise e

async def update_etl_task_status(
    db: Session,
    task_id: UUID,
    status: str,
    result: Optional[str] = None
) -> Optional[ETLTask]:
    """Update ETL task status and result."""
    try:
        etl_task = db.query(ETLTask).filter(ETLTask.id == task_id).first()
        if etl_task:
            etl_task.status = ETLTaskStatus(status)
            if result:
                etl_task.result = ETLTaskResult(result)
            db.commit()
            db.refresh(etl_task)
        return etl_task
    except SQLAlchemyError as e:
        db.rollback()
        raise e

async def get_etl_task_by_id(db: Session, task_id: UUID) -> Optional[ETLTask]:
    """Get ETL task by ID."""
    return db.query(ETLTask).filter(ETLTask.id == task_id).first()

async def check_if_etl_task_is_running(db: Session, task_type: ETLTaskType, group_id: UUID) -> bool:
    """Check if there is an ETL task running for a specific type and group."""
    task = db.query(ETLTask).filter(
        ETLTask.type == task_type, 
        ETLTask.group_id == group_id, 
        ETLTask.status == ETLTaskStatus.running
    ).first()
    return task is not None

async def save_conversation_topics(
    db: Session,
    chatbot_id: UUID,
    topics: List[str]
) -> ConversationTopics:
    """Save or update conversation topics for a chatbot."""
    try:
        # Check if topics already exist for this chatbot
        existing_topics: Optional[ConversationTopics] = db.query(ConversationTopics).filter(
            ConversationTopics.chatbot_id == chatbot_id
        ).first()
        
        if existing_topics:
            # Update existing record
            existing_topics.topics = topics
            existing_topics.updated_at = datetime.now(timezone.utc)
            db.commit()
            db.refresh(existing_topics)
            return existing_topics
        else:
            # Create new record
            conversation_topics = ConversationTopics(
                chatbot_id=chatbot_id,
                topics=topics
            )
            db.add(conversation_topics)
            db.commit()
            db.refresh(conversation_topics)
            return conversation_topics
    except SQLAlchemyError as e:
        db.rollback()
        raise e

async def update_conversation_topic_global_topic(db: Session, conversation_topic: ConversationTopics, global_topic: str):
    """Update the global topic for a conversation topic."""
    try:
        conversation_topic.global_topic = global_topic
        db.commit()
        db.refresh(conversation_topic)
        return conversation_topic
    except SQLAlchemyError as e:
        db.rollback()
        raise e

async def get_conversation_topics_for_chatbots(db: Session, chatbot_ids: List[UUID]) -> List[ConversationTopics]:
    """Get conversation topics for a list of chatbots."""
    return db.query(ConversationTopics).filter(
        ConversationTopics.chatbot_id.in_(chatbot_ids)
    ).all()

async def get_chatbot_ids_by_group(db: Session, group_id: UUID) -> List[UUID]:
    """Get all chatbot IDs for a specific group."""
    try:
        # Get all users in the group, then get their chatbots
        chatbot_ids = db.query(Chatbot.id).join(User, Chatbot.user_id == User.id).filter(
            User.group_id == group_id
        ).all()
        return [chatbot_id[0] for chatbot_id in chatbot_ids]
    except Exception as e:
        ic(f"Error getting chatbot IDs for group {group_id}: {str(e)}")
        return []

async def get_conversation_topics_by_chatbot_id(
    db: Session,
    chatbot_id: UUID
) -> Optional[ConversationTopics]:
    """Get conversation topics for a specific chatbot."""
    return db.query(ConversationTopics).filter(
        ConversationTopics.chatbot_id == chatbot_id
    ).first()

async def get_all_conversation_topics(db: Session) -> List[ConversationTopics]:
    """Get all conversation topics."""
    return db.query(ConversationTopics).all()

async def delete_conversation_topics_by_chatbot_id(
    db: Session,
    chatbot_id: UUID
) -> bool:
    """Delete conversation topics for a specific chatbot."""
    try:
        result = db.query(ConversationTopics).filter(
            ConversationTopics.chatbot_id == chatbot_id
        ).delete()
        db.commit()
        return result > 0
    except SQLAlchemyError as e:
        db.rollback()
        raise e

async def delete_conversation_topics_for_chatbots(
    db: Session,
    chatbot_ids: List[UUID]
) -> int:
    """Delete conversation topics for multiple chatbots."""
    try:
        result = db.query(ConversationTopics).filter(
            ConversationTopics.chatbot_id.in_(chatbot_ids)
        ).delete(synchronize_session=False)
        db.commit()
        return result
    except SQLAlchemyError as e:
        db.rollback()
        raise e
    
async def get_etl_task_configuration_by_type_and_group(db: Session, task_type: ETLTaskType, group_id: UUID) -> Optional[ETLTaskConfiguration]:
    """Get ETL task configuration by type and group."""
    try:
        return db.query(ETLTaskConfiguration).filter(
            ETLTaskConfiguration.type == task_type,
            ETLTaskConfiguration.group_id == group_id
        ).first()
    except SQLAlchemyError as e:
        db.rollback()
        raise e

async def create_etl_task_configuration(db: Session, task_type: ETLTaskType, group_id: UUID, configuration: dict) -> Optional[ETLTaskConfiguration]:
    """Create a new ETL task configuration."""
    try:
        etl_task_configuration = ETLTaskConfiguration(
            type=task_type,
            group_id=group_id,
            configuration=configuration
        )
        db.add(etl_task_configuration)
        db.commit()
        db.refresh(etl_task_configuration)
        return etl_task_configuration
    except SQLAlchemyError as e:
        db.rollback()
        raise e

async def update_etl_task_configuration(db: Session, task_type: ETLTaskType, group_id: UUID, configuration: dict) -> Optional[ETLTaskConfiguration]:
    """Update an existing ETL task configuration."""
    try:
        etl_task_config = db.query(ETLTaskConfiguration).filter(
            ETLTaskConfiguration.type == task_type,
            ETLTaskConfiguration.group_id == group_id
        ).first()
        
        if not etl_task_config:
            return None
            
        etl_task_config.configuration = configuration
        db.commit()
        db.refresh(etl_task_config)
        return etl_task_config
    except SQLAlchemyError as e:
        db.rollback()
        raise e

async def delete_etl_task_configuration(db: Session, task_type: ETLTaskType, group_id: UUID) -> bool:
    """Delete an ETL task configuration."""
    try:
        etl_task_config = db.query(ETLTaskConfiguration).filter(
            ETLTaskConfiguration.type == task_type,
            ETLTaskConfiguration.group_id == group_id
        ).first()
        
        if not etl_task_config:
            return False
            
        db.delete(etl_task_config)
        db.commit()
        return True
    except SQLAlchemyError as e:
        db.rollback()
        raise e


# ServiceToken CRUD functions
async def create_service_token(db: Session, token_id: str, group_id: str, name: str, 
                               description: str, expires_at: datetime, token_hash: str, 
                               public_key: str) -> ServiceToken:
    """Create a new service token."""
    try:
        service_token = ServiceToken(
            id=token_id,
            group_id=group_id,
            name=name,
            description=description,
            expires_at=expires_at,
            token_hash=token_hash,
            public_key=public_key
        )
        db.add(service_token)
        db.commit()
        db.refresh(service_token)
        return service_token
    except SQLAlchemyError as e:
        db.rollback()
        raise e
    
async def get_service_tokens_for_group(db: Session, group_id: UUID) -> List[ServiceToken]:
    """Get all service tokens for a specific group."""
    return db.query(ServiceToken).filter(ServiceToken.group_id == group_id).all()

async def get_service_token_by_id_and_group_id(db: Session, token_id: UUID, group_id: UUID) -> Optional[ServiceToken]:
    """Get a service token by its ID and group ID."""
    return db.query(ServiceToken).filter(ServiceToken.id == token_id, ServiceToken.group_id == group_id).first()

async def update_service_token_last_used_at(db: Session, token_id: UUID) -> Optional[ServiceToken]:
    """Update the last used at timestamp for a service token."""
    try:
        service_token = db.query(ServiceToken).filter(ServiceToken.id == token_id).first()
        if not service_token:
            return None
        service_token.last_used_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(service_token)
        return service_token
    except SQLAlchemyError as e:
        db.rollback()
        raise e

async def delete_service_token(db: Session, token_id: UUID) -> bool:
    """Delete a service token."""
    try:
        service_token = db.query(ServiceToken).filter(ServiceToken.id == token_id).first()
        if not service_token:
            return False
        db.delete(service_token)
        db.commit()
        return True
    except SQLAlchemyError as e:
        db.rollback()
        raise e

