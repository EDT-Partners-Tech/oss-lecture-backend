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

import io
import time
import uuid
import json
import asyncio
from typing import List
from fastapi import APIRouter, Body, File, HTTPException, Header, UploadFile, Form, BackgroundTasks
from database.schemas import ChatbotCreate, ConversationAccessRequest
from database.crud import create_chatbot, get_course, get_material, get_materials_by_course, get_request_by_title, get_teacher_courses, get_user_by_cognito_id, delete_chatbot_by_id, get_chatbots_by_user_id, get_chatbot_by_id, get_chatbot_materials_by_chatbot_id_with_is_main_true, get_messages_by_chatbot_id, update_chatbot_status
from database.db import get_db, SessionLocal
from sqlalchemy.orm import Session
from utility.auth import require_token_types
from fastapi import APIRouter, HTTPException, Depends
from utility.aws import get_s3_object
from utility.chatbot_processor import ChatbotProcessor
from utility.pdf_processor import PDFDocumentProcessor
from utility.service import handle_save_request
from utility.analytics import process_and_save_analytics, AnalyticsProcessor
from logging_config import setup_logging
from utility.async_manager import AsyncManager
from utility.tokens import JWTLectureTokenPayload

logger = setup_logging()
router = APIRouter()

# Convert the document to a markdown where each image is represented in base64.
async def process_document_with_images(db: Session, file: UploadFile = File(...), chatbot_data: ChatbotCreate = Form(...)) -> dict:
    processor = PDFDocumentProcessor(db, file, chatbot_data)
    return await processor.process_document()

# Chat with a chatbot
@router.post("/chatbot-conversation/")
async def chatbot_conversation(
    background_tasks: BackgroundTasks,
    body: dict = Body({
        "prompt": "Hello, how are you?",
        "chatbot_id": str(uuid.uuid4()),
        "async_processing": False
    }),
    token: JWTLectureTokenPayload = Depends(require_token_types(allowed_types=["cognito"])),
    db: Session = Depends(get_db)):
    """
    Process a chatbot conversation using the Bedrock agent.
    If async_processing is True, the process will be handled asynchronously and notifications will be sent through AppSync.
    """
    try:
        user_id = get_user_by_cognito_id(db, token.sub).id
        
        if body.get("async_processing", False):
            # Start the async process using BackgroundTasks
            logger.info(f"Starting async processing for chatbot_id: {body.get('chatbot_id')}")
            
            # Define the task with a simpler approach using synchronous functions
            def process_async_conversation(prompt, chatbot_id, user_id, token):
                # Create a new connection for the background task
                db_task = SessionLocal()
                try:
                    logger.info(f"Executing async processing for chatbot_id: {chatbot_id}")
                    
                    # Create an event loop to execute asynchronous code
                    loop = asyncio.new_event_loop()
                    
                    # Execute the conversation in the loop
                    result = loop.run_until_complete(
                        _process_conversation_internal(db_task, prompt, chatbot_id, user_id, token)
                    )
                    
                    logger.info(f"Async processing completed for chatbot_id: {chatbot_id}")
                    return result
                except Exception as e:
                    logger.error(f"Error in async processing: {str(e)}")
                    raise
                finally:
                    db_task.close()
            
            # Add the task to the BackgroundTasks
            background_tasks.add_task(
                process_async_conversation,
                prompt=body.get("prompt"),
                chatbot_id=body.get("chatbot_id"),
                user_id=user_id,
                token=token
            )
            
            return {"message": "Chatbot conversation process started", "chatbot_id": body.get("chatbot_id")}
        
        # Original synchronous process
        start_time = time.time()
        
        processor = ChatbotProcessor(db, body.get("prompt"))
        await processor.set_agent()
        await processor.set_chatbot(body.get("chatbot_id"))
        is_external = await processor.check_if_external_chatbot()
        if is_external:
            response = await processor.process_external_conversation()
        else:
            response = await processor.process_conversation()
        processing_time = time.time() - start_time
        
        request_id = get_request_by_title(db, body.get("chatbot_id"))
        if request_id is None:
            request_id = handle_save_request(db, body.get("chatbot_id"), user_id, "content_query_service")
        else:
            request_id = request_id.id
        
        await process_and_save_analytics(db, request_id, 'anthropic.claude-3-7-sonnet-20250219-v1:0', body.get("prompt"), response.get("response"), processing_time)

        return response
    except Exception as e:
        logger.error(f"Error in chatbot_conversation: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

# New function to execute the internal conversation processing
async def _process_conversation_internal(db, prompt, chatbot_id, user_id, token):
    """
    Internal function to process the conversation
    """
    app_sync = AsyncManager()
    app_sync.set_parameters()
    
    try:
        start_time = time.time()
        
        processor = ChatbotProcessor(db, prompt)
        await processor.set_agent()
        await processor.set_chatbot(chatbot_id)
        is_external = await processor.check_if_external_chatbot()
        
        # Process the conversation
        if is_external:
            response = await processor.process_external_conversation()
        else:
            response = await processor.process_conversation()
        
        processing_time = time.time() - start_time
        
        # Save the results
        request_id = get_request_by_title(db, chatbot_id)
        if request_id is None:
            request_id = handle_save_request(db, chatbot_id, user_id, "content_query_service")
        else:
            request_id = request_id.id
        
        await process_and_save_analytics(db, request_id, 'anthropic.claude-3-7-sonnet-20250219-v1:0', prompt, response.get("response"), processing_time)

        # Notify the completion
        await app_sync.send_event_with_notification(
            db=db,
            user_id=user_id,
            service_id="chatbot_conversation",
            title="chatbot_conversation.completed.title",
            body="chatbot_conversation.completed.body",
            data={
                "chatbot_id": chatbot_id,
                "stage": "completed",
                "response": response
            },
            notification_type="success",
            priority="normal",
            actions=[
                {
                    "label": "notifications.buttons.view",
                    "action": "navigate",
                    "url": f"/chatbot/{chatbot_id}"
                }
            ]
        )
        
        return response
    except Exception as e:
        # Notify the error
        await app_sync.send_event_with_notification(
            db=db,
            user_id=user_id,
            service_id="chatbot_conversation",
            title="chatbot_conversation.error.title",
            body="chatbot_conversation.error.body",
            data={
                "chatbot_id": chatbot_id,
                "stage": "error",
                "error": str(e)
            },
            notification_type="error",
            priority="high",
            actions=[
                {
                    "label": "notifications.buttons.view",
                    "action": "navigate",
                    "url": f"/chatbot/{chatbot_id}"
                }
            ]
        )
        raise

async def process_resource_data(db: Session, resource_data: str, files: List[UploadFile]) -> tuple[List[UploadFile], str]:
    if not resource_data:
        return files, resource_data
        
    try:
        resource_data_json = json.loads(resource_data)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid resource_data")
    
    if resource_data_json.get("resource_type") == "course_material":
        material_id = resource_data_json.get("resource_id")
        material = get_material(db, material_id)
        if material:
            blob = await get_s3_object(material.s3_uri)
            content = blob["Body"].read()
            file = UploadFile(file=io.BytesIO(content), filename=material.title)
            files.append(file)
    else:
        resource_data = json.dumps(resource_data_json)
    
    return files, resource_data

# Start a new chatbot
@router.post("/start-chatbot")
async def start_chatbot(
    background_tasks: BackgroundTasks,
    chatbot_name: str = Form(...),
    system_prompt: str = Form(default=""),
    resource_data: str = Form(default=""),
    files: List[UploadFile] = File([]),
    async_processing: bool = Form(default=False),
    token: JWTLectureTokenPayload = Depends(require_token_types(allowed_types=["cognito"])),
    db: Session = Depends(get_db)):

    cognito_id = token.sub
    user = get_user_by_cognito_id(db, cognito_id)
    if not user:
        raise HTTPException(status_code=404, detail=f"User with cognito_id {cognito_id} not found")
    
    if (files is None or len(files) == 0) and resource_data == "":
        raise HTTPException(status_code=400, detail="Files or resource_data are required")
    
    if system_prompt == "":
        system_prompt = "You are a helpful assistant that can answer questions about the user's materials."

    resource_data = resource_data or ""
    files = files or []
    
    files, resource_data = await process_resource_data(db, resource_data, files)
    chatbot_id = str(uuid.uuid4())

    if async_processing:
        # Start the async process using BackgroundTasks
        logger.info(f"Starting async processing for chatbot creation: {chatbot_id}")
        
        # Read file contents before passing to background task to avoid "closed file" error
        file_contents = []
        for file in files:
            try:
                content = await file.read()
                file_contents.append({
                    "filename": file.filename,
                    "content": content,
                    "content_type": file.content_type
                })
            except Exception as e:
                logger.error(f"Error reading file {file.filename}: {str(e)}")
                raise HTTPException(status_code=500, detail=f"Error reading file {file.filename}")
        
        # Define the task with a simpler approach using synchronous functions
        def process_async_chatbot_creation(chatbot_name, system_prompt, resource_data, file_contents, chatbot_id, user_id, token):
            # Create a new connection for the background task
            db_task = SessionLocal()
            try:
                logger.info(f"Executing async chatbot creation for chatbot_id: {chatbot_id}")
                
                # Create an event loop to execute asynchronous code
                loop = asyncio.new_event_loop()
                
                # Execute the chatbot creation in the loop
                result = loop.run_until_complete(
                    _process_chatbot_creation_internal(db_task, chatbot_name, system_prompt, resource_data, file_contents, chatbot_id, user_id, token)
                )
                
                logger.info(f"Async chatbot creation completed for chatbot_id: {chatbot_id}")
                return result
            except Exception as e:
                logger.error(f"Error in async chatbot creation: {str(e)}")
                raise
            finally:
                db_task.close()
        
        # Add the task to the BackgroundTasks
        background_tasks.add_task(
            process_async_chatbot_creation,
            chatbot_name=chatbot_name,
            system_prompt=system_prompt,
            resource_data=resource_data,
            file_contents=file_contents,
            chatbot_id=chatbot_id,
            user_id=user.id,
            token=token
        )
        
        return {"message": "Chatbot creation process started", "chatbot_id": chatbot_id}
    
    # Original synchronous process
    try:
        chatbot_data = ChatbotCreate(
            id=chatbot_id,
            name=f"{chatbot_name}",
            system_prompt=system_prompt,
            user_id=user.id,
            status="IN_PROGRESS",
            session_id=chatbot_id,
            memory_id=chatbot_id,
            resource_data=resource_data
        )
        chatbot = await create_chatbot(db, chatbot_data)
        if not chatbot:
            raise HTTPException(status_code=500, detail="Error creating chatbot")
        for file in files:
            await process_document_with_images(db,file, chatbot_data)
        
        # Update chatbot status to processing
        await update_chatbot_status(db, chatbot_id, "COMPLETED")

        return {
            "chatbot_id": chatbot.id,
            "chatbot_name": chatbot.name
        }
    except Exception as e:
        await delete_chatbot_by_id(db, chatbot_id)
        raise HTTPException(status_code=500, detail=str(e))

# New function to execute the internal chatbot creation processing
async def _process_chatbot_creation_internal(db, chatbot_name, system_prompt, resource_data, file_contents, chatbot_id, user_id, token):
    """
    Internal function to process the chatbot creation
    """
    app_sync = AsyncManager()
    app_sync.set_parameters()
    
    try:
        
        chatbot_data = ChatbotCreate(
            id=chatbot_id,
            name=f"{chatbot_name}",
            system_prompt=system_prompt,
            user_id=user_id,
            status="IN_PROGRESS",
            session_id=chatbot_id,
            memory_id=chatbot_id,
            resource_data=resource_data
        )
        
        chatbot = await create_chatbot(db, chatbot_data)
        if not chatbot:
            raise Exception("Error creating chatbot")
        
        # Notify the start of processing
        await app_sync.send_event_with_notification(
            db=db,
            user_id=user_id,
            service_id="start_chatbot",
            title="start_chatbot.processing.title",
            body="start_chatbot.processing.body",
            data={
                "chatbot_id": chatbot_id,
                "stage": "processing"
            },
            notification_type="info",
            priority="normal"
        )

        # Process each file
        for file_data in file_contents:
            # Recreate UploadFile object from the content
            file = UploadFile(
                file=io.BytesIO(file_data["content"]),
                filename=file_data["filename"]
            )
            await process_document_with_images(db, file, chatbot_data)
        
        # Update chatbot status to completed
        await update_chatbot_status(db, chatbot_id, "COMPLETED")

        # Notify the completion
        await app_sync.send_event_with_notification(
            db=db,
            user_id=user_id,
            service_id="start_chatbot",
            title="start_chatbot.completed.title",
            body="start_chatbot.completed.body",
            data={
                "chatbot_id": chatbot_id,
                "chatbot_name": chatbot.name,
                "stage": "completed"
            },
            notification_type="success",
            priority="normal",
            actions=[
                {
                    "label": "notifications.buttons.view",
                    "action": "navigate",
                    "url": f"/chatbot/{chatbot_id}"
                }
            ]
        )
        
        return {
            "chatbot_id": chatbot.id,
            "chatbot_name": chatbot.name
        }
    except Exception as e:
        # Clean up on error
        await delete_chatbot_by_id(db, chatbot_id)
        
        # Notify the error
        await app_sync.send_event_with_notification(
            db=db,
            user_id=user_id,
            service_id="chatbot_conversation",
            title="chatbot_conversation.error.title",
            body="chatbot_conversation.error.body",
            data={
                "chatbot_id": chatbot_id,
                "stage": "error",
                "error": str(e)
            },
            notification_type="error",
            priority="high"
        )
        raise

# Get all chatbots by user ID
@router.get("/")
async def get_chatbots(
    token: JWTLectureTokenPayload = Depends(require_token_types(allowed_types=["cognito"])),
    db: Session = Depends(get_db)):
    cognito_id = token.sub
    user = get_user_by_cognito_id(db, cognito_id)
    if not user:
        raise HTTPException(
            status_code=404,
            detail=f"User with cognito_id {cognito_id} not found"
        )
    
    chatbots = await get_chatbots_by_user_id(db, user.id)

    result = []
    for chatbot in chatbots:
        # Get is_main chatbot material
        is_main_chatbot_material = await get_chatbot_materials_by_chatbot_id_with_is_main_true(db, chatbot.id)
        
        if is_main_chatbot_material is None:
            is_main_chatbot_material = []
        else:
            is_main_chatbot_material = [
                {
                    "id": material.id,
                    "name": material.title
                }
                for material in is_main_chatbot_material
            ]
        
        result.append({
            "chatbot_id": chatbot.id,
            "chatbot_name": chatbot.name,
            "chatbot_system_prompt": chatbot.system_prompt,
            "updated_at": chatbot.updated_at,
            "materials": is_main_chatbot_material,
            "status": chatbot.status
        })

    return result

# Get all chatbot resources
@router.get("/resources")
async def get_chatbot_resources(
    token: JWTLectureTokenPayload = Depends(require_token_types(allowed_types=["cognito"])),
    db: Session = Depends(get_db)):
    cognito_id = token.sub
    user = get_user_by_cognito_id(db, cognito_id)
    if not user:
        raise HTTPException(
            status_code=404,
            detail=f"User with cognito_id {cognito_id} not found"
        )
    
    chatbots = await get_chatbots_by_user_id(db, user.id)

    resources = []

    for chatbot in chatbots:
        # Get is_main chatbot material
        is_main_chatbot_material = await get_chatbot_materials_by_chatbot_id_with_is_main_true(db, chatbot.id)
        
        if is_main_chatbot_material is None:
            is_main_chatbot_material = []
        else:
            is_main_chatbot_material = [
                {
                    "resource_id": material.id,
                    "resource_name": material.title,
                    "resource_type": "chatbot_material",
                }
                for material in is_main_chatbot_material
            ]
        resources.extend(is_main_chatbot_material)

    # Get all courses from the user
    courses = get_teacher_courses(db, user.id)
    for course in courses:
        # Get all materials from the course
        materials = get_materials_by_course(db, course.id)
        for material in materials:
            if material.type == "application/pdf":
                resources.append({
                    "resource_id": material.id,
                    "resource_name": material.title,
                    "resource_type": "course_material",
                })
        
        resources.append({
            "resource_id": course.knowledge_base_id,
            "resource_name": course.title,
            "resource_type": "course_knowledge_base" if not course.settings else "knowledge_base_manager",
        })
    
    return resources
    
# Get a chatbot by ID
@router.get("/{chatbot_id}")
async def get_chatbot(
    chatbot_id: str,
    token: JWTLectureTokenPayload = Depends(require_token_types(allowed_types=["cognito", "lti_services"])),
    db: Session = Depends(get_db)
):
    if token.token_type == 'cognito':
        # Check if the user exists
        cognito_id = token.sub
        user = get_user_by_cognito_id(db, cognito_id)
        if not user:
            raise HTTPException(
                status_code=404,
                detail=f"User with cognito_id {cognito_id} not found"
            )

    chatbot = await get_chatbot_by_id(db, chatbot_id)
    if not chatbot:
        raise HTTPException(
            status_code=404,
            detail=f"Chatbot with id {chatbot_id} not found"
        )
    # Init the chatbot processor
    print("Init the chatbot processor")
    processor = ChatbotProcessor(db, "")
    print("Set the agent")
    await processor.set_agent()
    print("Get all messages of the chatbot")
    # Get all messages of the chatbot
    messages = await get_messages_by_chatbot_id(db, chatbot_id)
    processed_messages = []

    if messages is None:
        messages = []
    else:
        for message in messages:
            message.content = await processor.process_markdown_images(message.content)
            processed_messages.append(
                {
                    "id": message.id,
                    "content": message.content,
                    "role": message.role,
                    "created_at": message.created_at,
                    "updated_at": message.updated_at
                }
            )


    return {
        "chatbot_id": chatbot.id,
        "chatbot_name": chatbot.name,
        "chatbot_status": chatbot.status,
        "chatbot_system_prompt": chatbot.system_prompt,
        "messages": processed_messages
    }

# Delete a chatbot by ID
@router.delete("/{chatbot_id}")
async def delete_chatbot(
    chatbot_id: str,
    token: JWTLectureTokenPayload = Depends(require_token_types(allowed_types=["cognito"])),
    db: Session = Depends(get_db)):
    cognito_id = token.sub
    user = get_user_by_cognito_id(db, cognito_id)
    if not user:
        raise HTTPException(
            status_code=404,
            detail=f"User with cognito_id {cognito_id} not found"
        )

    await delete_chatbot_by_id(db, chatbot_id)
    return {
        "message": f"Chatbot with id {chatbot_id} deleted successfully"
    }

# Conversation access
@router.post("/conversation-access")
async def conversation_access(
    request: ConversationAccessRequest,
    id: str = Header(..., description="Course ID"),
    conversation_access_token: str = Header(..., description="Conversation access token"),
    db: Session = Depends(get_db)
):
    """
    Validate conversation access by checking the access token.
    Start a conversation using the prompt, agent_id, alias_id and session_id.
    """
    try:
        # Create an asynchronous task for processing
        async def process_conversation():
            # Search for the course in the database
            if not id:
                raise HTTPException(
                    status_code=400,
                    detail="Course ID required"
                )
            
            # Get course data asynchronously
            course = await asyncio.to_thread(get_course, db, id)
            if not course:
                raise HTTPException(
                    status_code=404,
                    detail="Course not found"
                )

            if not request.session_id:
                request.session_id = str(uuid.uuid4())
                request.prompt = f"""<USER_PROMPT>{request.prompt}</USER_PROMPT><ID>{id}</ID>"""

            # Process the conversation access token
            processed_token = conversation_access_token
            if conversation_access_token.startswith("Bearer "):
                processed_token = conversation_access_token.split(" ")[1]
            else:
                raise HTTPException(
                    status_code=403,
                    detail="Invalid conversation access token"
                )

            # Verify that the access token matches
            if course.conversation_access_token != processed_token:
                raise HTTPException(
                    status_code=403,
                    detail="Invalid conversation access token"
                )

            start_time = time.time()
            
            # Initialize processors asynchronously
            analytics_processor = AnalyticsProcessor(db)
            processor = ChatbotProcessor(db, request.prompt, is_external=True, analytics_processor=analytics_processor)
            
            # Set up the processor asynchronously
            await processor.set_agent()
            await processor.set_course(id, request.session_id)
            processor.set_save_conversation(False)
            
            # Process the conversation asynchronously
            response = await processor.process_external_conversation()
            user_id = processor.get_user_id()
            processing_time = time.time() - start_time
            
            # Save analytics asynchronously if user_id exists
            if user_id:
                request_id = await asyncio.to_thread(
                    handle_save_request,
                    db=db,
                    title="external_chatbot_conversation",
                    user_id=user_id,
                    service_code="content_query_service"
                )
                if request_id:
                    await process_and_save_analytics(
                        db=db,
                        request_id=request_id,
                        model='default',
                        request_prompt=request.prompt,
                        response=response.get("response"),
                        processing_time=processing_time
                    )
            
            # Get analytics data
            request_tokens, response_tokens, estimated_cost = analytics_processor.get_analytics()

            # Process markdown images in response
            processed_response = await processor.process_markdown_images(response.get("response"))

            # Return the processed data
            return {
                "id": id,
                "prompt": request.prompt,
                "session_id": request.session_id,
                "status": "success",
                "message": processed_response,
                "tokens_input": request_tokens,
                "tokens_output": response_tokens,
                "total_tokens": request_tokens + response_tokens,
                "total_cost": estimated_cost
            }

        # Start processing in the background
        return await process_conversation()

    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
