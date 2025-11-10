# © [2025] EDT&Partners. Licensed under CC BY 4.0.

import asyncio
from datetime import datetime, timedelta, timezone
import os
import shutil
from typing import List
from uuid import UUID
import uuid
from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status, Form, BackgroundTasks
from fastapi.responses import StreamingResponse
from requests import Session
import tempfile
from pathlib import Path
import re
from concurrent.futures import ThreadPoolExecutor
from io import BytesIO

from constants import COURSE_NOT_FOUND_MESSAGE, MATERIAL_NOT_FOUND_MESSAGE, TEACHER_NOT_FOUND_MESSAGE
from database.crud import create_course_in_db, create_invite, create_material, create_user, delete_course, delete_invite, delete_material, delete_materials_by_course, enroll_user_in_course, get_course, get_invitations_by_course, get_invite_by_code, get_material, get_materials_by_course, get_teacher_courses, get_user_by_cognito_id, get_user_by_email, update_course_conversation_access_token, update_course_field, update_course_settings, update_material_status, update_material_transcription_uri, get_regional_bucket
from database.db import get_db
from database.models import Course, Material, User, UserRole, Group, Region
from database.schemas import ConversationAccessToken, CourseCreate, CourseResponse, CourseWithMaterialsResponse, InviteBase, InviteConfirm, InviteCreate, InviteResponse, MaterialCreate, MaterialResponse, PollStateMachineRequest, UserCreate, UserResponse, ChatbotCreate, CourseUpdateSettings
from utility.async_manager import AsyncManager
from utility.auth import require_token_types, verify_user_owner, verify_user_permission
from utility.aws import create_cognito_and_db_user, delete_from_s3, delete_resources, generate_course_questions, generate_course_summary, generate_presigned_url, get_execution_details, get_ingestion_summary, send_invite_email, setup_s3_directory, start_ingestion_job, start_step_function, upload_to_s3, run_preprocessing_job, get_s3_object
from utility.common import parse_failure_reasons, process_epub_file
from utility.pdf_processor import PDFDocumentProcessor
from utility.tokens import JWTLectureTokenPayload
from icecream import ic

# Load environment variables manually
REACT_APP_URL = os.getenv("REACT_APP_URL")

router = APIRouter()

def sanitize_filename(filename):
    """Remove potentially dangerous characters from filename"""
    # Remove path traversal characters and sanitize the filename
    safe_filename = re.sub(r'[^\w\.-]', '_', filename)
    return Path(safe_filename).name

@router.get("/", response_model=List[CourseResponse])
async def get_courses_by_teacher(
    is_kbm: bool = False,
    db: Session = Depends(get_db), 
    token: JWTLectureTokenPayload = Depends(require_token_types(allowed_types=["cognito"]))
    ):
    user_id = token.sub
    teacher = get_user_by_cognito_id(db, user_id)

    ic(user_id)
    ic(teacher)

    if not teacher:
        raise HTTPException(status_code=404, detail=TEACHER_NOT_FOUND_MESSAGE)

    if teacher.role not in [UserRole.teacher, UserRole.admin]:
        raise HTTPException(status_code=403, detail="Not authorized to list courses!")
    
    courses = get_teacher_courses(db, teacher.id)
    
    if not courses:
        return []
    
    filtered_courses = []
    for course in courses:
        print(course)
        if course.ingestion_status == None:
            course.ingestion_status = "IN_PROGRESS"
        if is_kbm:
            # Si is_kbm es True, incluir cursos donde settings no sea None
            if course.settings is not None:
                filtered_courses.append(course)
        else:
            # Si is_kbm es False, incluir cursos donde settings sea None
            if course.settings is None:
                filtered_courses.append(course)
    
    return filtered_courses


@router.post("/{course_id}/invite", response_model=List[UserResponse], status_code=status.HTTP_201_CREATED)
async def invite_students(
    course_id: UUID, 
    student_emails: List[str], 
    db: Session = Depends(get_db), 
    token: JWTLectureTokenPayload = Depends(require_token_types(allowed_types=["cognito"]))
):
    user = get_user_by_cognito_id(db, token.sub)
    if user.role not in [UserRole.teacher, UserRole.admin]:
        raise HTTPException(status_code=403, detail="Not authorized to invite students")

    # List to store created or updated student user objects
    invited_students = []
    
    for email in student_emails:
        db_user = get_user_by_email(db, email=email)
        if db_user is None:
            # Create new student user if not exists
            user_data = UserCreate(email=email, role=UserRole.student, name="")
            db_user = create_user(db=db, user=user_data)
        
        # Enroll student in the course
        enroll_user_in_course(db, user_id=db_user.id, course_id=course_id)
        invited_students.append(db_user)
    
    return invited_students


@router.delete("/{course_id}/", status_code=status.HTTP_204_NO_CONTENT)
async def delete_course_resources(
    course_id: UUID,
    async_processing: bool = Query(False, description="If True, run the process in the background"),
    background_tasks: BackgroundTasks = None,
    db: Session = Depends(get_db),
    token: JWTLectureTokenPayload = Depends(require_token_types(allowed_types=["cognito"]))
):
    # Check user permissions
    try:
        verify_user_owner(db, token, course_id)
    except HTTPException as e:
        if e.status_code == 404:
            print(f"Course with ID {course_id} not found. Skipping verification.")
        else:
            # If it's a different exception (e.g., 403), log it and re-raise it
            print(f"Error verifying user ownership for course {course_id}: {e.detail}")
            raise e

    if async_processing:
        # Asynchronous processing using BackgroundTasks
        if background_tasks is None:
            raise HTTPException(status_code=500, detail="BackgroundTasks not available for asynchronous processing")
        
        # Get user information for notifications
        user_id = token.sub
        teacher = get_user_by_cognito_id(db, user_id)
        
        # Start the process in the background
        background_tasks.add_task(
            process_delete_course_async,
            course_id=course_id,
            teacher_id=teacher.id,
            user_id=user_id
        )
        
        return {"message": "Course deletion process started in the background"}
    
    else:
        # Current flow (synchronous)
        return await _delete_course_sync(course_id, db)

async def _delete_course_sync(course_id: UUID, db: Session):
    """Function to delete the course (current flow)"""
    # Log the number of materials deleted
    try:
        deleted_materials = delete_materials_by_course(db, course_id)
        if deleted_materials > 0:
            print(f"Deleted {deleted_materials} materials for course ID {course_id}.")
        else:
            print(f"No materials found for course ID {course_id}.")
    except Exception as e:
        print(f"Error deleting materials for course ID {course_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Error deleting materials: {str(e)}")

    # Handle resource deletion (e.g., S3 bucket or external resources)
    try:
        await delete_resources(db, str(course_id))
        print(f"Deleted external resources for course ID {course_id}.")
    except Exception as e:
        print(f"Error deleting external resources for course ID {course_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Error deleting external resources: {str(e)}")

    # Log course deletion status
    try:
        course_deleted = delete_course(db, course_id)
        if course_deleted:
            print(f"Deleted course with ID {course_id}.")
        else:
            print(f"Course with ID {course_id} not found.")
    except Exception as e:
        print(f"Error deleting course with ID {course_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Error deleting course: {str(e)}")

    return {"message": "Course and resources deleted successfully"}

def process_delete_course_async(course_id: UUID, teacher_id: str, user_id: str):
    """
    Function that runs in the background to delete the course asynchronously
    """
    # Create a new database connection for the background task
    db = next(get_db())
    app_sync = AsyncManager()
    app_sync.set_parameters()
    
    try:
        update_course_field(db, course_id, 'ingestion_status', "IN_PROGRESS")
        
        # Send notification of start
        app_sync.send_event_with_notification_sync(
            db=db,
            user_id=teacher_id,
            service_id="course_deletion",
            title="course_deletion.processing.title",
            body="course_deletion.processing.body",
            data={"course_id": str(course_id), "stage": "starting"},
            notification_type="info",
            priority="normal"
        )
        
        # 1. Delete materials
        try:
            deleted_materials = delete_materials_by_course(db, course_id)
            if deleted_materials > 0:
                print(f"Deleted {deleted_materials} materials for course ID {course_id}.")
            else:
                print(f"No materials found for course ID {course_id}.")
            
        except Exception as e:
            print(f"Error deleting materials for course ID {course_id}: {e}")
            # Send error notification
            app_sync.send_event_with_notification_sync(
                db=db,
                user_id=teacher_id,
                service_id="course_deletion",
                title="course_deletion.error.title",
                body="course_deletion.error.body",
                data={"course_id": str(course_id), "stage": "error", "error": f"Error deleting materials: {str(e)}"},
                notification_type="error",
                priority="high"
            )
            raise

        # 2. Delete external resources (S3, etc.)
        try:
            asyncio.run(delete_resources(db, str(course_id)))
            print(f"Deleted external resources for course ID {course_id}.")
            
        except Exception as e:
            print(f"Error deleting external resources for course ID {course_id}: {e}")
            # Send error notification
            app_sync.send_event_with_notification_sync(
                db=db,
                user_id=teacher_id,
                service_id="course_deletion",
                title="course_deletion.error.title",
                body="course_deletion.error.body",
                data={"course_id": str(course_id), "stage": "error", "error": f"Error deleting external resources: {str(e)}"},
                notification_type="error",
                priority="high"
            )
            raise

        # 3. Delete the course from the database
        try:
            course_deleted = delete_course(db, course_id)
            if course_deleted:
                print(f"Deleted course with ID {course_id}.")
            else:
                print(f"Course with ID {course_id} not found.")
                
            # Send successful completion notification
            app_sync.send_event_with_notification_sync(
                db=db,
                user_id=teacher_id,
                service_id="course_deletion",
                title="course_deletion.completed.title",
                body="course_deletion.completed.body",
                data={"course_id": str(course_id), "stage": "completed"},
                notification_type="success",
                priority="normal"
            )
            
        except Exception as e:
            print(f"Error deleting course with ID {course_id}: {e}")
            # Send error notification
            app_sync.send_event_with_notification_sync(
                db=db,
                user_id=teacher_id,
                service_id="course_deletion",
                title="course_deletion.error.title",
                body="course_deletion.error.body",
                data={"course_id": str(course_id), "stage": "error", "error": f"Error deleting course: {str(e)}"},
                notification_type="error",
                priority="high"
            )
            raise
            
    except Exception as e:
        print(f"Error in async course deletion process: {str(e)}")
        # Send general error notification
        try:
            app_sync.send_event_with_notification_sync(
                db=db,
                user_id=teacher_id,
                service_id="course_deletion",
                title="course_deletion.error.title",
                body="course_deletion.error.body",
                data={"course_id": str(course_id), "stage": "error", "error": str(e)},
                notification_type="error",
                priority="high"
            )
        except Exception as notification_error:
            print(f"Error sending error notification: {str(notification_error)}")
    finally:
        # Close the database connection
        db.close()

@router.post("/", status_code=status.HTTP_201_CREATED)
async def create_course(
    course: CourseCreate,
    db: Session = Depends(get_db),
    token: JWTLectureTokenPayload = Depends(require_token_types(allowed_types=["cognito"]))
):
    # Check user permissions
    verify_user_permission(db, token)

    # Step 1: Create course in the database
    user_id = token.sub
    teacher = get_user_by_cognito_id(db, user_id)
    if not teacher:
        raise HTTPException(status_code=404, detail=TEACHER_NOT_FOUND_MESSAGE)

    course_data = create_course_in_db(db=db, course=course, teacher_id=teacher.id)
    
    user_group: Group = teacher.group
    group_region: Region = user_group.region
    s3_bucket = get_regional_bucket(db, group_region.name) 
    # Step 2: Create S3 subdirectory for course materials
    await setup_s3_directory(course_data.id, s3_bucket)

    return course_data


@router.post("/{course_id}/state_machine", status_code=status.HTTP_201_CREATED)
async def knowledgebase_state_machine(
    course_id: UUID,
    db: Session = Depends(get_db),
    token: JWTLectureTokenPayload = Depends(require_token_types(allowed_types=["cognito"]))
):
    # Check user permissions
    verify_user_owner(db, token, course_id)

    user = get_user_by_cognito_id(db, token.sub)
    user_group: Group = user.group
    group_region: Region = user_group.region
    
    input_data = {
        "course_id": str(course_id),
        "region_name": group_region.name,
        "region_bucket": group_region.s3_bucket
    }
    response = start_step_function(input_data)
    execution_arn = response.get("executionArn")
    update_course_field(db, course_id, 'execution_arn', execution_arn)
    
    return response

@router.post("/{course_id}/poll_state_machine", status_code=status.HTTP_200_OK)
async def poll_step_function(
    course_id: UUID,
    request: PollStateMachineRequest,
    db: Session = Depends(get_db),
    token: JWTLectureTokenPayload = Depends(require_token_types(allowed_types=["cognito"]))
):
    verify_user_owner(db, token, course_id)
    execution_arn = request.execution_arn
    
    if not request.execution_arn:
        execution_arn = get_course(db, course_id).execution_arn
    
    response = get_execution_details(execution_arn)
    
    if response.get("state_status") == "SUCCEEDED":
        # Update the course with the knowledge base ID and data source ID
        knowledge_base_id = response.get("execution_output").get("knowledge_base_id")
        data_source_id = response.get("execution_output").get("data_source_id")
        
        update_course_field(db, course_id, 'knowledge_base_id', knowledge_base_id)
        update_course_field(db, course_id, 'data_source_id', data_source_id)
    
    return response


@router.get("/{course_id}/ingestion", status_code=status.HTTP_200_OK)
async def start_ingestion(
    course_id: UUID,
    db: Session = Depends(get_db),
    token: JWTLectureTokenPayload = Depends(require_token_types(allowed_types=["cognito"]))
):
    # Check user permissions
    verify_user_permission(db, token)

    # Retrieve the course from the database
    course = get_course(db, course_id)
    if not course:
        raise HTTPException(status_code=404, detail=COURSE_NOT_FOUND_MESSAGE)

    # Retrieve knowledge_base_id and data_source_id from the course
    knowledge_base_id = course.knowledge_base_id
    data_source_id = course.data_source_id

    if not knowledge_base_id or not data_source_id:
        raise HTTPException(status_code=400, detail="Knowledge base or data source not set for this course")

    # Step 6: Start ingestion job for the knowledge base
    ingestion_job = await start_ingestion_job(knowledge_base_id, data_source_id)
    ingestion_job_id = ingestion_job.get("ingestionJobId")
    
    update_course_field(db, course_id, 'ingestion_job_id', ingestion_job_id)
    
    return {"message": "Ingestion job started"}

@router.get("/{course_id}/ingestion_status", status_code=status.HTTP_200_OK)
async def get_materials_summary(
    course_id: UUID,
    db: Session = Depends(get_db),
    token: JWTLectureTokenPayload = Depends(require_token_types(allowed_types=["cognito"]))
):
    # Check user permissions
    verify_user_permission(db, token)

    # Retrieve the course from the database
    course = get_course(db, course_id)
    if not course:
        return {"details": COURSE_NOT_FOUND_MESSAGE}

    # Retrieve knowledge_base_id and data_source_id from the course
    knowledge_base_id = course.knowledge_base_id
    data_source_id = course.data_source_id

    if not knowledge_base_id or not data_source_id:
        raise HTTPException(status_code=400, detail="Knowledge base or data source not set for this course. Please delete the course and create a new one.")

    # Retrieve ingestion_job_id from the course
    ingestion_job_id = course.ingestion_job_id

    if not ingestion_job_id:
        return {"details": "Ingestion job not started for this course"}

    try:
        # Get ingestion status
        response = await get_ingestion_summary(knowledge_base_id, data_source_id, ingestion_job_id)
        
        status = response.get("status")
        statistics = response.get("statistics")
        ic(statistics)
        
        if statistics.get("numberOfDocumentsFailed") and len(response.get("failureReasons")):
            error_map = parse_failure_reasons(response.get("failureReasons"))
            update_material_status(db, error_map)
            update_course_field(db, course_id, 'ingestion_status', 'COMPLETED')
            
        if status == "COMPLETE" and not statistics.get("numberOfDocumentsFailed"):
            update_course_field(db, course_id, 'ingestion_status', 'COMPLETED')

        return response
    except Exception as e:
        if "ResourceNotFoundException" in str(e):
            return {
                "details": "The knowledge base or data source no longer exists. Please restart the ingestion process.",
                "error": str(e)
            }
        raise HTTPException(status_code=500, detail=f"Error getting ingestion status: {str(e)}")

@router.get("/{course_id}/analyze_knowledge_base", status_code=status.HTTP_200_OK)
async def analyze_knowledge_base(
    course_id: UUID,
    db: Session = Depends(get_db),
    token: JWTLectureTokenPayload = Depends(require_token_types(allowed_types=["cognito"]))
):
    # Check user permissions
    verify_user_permission(db, token)

    # Retrieve the course from the database
    course = get_course(db, course_id)
    if not course:
        raise HTTPException(status_code=404, detail=COURSE_NOT_FOUND_MESSAGE)

    # Retrieve knowledge_base_id from the course
    knowledge_base_id = course.knowledge_base_id
    if not knowledge_base_id:
        raise HTTPException(status_code=400, detail="Knowledge base not set for this course")

    # Initialize results with existing data
    summary = course.description or ""
    questions = course.sample_questions or []

    # If we already have both summary and questions, return immediately
    if summary and questions:
        return {"summary": summary, "questions": questions}

    # Create tasks for missing data
    tasks = []
    task_types = []  # Keep track of which task is which type
    
    if not course.sample_questions:
        tasks.append(generate_course_questions(db, course_id, knowledge_base_id))
        task_types.append("questions")
    
    if not course.description:
        tasks.append(generate_course_summary(db, course_id, knowledge_base_id))
        task_types.append("summary")

    if not tasks:
        return {"summary": summary, "questions": questions}

    try:
        # Execute tasks in parallel and wait for all to complete
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Process results in order
        for result, task_type in zip(results, task_types):
            if isinstance(result, Exception):
                error_msg = str(result)
                ic(f"Error in {task_type} generation: {error_msg}")
                # Log the error but continue with empty results
                continue
                
            if task_type == "summary":
                if result and isinstance(result, str):
                    summary = result
            elif task_type == "questions":
                if result and isinstance(result, list):
                    questions = result

        # Return whatever results we have, even if empty
        return {
            "summary": summary,
            "questions": questions
        }

    except Exception as e:
        ic(f"Unexpected error in analyze_knowledge_base: {str(e)}")
        # Return empty results instead of raising an error
        return {
            "summary": summary,
            "questions": questions
        }

async def process_single_file(
    file: UploadFile,
    course_id: UUID,
    course: Course,
    teacher: User,
    extra_processing: bool,
    executor: ThreadPoolExecutor,
    db: Session
) -> Material:
    ic(file.filename, file.content_type)
    safe_filename = sanitize_filename(file.filename)
    file_ext = file.filename.rsplit(".", 1)[-1].lower()
    teacher_id = str(teacher.id)
    
    temp_path = None
    try:
        # Create a secure temporary file asynchronously
        loop = asyncio.get_event_loop()
        temp_path = await loop.run_in_executor(
            executor,
            lambda: create_temp_file(file, file_ext)
        )
        
        # Upload original file to S3 asynchronously
        s3_uri = await loop.run_in_executor(
            executor,
            lambda: upload_to_s3('content', temp_path, f"materials/{course_id}/{safe_filename}")
        )

        # Initialize transcription_s3_uri as None
        transcription_s3_uri = None

        if file_ext == "epub":
            transcription_s3_uri = await process_epub_file(temp_path, course_id, safe_filename)

        # Create material record in database
        material_data = MaterialCreate(
            title=file.filename,
            type=file.content_type,
            s3_uri=s3_uri,
            transcription_s3_uri=transcription_s3_uri,
            course_id=course_id
        )

        material = create_material(db=db, material=material_data)
        ic("Material created", material)

        # Check if is pdf extension and process with pdr_processor
        if file_ext == "pdf" and extra_processing:
            # Create a ChatbotCreate instance with necessary data
            chatbot_data = ChatbotCreate(
                name=safe_filename,
                id=str(course_id),
                system_prompt="You are a helpful assistant that transcribes audio and video files.",
                user_id=teacher_id,
                status="PROCESSING",
                session_id=str(uuid.uuid4()),
                memory_id=str(uuid.uuid4()),
                resource_data=str(uuid.uuid4())
            )

            knowledge_base_filter_structure = course.settings.get("knowledge_base_filter_structure", [])
            metadata = {}
            filename_splitted = safe_filename.split("_")
            properties_order = []
            
            # For each knowledge_base_filter_structure, create a metadata with the filter name and the value of the index according to the for loop
            for index, filter in enumerate(knowledge_base_filter_structure):
                if index < len(filename_splitted):
                    name = filename_splitted[index]
                    properties_order.append(filter)
                    name = name.lower()
                    metadata[filter] = name
                else:
                    # If there are not enough parts in the file name, use a default value
                    metadata[filter] = "default"
                    properties_order.append(filter)

            # Create a copy of the file for processing
            file_copy = UploadFile(
                filename=file.filename,
                file=open(temp_path, "rb")
            )
            
            try:
                # Process the PDF and get the transcription
                processor = PDFDocumentProcessor(db, file_copy, chatbot_data, True, material_uuid=material.id)
                ic("Processing PDF")
                
                # Execute the processing in a ThreadPoolExecutor to not block
                loop = asyncio.get_event_loop()
                await loop.run_in_executor(
                    executor,
                    lambda: asyncio.run(processor.process_and_upload_to_s3(f"materials/{course_id}", metadata, properties_order))
                )
            finally:
                # Close the file after processing
                file_copy.file.close()

        return material
    
    except Exception as e:
        ic("Error during file handling", e)
        raise HTTPException(status_code=500, detail=f"Error uploading file: {safe_filename}, {str(e)}")
    
    finally:
        if temp_path:
            try:
                await loop.run_in_executor(executor, lambda: os.unlink(temp_path))
                ic(f"Temporary file {temp_path} removed")
            except Exception as e:
                ic(f"Error removing temporary file: {temp_path}", e)

def create_temp_file(file: UploadFile, file_ext: str) -> str:
    """Helper function to create temporary file synchronously"""
    with tempfile.NamedTemporaryFile(delete=False, suffix=f".{file_ext}") as tmp_file:
        shutil.copyfileobj(file.file, tmp_file)
        return tmp_file.name

@router.post("/{course_id}/materials/", status_code=status.HTTP_201_CREATED)
async def upload_materials(
    course_id: UUID,
    extra_processing: bool = Form(...),
    files: List[UploadFile] = File(...),
    db: Session = Depends(get_db),
    token: JWTLectureTokenPayload = Depends(require_token_types(allowed_types=["cognito"]))
):
    course = get_course(db, course_id)
    ic(course)
    if not course:
        raise HTTPException(status_code=404, detail=COURSE_NOT_FOUND_MESSAGE)

    user_id = token.sub
    teacher = get_user_by_cognito_id(db, user_id)
    user_role = teacher.role
    
    if not teacher:
        raise HTTPException(status_code=404, detail=TEACHER_NOT_FOUND_MESSAGE)

    if user_role not in [UserRole.teacher, UserRole.admin] or course.teacher_id != teacher.id:
        raise HTTPException(status_code=403, detail="Not authorized to upload materials")
    
    files_length = len(files)
    files_processed = 0

    with ThreadPoolExecutor(max_workers=1) as executor:
        try:
            tasks = []
            for file in files:
                task = process_single_file(file, course_id, course, teacher, extra_processing, executor, db)
                tasks.append(task)
                files_processed += 1
                ic(files_length, files_processed)
            
            # Use gather with return_exceptions=True to handle errors
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            # Filter and handle the exceptions
            errors = [str(r) for r in results if isinstance(r, Exception)]
            if errors:
                raise HTTPException(
                    status_code=500,
                    detail=f"Error processing files: {errors}"
                )
            
            materials = [r for r in results if not isinstance(r, Exception)]

        except Exception as e:
            raise HTTPException(
                status_code=500,
                detail=f"Error processing files: {str(e)}"
            )

    if course.ingestion_status is not None:
        update_course_field(db, course_id, 'ingestion_status', None)

    return materials

async def _delete_material_files(material: Material, course_id: UUID, extra_processing: bool):
    await delete_from_s3(bucket='content', s3_uri=material.s3_uri)
    if transcription_s3_uri := material.transcription_s3_uri:
        await delete_from_s3(bucket='content', s3_uri=transcription_s3_uri)
    if extra_processing and material.type == "application/pdf":
        s3_uri = 'materials/' + str(course_id) + '/' + str(material.id) + ".md"
        try:
            await delete_from_s3(bucket='content', s3_uri=s3_uri)
            await delete_from_s3(bucket='content', s3_uri=s3_uri + ".metadata.json")
        except Exception as e:
            ic(f"Error deleting material: {str(e)}")

@router.delete("/{course_id}/materials/", status_code=status.HTTP_200_OK)
async def delete_materials(
    course_id: UUID,
    material_ids: List[UUID],
    extra_processing: List[str] = Query(None, description="Extra processing for the materials"),
    db: Session = Depends(get_db),
    token: JWTLectureTokenPayload = Depends(require_token_types(allowed_types=["cognito"]))
):
    verify_user_owner(db, token, course_id)
    extra_processing = extra_processing if extra_processing else []
    extra_processing = (extra_processing[0] if len(extra_processing) > 0 else "0") == "1"

    for material_id in material_ids:
        material = get_material(db, material_id)
        if not material:
            raise HTTPException(status_code=404, detail=MATERIAL_NOT_FOUND_MESSAGE)

        try:
            await _delete_material_files(material, course_id, extra_processing)
            delete_material(db, material.id)
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Error deleting material: {str(e)}")

@router.get("/{course_id}/materials/preprocess", status_code=status.HTTP_200_OK)
async def preprocess_materials(
    course_id: UUID, 
    db: Session = Depends(get_db), 
    token: JWTLectureTokenPayload = Depends(require_token_types(allowed_types=["cognito"]))
):
    # Get course
    course = get_course(db, course_id)
    ic(course)
    if not course:
        ic(COURSE_NOT_FOUND_MESSAGE)
        raise HTTPException(status_code=404, detail=COURSE_NOT_FOUND_MESSAGE)
    
    # Check user permissions
    verify_user_owner(db, token, course_id)
    
    # Recover materials, check if any of them is suitable for transcription
    materials = get_materials_by_course(db, course_id)
    transcriptable_materials = [material for material in materials
                                if material.type.startswith(('audio/', 'video/')) and material.transcription_s3_uri is None]
    if len(transcriptable_materials) > 0:
        # Preprocess transcriptable materials
        input_data = {
            "files": [
                {
                    "fileUri": material.s3_uri,
                    "materialId": str(material.id)
                } 
                for material in transcriptable_materials
            ],
            "courseId": str(course_id)
        }
        result = await run_preprocessing_job(input_data)
        # Update materials with transcription URIs
        for item in result:
            material_id = item.get("materialId")
            transcription_s3_uri = item.get("transcribedFileUri")
            update_material_transcription_uri(db, material_id, transcription_s3_uri)
        ic("Preprocessing completed.")
        return {"message": "Preprocessing completed."}
    else:
        ic("No audio/video materials found for transcription.")
        return {"message": "No audio/video materials found for transcription."}

@router.get("/{course_id}/sample_questions", status_code=status.HTTP_200_OK)
async def get_sample_questions(
    course_id: UUID,
    db: Session = Depends(get_db),
    token: JWTLectureTokenPayload = Depends(require_token_types(allowed_types=["cognito"]))
):
    # Check user permissions
    verify_user_owner(db, token, course_id)
    
    course = get_course(db, course_id)
    if not course:
        raise HTTPException(status_code=404, detail=COURSE_NOT_FOUND_MESSAGE)
    
    questions = course.sample_questions or []
    
    return {"questions": questions}

@router.get("/{course_id}/materials/", response_model=CourseWithMaterialsResponse)
async def get_course_with_materials(
    course_id: UUID,
    db: Session = Depends(get_db)
):
    course = get_course(db, course_id)
    if not course:
        raise HTTPException(status_code=404, detail=COURSE_NOT_FOUND_MESSAGE)        

    materials = get_materials_by_course(db, course_id)
    course_data = {
        "id": course.id,
        "title": course.title,
        "description": course.description,
        "ingestion_status": course.ingestion_status,
        "created_at": course.created_at,
        "materials": [
            {
                "id": material.id,
                "title": material.title,
                "type": material.type,
                "s3_uri": generate_presigned_url('content', material.s3_uri),
                "status": material.status,
            } for material in materials
        ]
    }

    return course_data

@router.post("/invites/")
async def invite_user(invite_create: InviteCreate, db: Session = Depends(get_db)):
    try:
        invite_code = uuid.uuid4().hex
        expires_at = datetime.now(timezone.utc) + timedelta(days=7)

        invite_data = InviteBase(
            invite_code=invite_code,
            email=invite_create.email,
            course_id=invite_create.course_id,
            expires_at=expires_at
        )
        
        new_invite = create_invite(db, invite_data)
        course  = get_course(db, invite_create.course_id);
        
        # Send invite email with the invite code in the URL
        invite_url = f"{REACT_APP_URL}/invite/confirm/{invite_code}"
        send_invite_email(invite_create.email, invite_url, course.title)

        return {"message": "Invite sent", "invite_code": new_invite.invite_code}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


# Get all invitations for a specific course
@router.get("/invites/{course_id}", response_model=list[InviteResponse])
def get_invitations_by_course_endpoint(course_id: UUID, db: Session = Depends(get_db)):
    invites = get_invitations_by_course(db, course_id)
    if not invites:
        return []
    return invites

@router.post("/invites/confirm")
async def confirm_invite(user: InviteConfirm, db: Session = Depends(get_db)):
    invite = get_invite_by_code(db, user.invite_code)
    
    if invite and invite.expires_at.replace(tzinfo=timezone.utc) > datetime.now(timezone.utc):
        try:
            role = "student"
            user = {
                "email": invite.email,
                "password": user.password,
                "role": role,
                "given_name": user.given_name,
                "family_name": user.family_name,
                "locale": user.locale
            }
            create_user = create_cognito_and_db_user(user=user,db=db)
            ic(create_user)

            delete_invite(db, invite.invite_code)

            return {
                "message": "User created in Cognito and database",
                "email": invite.email,
            }

        except Exception as e:
            raise HTTPException(status_code=400, detail=str(e))
    else:
        raise HTTPException(status_code=400, detail="Invalid or expired invite")

@router.get("/all_teacher_materials/", response_model=List[MaterialResponse])
async def get_all_teacher_materials(
    db: Session = Depends(get_db), 
    token: JWTLectureTokenPayload = Depends(require_token_types(allowed_types=["cognito"]))
):    
    user_id = token.sub
    teacher = get_user_by_cognito_id(db, user_id)
    user_role = teacher.role

    if user_role not in [UserRole.teacher, UserRole.admin]:
        raise HTTPException(status_code=403, detail="Not authorized to upload materials")
    # Get all courses for the teacher
    curses = await get_courses_by_teacher(False, db, token)

    # Get all materials for the courses
    materials = []
    for course in curses:
        materials.extend(get_materials_by_course(db, course.id))
    
    if len(materials) == 0:
        return []
    
    return materials

@router.get("/materials/{material_id}")
async def get_material_by_id(
    material_id: UUID,
    db: Session = Depends(get_db),
    token: JWTLectureTokenPayload = Depends(require_token_types(allowed_types=["cognito"]))
):
    material = get_material(db, material_id)
    if not material:
        raise HTTPException(status_code=404, detail=MATERIAL_NOT_FOUND_MESSAGE)

    # Use the s3_uri to get the file from S3
    s3_object = await get_s3_object(material.s3_uri)
    
    return StreamingResponse(
        s3_object["Body"].iter_chunks(1024),
        media_type=material.type,
        headers={
            "Content-Disposition": f"attachment;filename={material.title}"
        }
    )

@router.put("/{course_id}/settings")
async def update_files_structure(
    course_id: UUID,
    settings: CourseUpdateSettings,
    db: Session = Depends(get_db)
):
    # Update the files structure for the course
    return await update_course_settings(db, course_id, settings)

@router.put("/{course_id}/conversation_access_token")
async def update_conversation_access_token(
    course_id: UUID,
    token_data: ConversationAccessToken,
    db: Session = Depends(get_db)
):
    # Update the conversation access token for the course
    return await update_course_conversation_access_token(db, course_id, token_data.conversation_access_token)

# Get the course data with course_id
@router.get("/{course_id}/data")
async def get_course_data(
    course_id: UUID,
    db: Session = Depends(get_db)
):
    return get_course(db, course_id)

@router.post("/generate-course/", status_code=status.HTTP_202_ACCEPTED)
async def generate_course(
    course_id: UUID,
    extra_processing: bool = Form(...),
    files: List[UploadFile] = File(...),
    db: Session = Depends(get_db),
    token: JWTLectureTokenPayload = Depends(require_token_types(allowed_types=["cognito"]))
):
    """
    Async endpoint to generate a complete course with all its materials and configurations.
    The process includes:
    1. Uploading materials
    2. Creating knowledge base
    3. Preprocessing materials
    4. Ingestion of data
    5. Analysis of the knowledge base
    """
    course = get_course(db, course_id)
    if not course:
        raise HTTPException(status_code=404, detail=COURSE_NOT_FOUND_MESSAGE)

    user_id = token.sub
    teacher = get_user_by_cognito_id(db, user_id)
    if not teacher:
        raise HTTPException(status_code=404, detail=TEACHER_NOT_FOUND_MESSAGE)

    if teacher.role not in [UserRole.teacher, UserRole.admin] or course.teacher_id != teacher.id:
        raise HTTPException(status_code=403, detail="Not authorized to generate course")

    # Get the information of the group and region before starting the async process
    user_group = teacher.group
    group_region = user_group.region
    region_name = group_region.name
    region_bucket = group_region.s3_bucket

    # Create copies of the files for the async process
    file_copies = []
    for file in files:
        content = await file.read()
        try:
            file_copy = UploadFile(
                filename=file.filename,
                file=BytesIO(content),
                headers={"content-type": file.content_type}
            )
            file_copies.append(file_copy)
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Error processing file: {str(e)}")

    # Start the async process
    asyncio.create_task(process_course_generation(
        course_id=course_id,
        files=file_copies,
        extra_processing=extra_processing,
        db=db,
        teacher=teacher,
        region_name=region_name,
        region_bucket=region_bucket
    ))

    return {"message": "Course generation process started"}

async def retry_with_delay(func, *args, max_retries=3, delay=30):
    """
    Try to execute a function until max_retries times, waiting delay seconds between attempts.
    
    Args:
        func: The function to execute (must be async)
        *args: Arguments for the function
        max_retries: Maximum number of retries
        delay: Time to wait between retries in seconds
        
    Returns:
        The result of the function if successful
        
    Raises:
        Exception: If all retries fail
    """
    last_error = None
    
    for attempt in range(max_retries):
        try:
            return await func(*args)
        except Exception as e:
            last_error = e
            if attempt < max_retries - 1:
                await asyncio.sleep(delay)
                continue
            raise last_error

async def process_course_generation(
    course_id: UUID,
    files: List[UploadFile],
    extra_processing: bool,
    db: Session,
    teacher: User,
    region_name: str,
    region_bucket: str
):
    """
    Async function that handles the entire course generation process
    """
    app_sync = AsyncManager()
    app_sync.set_parameters()

    # Determine the translation key prefix
    translation_prefix = "kbm_generation" if extra_processing else "course_generation"

    try:
        # Get the course at the beginning
        course = get_course(db, course_id)
        if not course:
            raise HTTPException(status_code=404, detail=COURSE_NOT_FOUND_MESSAGE)
        
        # Update the ingestion status to in progress
        # update_course_field(db, course_id, 'ingestion_status', "IN_PROGRESS")

        with ThreadPoolExecutor(max_workers=2) as executor:
            tasks = []
            for file in files:
                task = process_single_file(file, course_id, course, teacher, extra_processing, executor, db)
                tasks.append(task)
            
            results = await asyncio.gather(*tasks, return_exceptions=True)
            errors = [str(r) for r in results if isinstance(r, Exception)]
            if errors:
                raise HTTPException(status_code=500, detail=f"Error processing files: {errors}")

        # 2. Starting the state machine
        await app_sync.send_event_with_notification(
            db=db,
            user_id=teacher.id,
            service_id=f"{translation_prefix}",
            title=f"{translation_prefix}.creating_knowledge_base.title",
            body=f"{translation_prefix}.creating_knowledge_base.body",
            data={"course_id": str(course_id), "stage": "create_knowledge_base"},
            notification_type="info",
            priority="normal"
        )

        input_data = {
            "course_id": str(course_id),
            "region_name": region_name,
            "region_bucket": region_bucket
        }
        response = start_step_function(input_data)
        execution_arn = response.get("executionArn")
        update_course_field(db, course_id, 'execution_arn', execution_arn)

        # 3. Polling the state machine
        while True:
            state_response = get_execution_details(execution_arn)
            status = state_response.get("state_status")
            
            if status == "SUCCEEDED":    
                knowledge_base_id = state_response.get("execution_output", {}).get("knowledge_base_id")
                data_source_id = state_response.get("execution_output", {}).get("data_source_id")
                update_course_field(db, course_id, 'knowledge_base_id', knowledge_base_id)
                update_course_field(db, course_id, 'data_source_id', data_source_id)
                break
            elif status in ["FAILED", "TIMED_OUT", "ABORTED"]:
                await app_sync.send_event_with_notification(
                    db=db,
                    user_id=teacher.id,
                    service_id=f"{translation_prefix}",
                    title=f"{translation_prefix}.state_machine.title",
                    body=f"{translation_prefix}.state_machine.error",
                    data={"course_id": str(course_id), "stage": "state_machine", "status": status},
                    notification_type="error",
                    priority="high"
                )
                raise Exception("State machine execution failed")
            
            await asyncio.sleep(15)

        materials = get_materials_by_course(db, course_id)
        transcriptable_materials = [material for material in materials
                                if material.type.startswith(('audio/', 'video/')) and material.transcription_s3_uri is None]
        
        if transcriptable_materials:
            input_data = {
                "files": [
                    {
                        "fileUri": material.s3_uri,
                        "materialId": str(material.id)
                    } 
                    for material in transcriptable_materials
                ],
                "courseId": str(course_id)
            }
            result = await run_preprocessing_job(input_data)
            for item in result:
                material_id = item.get("materialId")
                transcription_s3_uri = item.get("transcribedFileUri")
                update_material_transcription_uri(db, material_id, transcription_s3_uri)

        course = get_course(db, course_id)
        ingestion_job = await start_ingestion_job(course.knowledge_base_id, course.data_source_id)
        ingestion_job_id = ingestion_job.get("ingestionJobId")
        update_course_field(db, course_id, 'ingestion_job_id', ingestion_job_id)

        # 6. Polling the ingestion status
        while True:
            ingestion_status = await get_ingestion_summary(
                course.knowledge_base_id,
                course.data_source_id,
                ingestion_job_id
            )
            
            if ingestion_status.get("status") == "COMPLETE":
                break
            elif ingestion_status.get("status") in ["FAILED", "ERROR"]:
                raise Exception("Ingestion process failed")
            
            await asyncio.sleep(15)

        # 7. Generate course questions and summary in parallel
        tasks = []
        if not course.sample_questions:
            tasks.append(retry_with_delay(
                generate_course_questions,
                db,
                course_id,
                course.knowledge_base_id
            ))
        if not course.description:
            tasks.append(retry_with_delay(
                generate_course_summary,
                db,
                course_id,
                course.knowledge_base_id
            ))

        if tasks:
            # Execute tasks in parallel and wait for all to complete
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            # Process results and handle exceptions
            for result in results:
                if isinstance(result, Exception):
                    ic(f"Error in course generation: {result}")
                    # Log the error but continue with the process
                    continue

        # Update the ingestion status to completed
        update_course_field(db, course_id, 'ingestion_status', "COMPLETED")

        # Process completed
        await app_sync.send_event_with_notification(
            db=db,
            user_id=teacher.id,
            service_id=f"{translation_prefix}",
            title=f"{translation_prefix}.completed.title",
            body=f"{translation_prefix}.completed.body",
            data={"course_id": str(course_id), "stage": "completed"},
            notification_type="success",
            priority="normal",
            actions=[
                {
                    "label": "notifications.buttons.view",
                    "action": "navigate",
                    "url": f"/{'knowledge-base/view' if extra_processing else 'course'}/{course_id}"
                }
            ]
        )

    except Exception as e:
        # Update the ingestion status to failed
        if course.ingestion_status is None or course.knowledge_base_id is None or course.data_source_id is None or course.ingestion_job_id is None:
            update_course_field(db, course_id, 'ingestion_status', "ERROR")
        
            # Notify error
            await app_sync.send_event_with_notification(
                db=db,
                user_id=teacher.id,
                service_id=f"{translation_prefix}",
                title=f"{translation_prefix}.error.title",
                body=f"{translation_prefix}.error.body",
                data={"course_id": str(course_id), "stage": "error", "error": str(e)},
                notification_type="error",
                priority="high"
            )
        else:
            # Update the ingestion status to completed
            update_course_field(db, course_id, 'ingestion_status', "COMPLETED")

            # Process completed
            await app_sync.send_event_with_notification(
                db=db,
                user_id=teacher.id,
                service_id=f"{translation_prefix}",
                title=f"{translation_prefix}.completed.title",
                body=f"{translation_prefix}.completed.body",
                data={"course_id": str(course_id), "stage": "completed"},
                notification_type="success",
                priority="normal",
                actions=[
                    {
                        "label": "notifications.buttons.view",
                        "action": "navigate",
                        "url": f"/{'knowledge-base/view' if extra_processing else 'course'}/{course_id}"
                    }
                ]
            )

        raise

@router.post("/update-course/{course_id}/", status_code=status.HTTP_202_ACCEPTED)
async def update_course_materials(
    course_id: UUID,
    extra_processing: bool = Form(...),
    files: List[UploadFile] = File(...),
    db: Session = Depends(get_db),
    token: JWTLectureTokenPayload = Depends(require_token_types(allowed_types=["cognito"]))
):
    """
    Async endpoint to update the materials of an existing course.
    The process includes:
    1. Uploading new materials
    2. Preprocessing materials
    3. Starting the ingestion
    4. Monitoring the ingestion status
    """
    course = get_course(db, course_id)
    if not course:
        raise HTTPException(status_code=404, detail=COURSE_NOT_FOUND_MESSAGE)

    user_id = token.sub
    teacher = get_user_by_cognito_id(db, user_id)
    if not teacher:
        raise HTTPException(status_code=404, detail=TEACHER_NOT_FOUND_MESSAGE)

    if teacher.role not in [UserRole.teacher, UserRole.admin] or course.teacher_id != teacher.id:
        raise HTTPException(status_code=403, detail="Not authorized to update course")

    # Create copies of the files for the async process
    file_copies = []
    for file in files:
        content = await file.read()
        try:
            file_copy = UploadFile(
                filename=file.filename,
                file=BytesIO(content),
                headers={"content-type": file.content_type}
            )
            file_copies.append(file_copy)
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Error processing file: {str(e)}")

    update_course_field(db, course_id, 'ingestion_status', "IN_PROGRESS")
    
    # Start the async process
    asyncio.create_task(process_course_update(
        course_id=course_id,
        files=file_copies,
        extra_processing=extra_processing,
        teacher=teacher,
        db=db
    ))

    return {"message": "Course update process started"}

async def process_course_update(
    course_id: UUID,
    files: List[UploadFile],
    extra_processing: bool,
    teacher: User,
    db: Session
):
    """
    Async function that handles the entire update process of the course
    """
    app_sync = AsyncManager()
    app_sync.set_parameters()

    # Determine the translation key prefix
    translation_prefix = "kbm_update" if extra_processing else "course_update"

    try:
        # Get the course at the beginning
        course = get_course(db, course_id)
        if not course:
            raise HTTPException(status_code=404, detail=COURSE_NOT_FOUND_MESSAGE)
        
        # Send event to start the update
        await app_sync.send_event_with_notification(
            db=db,
            user_id=teacher.id,
            service_id=f"{translation_prefix}",
            title=f"{translation_prefix}.starting.title",
            body=f"{translation_prefix}.starting.body",
            data={"course_id": str(course_id), "stage": "starting"},
            notification_type="info",
            priority="normal"
        )

        # 1. Upload the new materials
        with ThreadPoolExecutor(max_workers=2) as executor:
            tasks = []
            for file in files:
                task = process_single_file(file, course_id, course, teacher, extra_processing, executor, db)
                tasks.append(task)
            
            results = await asyncio.gather(*tasks, return_exceptions=True)
            errors = [str(r) for r in results if isinstance(r, Exception)]
            if errors:
                raise HTTPException(status_code=500, detail=f"Error processing files: {errors}")

        # 2. Preprocess the materials
        materials = get_materials_by_course(db, course_id)
        transcriptable_materials = [material for material in materials
                                if material.type.startswith(('audio/', 'video/')) and material.transcription_s3_uri is None]
        
        if transcriptable_materials:
            input_data = {
                "files": [
                    {
                        "fileUri": material.s3_uri,
                        "materialId": str(material.id)
                    } 
                    for material in transcriptable_materials
                ],
                "courseId": str(course_id)
            }
            result = await run_preprocessing_job(input_data)
            for item in result:
                material_id = item.get("materialId")
                transcription_s3_uri = item.get("transcribedFileUri")
                update_material_transcription_uri(db, material_id, transcription_s3_uri)

        # 3. Start the ingestion
        course = get_course(db, course_id)
        ingestion_job = await start_ingestion_job(course.knowledge_base_id, course.data_source_id)
        ingestion_job_id = ingestion_job.get("ingestionJobId")
        update_course_field(db, course_id, 'ingestion_job_id', ingestion_job_id)

        # 4. Monitor the ingestion status
        while True:
            ingestion_status = await get_ingestion_summary(
                course.knowledge_base_id,
                course.data_source_id,
                ingestion_job_id
            )
            
            if ingestion_status.get("status") == "COMPLETE":
                break
            elif ingestion_status.get("status") in ["FAILED", "ERROR"]:
                raise Exception("Ingestion process failed")
            
            await asyncio.sleep(15)

        # Update the ingestion status to completed
        update_course_field(db, course_id, 'ingestion_status', "COMPLETED")

        # Process completed
        await app_sync.send_event_with_notification(
            db=db,
            user_id=teacher.id,
            service_id=f"{translation_prefix}",
            title=f"{translation_prefix}.completed.title",
            body=f"{translation_prefix}.completed.body",
            data={"course_id": str(course_id), "stage": "completed"},
            notification_type="success",
            priority="normal",
            actions=[
                {
                    "label": "notifications.buttons.view",
                    "action": "navigate",
                    "url": f"/{'knowledge-base/view' if extra_processing else 'course'}/{course_id}"
                }
            ]
        )

    except Exception as e:
        # Update the ingestion status to error
        update_course_field(db, course_id, 'ingestion_status', "ERROR")
        
        # Notify error
        await app_sync.send_event_with_notification(
            db=db,
            user_id=teacher.id,
            service_id=f"{translation_prefix}",
            title=f"{translation_prefix}.error.title",
            body=f"{translation_prefix}.error.body",
            data={"course_id": str(course_id), "stage": "error", "error": str(e)},
            notification_type="error",
            priority="high"
        )
        raise
    
    finally:
        db.close()

@router.delete("/{course_id}/materials-update/", status_code=status.HTTP_202_ACCEPTED)
async def delete_and_update_course(
    course_id: UUID,
    material_ids: List[UUID],
    extra_processing: List[str] = Query(None, description="Procesamiento adicional para los materiales"),
    db: Session = Depends(get_db),
    token: JWTLectureTokenPayload = Depends(require_token_types(allowed_types=["cognito"]))
):
    """
    Async endpoint to delete materials and update the course.
    The process includes:
    1. Deleting the specified materials
    2. Preprocessing the remaining materials
    3. Starting the ingestion
    4. Monitoring the ingestion status
    """
    course = get_course(db, course_id)
    if not course:
        raise HTTPException(status_code=404, detail=COURSE_NOT_FOUND_MESSAGE)

    user_id = token.sub
    teacher = get_user_by_cognito_id(db, user_id)
    if not teacher:
        raise HTTPException(status_code=404, detail=TEACHER_NOT_FOUND_MESSAGE)

    if teacher.role not in [UserRole.teacher, UserRole.admin] or course.teacher_id != teacher.id:
        raise HTTPException(status_code=403, detail="Not authorized to update course")

    # Convert extra_processing to boolean
    extra_processing_bool = (extra_processing[0] if len(extra_processing) > 0 else "0") == "1"

    # Update the ingestion status to in progress
    update_course_field(db, course_id, 'ingestion_status', "IN_PROGRESS")

    # Start the async process
    asyncio.create_task(process_delete_and_update(
        course_id=course_id,
        material_ids=material_ids,
        extra_processing=extra_processing_bool,
        teacher=teacher
    ))

    return {"message": "Delete and update process started"}

async def process_delete_and_update(
    course_id: UUID,
    material_ids: List[UUID],
    extra_processing: bool,
    teacher: User
):
    """
    Async function that handles the deletion and update process
    """
    app_sync = AsyncManager()
    app_sync.set_parameters()
    db = next(get_db())
    teacher_id = str(teacher.id)

    # Determine the translation key prefix
    translation_prefix = "kbm_update" if extra_processing else "course_update"

    try:
        # Get the course at the beginning
        course = get_course(db, course_id)
        if not course:
            raise HTTPException(status_code=404, detail=COURSE_NOT_FOUND_MESSAGE)

        # Send event to start the update
        await app_sync.send_event_with_notification(
            db=db,
            user_id=teacher_id,
            service_id=f"{translation_prefix}",
            title=f"{translation_prefix}.starting.title",
            body=f"{translation_prefix}.starting.body",
            data={"course_id": str(course_id), "stage": "starting"},
            notification_type="info",
            priority="normal"
        )

        # 1. Delete the specified materials
        for material_id in material_ids:
            material = get_material(db, material_id)
            if not material:
                continue

            try:
                await _delete_material_files(material, course_id, extra_processing)
                delete_material(db, material.id)
            except Exception as e:
                raise HTTPException(status_code=500, detail=f"Error deleting material: {str(e)}")

        # 2. Preprocess the remaining materials
        materials = get_materials_by_course(db, course_id)
        transcriptable_materials = [material for material in materials
                                if material.type.startswith(('audio/', 'video/')) and material.transcription_s3_uri is None]
        
        if transcriptable_materials:
            input_data = {
                "files": [
                    {
                        "fileUri": material.s3_uri,
                        "materialId": str(material.id)
                    } 
                    for material in transcriptable_materials
                ],
                "courseId": str(course_id)
            }
            result = await run_preprocessing_job(input_data)
            for item in result:
                material_id = item.get("materialId")
                transcription_s3_uri = item.get("transcribedFileUri")
                update_material_transcription_uri(db, material_id, transcription_s3_uri)

        # 3. Start the ingestion
        course = get_course(db, course_id)
        ingestion_job = await start_ingestion_job(course.knowledge_base_id, course.data_source_id)
        ingestion_job_id = ingestion_job.get("ingestionJobId")
        update_course_field(db, course_id, 'ingestion_job_id', ingestion_job_id)

        # 4. Monitor the ingestion status
        while True:
            ingestion_status = await get_ingestion_summary(
                course.knowledge_base_id,
                course.data_source_id,
                ingestion_job_id
            )
            
            if ingestion_status.get("status") == "COMPLETE":
                break
            elif ingestion_status.get("status") in ["FAILED", "ERROR"]:
                raise Exception("Ingestion process failed")
            
            await asyncio.sleep(15)

        # Update the ingestion status to completed
        update_course_field(db, course_id, 'ingestion_status', "COMPLETED")

        # Process completed
        await app_sync.send_event_with_notification(
            db=db,
            user_id=teacher_id,
            service_id=f"{translation_prefix}",
            title=f"{translation_prefix}.completed.title",
            body=f"{translation_prefix}.completed.body",
            data={"course_id": str(course_id), "stage": "completed"},
            notification_type="success",
            priority="normal"
        )

    except Exception as e:
        # Update the ingestion status to error
        update_course_field(db, course_id, 'ingestion_status', "ERROR")
        
        # Notify error
        await app_sync.send_event_with_notification(
            db=db,
            user_id=teacher_id,
            service_id=f"{translation_prefix}",
            title=f"{translation_prefix}.error.title",
            body=f"{translation_prefix}.error.body",
            data={"course_id": str(course_id), "stage": "error", "error": str(e)},
            notification_type="error",
            priority="high"
        )
        raise
    finally:
        db.close()
