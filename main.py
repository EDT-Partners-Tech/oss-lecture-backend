# © [2025] EDT&Partners. Licensed under CC BY 4.0.

import asyncio
from contextlib import asynccontextmanager
from datetime import datetime
from io import BytesIO
import json
import os
import re
import time
from typing import Optional, List
import uuid
import tempfile
from pathlib import Path
from urllib.parse import quote
from logging_config import setup_logging
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi import FastAPI, File, UploadFile, Form, Depends, HTTPException, Request, BackgroundTasks
from fastapi.security import HTTPBearer
from fastapi.staticfiles import StaticFiles
import json_repair
from sqlalchemy import cast
from sqlalchemy.orm import Session
from sqlalchemy.dialects.postgresql import JSONB
from icecream import ic
import uvicorn
import aiofiles
from starlette.middleware.sessions import SessionMiddleware

from constants import ACCESS_DENIED_MESSAGE, INTERNAL_SERVER_ERROR_MESSAGE
from routers.evaluations import router as evaluations_router
from routers.courses import router as courses_router
from routers.users import router as users_router
from routers.podcast import router as podcast_router
from routers.compare import router as compare_router
from routers.chatbot import router as chatbot_router
from routers.groups import router as groups_router
from routers.analytics import router as analytics_router
from routers.auth import router as auth_router
from routers.integrations import router as integrations_router
from routers.notifications import router as notifications_router
from routers.lti_management import router as lti_platforms_router
from routers.topics import router as topics_router
from routers.service_token import router as service_token_router
from lti.router import router as lti_router
from routers.guardrails import router as guardrails_router
from routers.health import router as cg_health_router
from routers.ai_content import router as cg_ai_content_router
from routers.html_content import router as cg_html_content_router
from routers.documents import router as cg_documents_router
from database.models import Agent, UserRole, Group, Region, AIModel
from database.schemas import AgentCreate, ExportQuestionsRequest, Question, QuestionUpdate, RefreshQuestionRequest, SummarizeRequest, TextActionRequest, TextInput, UploadRequest, ChatbotCreate
from function.transcribe.transcribe_utils import download_youtube_audio, generate_presigned_url, get_audio_duration, get_transcription_status, handle_uploaded_file
from utility.analytics import process_and_save_analytics
from utility.auth import require_token_types
from utility.tokens import JWTLectureTokenPayload, LTIServicesTokenPayload
from utility.aws import delete_from_s3, detect_language, generate_text_translation, get_s3_buckets, upload_file_to_s3, upload_to_s3, start_transcription, generate_file_translation
from utility.service import handle_save_request, get_service_id_by_code
from utility.session import get_session_data, get_session_secret_key
from utility.common import clean_raw_data, convert_to_gift, extract_text_from_pdf, extract_text_from_url, get_selected_text, replace_selected_text, extract_text_from_data, split_text_into_chunks, is_valid_file_format_for_translation, extract_text_from_txt, model_to_dict
from utility.prompt_utility import build_key_points_prompt, build_prompt_agent, build_prompt_document, build_reload_prompt, build_summary_prompt, build_text_processing_prompt
from database.db import init_db, get_db, SessionLocal
from database.crud import delete_question_by_id, delete_transcript_by_id, delete_request_by_id, get_agents, get_ai_model_by_id, get_ai_models_by_filters, get_analytics_by_request_id, get_course_by_id, get_materials_by_id, get_question_bank, get_question_by_id, get_questions_by_course_id, get_questions_by_ids, get_request_by_id, get_requests_by_user_service, get_summary, get_third_party_integration_by_service, get_transcript_by_id, get_transcript_by_request_id, get_user_by_cognito_id, save_request_and_questions, save_questions_to_existing_request, get_requests_and_questions, get_questions_request, save_summary, get_request_id_by_document, save_transcription_to_db, update_question_by_id, update_transcript_summary, get_available_services_for_user, get_available_models_for_user, create_chatbot
from database.models import Chatbot
from startup import run_startup_tasks
from function.llms.bedrock_invoke import get_default_model_ids, invoke_bedrock_model, retrieve_and_generate
from function.content_query.query_utils import store_parsed_document, generate_summary_and_title
from constants import DOCX_EXTENSION, TXT_EXTENSION
from utility.async_manager import AsyncManager
from utility.chatbot_processor import ChatbotProcessor

# Configure logging first
logger = setup_logging(module_name='main')

# Constants
MAX_TRANSLATOR_FILE_SIZE = 102400  # 100kb

# Mount the static directory to serve the files
temporary_files_dir = "temporary_files"
if not os.path.exists(temporary_files_dir):
    os.makedirs(temporary_files_dir)

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting application lifespan...")
    db = None
    try:
        # Get database connection
        logger.info("Initializing database connection...")
        db = next(get_db())
        logger.info("Database connection established successfully")
        
        # Run startup tasks
        await run_startup_tasks(db)
        
    except Exception as e:
        logger.error(f"Critical error during application startup: {str(e)}")
        logger.error(f"Error type: {type(e).__name__}")
        logger.error(f"Error details: {e}")
        import traceback
        logger.error(f"Full traceback: {traceback.format_exc()}")
        # Re-raise the exception to prevent the application from starting with errors
        raise
    finally:
        # Ensure database connection is properly closed
        if db:
            try:
                db.close()
                logger.debug("Database connection closed successfully")
            except Exception as e:
                logger.error(f"Error closing database connection: {str(e)}")
    
    logger.info("Application startup completed, yielding control...")
    yield
    
    logger.info("Application shutdown initiated...")

# Configure security schemes for OpenAPI/Swagger
security_schemes = {
    "Bearer": {
        "type": "http",
        "scheme": "bearer",
        "bearerFormat": "JWT",
        "description": "Enter your JWT authentication token"
    }
}

app = FastAPI(
    lifespan=lifespan,
    openapi_tags=[
        {"name": "Users", "description": "User operations"},
        {"name": "Courses", "description": "Course management"},
        {"name": "Evaluations", "description": "Evaluation system"},
        {"name": "Podcast", "description": "Podcast generation"},
        {"name": "Compare", "description": "Comparison tools"},
        {"name": "Chatbot", "description": "Chatbot system"},
        {"name": "Analytics", "description": "Analytics and metrics"},
        {"name": "Auth", "description": "Authentication and authorization"},
        {"name": "Integrations", "description": "External integrations"},
        {"name": "Notifications", "description": "Notification system"},
        {"name": "LTI", "description": "LTI integration"},
        {"name": "LTI Management", "description": "LTI platform management"},
        {"name": "Guardrails Management", "description": "Guardrails management"},
        {"name": "Service Tokens", "description": "Service token management"},
        {"name": "Topics", "description": "Topic management"}
    ]
)

app.add_middleware(
    SessionMiddleware,
    secret_key=get_session_secret_key(),
    max_age=3600,
    same_site="lax",
    https_only=True,
)

app.include_router(users_router, prefix="/users", tags=["Users"])
app.include_router(courses_router, prefix="/courses", tags=["Courses"])
app.include_router(evaluations_router, prefix="/evaluations", tags=["Evaluations"])
app.include_router(podcast_router, prefix="/podcast", tags=["Podcast"])
app.include_router(compare_router, prefix="/compare", tags=["Compare"])
app.include_router(chatbot_router, prefix="/chatbot", tags=["Chatbot"])
app.include_router(groups_router, prefix="/groups")
app.include_router(analytics_router, prefix="/analytics", tags=["Analytics"])
app.include_router(auth_router, prefix="/auth", tags=["Auth"])
app.include_router(integrations_router, prefix="/integrations", tags=["Integrations"])
app.include_router(notifications_router, prefix="/notifications", tags=["Notifications"])
app.include_router(lti_router, prefix="/lti", tags=["LTI"])
app.include_router(lti_platforms_router, prefix="/lti-management", tags=["LTI Management"])
app.include_router(guardrails_router, prefix="/guardrails", tags=["Guardrails Management"])
app.include_router(service_token_router, prefix="/service-tokens", tags=["Service Tokens"])
app.include_router(cg_health_router, prefix="/cg-health", tags=["CG - Health"])
app.include_router(cg_ai_content_router, prefix="/cg-ai-content", tags=["CG - AI Content"])
app.include_router(cg_html_content_router, prefix="/cg-html-content", tags=["CG - HTML Content"])
app.include_router(cg_documents_router, prefix="/cg-documents", tags=["CG - Documents"])
app.include_router(topics_router, prefix="/topics", tags=["Topics"])
app.mount("/temporary_files", StaticFiles(directory=temporary_files_dir), name="temporary_files")

# Function to customize the OpenAPI schema
def custom_openapi():
    if app.openapi_schema:
        return app.openapi_schema
    
    from fastapi.openapi.utils import get_openapi
    openapi_schema = get_openapi(
        title="Lecture Backend API",
        version="1.0.0",
        description="API para el sistema Lecture - Plataforma educativa con IA",
        routes=app.routes,
    )
    
    # Add security schemes
    openapi_schema["components"]["securitySchemes"] = security_schemes
    
    # Add global security to all endpoints that require authentication
    for path, path_item in openapi_schema["paths"].items():
        for method, operation in path_item.items():
            if method in ["get", "post", "put", "delete", "patch"]:
                # Only add security if the endpoint is not public
                if path not in ["/", "/health", "/config", "/lti/login", "/lti/deep-link"]:
                    operation["security"] = [{"Bearer": []}]
    
    app.openapi_schema = openapi_schema
    return app.openapi_schema

app.openapi = custom_openapi

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["Content-Disposition"]
)

# Add middleware for request logging
@app.middleware("http")
async def log_requests(request: Request, call_next):
    logger.info(f"Request: {request.method} {request.url}")
    try:
        response = await call_next(request)
        logger.info(f"Response status: {response.status_code}")
        return response
    except Exception as e:
        logger.error(f"Request failed: {str(e)}")
        raise

@app.get("/")
def read_root():
    return {"status": "API is up and running", "version": "1.0.0"}

@app.get("/health")
async def health_check(db: Session = Depends(get_db)):
    try:
        db.execute("SELECT 1")
        return {"status": "healthy"}
    except Exception:
        raise HTTPException(status_code=500, detail=INTERNAL_SERVER_ERROR_MESSAGE)

@app.get("/config")
def get_config():
    return {
        "COGNITO_REGION": os.getenv("COGNITO_REGION"),
        "COGNITO_APP_CLIENT_ID": os.getenv("COGNITO_APP_CLIENT_ID"),
        "GOOGLE_CLIENT_ID": os.getenv("GOOGLE_CLIENT_ID")
    }

@app.post("/translate-text/")
async def translate_text(input: TextInput,
                         token: JWTLectureTokenPayload = Depends(require_token_types(allowed_types=["cognito", "service_api"])),
                         db: Session = Depends(get_db)
                         ):
    start_time = time.time()
    translation = generate_text_translation(
        text=input.text,
        source_lang=input.source_lang,
        target_lang=input.target_lang,
    )
    processing_time = time.time() - start_time
    user_id = get_user_by_cognito_id(db, token.sub).id
    
    request_id = handle_save_request(db, "text", user_id, "translation_service")
    print(f"Request ID: {request_id}, User ID: {user_id}, Input Text: {input.text}, Translation: {translation}")

    await process_and_save_analytics(db, request_id, 'translate', input.text, translation, processing_time)
    
    return {"source_text": input.text, "translation": translation}

@app.post("/translate-file/")
async def translate_file(
    source_lang: str = Form(...),
    target_lang: str = Form(...),
    file: UploadFile = File(...),
    token: JWTLectureTokenPayload = Depends(require_token_types(allowed_types=["cognito", "service_api"])),
    db: Session = Depends(get_db)
):
    try:
        # Get suffix of the file
        file_suffix = Path(file.filename).suffix

        # Get the content type
        content_type = file.content_type

        # Check if decode is required
        is_decode_required = True
        
        # Extract text using the async function from common.py
        text_content = await extract_text_from_data(file, file_suffix == TXT_EXTENSION, True)
        if not text_content:
            raise HTTPException(status_code=400, detail="Could not extract text from file")
        translation = ""

        start_time = time.time()
        # Check if file is more than 10kb
        if file.size <= MAX_TRANSLATOR_FILE_SIZE and is_valid_file_format_for_translation(file, allowed_extensions=[TXT_EXTENSION, DOCX_EXTENSION]):
            # print("File size is less than 10kb")
            
            translation = await generate_file_translation(
                blob_file=file,
                source_lang=source_lang,
                target_lang=target_lang,
            )

            # Extract text from the temporary file depending on the file format
            if file_suffix == ".txt":
                # Save the translated content to a temporary file
                with tempfile.NamedTemporaryFile(delete=False, suffix=file_suffix) as temp_file:
                    temp_file.write(translation)
                    temp_file_path = temp_file.name
                translation = await extract_text_from_txt(temp_file_path)
            else:
                is_decode_required = False

        else:
            # Set Content-Type for the response to be a text file
            content_type = "text/plain"

            # Force presuffix to be .txt
            file_suffix = ".txt"

            # Split the text into chunks
            text_array = split_text_into_chunks(text_content)

            # Generate translation
            for text in text_array:
                previous_translation = generate_text_translation(
                    text=text,
                    source_lang=source_lang,
                    target_lang=target_lang,
                )
                translation += previous_translation

        processing_time = time.time() - start_time

        # Save analytics
        user_id = get_user_by_cognito_id(db, token.sub).id
        request_id = handle_save_request(db, file.filename, user_id, "translation_service")
        await process_and_save_analytics(db, request_id, 'translate', text_content, translation, processing_time)

        # Create safe filename for the translation
        safe_filename = f"{Path(os.path.basename(file.filename)).stem}{file_suffix}"
        
        # Encode the filename using RFC 6266
        encoded_filename = f"filename=''{quote(safe_filename)}"
        
        return StreamingResponse(
            BytesIO(translation.encode('utf-8') if is_decode_required else translation),
            media_type=content_type,
            headers={"Content-Disposition": f"attachment; {encoded_filename}"}
        )

    except HTTPException as http_exc:
        raise http_exc
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Translation failed: {str(e)}"
        )

@app.post("/generate-exam/")
async def generate_exam(
    title: str = Form(...),
    file: UploadFile = File(...),
    number_mcq: int = Form(...),
    number_tfq: int = Form(...),
    number_open: int = Form(...),
    custom_instructions: Optional[str] = Form(None),
    llm_id: Optional[str] = Form(None),
    async_processing: bool = Form(default=False),
    token: JWTLectureTokenPayload = Depends(require_token_types(allowed_types=["cognito", "service_api"])),
    db: Session = Depends(get_db),
    background_tasks: BackgroundTasks = None
):
    try:
        # Extract text using the async function from common.py
        start_time = time.time()
        source_text = await extract_text_from_data(file)
        if not source_text:
            raise HTTPException(status_code=400, detail="Could not extract text from file")

        # Save initial request to database
        service_id = get_service_id_by_code(db, "questions_generator_service")
        user_id = get_user_by_cognito_id(db, token.sub).id
        request_id = handle_save_request(db, title, user_id, "questions_generator_service")

        if async_processing and token.token_type != "service_api":
            # Asynchronous processing with BackgroundTasks
            if not background_tasks:
                raise HTTPException(status_code=500, detail="BackgroundTasks not available for asynchronous processing")
            
            # Start asynchronous processing
            background_tasks.add_task(
                _process_exam_generation_async,
                title=title,
                source_text=source_text,
                number_mcq=number_mcq,
                number_tfq=number_tfq,
                number_open=number_open,
                custom_instructions=custom_instructions,
                llm_id=llm_id,
                user_id=user_id,
                request_id=request_id
            )
            
            return JSONResponse(content={
                "title": title,
                "request_id": str(request_id),
                "status": "PROCESSING",
                "async": True
            })
        else:
            # Synchronous processing (using the same request_id)
            # Generate prompt and get relevant content
            relevance_prompt = build_key_points_prompt(source_text)
            relevance_response = await invoke_bedrock_model(relevance_prompt, llm_id)
            relevant_source = relevance_response
            ic(f"Relevant source: {relevant_source}")

            # Build prompt and generate questions
            prompt = build_prompt_document(number_mcq, number_tfq, number_open, relevant_source, custom_instructions)
            ic("Building prompt completed")

            response = await invoke_bedrock_model(prompt, llm_id)
            ic(f"Response: {response}")
            
            formatted_response = clean_raw_data(response)

            # Save questions to the existing request (same as async processing)
            saved_data = save_questions_to_existing_request(db, request_id, formatted_response)
            processing_time = time.time() - start_time
            
            await process_and_save_analytics(db, request_id, llm_id if llm_id else get_default_model_ids()["claude"], response, response, processing_time)

            return JSONResponse(content={
                "title": title,
                "questions": saved_data['questions']
            })

    except HTTPException as he:
        raise he
    except Exception as e:
        # Log the detailed error
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Internal Server Error: {str(e)}")


@app.get("/get-exams/")
async def get_exams(token: JWTLectureTokenPayload = Depends(require_token_types(allowed_types=["cognito", "service_api"])), 
                    db: Session = Depends(get_db)):
    try:
        user_id = get_user_by_cognito_id(db, token.sub).id
        service_id = get_service_id_by_code(db, "questions_generator_service")
        exams = get_requests_and_questions(db, str(user_id), service_id)
        return JSONResponse(content=exams)
    except Exception as exception:
        ic(f"Error in get-exam endpoint: {exception}")
        return JSONResponse(status_code=500, content={"detail": INTERNAL_SERVER_ERROR_MESSAGE})
    
@app.get("/get-question-bank/{course_id}")
async def get_exam(course_id: str, 
                   token: JWTLectureTokenPayload = Depends(require_token_types(allowed_types=["cognito", "service_api"])), 
                   db: Session = Depends(get_db)):
    try:
        user_id = get_user_by_cognito_id(db, token.sub).id
        exams = get_question_bank(db, str(user_id), course_id)

        return JSONResponse(content=exams)
    except Exception as exception:
        ic(f"Error in get-exam endpoint: {exception}")
        return JSONResponse(status_code=500, content={"detail": INTERNAL_SERVER_ERROR_MESSAGE})

@app.get("/get-request/{request_id}")
async def get_request(request_id: uuid.UUID, 
                      token: JWTLectureTokenPayload = Depends(require_token_types(allowed_types=["cognito", "service_api"])), 
                      db: Session = Depends(get_db)):
    try:
        ic(f"Request received for ID: {request_id} with token: {token}")
        user_id = get_user_by_cognito_id(db, token.sub).id
        request_data = get_questions_request(db, request_id, user_id)
        ic(f"Request data: {request_data}")

        if request_data is None:
            raise HTTPException(status_code=404, detail="Request not found")

        return request_data
    except HTTPException as http_exception:
        ic(f"HTTPException: {http_exception.detail}")
        raise http_exception
    except Exception as exception:
        ic(f"Error in get_request endpoint: {exception}")
        raise HTTPException(status_code=500, detail=INTERNAL_SERVER_ERROR_MESSAGE)

@app.post("/questions/refresh/", response_model=Question)
async def refresh_question(request: RefreshQuestionRequest, 
                           db: Session = Depends(get_db), 
                           token: JWTLectureTokenPayload = Depends(require_token_types(allowed_types=["cognito", "service_api"]))):
    try:
        start_time = time.time()
        question_data = request.question
        user_prompt = request.prompt
        user_id = get_user_by_cognito_id(db, token.sub).id
        service_code = "questions_generator_service"
        
        question_id = str(question_data.id)
        question = get_question_by_id(db, question_id)
        
        # Only try to get course if course_id exists
        course = None
        if question and question.course_id:
            course = get_course_by_id(db, str(question.course_id))
        
        serialized_question = json.dumps(question_data.model_dump(), ensure_ascii=False)
        prompt = build_reload_prompt(serialized_question, user_prompt)
        
        ic(f"Prompt: {prompt}")
        text_input = "Refresh the question based on the provided text."
        
        # Use knowledge base if course exists and has KB ID, otherwise use default approach
        if course and course.knowledge_base_id:
            response = retrieve_and_generate(
                prompt=prompt, 
                kb_id=course.knowledge_base_id,
                text_input=text_input,
            )
            llm_response = json.loads(json_repair.repair_json(response["text"]))
            service_code = "knowledge_base_questions_generator"
        else:
            # Fallback to regular prompt without knowledge base
            response = await invoke_bedrock_model(prompt)
            llm_response = json.loads(json_repair.repair_json(response))
            
        # Add the question ID to the response
        llm_response["id"] = question_id
        
        ic(llm_response)
        
        updated_question_data = QuestionUpdate(**llm_response)
        updated_question = update_question_by_id(db=db, question_id=question_id, question_data=updated_question_data)

        request_id = handle_save_request(db, f"Refresh: {question.question}", user_id, service_code)
        
        processing_time = time.time() - start_time
        await process_and_save_analytics(db, request_id, 'default' , prompt, response, processing_time, {}, 'text', "refresh")

        return Question(
            id=str(updated_question["id"]),
            question=updated_question["question"],
            options=updated_question["options"],
            correct_answer=updated_question["correct_answer"],
            reason=updated_question["reason"],
            type=updated_question["type"]
        )

    except Exception as e:
        message = str(e)
        ic(f"Error occurred: {message}")
        if "Too many requests" in message or "__init__() missing 1 required positional argument" in message:
            raise HTTPException(status_code=429, detail="Too many requests. Please wait before trying again.")
        else:
            raise HTTPException(status_code=500, detail=f"Error refreshing question: {str(e)}")

@app.put("/questions/{question_id}", response_model=QuestionUpdate)
async def update_question(
    question_id: uuid.UUID, 
    question_data: QuestionUpdate, 
    token: JWTLectureTokenPayload = Depends(require_token_types(allowed_types=["cognito", "service_api"])), 
    db: Session = Depends(get_db)
):
    updated_question = update_question_by_id(db=db, question_id=question_id, question_data=question_data)
    if updated_question is None:
        raise HTTPException(status_code=404, detail="Question not found")
    return updated_question

@app.delete("/questions/{question_id}")
async def delete_question(
    question_id: uuid.UUID, 
    token: JWTLectureTokenPayload = Depends(require_token_types(allowed_types=["cognito", "service_api"])), 
    db: Session = Depends(get_db)
):
    try:
        question = get_question_by_id(db, str(question_id))
        if not question:
            raise HTTPException(status_code=404, detail="Question not found")

        # Delete the question
        delete_question_by_id(db, str(question_id))

        return {"message": "Question deleted successfully"}

    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))  

@app.delete("/exam/{request_id}")
async def delete_exam(
    request_id: uuid.UUID,
    token: JWTLectureTokenPayload = Depends(require_token_types(allowed_types=["cognito", "service_api"])),
    db: Session = Depends(get_db)
):
    user_id = get_user_by_cognito_id(db, token.sub).id

    try:
        # Get the request and verify that the user has access to it
        request = get_request_by_id(db, request_id, user_id)
        if not request:
            raise HTTPException(status_code=404, detail="Examen no encontrado.")
        
        # Delete the request and all its associated data (questions, analytics, etc.)
        deleted = delete_request_by_id(db, request_id)
        if not deleted:
            raise HTTPException(status_code=404, detail="Examen no encontrado.")

        return {"message": "Examen eliminado exitosamente"}

    except HTTPException as e:
        raise e
    
    except Exception as e:
        ic(f"Error inesperado en delete_exam endpoint: {e}")
        raise HTTPException(status_code=500, detail="An unexpected error occurred.")

@app.post("/upload-pdf/")
async def upload_pdf(
    file: UploadFile = File(...),
    llm_id: Optional[str] = Form(None),
    token: JWTLectureTokenPayload = Depends(require_token_types(allowed_types=["cognito"])),
    db: Session = Depends(get_db)
):
    try:
        start_time = time.time()
        # Extract text using the async function from common.py
        pdf_text = await extract_text_from_data(file)
        if not pdf_text:
            raise HTTPException(status_code=400, detail="Could not extract text from PDF")

        # Process the extracted text
        doc_id = store_parsed_document(pdf_text)
        language = detect_language(pdf_text)
        prompt = build_summary_prompt(pdf_text, language)
        response, summary, title = await generate_summary_and_title(prompt)

        # Save to database
        user_id = get_user_by_cognito_id(db, token.sub).id
        request_id = handle_save_request(db, title, user_id, "content_query_service")
        save_summary(db, request_id, doc_id, summary)

        
        session_data = get_session_data(str(request_id))
        session_data['document_summary'] = summary

        processing_time = time.time() - start_time
        await process_and_save_analytics(db, request_id, 'default' , prompt, response, processing_time)

        return {
            "title": title,
            "request_id": request_id,
            "doc_id": doc_id,
            "summary": summary
        }

    except ValueError as ve:
        logger.warning(f"ValueError during /upload-pdf/: {ve}")
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        logger.exception(f"Unhandled exception during /upload-pdf/: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/upload-url/")
async def upload_url(
    request: UploadRequest,
    token: JWTLectureTokenPayload = Depends(require_token_types(allowed_types=["cognito"])), 
    db: Session = Depends(get_db)
):
    try:
        start_time = time.time()
        website_text = await extract_text_from_url(request.url)
        doc_id = store_parsed_document(website_text)
        
        language = detect_language(website_text)
        prompt = build_summary_prompt(website_text, language)
        response, summary, title = await generate_summary_and_title(prompt)
        
        user_id = get_user_by_cognito_id(db, token.sub).id
        request_id = handle_save_request(db, title, user_id, "content_query_service")

        save_summary(db, request_id, doc_id, summary)
        processing_time = time.time() - start_time
        await process_and_save_analytics(db, request_id, 'default' , prompt, response, processing_time)

        return {"title": title, "request_id": request_id, "doc_id": doc_id, "summary": summary}

    except Exception as e:
        logger.exception(f"Unhandled exception during /upload-url/: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/ask-question/{doc_id}/")
async def ask_question(
    doc_id: str,
    question: str = Form(...),
    llm_id: Optional[str] = Form(None),
    token: JWTLectureTokenPayload = Depends(require_token_types(allowed_types=["cognito"])),
    db: Session = Depends(get_db)
):
    try:
        start_time = time.time()
        try:
            validated_doc_id = str(uuid.UUID(doc_id))
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid document ID format")

        request_id = get_request_id_by_document(db, validated_doc_id)
        if not request_id:
            raise HTTPException(status_code=404, detail="Document not found")

        session_data = get_session_data(str(request_id))
        summary = session_data.get('document_summary')

        if not summary:
            summary = get_summary(db, validated_doc_id)
            if not summary:
                raise HTTPException(status_code=404, detail="Summary not found")

            session_data['document_summary'] = summary

        # Sanitize question input
        sanitized_question = re.sub(r'[^\w\s\?\.,]', '', question)

        prompt = (
            "Human: Please answer the following question about the document:\n\n"
            f"Document:\n{summary}\n\n"
            f"Question: {sanitized_question}\n\n"
            "Assistant:"
        )

        ic("Using Bedrock for completion")
        response = await invoke_bedrock_model(prompt, llm_id)
        processing_time = time.time() - start_time
        await process_and_save_analytics(db, request_id, llm_id, prompt, response, processing_time)

        return {"question": sanitized_question, "answer": response}

    except HTTPException as he:
        raise he
    except Exception as e:
        ic(f"Error processing question: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/transcribe")
async def transcribe(
    youtube_url: Optional[str] = Form(None),
    file: Optional[UploadFile] = File(None),
    language_code: Optional[str] = Form(None),
    async_processing: bool = Form(default=False),
    token: JWTLectureTokenPayload = Depends(require_token_types(allowed_types=["cognito", "service_api"])),
    db: Session = Depends(get_db),
    background_tasks: BackgroundTasks = None
):
    duration_limit = 600

    try:
        start_time = time.time()
        if youtube_url:
            audio_path, title = await download_youtube_audio(youtube_url)
        elif file:
            audio_path, title = await handle_uploaded_file(file)
        else:
            raise HTTPException(status_code=400, detail="No valid input provided.")
        
        audio_duration = get_audio_duration(audio_path)
        if (audio_duration > duration_limit):
            raise HTTPException(status_code=400, detail="Audio duration exceeds 10 minutes.")

        s3_key = f'audio/{uuid.uuid4()}.mp3'
        s3_uri = upload_to_s3('audio', audio_path, s3_key)

        user_id = get_user_by_cognito_id(db, token.sub).id
        request_id = handle_save_request(db, title, user_id, "transcription_service")

        transcription_job_name = f'transcription-{uuid.uuid4()}'
        response = start_transcription(s3_uri, transcription_job_name, language_code)

        save_transcription_to_db(
            db=db,
            job_name=transcription_job_name,
            s3_uri=s3_uri,
            language_code=language_code,
            status=response['TranscriptionJob']['TranscriptionJobStatus'],
            request_id=request_id
        )
        processing_time = time.time() - start_time
        await process_and_save_analytics(db, request_id, 'transcribe', '', response, processing_time, {}, 'audio')

        if async_processing and token.token_type != "service_api":
            # Asynchronous processing with BackgroundTasks
            if not background_tasks:
                raise HTTPException(status_code=500, detail="BackgroundTasks not available for asynchronous processing")
            
            # Start asynchronous processing
            background_tasks.add_task(
                _process_transcription_async,
                transcription_job_name=transcription_job_name,
                user_id=user_id,
                title=title,
                request_id=request_id
            )
            
            return {"title": title, "job_name": transcription_job_name, "status": "PROCESSING", "async": True}
        else:
            # Synchronous processing (original behavior)
            return {"title": title, "job_name": transcription_job_name, "status": response['TranscriptionJob']['TranscriptionJobStatus']}
    
    except HTTPException as he:
        raise he
    except Exception as e:
        # Log the detailed error
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Internal Server Error: {str(e)}")


async def _process_transcription_async(transcription_job_name: str, user_id: str, title: str, request_id: str):
    """
    Asynchronous function to process the transcription and send notifications
    """
    db = SessionLocal()
    app_sync = AsyncManager()
    app_sync.set_parameters()
    
    try:
        # Notify start of processing
        await app_sync.send_event_with_notification(
            db=db,
            user_id=str(user_id),
            service_id="transcriber_generation",
            title="transcriber_generation.processing.title",
            body="transcriber_generation.processing.body",
            data={
                "job_name": transcription_job_name,
                "title": title,
                "request_id": str(request_id),
                "stage": "processing"
            },
            notification_type="info",
            priority="normal"
        )

        # Loop to check the status of the transcription
        max_attempts = 60  # Maximum 5 minutes (60 * 5 seconds)
        attempt = 0
        
        while attempt < max_attempts:
            try:
                # Verify the status of the transcription
                status_response = await get_transcription_status(db, transcription_job_name)
                
                if status_response.get('status') == 'COMPLETED':
                    # Transcription completed successfully
                    await app_sync.send_event_with_notification(
                        db=db,
                        user_id=str(user_id),
                        service_id="transcriber_generation",
                        title="transcriber_generation.completed.title",
                        body="transcriber_generation.completed.body",
                        data={
                            "job_name": transcription_job_name,
                            "title": title,
                            "request_id": str(request_id),
                            "transcript_id": str(status_response.get('transcript_id')),
                            "stage": "completed"
                        },
                        notification_type="success",
                        priority="normal",
                        actions=[
                            {
                                "label": "notifications.buttons.view",
                                "action": "navigate",
                                "url": f"/transcript/{status_response.get('transcript_id')}"
                            }
                        ]
                    )
                    break
                elif status_response.get('status') == 'FAILED':
                    # Transcription failed
                    await app_sync.send_event_with_notification(
                        db=db,
                        user_id=str(user_id),
                        service_id="transcriber_generation",
                        title="transcriber_generation.error.title",
                        body="transcriber_generation.error.body",
                        data={
                            "job_name": transcription_job_name,
                            "title": title,
                            "request_id": str(request_id),
                            "stage": "error",
                            "error": "Transcription job failed"
                        },
                        notification_type="error",
                        priority="high"
                    )
                    break
                else:
                    # Transcription still in progress, wait before checking again
                    await asyncio.sleep(5)  # Wait 5 seconds
                    attempt += 1
                    
            except Exception as e:
                # Error verifying the status
                await app_sync.send_event_with_notification(
                    db=db,
                    user_id=str(user_id),
                    service_id="transcriber_generation",
                    title="transcriber_generation.error.title",
                    body="transcriber_generation.error.body",
                    data={
                        "job_name": transcription_job_name,
                        "title": title,
                        "request_id": str(request_id),
                        "stage": "error",
                        "error": str(e)
                    },
                    notification_type="error",
                    priority="high"
                )
                break
        
        # If the attempts are exhausted, notify timeout
        if attempt >= max_attempts:
            await app_sync.send_event_with_notification(
                db=db,
                user_id=str(user_id),
                service_id="transcriber_generation",
                title="transcriber_generation.timeout.title",
                body="transcriber_generation.timeout.body",
                data={
                    "job_name": transcription_job_name,
                    "title": title,
                    "request_id": str(request_id),
                    "stage": "timeout"
                },
                notification_type="warning",
                priority="normal"
            )
            
    except Exception as e:
        # General error in asynchronous processing
        try:
            await app_sync.send_event_with_notification(
                db=db,
                user_id=str(user_id),
                service_id="transcriber_generation",
                title="transcriber_generation.error.title",
                body="transcriber_generation.error.body",
                data={
                    "job_name": transcription_job_name,
                    "title": title,
                    "request_id": str(request_id),
                    "stage": "error",
                    "error": str(e)
                },
                notification_type="error",
                priority="high"
            )
        except Exception as notification_error:
            # If the notification fails, only log the error
            ic(f"Error sending notification: {str(notification_error)}")
    finally:
        # Close the database connection
        db.close()


async def _process_exam_generation_async(
    title: str,
    source_text: str,
    number_mcq: int,
    number_tfq: int,
    number_open: int,
    custom_instructions: Optional[str],
    llm_id: Optional[str],
    user_id: str,
    request_id: str
):
    """
    Asynchronous function to process exam generation and send notifications
    """
    db = SessionLocal()
    app_sync = AsyncManager()
    app_sync.set_parameters()
    
    try:
        # Notify start of processing
        await app_sync.send_event_with_notification(
            db=db,
            user_id=str(user_id),
            service_id="exam_generation",
            title="exam_generation.processing.title",
            body="exam_generation.processing.body",
            data={
                "title": title,
                "request_id": str(request_id),
                "stage": "processing"
            },
            notification_type="info",
            priority="normal"
        )

        # Generate prompt and get relevant content
        relevance_prompt = build_key_points_prompt(source_text)
        relevance_response = await invoke_bedrock_model(relevance_prompt, llm_id)
        relevant_source = relevance_response
        ic(f"Relevant source: {relevant_source}")

        # Build prompt and generate questions
        prompt = build_prompt_document(number_mcq, number_tfq, number_open, relevant_source, custom_instructions)
        ic("Building prompt completed")

        response = await invoke_bedrock_model(prompt, llm_id)
        ic(f"Response: {response}")
        
        formatted_response = clean_raw_data(response)

        # Save questions to the existing request
        saved_data = save_questions_to_existing_request(db, request_id, formatted_response)
        
        # Notify successful completion
        await app_sync.send_event_with_notification(
            db=db,
            user_id=str(user_id),
            service_id="exam_generation",
            title="exam_generation.completed.title",
            body="exam_generation.completed.body",
            data={
                "title": title,
                "request_id": str(request_id),
                "questions_count": len(saved_data['questions']),
                "stage": "completed"
            },
            notification_type="success",
            priority="normal",
            actions=[
                {
                    "label": "notifications.buttons.view",
                    "action": "navigate",
                    "url": f"/request/{request_id}"
                }
            ]
        )
            
    except Exception as e:
        # General error in asynchronous processing
        try:
            await app_sync.send_event_with_notification(
                db=db,
                user_id=str(user_id),
                service_id="exam_generation",
                title="exam_generation.error.title",
                body="exam_generation.error.body",
                data={
                    "title": title,
                    "request_id": str(request_id),
                    "stage": "error",
                    "error": str(e)
                },
                notification_type="error",
                priority="high"
            )
        except Exception as notification_error:
            # If the notification fails, only log the error
            ic(f"Error sending notification: {str(notification_error)}")
    finally:
        # Close the database connection
        db.close()


@app.get("/transcription-status/{job_name}")
async def check_transcription_status(
    job_name: str, 
    token: JWTLectureTokenPayload = Depends(require_token_types(allowed_types=["cognito", "service_api"])), 
    db: Session = Depends(get_db)
):
    try:
        response = await get_transcription_status(db, job_name)
        if response.get('completed_at'):
            analytics = get_analytics_by_request_id(db, response['request_id'])
            if analytics and analytics.created_at:
                # Convert completed_at from ISO string to datetime if it's a string
                completed_at = response['completed_at']
                if isinstance(completed_at, str):
                    completed_at = datetime.fromisoformat(completed_at)
                # Calculate processing time as completion time minus creation time
                processing_time = (completed_at - analytics.created_at).total_seconds()
                await process_and_save_analytics(
                    db=db, 
                    request_id=response['request_id'], 
                    model='transcribe', 
                    request_prompt='', 
                    response=response, 
                    processing_time=processing_time, 
                    response_type='audio', 
                    reference="transcription_status"
                )

        return response
    except Exception as e:
        raise HTTPException(status_code=404, detail=str(e))
    

@app.get("/transcription-history")
async def get_user_requests(
    token: JWTLectureTokenPayload = Depends(require_token_types(allowed_types=["cognito", "service_api"])),
    db: Session = Depends(get_db)
):
    user_id = get_user_by_cognito_id(db, token.sub).id
    service_id = get_service_id_by_code(db, "transcription_service")

    requests = get_requests_by_user_service(db, user_id, service_id)

    if not requests:
        raise HTTPException(status_code=404, detail="No requests found for this user.")

    response_data = []
    
    for request in requests:
        transcript = get_transcript_by_request_id(db, request.id)
        
        if transcript:
            response_data.append({
                "id": transcript.id,
                "title": request.title,
                "transcription_text": transcript.transcription_text,
                "status": transcript.status,
                "completed_at": transcript.completed_at
            })
    
    response_data.sort(key=lambda x: x["completed_at"] or datetime.max, reverse=True)
    
    return response_data

@app.get("/transcript/{id}")
async def get_transcript(
    id: uuid.UUID,
    token: JWTLectureTokenPayload = Depends(require_token_types(allowed_types=["cognito", "service_api"])),
    db: Session = Depends(get_db)
):
    user_id = get_user_by_cognito_id(db, token.sub).id

    try:
        transcript = get_transcript_by_id(db, id)
        if not transcript:
            raise HTTPException(status_code=404, detail="Transcript not found.")
        
        request = get_request_by_id(db, transcript.request_id, user_id)
        if not request:
            raise HTTPException(status_code=403, detail=ACCESS_DENIED_MESSAGE)

        audio_url = generate_presigned_url('audio', transcript.s3_uri) if transcript.s3_uri else None

        return {
            "id": transcript.id,
            "title": request.title,
            "transcription_text": transcript.transcription_text,
            "status": transcript.status,
            "job_name": transcript.job_name,
            "completed_at": transcript.completed_at,
            "audioUrl": audio_url,
            "language_code": transcript.language_code,
            "summary": transcript.summary,
        }
    
    except HTTPException as e:
        raise e
    
    except Exception as e:
        ic(f"Unexpected error in get_transcript endpoint: {e}")
        raise HTTPException(status_code=500, detail="An unexpected error occurred.")

@app.delete("/transcript/{id}")
async def delete_transcript(
    id: uuid.UUID,
    token: JWTLectureTokenPayload = Depends(require_token_types(allowed_types=["cognito", "service_api"])),
    db: Session = Depends(get_db)
):
    user_id = get_user_by_cognito_id(db, token.sub).id

    try:
        # Get the transcript
        transcript = get_transcript_by_id(db, id)
        if not transcript:
            raise HTTPException(status_code=404, detail="Transcript not found.")
        
        # Verify that the user has access to the transcript
        request = get_request_by_id(db, transcript.request_id, user_id)
        if not request:
            raise HTTPException(status_code=403, detail=ACCESS_DENIED_MESSAGE)

        # Delete the audio file from S3 if it exists
        if transcript.s3_uri:
            try:
                await delete_from_s3('audio', transcript.s3_uri)
            except Exception as e:
                ic(f"Error deleting file from S3: {e}")
                # Continue with the deletion of the database even if S3 fails

        # Delete the transcript from the database
        deleted = delete_transcript_by_id(db, id)
        if not deleted:
            raise HTTPException(status_code=404, detail="Transcript not found.")

        return {"message": "Transcript deleted successfully"}

    except HTTPException as e:
        raise e
    
    except Exception as e:
        ic(f"Unexpected error in delete_transcript endpoint: {e}")
        raise HTTPException(status_code=500, detail="An unexpected error occurred.")

@app.post("/summarize")
async def summarize(request: SummarizeRequest,
                    db: Session = Depends(get_db),
                    token: JWTLectureTokenPayload = Depends(require_token_types(allowed_types=["cognito", "service_api"])),
):
    try:
        start_time = time.time()
        user_id = get_user_by_cognito_id(db, token.sub).id
        transcript_id = get_transcript_by_id(db, request.transcript_id)
        transcription_request = get_request_by_id(db, transcript_id.request_id, user_id)
        
        if user_id != transcription_request.user_id:
            raise HTTPException(status_code=403, detail="Access denied")
        
        prompt = build_summary_prompt(request.transcript, request.language)

        response = await invoke_bedrock_model(prompt)
        summary = response

        updated_transcript = update_transcript_summary(db, request.transcript_id, summary)

        processing_time = time.time() - start_time
        await process_and_save_analytics(db=db, request_id=transcription_request.id, model='default', request_prompt=prompt, response=response, processing_time=processing_time, reference="summary")

        if not updated_transcript:
            raise HTTPException(status_code=404, detail="Transcript not found")

        return {"data": summary}
    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/agent-exam/")
async def agent_exam(
    course_id: str = Form(...),
    file: Optional[UploadFile] = File(None),
    number_mcq: int = Form(...),
    number_tfq: int = Form(...),
    number_open: int = Form(...),
    custom_instructions: Optional[str] = Form(None),
    materials: Optional[str] = Form(None),
    llm_id: Optional[str] = Form(None),
    token: JWTLectureTokenPayload = Depends(require_token_types(allowed_types=["cognito"])),
    db: Session = Depends(get_db)
):
    try:
        # Create an asynchronous task for processing
        async def process_exam():
            start_time1 = time.time()
            file_path = None
            if file:
                with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as temp_file:
                    file_path = temp_file.name
                async with aiofiles.open(file_path, "wb") as f:
                    await f.write(await file.read())

            # Get course and user data asynchronously
            course = await asyncio.to_thread(get_course_by_id, db, course_id)
            user = await asyncio.to_thread(get_user_by_cognito_id, db, token.sub)
            kbid = course.knowledge_base_id
            s3_uris = []

            if user.id != course.teacher_id:
                raise HTTPException(status_code=403, detail=ACCESS_DENIED_MESSAGE)

            # Process materials asynchronously
            materials_list = []
            if materials:
                materials_ids = materials.split(",")
                if materials_ids:
                    materials_list = await asyncio.to_thread(get_materials_by_id, db, materials_ids)
                    s3_uris = [
                        material.transcription_s3_uri 
                        if material.type.startswith(('audio', 'video')) or ('epub' in material.type) 
                        else material.s3_uri
                        for material in materials_list
                    ]
                
            relevant_text = None
            if file_path:
                source_text = await extract_text_from_pdf(file_path)
                relevance_prompt = build_key_points_prompt(source_text)
                model_id = 'anthropic.claude-3-7-sonnet-20250219-v1:0'
                
                response = await asyncio.to_thread(
                    retrieve_and_generate,
                    prompt=relevance_prompt, 
                    kb_id=kbid,
                    model_id=model_id
                )
                relevant_text = response.get("text")
                
            processing_time1 = time.time() - start_time1

            start_time2 = time.time()

            # Get existing questions asynchronously
            questions_data = await asyncio.to_thread(
                lambda: get_questions_by_course_id(db, course_id).get("questions", [])
            )
            questions = ",\n".join(questions_data) if questions_data else ""

            prompt = build_prompt_agent(number_tfq, number_mcq, number_open, custom_instructions, questions)
            
            text_input = "Generate exam questions based on the provided text."
            if file_path and relevant_text:
                text_input = f"Generate exam questions based on the search results and the following text between <source></source> tags:\n\n<source>{relevant_text}</source>"

            # Generate questions asynchronously
            response = await asyncio.to_thread(
                retrieve_and_generate,
                prompt=prompt, 
                kb_id=kbid,
                model_id=llm_id,
                text_input=text_input,
                files=s3_uris
            )
            text_response = response.get("text")
            json_response = clean_raw_data(text_response)
            
            if not json_response or json_response == "\"\"":
                return JSONResponse(content={"error": text_response})
            
            user_id = user.id
            service_id = await asyncio.to_thread(get_service_id_by_code, db, "questions_generator_service")
            
            data = {
                'title': f"Knowledge base: {kbid}",
                'user_id': user_id,
                'questions': json_response,
                'service_id': str(service_id),
                'course_id': str(course_id),
                'llm': llm_id if llm_id else get_default_model_ids()["claude"],
            }
            
            # Save data asynchronously
            saved_data = await asyncio.to_thread(save_request_and_questions, db, data)
            
            # Process analytics asynchronously
            if file_path:
                await process_and_save_analytics(
                    db=db, 
                    request_id=saved_data['request']['id'], 
                    model='default', 
                    request_prompt=relevance_prompt, 
                    response=relevant_text, 
                    processing_time=processing_time1, 
                    reference="relevance"
                )

            processing_time = time.time() - start_time2
            await process_and_save_analytics(
                db=db, 
                request_id=saved_data['request']['id'], 
                model=data['llm'], 
                request_prompt=prompt, 
                response=text_response, 
                processing_time=processing_time
            )

            return JSONResponse(content={
                "title": saved_data['request']['title'],
                "questions": saved_data['questions']
            })

        # Start background processing
        return await process_exam()

    except HTTPException as http_exception:
        raise http_exception
    except Exception as exception:
        ic(f"Error in agent-exam endpoint: {exception}")
        raise HTTPException(status_code=500, detail="Failed to generate questions from the knowledge base.") from exception


@app.post("/ask-agent/{course_id}/")
async def ask_agent(
    course_id: str,
    question: str = Form(...),
    materials: Optional[str] = Form(None),
    llm_id: Optional[str] = Form(None),
    token: JWTLectureTokenPayload = Depends(require_token_types(allowed_types=["cognito", "service_api"])),
    db: Session = Depends(get_db)
):
    try:
        # Create an asynchronous task for processing
        async def process_agent_question():
            start_time = time.time()
            
            # Get user and course data asynchronously
            user = await asyncio.to_thread(get_user_by_cognito_id, db, token.sub)
            course = await asyncio.to_thread(get_course_by_id, db, course_id)
            
            if user.id != course.teacher_id:    
                raise HTTPException(status_code=403, detail=ACCESS_DENIED_MESSAGE)

            # Process materials asynchronously
            s3_uris = []
            if materials:
                materials_ids = materials.split(",")
                if materials_ids:
                    materials_list = await asyncio.to_thread(get_materials_by_id, db, materials_ids)
                    s3_uris = [
                        material.transcription_s3_uri 
                        if material.type.startswith(('audio', 'video')) or ('epub' in material.type) 
                        else material.s3_uri
                        for material in materials_list
                    ]

            prompt = (
                "Human: Please answer the following question about the content in the knowledge base:\n\n"
                f"Course: {course.title}\n\n"
                f"Question: {question}\n\n"
                "Assistant:"
            )
            
            model_id = llm_id if llm_id else "anthropic.claude-instant-v1"
            
            # Generate response asynchronously
            response = await asyncio.to_thread(
                retrieve_and_generate,
                prompt=prompt, 
                kb_id=course.knowledge_base_id,
                model_id=model_id,
                files=s3_uris
            )
            
            # Save request asynchronously
            request_id = await asyncio.to_thread(
                handle_save_request,
                db=db,
                title="Agent Question",
                user_id=user.id,
                service_code="knowledge_base_chat_service"
            )

            processing_time = time.time() - start_time
            
            # Process analytics asynchronously
            await process_and_save_analytics(
                db=db,
                request_id=request_id,
                model=model_id,
                request_prompt=prompt,
                response=response["text"],
                processing_time=processing_time
            )
            
            return {
                "question": question,
                "answer": response["text"],
                "citation": response["contexts"],
            }

        # Start processing in the background
        return await process_agent_question()

    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e

@app.post("/process_text")
async def process_text(
    request: TextActionRequest,
    token: JWTLectureTokenPayload = Depends(require_token_types(allowed_types=["cognito", "service_api"])),
    db: Session = Depends(get_db)
):
    start_time = time.time()
    user = get_user_by_cognito_id(db, token.sub)
    
    action_prompts = {"summarize": "Summarize", "expand": "Expand on", "rephrase": "Rephrase", "format": "Format"}
    if request.action not in action_prompts:
        raise HTTPException(status_code=400, detail="Invalid action type")

    ic(f"Received action: {request.action}")

    selected_text = get_selected_text(request.text, request.start_index, request.end_index)
    if (selected_text):
        ic(f"Selected text: '{selected_text}'")
        
    if request.llm_id == "" or request.llm_id is None:
        request.llm_id = get_default_model_ids()["claude"]

    prompt = build_text_processing_prompt(
        request.action, 
        request.tones, 
        request.audiences, 
        request.text, 
        selected_text
    )
    ic(f"Generated prompt: {prompt}")

    try:
        response_text = await invoke_bedrock_model(prompt, request.llm_id)
        ic(f"Response from Bedrock: {response_text}")
    except Exception as e:
        message = str(e)
        ic(f"A client error occurred: {message}")
        if "Too many requests" in message or "__init__() missing 1 required positional argument" in message:
            raise HTTPException(status_code=429, detail="Too many requests. Please wait before trying again.")
        raise HTTPException(status_code=500, detail=f"Claude invocation failed: {message}")

    match = re.search(r"<response>(.*?)</response>", response_text, re.DOTALL)
    generated_text = match.group(1).strip() if match else response_text
    ic(f"Generated text after regex match: '{generated_text}'")

    if selected_text:
        result = replace_selected_text(request.text, request.start_index - 1, request.end_index - 1, generated_text)
        ic(f"Modified text: '{result}'")
    else:
        result = generated_text
        ic("No selected text; returning generated text as response.")

    request_id = handle_save_request(db, "Agent Question", user.id, "ai_rich_text_editor_service")

    processing_time = time.time() - start_time
    await process_and_save_analytics(db=db, request_id=request_id, model=request.llm_id, request_prompt=prompt, response=response_text, processing_time=processing_time)

    return {"response": result}

@app.get("/models")
async def get_models(
    input_modality: Optional[str] = None,
    output_modality: Optional[str] = None,
    category: Optional[str] = None,
    supports_knowledge_base: Optional[bool] = None,
    all_models: Optional[bool] = False,
    token: JWTLectureTokenPayload = Depends(require_token_types(allowed_types=["cognito"])),
    db: Session = Depends(get_db)
):
    try:
        user = get_user_by_cognito_id(db, token.sub)
        available_models = get_available_models_for_user(db, user)

        user_group: Group = user.group
        region: Region = user_group.region

        models: List[AIModel] = []

        if all_models:
            if user.role != UserRole.admin:
                raise HTTPException(status_code=403, detail="Access denied")
            models = available_models
        else:
            # If no filters are provided, return the cached default models
            if not any([input_modality, output_modality, category, supports_knowledge_base]):
                default_models = []
                default_ids = get_default_model_ids(region.name)
                
                for model_id in default_ids.values():
                    if model_id:  # Check if model_id is not None
                        model = get_ai_model_by_id(db, model_id)
                        if model:
                            default_models.append(model)
                            
                models = default_models
            else:
                # If filters are provided, use the database query
                models = get_ai_models_by_filters(
                    db,
                    input_modality=input_modality,
                    output_modality=output_modality,
                    supports_knowledge_base=supports_knowledge_base,
                    category=category,
                    region=region.name
                )

        if not models:
            raise HTTPException(status_code=404, detail="No models found matching the criteria")
        
        allowed_models = [model for model in models if model in available_models]
        if not allowed_models:
            raise HTTPException(status_code=403, detail="No allowed models found for the user")

        return {"models": [
            {
                **model_to_dict(model),
                "region_name": model.region.name,
                "region_suffix": model.region.suffix
            }
            for model in allowed_models
        ]}
    except HTTPException as he:
        raise he
    except Exception as e:
        print(f"Error: {e}")
        raise HTTPException(status_code=500, detail=f"Error retrieving models: {str(e)}")

@app.get("/services")
async def get_available_services(
    token: JWTLectureTokenPayload = Depends(require_token_types(allowed_types=["cognito"])),
    db: Session = Depends(get_db)
):
    try:
        user = get_user_by_cognito_id(db, token.sub)
        services = get_available_services_for_user(db, user)
        if not services:
            raise HTTPException(status_code=404, detail="No services found")
        return {"services": services}
    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error retrieving services: {str(e)}")
    
@app.get("/agents")
async def agents(
    db: Session = Depends(get_db)
):
    agents = await get_agents(db)
    return {"agents": agents}

@app.post("/agent-chatbot/")
async def agent_chatbot(
    request: AgentCreate,
    db: Session = Depends(get_db)
):
    try:
        agent = Agent(
            code=request.code,
            name=request.name,
            description=request.description,
            agent_id=request.agent_id,
            alias_id=request.alias_id
        )
        db.add(agent)
        db.commit()
        db.refresh(agent)
        return agent
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error creating agent: {str(e)}")


@app.post("/export-questions")
async def export_questions_to_s3(
    request: ExportQuestionsRequest,
    token: JWTLectureTokenPayload = Depends(require_token_types(allowed_types=["cognito"])),
    db: Session = Depends(get_db)
):
    try:
        # Get S3 integration details from database
        s3_integration = await get_third_party_integration_by_service(db, "s3")
        if not s3_integration or not s3_integration.service_value:
            raise HTTPException(
                status_code=500,
                detail="S3 configuration not found in database"
            )

        # service_value is already a dictionary, no need for json.loads
        s3_config = s3_integration.service_value
        bucket = s3_config.get("bucket_name")
        region = s3_config.get("region")

        if not bucket or not region:
            raise HTTPException(
                status_code=400,
                detail="Invalid S3 configuration: missing bucket_name or region"
            )

        # Get available buckets and validate bucket name
        available_buckets = await get_s3_buckets()
        if bucket not in available_buckets:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid bucket name: {bucket}"
            )

        # Debug logging
        ic(f"Received question_ids: {request.question_ids}")

        # Ensure question_ids are UUIDs
        try:
            question_ids = [uuid.UUID(str(qid)) for qid in request.question_ids]
        except ValueError as e:
            raise HTTPException(status_code=400, detail=f"Invalid question ID format: {str(e)}")

        # Get questions by their IDs
        questions = get_questions_by_ids(db, question_ids)
        if not questions:
            raise HTTPException(status_code=404, detail="No questions found")

        # Debug logging
        ic(f"Retrieved questions: {questions}")

        # Convert questions to list of dictionaries
        questions_data = []
        for q in questions:
            try:
                # Ensure options is a list
                if isinstance(q.options, str):
                    try:
                        options = json.loads(q.options)
                    except json.JSONDecodeError:
                        options = []
                else:
                    options = q.options or []

                # Create question dictionary with proper types
                question_dict = {
                    "type": str(q.type),
                    "question": str(q.question),
                    "options": options,
                    "correct_answer": str(q.correct_answer) if q.correct_answer else None,
                    "reason": str(q.reason) if q.reason else None
                }
                questions_data.append(question_dict)
            except Exception as e:
                ic(f"Error processing question {q.id}: {str(e)}")
                continue

        if not questions_data:
            raise HTTPException(status_code=400, detail="No valid questions could be processed")

        # Debug logging
        ic(f"Processed questions data: {questions_data}")

        # Convert questions to GIFT format
        gift_content = convert_to_gift(questions_data)

        # Generate filename with timestamp for sorting
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        file_name = f"{timestamp}_questions.gift"

        with open(file_name, "w") as file:
            file.write(gift_content)

        try:
            # Define the S3 key
            s3_key = f"questions/{file_name}"
            # Upload the file to S3 using configuration from database
            s3_uri = await upload_file_to_s3(bucket, file_name, s3_key)
            return {"s3_uri": s3_uri}
        finally:
            # Remove the local file after upload, even if upload fails
            if os.path.exists(file_name):
                os.remove(file_name)

    except HTTPException as http_exception:
        raise http_exception
    except Exception as exception:
        ic(f"Error in export_questions_to_s3: {str(exception)}")
        raise HTTPException(
            status_code=500, detail=f"Internal Server Error: {str(exception)}"
        )


@app.post("/api/chat-old")
async def lti_chat_old(
    request: Request,
    db: Session = Depends(get_db),
    lti_session_params: LTIServicesTokenPayload = Depends(require_token_types(allowed_types=["lti_services"]))
):
    try:
        logger.info(f"LTI session params received: {lti_session_params}")
        
        # Get and validate request data
        data = await request.json()
        logger.info(f"Request data: {data}")
        
        # Validate required fields
        if not data.get('message'):
            raise HTTPException(status_code=400, detail="Message is required")
        
        # Extract user information
        user_id = data.get('user_id')
        user_name = data.get('user_name')
        user_email = data.get('user_email')
        
        logger.info(f"User info - ID: {user_id}, Name: {user_name}, Email: {user_email}")
        
        course_id = lti_session_params.course_id
        logger.info(f"Course ID from session: {course_id}")
        logger.info(f"Course ID type: {type(course_id)}")
        
        if not course_id:
            raise HTTPException(status_code=422, detail="Course ID is required in LTI session")
        
        # The course_id should now be the UUID selected during deep link creation
        logger.info(f"Looking for course with UUID: {course_id}")
        
        try:
            course_uuid = uuid.UUID(course_id) if isinstance(course_id, str) else course_id
            logger.info(f"Course UUID: {course_uuid}")
            
            course = get_course_by_id(db, course_uuid)
            logger.info(f"Course found: {course}")
            
            if not course:
                raise HTTPException(status_code=404, detail=f"Course with ID {course_id} not found")
                
        except ValueError as e:
            logger.error(f"Invalid UUID format: {e}")
            raise HTTPException(status_code=422, detail=f"Invalid course ID format: {course_id}")
        
        kb_id = course.knowledge_base_id
        logger.info(f"Knowledge base ID: {kb_id}")
        
        # Build user context for the prompt
        user_context = ""
        if user_name:
            user_context += f"User: {user_name}"
        if user_email:
            user_context += f" ({user_email})"
        if user_id:
            user_context += f" [ID: {user_id}]"
        
        prompt = (
            "Human: Please answer the following question about the content in the knowledge base:\n\n"
            f"Question: {data['message']}\n\n"
            f"User Context: {user_context}\n\n"
            "Assistant:"
        )
        
        response = retrieve_and_generate(
            prompt=prompt,
            kb_id=kb_id,
            model_id="anthropic.claude-3-7-sonnet-20250219-v1:0"
        )
        
        return {
            "question": data['message'],
            "answer": response["text"],
            "citation": response["contexts"]
        }
        
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON data")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/chat")
async def lti_chat(
    request: Request,
    db: Session = Depends(get_db),
    lti_session_params: LTIServicesTokenPayload = Depends(require_token_types(allowed_types=["lti_services"]))
):
    """Endpoint principal de chat LTI: crea/busca chatbot por user_id y charla."""
    try:
        logger.info(f"LTI session params received: {lti_session_params}")
        logger.info(f"Request received: {request}")
        # Get and validate request data
        data = await request.json()
        
        course_id = lti_session_params.course_id
        message = data.get('message')
        lms_user_id = int(lti_session_params.sub)
        lms_url = lti_session_params.iss

        if not message:
            raise HTTPException(status_code=400, detail="message is required")
        if not course_id:
            raise HTTPException(status_code=400, detail="course_id is required")
        if not lms_user_id:
            raise HTTPException(status_code=400, detail="lms_user_id is required")
        if not lms_url:
            raise HTTPException(status_code=400, detail="lms_url is required")

        try:
            course_uuid = uuid.UUID(course_id) if isinstance(course_id, str) else course_id
        except ValueError:
            raise HTTPException(status_code=422, detail=f"Invalid course ID format: {course_id}")

        saved_chatbot_id = data.get("chatbot_id")

        if saved_chatbot_id is not None:
            chatbot_id = saved_chatbot_id
        else:
            course = get_course_by_id(db, course_uuid)
            if not course:
                raise HTTPException(status_code=404, detail=f"Course with ID {course_id} not found")

            lti_config = {
                "lms_user_id": lms_user_id,
                "lms_url": lms_url,
                **lti_session_params.lti_params
            }
            
            # Sanity check before creating a new chatbot
            chatbot = db.query(Chatbot).filter(
                cast(Chatbot.resource_data, JSONB).contains({"resource_id": course.knowledge_base_id,
                                                "resource_type": "knowledge_base_manager"}),
                Chatbot.lti_config.contains(lti_config)
            ).first()

            if chatbot:
                logger.warning(f"Inconsistent state. Chatbot found for the user {lms_user_id}, platform {lms_url} \
                    in course {course_id} with the same lti settings but no previous chatbot_id provided.")
                raise HTTPException(
                    status_code=400, 
                    detail="Inconsistent state. Chatbot found for the user with the same lti settings but no previous chatbot_id provided."
                )
            
            # Consistent state: create a new chatbot.
            chatbot_id = str(uuid.uuid4())
            chatbot_name = "LTI_Chatbot_" + str(course_id)
            resource_data = json.dumps({
                "resource_id": str(course.knowledge_base_id),
                "resource_name": course.title,
                "resource_type": "knowledge_base_manager"
            })

            chatbot_data = {
                "id": chatbot_id,
                "name": chatbot_name,
                "system_prompt": lti_session_params.lti_params.get("system_prompt", 
                    "You are a helpful assistant for course knowledge."),
                # Use the teacher of the course as the user_id
                "user_id": str(course.teacher_id),
                "status": "COMPLETED",
                "session_id": chatbot_id,
                "memory_id": chatbot_id,
                "resource_data": resource_data,
                "lti_config": lti_config
            }

            created_id = await create_chatbot(db, ChatbotCreate(**chatbot_data))
            chatbot: Chatbot = db.query(Chatbot).filter(Chatbot.id == created_id.id).first()
            if not chatbot:
                raise HTTPException(status_code=500, detail="Failed to create chatbot")

            chatbot_id = str(chatbot.id)

        # Send message using ChatbotProcessor and the found/created chatbot
        processor = ChatbotProcessor(db, message)
        await processor.set_agent()
        await processor.set_chatbot(chatbot_id)
        is_external = await processor.check_if_external_chatbot()
        if is_external:
            result = await processor.process_external_conversation()
        else:
            result = await processor.process_conversation()

        return {
            "question": message,
            "answer": result.get("response"),
            "citations": [],
            "chatbot_id": chatbot_id
        }

    except HTTPException:
        raise
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON data")
    except Exception as e:
        logger.error(f"Error in /api/chat: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Internal Server Error: {str(e)}")

@app.post("/quiz/generate")
async def generate_quiz(
    request: Request,
    db: Session = Depends(get_db),
    lti_session_params: LTIServicesTokenPayload = Depends(require_token_types(allowed_types=["lti_services"]))
):
    """Generate quiz questions using the course knowledge base - simplified version for LTI"""
    try:
        # Get and validate request data
        data = await request.json()
        
        # Validate required fields
        topic = data.get('topic')
        if not topic:
            raise HTTPException(status_code=400, detail="Topic is required")
        
        # Get parameters from client request
        content = data.get('content', '')
        num_questions = data.get('num_questions', 10)  # Use client-provided number
        difficulty = data.get('difficulty', 'medium')
        question_type = data.get('question_type', 'mixed')
        
        # Validate num_questions
        if not isinstance(num_questions, int) or num_questions < 1 or num_questions > 20:
            raise HTTPException(status_code=400, detail="Number of questions must be between 1 and 20")
        
        course_id = lti_session_params.course_id
        if not course_id:
            raise HTTPException(status_code=422, detail="Course ID is required in LTI session")
        
        try:
            course_uuid = uuid.UUID(course_id) if isinstance(course_id, str) else course_id
            course = get_course_by_id(db, course_uuid)
            
            if not course:
                raise HTTPException(status_code=404, detail=f"Course with ID {course_id} not found")
                
        except ValueError as e:
            raise HTTPException(status_code=422, detail=f"Invalid course ID format: {course_id}")
        
        kb_id = course.knowledge_base_id
        if not kb_id:
            raise HTTPException(status_code=422, detail="Course does not have a knowledge base configured")
        
        # Map question types to counts
        if question_type == 'multiple_choice':
            mcq_count = num_questions
            tf_count = 0
            open_count = 0
        elif question_type == 'true_false':
            mcq_count = 0
            tf_count = num_questions
            open_count = 0
        elif question_type == 'short_answer':
            mcq_count = 0
            tf_count = 0
            open_count = num_questions
        else:  # mixed
            # Distribute questions: 50% MCQ, 30% TF, 20% Open
            mcq_count = int(num_questions * 0.5)
            tf_count = int(num_questions * 0.3)
            open_count = num_questions - mcq_count - tf_count
        
        # Build prompt for quiz generation
        custom_instructions = f"Focus on {topic}. Difficulty level: {difficulty}."
        if content:
            custom_instructions += f" Additional context: {content}"
        
        prompt = build_prompt_agent(tf_count, mcq_count, open_count, custom_instructions)
        
        text_input = f"Generate {num_questions} quiz questions about {topic}"
        if content:
            text_input += f" based on this additional content: {content}"
        
        # Generate questions using knowledge base
        response = retrieve_and_generate(
            prompt=prompt,
            kb_id=kb_id,
            model_id="anthropic.claude-3-7-sonnet-20250219-v1:0",
            text_input=text_input
        )
        logger.info(f"Response: {response}")
        
        # Parse the response - clean_raw_data returns a list of parsed objects
        try:
            questions = clean_raw_data(response["text"])
            
            if not questions or not isinstance(questions, list):
                raise HTTPException(status_code=500, detail="Failed to generate valid questions")
                
        except Exception as e:
            logger.error(f"Error parsing quiz response: {str(e)}")
            raise HTTPException(status_code=500, detail="Invalid response format from question generator")
        
        # Transform questions to match frontend expectations
        transformed_questions = []
        for q in questions:
            question_type_map = {
                'mcq': 'multiple_choice',
                'tf': 'true_false', 
                'open': 'short_answer'
            }
            
            transformed_q = {
                'question': q.get('question', ''),
                'type': question_type_map.get(q.get('type', 'mcq'), 'multiple_choice'),
                'correct_answer': q.get('correct_answer', ''),
                'explanation': q.get('reason', '')
            }
            
            if q.get('options'):
                transformed_q['options'] = q['options']
                
            transformed_questions.append(transformed_q)
        
        return {
            "topic": topic,
            "questions": transformed_questions,
            "difficulty": difficulty
        }
        
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON data")
    except Exception as e:
        logger.error(f"Quiz generation error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    init_db()
    uvicorn.run(app, host="0.0.0.0", port=8000)
