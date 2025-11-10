# © [2025] EDT&Partners. Licensed under CC BY 4.0.

from datetime import datetime, timedelta, timezone
from typing import Optional
import os
import enum
import uuid
from sqlalchemy import Column, Float, Integer, String, ForeignKey, Text, DateTime, Enum, Table, Boolean, UniqueConstraint, LargeBinary
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from cryptography.fernet import Fernet
from constants import ALL_DELETE_ORPHAN, COURSES_ID, REQUESTS_ID, USERS_ID, GROUPS_ID, SERVICES_ID, AI_MODELS_ID, CHATBOTS_ID
from database.db import Base
from lti.secrets import get_lti_secrets

LTI_ENCRYPTION_SECRET = get_lti_secrets().encryption_secret
if not LTI_ENCRYPTION_SECRET:
    raise ValueError("LTI_ENCRYPTION_SECRET is not set")

fernet = Fernet(LTI_ENCRYPTION_SECRET.encode())

# Association Table for many-to-many relationship between Course and User
course_student = Table(
    'course_student',
    Base.metadata,
    Column('course_id', UUID(as_uuid=True), ForeignKey(COURSES_ID), primary_key=True),
    Column('user_id', UUID(as_uuid=True), ForeignKey(USERS_ID), primary_key=True)
)

group_services = Table(
    'group_services',
    Base.metadata,
    Column('group_id', UUID(as_uuid=True), ForeignKey(GROUPS_ID), primary_key=True),
    Column('service_id', UUID(as_uuid=True), ForeignKey(SERVICES_ID), primary_key=True)
)

group_models = Table(
    'group_models',
    Base.metadata,
    Column('group_id', UUID(as_uuid=True), ForeignKey(GROUPS_ID), primary_key=True),
    Column('model_id', Integer, ForeignKey(AI_MODELS_ID), primary_key=True)
)

class UserRole(str, enum.Enum):
    student = 'student'
    teacher = 'teacher'
    admin = 'admin'

class ETLTaskType(str, enum.Enum):
    topics_analysis = 'topics_analysis'

class ETLTaskStatus(str, enum.Enum):
    pending = 'pending'
    running = 'running'
    completed = 'completed'
    failed = 'failed'

class ETLTaskResult(str, enum.Enum):
    success = 'success'
    error = 'error'

class User(Base):
    __tablename__ = 'users'
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    cognito_id = Column(String, unique=True, nullable=False)
    name = Column(String, nullable=False)
    email = Column(String, unique=True, nullable=False)
    role = Column(Enum(UserRole), nullable=False)
    group_id = Column(UUID(as_uuid=True), ForeignKey(GROUPS_ID), nullable=False)
    
    courses = relationship("Course", secondary=course_student, back_populates="students")
    rubrics = relationship("Rubric", back_populates="user")
    group = relationship("Group", back_populates="users")
    chatbots = relationship("Chatbot", back_populates="user", cascade=ALL_DELETE_ORPHAN)
    comparison_engines = relationship("ComparisonEngine", back_populates="user", cascade=ALL_DELETE_ORPHAN)
    comparison_documents = relationship("ComparisonDocument", back_populates="user", cascade=ALL_DELETE_ORPHAN)
    comparison_rules = relationship("ComparisonRule", back_populates="user", cascade=ALL_DELETE_ORPHAN)
    comparison_configs = relationship("ComparisonConfig", back_populates="user", cascade=ALL_DELETE_ORPHAN)

class Service(Base):
    __tablename__ = 'services'
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    name = Column(String, unique=True, nullable=False)
    code = Column(String, unique=True, nullable=False)
    description = Column(Text, nullable=True)
    isknowledgebase = Column(Boolean, nullable=False, default=False)

    requests = relationship("Request", back_populates="service")
    groups_with_access = relationship("Group", secondary=group_services, back_populates="available_services")

class Group(Base):
    __tablename__ = 'groups'
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    domain = Column(String, nullable=False)
    name = Column(String, nullable=True)
    region_id = Column(UUID(as_uuid=True), ForeignKey("regions.id"), nullable=False)
    logo_s3_uri = Column(String, nullable=True, default="")
    _lti_private_key = Column("lti_private_key", LargeBinary, nullable=True)

    @property
    def lti_private_key(self) -> Optional[str]:
        if not self._lti_private_key:
            return None
        try:
            return fernet.decrypt(self._lti_private_key).decode()
        except Exception as e:
            raise ValueError(f"Error decrypting LTI private key: {e}")

    @lti_private_key.setter
    def lti_private_key(self, value: str):
        if value:
            self._lti_private_key = fernet.encrypt(value.encode())
        else:
            self._lti_private_key = None

    users = relationship("User", back_populates="group", cascade=ALL_DELETE_ORPHAN)
    region = relationship("Region", back_populates="groups")
    available_services = relationship("Service", secondary=group_services, back_populates="groups_with_access")
    available_models = relationship("AIModel", secondary=group_models, back_populates="groups_with_access")
    lti_platforms = relationship("LTIPlatform", back_populates="group", cascade=ALL_DELETE_ORPHAN)
    service_tokens = relationship("ServiceToken", back_populates="group", cascade=ALL_DELETE_ORPHAN)
    etl_tasks = relationship("ETLTask", back_populates="group", cascade=ALL_DELETE_ORPHAN)
    etl_tasks_configuration = relationship("ETLTaskConfiguration", back_populates="group", cascade=ALL_DELETE_ORPHAN)

class Request(Base):
    __tablename__ = 'requests'
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    title = Column(String, nullable=False)
    user_id = Column(UUID(as_uuid=True), ForeignKey(USERS_ID), index=True, nullable=False)
    service_id = Column(UUID(as_uuid=True), ForeignKey('services.id'), nullable=False)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)

    service = relationship("Service", back_populates="requests")
    questions = relationship("Question", back_populates="request", cascade=ALL_DELETE_ORPHAN)
    documents = relationship("Document", back_populates="request", cascade=ALL_DELETE_ORPHAN)
    transcripts = relationship("Transcript", back_populates="request", cascade=ALL_DELETE_ORPHAN)
    podcasts = relationship("Podcast", back_populates="request", cascade=ALL_DELETE_ORPHAN)
    analytics = relationship("Analytics", back_populates="request")

class Question(Base):
    __tablename__ = 'questions'
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    request_id = Column(UUID(as_uuid=True), ForeignKey(REQUESTS_ID), index=True)
    course_id = Column(UUID(as_uuid=True), ForeignKey('courses.id'), index=True)
    question = Column(String)
    options = Column(JSONB, nullable=True)
    type = Column(String)
    correct_answer = Column(String, nullable=True)
    reason = Column(Text, nullable=True)

    request = relationship("Request", back_populates="questions")
    course = relationship("Course", back_populates="questions")

class Document(Base):
    __tablename__ = "documents"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    text = Column(Text, nullable=False)
    type = Column(String, nullable=False)
    request_id = Column(UUID(as_uuid=True), ForeignKey(REQUESTS_ID), nullable=False)

    request = relationship("Request", back_populates="documents")

class Transcript(Base):
    __tablename__ = 'transcripts'
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    job_name = Column(String, unique=True, nullable=False)
    s3_uri = Column(String, nullable=False)
    transcription_text = Column(Text, nullable=True)
    status = Column(String, nullable=False)
    summary = Column(Text, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    language_code = Column(String, nullable=True)
    request_id = Column(UUID(as_uuid=True), ForeignKey('requests.id'), nullable=False)

    request = relationship("Request", back_populates="transcripts")

class Podcast(Base):
    __tablename__ = 'podcasts'
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    language = Column(String, nullable=False)
    title = Column(String, nullable=True)
    dialog = Column(JSONB, nullable=True)
    audio_s3_uri = Column(String, nullable=True)
    image_s3_uri = Column(String, nullable=True)
    image_prompt = Column(Text, nullable=True)
    status = Column(String, nullable=False)
    completed_at = Column(DateTime, nullable=True)
    request_id = Column(UUID(as_uuid=True), ForeignKey(REQUESTS_ID), nullable=False)

    request = relationship("Request", back_populates="podcasts")

class Analytics(Base):
    __tablename__ = 'analytics'
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    request_id = Column(UUID(as_uuid=True), ForeignKey('requests.id'), nullable=False)
    model = Column(String, nullable=False)
    request_token_count = Column(Integer, nullable=True)
    response_token_count = Column(Integer, nullable=True)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    response_type = Column(String, nullable=True)
    error = Column(String, nullable=True)
    model_parameters = Column(JSONB, nullable=True)
    status = Column(String, nullable=True)
    processing_time = Column(Float, nullable=True)
    estimated_cost = Column(Float, nullable=True)
    reference = Column(String, nullable=True)

    request = relationship("Request", back_populates="analytics")

class Course(Base):
    __tablename__ = 'courses'
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    title = Column(String, nullable=False)
    description = Column(Text, nullable=True)
    teacher_id = Column(UUID(as_uuid=True), ForeignKey(USERS_ID), nullable=False)
    knowledge_base_id = Column(String, nullable=True)
    data_source_id = Column(String, nullable=True)
    ingestion_job_id = Column(String, nullable=True)
    execution_arn = Column(String, nullable=True)
    sample_questions = Column(JSONB, nullable=True)
    ingestion_status = Column(String, nullable=True)
    language = Column(String, nullable=True)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    settings = Column(JSONB, nullable=True)
    conversation_access_token = Column(String, nullable=True)

    materials = relationship("Material", back_populates="course", cascade=ALL_DELETE_ORPHAN)
    students = relationship("User", secondary=course_student, back_populates="courses")
    invites = relationship("Invite", back_populates="course")
    questions = relationship("Question", back_populates="course", cascade=ALL_DELETE_ORPHAN)

class Material(Base):
    __tablename__ = 'materials'
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    title = Column(String, nullable=False)
    type = Column(String, nullable=False)
    s3_uri = Column(String, nullable=False)
    transcription_s3_uri = Column(String, nullable=True)
    course_id = Column(UUID(as_uuid=True), ForeignKey(COURSES_ID), nullable=False)
    status = Column(String, nullable=True)
    uploaded_at = Column(DateTime, server_default=func.now(), nullable=False)

    course = relationship("Course", back_populates="materials")

class Invite(Base):
    __tablename__ = 'invites'
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    invite_code = Column(String, unique=True, nullable=False)
    email = Column(String, nullable=False)
    course_id = Column(UUID(as_uuid=True), ForeignKey(COURSES_ID), nullable=False)
    expires_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc) + timedelta(days=7))
    course = relationship("Course", back_populates="invites")

class Rubric(Base):
    __tablename__ = 'rubrics'

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    name = Column(String, nullable=False)
    description = Column(Text, nullable=True)
    created_by = Column(UUID(as_uuid=True), ForeignKey(USERS_ID), nullable=False)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)

    user = relationship("User", back_populates="rubrics", foreign_keys=[created_by])
    indicators = relationship("PerformanceIndicator", back_populates="rubric", cascade=ALL_DELETE_ORPHAN)
    evaluations = relationship("Evaluation", back_populates="rubric", cascade=ALL_DELETE_ORPHAN)
    
class PerformanceIndicator(Base):
    __tablename__ = 'performance_indicators'

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    rubric_id = Column(UUID(as_uuid=True), ForeignKey('rubrics.id'), nullable=False)
    name = Column(String, nullable=False)
    weight = Column(Float, nullable=False)
    criteria = Column(JSONB, default=dict, nullable=False)

    rubric = relationship("Rubric", back_populates="indicators")

class Evaluation(Base):
    __tablename__ = "evaluations"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    rubric_id = Column(UUID(as_uuid=True), ForeignKey("rubrics.id", ondelete="CASCADE"), nullable=False)
    created_by = Column(UUID(as_uuid=True), ForeignKey(USERS_ID), nullable=False)
    course_name = Column(String, nullable=False)
    student_name = Column(String, nullable=False)
    student_surname = Column(String, nullable=False)
    exam_description = Column(String, nullable=False)
    feedback = Column(Text, nullable=False)
    criteria_evaluation = Column(JSONB, nullable=False)
    overall_comments = Column(Text, nullable=True)
    source_text = Column(Text, nullable=False)

    user = relationship("User", foreign_keys=[created_by])
    rubric = relationship("Rubric", back_populates="evaluations")

class AIModel(Base):
    __tablename__ = "ai_models"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String, unique=True, nullable=False)
    provider = Column(String, nullable=False)
    identifier = Column(String, unique=True, nullable=False)
    is_default = Column(Boolean, default=False)
    max_input_tokens = Column(Integer, nullable=True)
    max_output_tokens = Column(Integer, nullable=True)
    input_modalities = Column(JSONB, nullable=True)
    output_modalities = Column(JSONB, nullable=True)
    inference = Column(Boolean, nullable=True)
    supports_knowledge_base = Column(Boolean, nullable=True)
    category = Column(String, nullable=True)
    description = Column(Text, nullable=True)
    token_rate = Column(Float, nullable=True)
    input_price = Column(Float, nullable=True)
    output_price = Column(Float, nullable=True)
    region_id = Column(UUID(as_uuid=True), ForeignKey("regions.id"), nullable=False)

    region = relationship("Region", back_populates="models")
    groups_with_access = relationship("Group", secondary=group_models, back_populates="available_models")

class Region(Base):
    __tablename__ = "regions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    name = Column(String, unique=True, nullable=False)
    suffix = Column(String, unique=True, nullable=False)
    s3_bucket = Column(String, nullable=False)

    models = relationship("AIModel", back_populates="region")
    groups = relationship("Group", back_populates="region")

class ComparisonEngine(Base):
    __tablename__ = "comparison_engines"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    name = Column(String, nullable=False)
    description = Column(Text, nullable=True)
    type = Column(String, nullable=False)
    content = Column(JSONB, nullable=False)
    status = Column(String, nullable=False, default="PROCESSING")
    user_id = Column(UUID(as_uuid=True), ForeignKey(USERS_ID), nullable=False)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)
    user = relationship("User", back_populates="comparison_engines")

class ComparisonDocument(Base):
    __tablename__ = "comparison_documents"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    title = Column(String, nullable=False)
    type = Column(String, nullable=False)
    s3_uri = Column(String, nullable=False)
    language = Column(String, nullable=True)
    uploaded_at = Column(DateTime, server_default=func.now(), nullable=False)
    user_id = Column(UUID(as_uuid=True), ForeignKey(USERS_ID), nullable=False)
    comparison_engine_id = Column(String, nullable=False, default="")
    user = relationship("User", back_populates="comparison_documents")

class ComparisonRule(Base):
    __tablename__ = "comparison_rules"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    name = Column(String, nullable=False)
    description = Column(Text, nullable=True)
    data = Column(JSONB, nullable=False)
    type = Column(String, nullable=False)
    user_id = Column(UUID(as_uuid=True), ForeignKey(USERS_ID), nullable=False)
    user = relationship("User", back_populates="comparison_rules")

class ComparisonConfig(Base):
    __tablename__ = "comparison_configs"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    threshold = Column(String, nullable=False)
    user_id = Column(UUID(as_uuid=True), ForeignKey(USERS_ID), nullable=False)
    user = relationship("User", back_populates="comparison_configs")

# Add a model to store chatbot data, each chatbot has an id, name, system_prompt, user_id, created_at, updated_at, status, session_id, memory_id
class Chatbot(Base):
    __tablename__ = "chatbots"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    name = Column(String, nullable=False)
    system_prompt = Column(Text, nullable=False)
    user_id = Column(UUID(as_uuid=True), ForeignKey(USERS_ID), nullable=False)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)
    status = Column(String, nullable=False)
    session_id = Column(String, nullable=False)
    memory_id = Column(String, nullable=False)
    resource_data = Column(String, nullable=True)
    lti_config = Column(JSONB, nullable=True)

    user = relationship("User", back_populates="chatbots")
    conversations = relationship("Conversation", back_populates="chatbot", cascade=ALL_DELETE_ORPHAN)
    materials = relationship("ChatbotMaterial", back_populates="chatbot", cascade=ALL_DELETE_ORPHAN)
    topics = relationship("ConversationTopics", back_populates="chatbot", cascade=ALL_DELETE_ORPHAN)

# Add a model to store conversation data, each conversation has an id, chatbot_id, role, content, created_at, updated_at
class Conversation(Base):
    __tablename__ = "chatbot_conversations"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    chatbot_id = Column(UUID(as_uuid=True), ForeignKey(CHATBOTS_ID), nullable=False)
    role = Column(String, nullable=False)
    content = Column(Text, nullable=False)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)

    chatbot = relationship("Chatbot", back_populates="conversations")

class ChatbotMaterial(Base):
    __tablename__ = "chatbot_materials"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    chatbot_id = Column(UUID(as_uuid=True), ForeignKey(CHATBOTS_ID), nullable=False)
    title = Column(String, nullable=False)
    type = Column(String, nullable=False)
    s3_uri = Column(String, nullable=False)
    status = Column(String, nullable=True)
    is_main = Column(Boolean, nullable=False, default=False)
    uploaded_at = Column(DateTime, server_default=func.now(), nullable=False)
    
    chatbot = relationship("Chatbot", back_populates="materials")

class Agent(Base):
    __tablename__ = "agents"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    code = Column(String, nullable=False)
    name = Column(String, nullable=False)
    description = Column(Text, nullable=True)
    agent_id = Column(String, nullable=False)
    alias_id = Column(String, nullable=False)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)

class Notification(Base):
    __tablename__ = "notifications"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey(USERS_ID), nullable=False, index=True)
    service_id = Column(String, nullable=False)
    title = Column(String, nullable=False)
    body = Column(Text, nullable=False)
    data = Column(JSONB, nullable=True)
    use_push_notification = Column(Boolean, nullable=False, default=True)
    is_read = Column(Boolean, nullable=False, default=False)
    actions = Column(JSONB, nullable=True)  # Para almacenar botones/acciones
    notification_type = Column(String, nullable=False, default="info")  # info, success, warning, error
    priority = Column(String, nullable=False, default="normal")  # low, normal, high, urgent
    expires_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    read_at = Column(DateTime, nullable=True)

    user = relationship("User", foreign_keys=[user_id])

class ThirdPartyIntegration(Base):
    __tablename__ = "third_party_integrations"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    service_name = Column(String, nullable=False)
    service_value = Column(JSONB, nullable=False)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)

    __table_args__ = (
        UniqueConstraint('service_name', name='uq_service'),
    )

class LTIPlatform(Base):
    __tablename__ = "lti_platforms"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    client_id = Column(String, unique=True, index=True, nullable=False)
    issuer = Column(String, nullable=False)
    platform_type = Column(String, nullable=True)  # e.g., 'moodle', 'canvas', 'blackboard', etc.
    auth_login_url = Column(String, nullable=False)
    auth_token_url = Column(String, nullable=False)
    key_set_url = Column(String, nullable=False)
    deployment_ids = Column(JSONB, nullable=False)  # Store as JSON array
    is_active = Column(Boolean, default=True)
    is_default = Column(Boolean, default=False)
    custom_params = Column(JSONB, nullable=True)  # For any platform-specific custom parameters
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)
    group_id = Column(UUID(as_uuid=True), ForeignKey(GROUPS_ID), nullable=False)

    group = relationship("Group", back_populates="lti_platforms")

class ConversationTopics(Base):
    __tablename__ = "conversation_topics"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    chatbot_id = Column(UUID(as_uuid=True), ForeignKey(CHATBOTS_ID), nullable=False)
    topics = Column(JSONB, nullable=False)
    global_topic = Column(String, nullable=True)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)

    chatbot = relationship("Chatbot", back_populates="topics")

class ETLTask(Base):
    __tablename__ = "etl_tasks"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    group_id = Column(UUID(as_uuid=True), ForeignKey(GROUPS_ID), nullable=False)
    type = Column(Enum(ETLTaskType), nullable=False)
    status = Column(Enum(ETLTaskStatus), nullable=False)
    result = Column(Enum(ETLTaskResult), nullable=True)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)

    group = relationship("Group", back_populates="etl_tasks")

class ETLTaskConfiguration(Base):
    __tablename__ = "etl_tasks_configuration"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    group_id = Column(UUID(as_uuid=True), ForeignKey(GROUPS_ID), nullable=False)
    type = Column(Enum(ETLTaskType), nullable=False)
    configuration = Column(JSONB, nullable=False)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)

    group = relationship("Group", back_populates="etl_tasks_configuration")



class ServiceToken(Base):
    __tablename__ = "service_tokens"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    group_id = Column(UUID(as_uuid=True), ForeignKey(GROUPS_ID), nullable=False)
    name = Column(String, nullable=False)
    description = Column(Text, nullable=True)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    expires_at = Column(DateTime, nullable=False)
    last_used_at = Column(DateTime, nullable=True)
    is_active = Column(Boolean, nullable=False, default=True)
    token_hash = Column(String, nullable=False)
    public_key = Column(String, nullable=False)

    group = relationship("Group", back_populates="service_tokens")




