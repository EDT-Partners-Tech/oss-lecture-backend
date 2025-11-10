# © [2025] EDT&Partners. Licensed under CC BY 4.0.

from datetime import datetime
from typing import Any, List, Optional, Dict
from uuid import UUID
from fastapi import UploadFile
from pydantic import BaseModel, ConfigDict, EmailStr, Field
from enum import Enum

from database.models import UserRole, ETLTaskType
import os

AWS_REGION_NAME = os.environ.get('AWS_REGION_NAME', 'eu-central-1')

class TextInput(BaseModel):
    text: str
    source_lang: str
    target_lang: str
    
class Question(BaseModel):
    id: str
    question: str
    options: Optional[List[str]] = None
    correct_answer: Optional[str] = None
    reason: str
    type: str

class UploadRequest(BaseModel):
    url: str
    
class UserBase(BaseModel):
    name: Optional[str] = None
    email: Optional[EmailStr] = None
    role: Optional[UserRole] = None

class UserCreate(UserBase):
    cognito_id: Optional[str] = None
    name: str
    email: EmailStr
    role: UserRole
    group_id: Optional[UUID] = None

class UserUpdate(UserBase):
    pass

class UserResponse(BaseModel):
    id: str
    cognito_id: str
    name: str
    email: EmailStr

    model_config = ConfigDict(from_attributes=True)

class CourseCreate(BaseModel):
    title: str
    description: Optional[str] = None

class CourseResponse(BaseModel):
    id: UUID
    title: str
    description: Optional[str] = None
    teacher_id: UUID
    created_at: datetime
    settings: Optional[dict] = None
    ingestion_status: Optional[str] = None
    model_config = ConfigDict(from_attributes=True)

class CourseUpdateSettings(BaseModel):
    settings: dict

class ConversationAccessToken(BaseModel):
    conversation_access_token: str

class ConversationAccessRequest(BaseModel):
    prompt: str
    session_id: str
    
class MaterialCreate(BaseModel):
    title: str
    type: str
    s3_uri: str
    course_id: UUID
    transcription_s3_uri: Optional[str] = None

class MaterialResponse(BaseModel):
    id: UUID
    title: str
    type: str
    s3_uri: str
    status: Optional[str] = None

class CourseWithMaterialsResponse(BaseModel):
    id: UUID
    title: str
    description: Optional[str] = None
    ingestion_status: Optional[str] = None
    created_at: datetime
    materials: List[MaterialResponse]
    
class InviteBase(BaseModel):
    invite_code: str
    email: str
    course_id: UUID
    expires_at: datetime

class InviteCreate(BaseModel):
    course_id: UUID
    email: str

class InviteResponse(InviteBase):
    id: UUID
    status: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)
        
class InviteConfirm(BaseModel):
    invite_code: str
    password: str
    given_name: str
    family_name: str
    locale: str
    
class KnowledgeBaseRequest(BaseModel):
    collection_arn: str


class QuestionUpdate(BaseModel):
    id: str
    question: str
    options: Optional[List[str]] = None
    correct_answer: Optional[str] = None
    reason: Optional[str] = None
    type: str

    model_config = ConfigDict(from_attributes=True)

class RefreshQuestionRequest(BaseModel):
    prompt: str
    question: Question
    
class PollStateMachineRequest(BaseModel):
    execution_arn: str
    
class TextActionRequest(BaseModel):
    text: str
    action: str
    start_index: Optional[int] = None
    end_index: Optional[int] = None
    tones: Optional[List[str]] = None
    audiences: Optional[List[str]] = None
    llm_id: Optional[str] = None
    
class SummarizeRequest(BaseModel):
    transcript_id: UUID
    transcript: str
    language: str


class PerformanceIndicator(BaseModel):
    name: str
    weight: float  
    criteria: dict  


class Rubric(BaseModel):
    id: Optional[UUID] = None  
    name: str  
    description: Optional[str] = None  
    created_by: Optional[str] = None  
    indicators: List[PerformanceIndicator]  
    created_at: Optional[str] = None  
    updated_at: Optional[str] = None  

class RubricCreate(BaseModel):
    name: str
    description: Optional[str] = None
    indicators: List[PerformanceIndicator]

class RubricUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    indicators: Optional[List[PerformanceIndicator]] = None

class RubricEvaluationRequest(BaseModel):
    response: str  
    rubric_id: UUID  

class RubricEvaluationResult(BaseModel):
    scores: dict  
    overall_score: float  
    feedback: str  

class EvaluationCreate(BaseModel):
    rubric_id: UUID  
    created_by: Optional[UUID] = None  
    course_name: Optional[str] = None  
    student_name: Optional[str] = None  
    student_surname: Optional[str] = None  
    exam_description: Optional[str] = None  
    feedback: str  
    criteria_evaluation: List[dict]  
    overall_comments: Optional[str] = None  
    source_text: str  

    model_config = ConfigDict(from_attributes=True)


class EvaluationUpdate(BaseModel):
    course_name: Optional[str] = None  
    student_name: Optional[str] = None  
    student_surname: Optional[str] = None  
    exam_description: Optional[str] = None  
    feedback: Optional[str] = None  
    criteria_evaluation: Optional[List[dict]] = None  
    overall_comments: Optional[str] = None  
    source_text: Optional[str] = None  

    model_config = ConfigDict(from_attributes=True)


class EvaluationResponse(BaseModel):
    id: UUID  
    rubric_id: UUID  
    created_by: Optional[UUID] = None  
    feedback: str  
    criteria_evaluation: List[Any]  
    overall_comments: Optional[str] = None  
    source_text: str  

    model_config = ConfigDict(from_attributes=True)


class PodcastCreate(BaseModel):
    language: str
    request_id: UUID

class PodcastStatus(str, Enum):
    PROCESSING = "PROCESSING"
    AUDIO = "AUDIO_GENERATION"
    IMAGE = "IMAGE_GENERATION"
    COMPLETED = "COMPLETED"
    ERROR = "ERROR"

class PodcastUpdate(BaseModel):
    title: Optional[str] = None
    dialog: Optional[str] = None
    audio_s3_uri: Optional[str] = None
    image_s3_uri: Optional[str] = None
    image_prompt: Optional[str] = None
    completed_at: Optional[datetime] = None

class ConfigureServicesRequest(BaseModel):
    services_ids: List[UUID]

class ConfigureModelsRequest(BaseModel):
    models_ids: List[int]

class SetGroupAdminRequest(BaseModel):
    user_id: UUID

class GroupCreate(BaseModel):
    domain: str
    name: Optional[str] = None
    region_name: str = AWS_REGION_NAME
    logo_s3_uri: Optional[str] = None

class GroupUpdate(BaseModel):
    name: str
    logo_s3_uri: Optional[str] = None

class RegionResponse(BaseModel):
    id: UUID
    name: str
    suffix: str
    s3_bucket: str

    model_config = ConfigDict(from_attributes=True)

class GroupResponse(BaseModel):
    id: UUID
    domain: str
    name: Optional[str] = None
    region_id: UUID
    logo_s3_uri: Optional[str] = None
    region: Optional[RegionResponse] = None

    model_config = ConfigDict(from_attributes=True)

class ComparisonEngineDB(BaseModel):
    id: UUID
    name: str
    description: Optional[str] = None
    type: str
    content: Optional[str] = None
    user_id: UUID

class ComparisonEngineCreateRequest(BaseModel):
    process_id: str
    name: str
    description: Optional[str] = None
    document1_id: str
    document2_id: str
    rules_ids: List[str]
    config_id: str
    language: str
    model: str

class ComparisonEngineResponse(BaseModel):
    id: UUID
    name: str
    description: Optional[str] = None

class ComparisonEngineResponseWithContent(BaseModel):
    id: UUID
    name: str
    description: Optional[str] = None
    content: Optional[str] = ""

class ComparisonRuleResponse(BaseModel):
    id: UUID
    name: str
    description: Optional[str] = None
    data: dict

class ComparisonRuleCreateRequest(BaseModel):
    name: str
    description: Optional[str] = None
    data: dict
    

class ComparisonRule(BaseModel):
    data: dict
    type: str

class ChatbotCreate(BaseModel):
    id: str
    name: str
    system_prompt: str
    user_id: UUID
    status: str
    session_id: str
    memory_id: str
    resource_data: str
    lti_config: Optional[dict] = None


class ChatTestRequest(BaseModel):
    message: str
    user_id: str
    user_name: Optional[str] = None
    user_email: Optional[str] = None
    course_id: str

    model_config = ConfigDict(json_schema_extra={
        "example": {
            "message": "Can you explain the main concepts from this course?",
            "user_id": "2",
            "user_name": "None",
            "user_email": "None",
            "course_id": "00000000-0000-0000-0000-000000000000"
        }
    })

class ChatbotUpdate(BaseModel):
    status: str

class ChatbotMaterialCreate(BaseModel):
    chatbot_id: UUID
    title: str
    type: str
    s3_uri: str
    status: Optional[str] = None
    is_main: bool

class AgentCreate(BaseModel):
    code: str
    name: str
    description: Optional[str] = None
    agent_id: str
    alias_id: str

class AgentResponse(BaseModel):
    id: UUID
    code: str
    name: str
    description: Optional[str] = None
    agent_id: str
    alias_id: str

    model_config = ConfigDict(from_attributes=True)

class ThirdPartyIntegrationUpdate(BaseModel):
    service_value: dict

class ThirdPartyIntegrationResponse(BaseModel):
    id: UUID
    service_name: str
    service_value: dict
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)

class ServiceValueResponse(BaseModel):
    service_value: dict

    model_config = ConfigDict(from_attributes=True)

class AllowedServiceName(str, Enum):
    SENTRY = "sentry"
    GOOGLE = "google"
    S3 = "s3"

class ExportQuestionsRequest(BaseModel):
    question_ids: List[UUID]

# LTI Platform Registration Models
class LTIPlatformCreate(BaseModel):
    client_id: str
    issuer: str
    platform_type: str
    auth_login_url: str
    auth_token_url: str
    key_set_url: str
    deployment_ids: List[str]
    is_default: bool = False
    custom_params: Optional[Dict[str, Any]] = None

class LTIPlatformUpdate(BaseModel):
    auth_login_url: Optional[str] = None
    auth_token_url: Optional[str] = None
    key_set_url: Optional[str] = None
    deployment_ids: Optional[List[str]] = None
    is_active: Optional[bool] = None
    is_default: Optional[bool] = None
    custom_params: Optional[Dict[str, Any]] = None

class NotificationAction(BaseModel):
    """Schema for the action buttons in the notifications"""
    label: str
    action: Optional[str] = None
    url: Optional[str] = None
    data: Optional[dict] = None
    style: Optional[str] = "default"  # default, primary, secondary, danger

class NotificationCreate(BaseModel):
    """Schema to create a new notification"""
    user_id: UUID
    service_id: str
    title: str
    body: str
    data: Optional[dict] = None
    use_push_notification: bool = True
    actions: Optional[List[NotificationAction]] = None
    notification_type: str = "info"  # info, success, warning, error
    priority: str = "normal"  # low, normal, high, urgent
    expires_at: Optional[datetime] = None

class NotificationUpdate(BaseModel):
    """Schema to update a notification"""
    is_read: Optional[bool] = None
    actions: Optional[List[NotificationAction]] = None
    notification_type: Optional[str] = None
    priority: Optional[str] = None
    expires_at: Optional[datetime] = None

class NotificationResponse(BaseModel):
    """Schema for the notification response"""
    id: UUID
    user_id: UUID
    service_id: str
    title: str
    body: str
    data: Optional[dict] = None
    use_push_notification: bool
    is_read: bool
    actions: Optional[List[NotificationAction]] = None
    notification_type: str
    priority: str
    expires_at: Optional[datetime] = None
    created_at: datetime
    read_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)

class NotificationFilter(BaseModel):
    """Schema to filter notifications"""
    is_read: Optional[bool] = None
    notification_type: Optional[str] = None
    priority: Optional[str] = None
    service_id: Optional[str] = None
    limit: Optional[int] = 50
    offset: Optional[int] = 0

class ETLTaskConfiguration(BaseModel):
    id: UUID
    type: ETLTaskType
    configuration: dict

class ETLTaskTopicsAnalysisConfiguration(BaseModel):
    overwrite: bool = True
    max_supertopics: int = 20

# Service Tokens models
class ServiceTokenCreate(BaseModel):
    name: str = Field(..., description="Descriptive name for the token", min_length=1, max_length=100)
    description: Optional[str] = Field(None, description="Optional description of the token's purpose", max_length=500)
    expires_in_days: int = Field(30, description="Number of days until token expires", ge=1, le=365)

class ServiceTokenResponse(BaseModel):
    id: str
    name: str
    description: Optional[str]
    created_at: datetime
    expires_at: datetime
    last_used_at: Optional[datetime]
    is_active: bool

class ServiceTokenWithSecret(ServiceTokenResponse):
    token: str

class ServiceTokenList(BaseModel):
    tokens: List[ServiceTokenResponse]
    total: int

# Modelos de AI Content Router
class AIRequest(BaseModel):
    prompt: str

class MessageHistory(BaseModel):
    role: str
    content: str


class FilePayload(BaseModel):
    name: str
    type: str
    content: str  # en base64

class GenerateMDRequest(BaseModel):
    prompt: str
    conversation_id: Optional[str] = None
    user_profile: Optional[str] = None
    system_prompt: Optional[str] = None
    content: str
    message_history: Optional[list[MessageHistory]] = None
    model_id: Optional[str] = None
    model_region: Optional[str] = None
    files: Optional[List[FilePayload]] = None
    deepThinkingEnabled: Optional[bool] = False

class GenerateHTMLRequest(BaseModel):
    prompt: str
    system_prompt: str
    context: Optional[str] = None
    content_id: Optional[str] = None
    model_id: Optional[str] = None
    model_region: Optional[str] = None

class Context(BaseModel):
    id: str
    title: str
    content: str

class Routine(BaseModel):
    id: Optional[str] = None
    type: str # "title", "subtitle", "subitem"
    content: str

class PromptData(BaseModel):
    contexts: list[Context]
    routines: list[Routine]

class GenerateRoutinesRequest(BaseModel):
    prompt: PromptData
    system_prompt: str
    content_type: str = "ai_html"
    content_id: Optional[str] = None
    model_id: Optional[str] = None
    model_region: Optional[str] = None

class GenerateIndexRequest(BaseModel):
    prompt: str
    async_processing: bool = False

class AIResponse(BaseModel):
    success: bool
    message: str
    html_content: Optional[str] = None
    markdown_content: Optional[str] = None
    routines: Optional[list[Routine]] = None
    content_id: Optional[str] = None

class GenerateMDResponse(BaseModel):
    success: bool
    message: str
    response: dict

class HybridContentItem(BaseModel):
    index: int
    type: str  # "simple" o "iframe"
    content: str
    original_content: Optional[str] = None

class HybridResponse(BaseModel):
    success: bool
    message: str
    simple_content: list[HybridContentItem]
    complex_content: list[HybridContentItem]
    total_items: int

# Modelos de Documents Router
class ContextItem(BaseModel):
    title: str
    context: str

class GenerateStructuredContentRequest(BaseModel):
    prompt: str
    context: List[ContextItem]
    profile: str
    files: List[UploadFile]

# Modelos de HTML Content Router
class GenerateStructureRequest(BaseModel):
    title: str = "Document"

class AddHeadTagsRequest(BaseModel):
    html_content: str
    tags: str

class AddScriptRequest(BaseModel):
    html_content: str
    script: str
    position: str = "body_end"

class ReplaceElementRequest(BaseModel):
    html_content: str
    element_id: str
    new_html: str

class AddIdentificationRequest(BaseModel):
    html_content: str

class WrapElementRequest(BaseModel):
    html_element: str

class CleanVoidRequest(BaseModel):
    html_content: str

class HTMLResponse(BaseModel):
    success: bool
    message: str
    html_content: Optional[str] = None

