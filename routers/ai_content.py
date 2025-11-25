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

"""
Router for AI endpoints
"""
from fastapi import APIRouter, HTTPException, Depends, BackgroundTasks
from typing import Optional
import asyncio
import time

from requests import Session

import time
from database.crud import get_user_by_cognito_id
from database.db import get_db, SessionLocal
from database.schemas import (
    AIRequest, 
    GenerateRoutinesRequest,  AIResponse,
    HybridResponse
)
from services.content_storage_service import ContentStorageService
from services.ai_service import AIService
from services.aws_service import AWSService
from utility.auth import require_token_types
from utility.async_manager import AsyncManager
from utility.tokens import JWTLectureTokenPayload
from function.llms.bedrock_invoke import get_caller_identity, get_model_by_id, get_model_region, is_inference_model, get_default_model_ids

router = APIRouter()

# Internal function to process AI generation with notifications
async def _process_ai_generation_internal(db, user_id, prompt, task_type):
    """
    Internal function to process AI generation with notifications
    """
    app_sync = AsyncManager()
    app_sync.set_parameters()
    
    try:
        # Notify the start of processing
        await app_sync.send_event_with_notification(
            db=db,
            user_id=str(user_id),
            service_id="ai_content_generation",
            title="ai_content.processing.title",
            body="ai_content.processing.body",
            data={
                "task_type": task_type,
                "stage": "processing"
            },
            notification_type="info",
            priority="normal"
        )

        # Process the AI generation
        ai_service = AIService()
        result = await ai_service.generate_content(prompt=prompt)

        # Notify the completion
        await app_sync.send_event_with_notification(
            db=db,
            user_id=str(user_id),
            service_id="ai_content_generation",
            title="ai_content.completed.title",
            body="ai_content.completed.body",
            data={
                "task_type": task_type,
                "stage": "completed",
                "result_preview": result[:100] + "..." if len(result) > 100 else result
            },
            notification_type="success",
            priority="normal"
        )
        
        return result
    except Exception as e:
        # Notify the error
        await app_sync.send_event_with_notification(
            db=db,
            user_id=str(user_id),
            service_id="ai_content_generation",
            title="ai_content.error.title",
            body="ai_content.error.body",
            data={
                "task_type": task_type,
                "stage": "error",
                "error": str(e)
            },
            notification_type="error",
            priority="high"
        )
        raise

# Internal function to process AI hybrid generation with notifications
async def _process_ai_hybrid_generation_internal(db, user_id, prompt_data, system_prompt, task_type):
    """
    Internal function to process AI hybrid generation with notifications
    """
    app_sync = AsyncManager()
    app_sync.set_parameters()
    
    try:
        # Notify the start of processing
        await app_sync.send_event_with_notification(
            db=db,
            user_id=str(user_id),
            service_id="ai_hybrid_generation",
            title="ai_hybrid.processing.title",
            body="ai_hybrid.processing.body",
            data={
                "task_type": task_type,
                "stage": "processing",
                "routines_count": len(prompt_data.routines) if prompt_data.routines else 0
            },
            notification_type="info",
            priority="normal"
        )

        # Process the AI hybrid generation
        ai_service = AIService()
        result = await ai_service.generate_routines_content_hybrid(
            prompt_data=prompt_data,
            system_prompt=system_prompt
        )

        # Notify the completion
        await app_sync.send_event_with_notification(
            db=db,
            user_id=str(user_id),
            service_id="ai_hybrid_generation",
            title="ai_hybrid.completed.title",
            body="ai_hybrid.completed.body",
            data={
                "task_type": task_type,
                "stage": "completed",
                "routines_count": len(prompt_data.routines) if prompt_data.routines else 0,
                "total_items": result.get("total_items", 0)
            },
            notification_type="success",
            priority="normal"
        )
        
        return result
    except Exception as e:
        # Notify the error
        await app_sync.send_event_with_notification(
            db=db,
            user_id=str(user_id),
            service_id="ai_hybrid_generation",
            title="ai_hybrid.error.title",
            body="ai_hybrid.error.body",
            data={
                "task_type": task_type,
                "stage": "error",
                "error": str(e)
            },
            notification_type="error",
            priority="high"
        )
        raise

# Internal function to process AI agent generation with notifications
async def _process_ai_agent_generation_internal(db, user_id, prompt, task_type):
    """
    Internal function to process AI agent generation with notifications
    """
    app_sync = AsyncManager()
    app_sync.set_parameters()
    
    try:
        # Notify the start of processing
        await app_sync.send_event_with_notification(
            db=db,
            user_id=str(user_id),
            service_id="ai_agent_generation",
            title="ai_agent.processing.title",
            body="ai_agent.processing.body",
            data={
                "task_type": task_type,
                "stage": "processing"
            },
            notification_type="info",
            priority="normal"
        )

        # Process the AI agent generation
        ai_service = AIService()
        result = await ai_service.generate_text_with_agent(prompt=prompt)

        # Notify the completion
        await app_sync.send_event_with_notification(
            db=db,
            user_id=str(user_id),
            service_id="ai_agent_generation",
            title="ai_agent.completed.title",
            body="ai_agent.completed.body",
            data={
                "task_type": task_type,
                "stage": "completed",
                "result_preview": result[:100] + "..." if len(result) > 100 else result
            },
            notification_type="success",
            priority="normal"
        )
        
        return result
    except Exception as e:
        # Notify the error
        await app_sync.send_event_with_notification(
            db=db,
            user_id=str(user_id),
            service_id="ai_agent_generation",
            title="ai_agent.error.title",
            body="ai_agent.error.body",
            data={
                "task_type": task_type,
                "stage": "error",
                "error": str(e)
            },
            notification_type="error",
            priority="high"
        )
        raise

@router.post("/generate", response_model=AIResponse)
async def generate_content(
    request: AIRequest, 
    async_processing: bool = False,
    background_tasks: BackgroundTasks = None,
    token: JWTLectureTokenPayload = Depends(require_token_types(allowed_types=["cognito"])), 
    db: Session = Depends(get_db)
):
    """
    Generate content using AI
    
    Args:
        request (AIRequest): Request with prompt and optional parameters
        async_processing (bool): Whether to process asynchronously
        background_tasks (BackgroundTasks): Background tasks for async processing
        
    Returns:
        AIResponse: Response with generated content
    """

    # Verify user token
    user = get_user_by_cognito_id(db, token.sub)
    user_id = user.id if user else None

    if user_id is None:
        raise HTTPException(status_code=401, detail="Unauthorized")

    try:
        if async_processing and background_tasks:
            # Async processing with AppSync
            def process_async_ai_generation(prompt, user_id, task_type):
                # Create a new connection for the background task
                db_task = SessionLocal()
                try:
                    # Create an event loop to execute asynchronous code
                    loop = asyncio.new_event_loop()
                    
                    # Execute the AI generation in the loop
                    result = loop.run_until_complete(
                        _process_ai_generation_internal(db_task, user_id, prompt, task_type)
                    )
                    
                    return result
                except Exception as e:
                    raise
                finally:
                    db_task.close()
            
            # Add task to background
            background_tasks.add_task(
                process_async_ai_generation,
                prompt=request.prompt,
                user_id=user_id,
                task_type="generate_content"
            )
            
            return AIResponse(
                success=True,
                message="Content generation started in background",
                html_content="Processing started. You will be notified when complete."
            )
        else:
            # Synchronous processing
            ai_service = AIService()
            result = await ai_service.generate_content(
                prompt=request.prompt
            )
            
            return AIResponse(
                success=True,
                message="Content generated successfully",
                html_content=result
            )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error generating content: {str(e)}"
        )

@router.get("/status", response_model=AIResponse)
async def get_ai_status(token: JWTLectureTokenPayload = Depends(require_token_types(allowed_types=["cognito"]))):
    """
    Get the status of the AI service
    
    Returns:
        AIResponse: Status of the AI service
    """
    try:
        ai_service = AIService()
        status = await ai_service.get_status()
        
        return AIResponse(
            success=True,
            message="AI service is working correctly",
            html_content=status
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error getting AI status: {str(e)}"
        )


@router.post("/generate-routines-hybrid", response_model=HybridResponse)
async def generate_routines_content_hybrid(
    request: GenerateRoutinesRequest, 
    async_processing: bool = False,
    background_tasks: BackgroundTasks = None,
    token: JWTLectureTokenPayload = Depends(require_token_types(allowed_types=["cognito"])), 
    db: Session = Depends(get_db)
):
    """
    Generate HTML content for multiple routines using hybrid approach
    
    Args:
        request (GenerateRoutinesRequest): Request with contexts, routines and system_prompt
        async_processing (bool): Whether to process asynchronously
        background_tasks (BackgroundTasks): Background tasks for async processing
        
    Returns:
        HybridResponse: Response with simple and complex content separated
    """
    try:
        user = get_user_by_cognito_id(db, token.sub)
        user_id = user.id if user else None

        if user_id is None:
            raise HTTPException(status_code=401, detail="Unauthorized")
        
        # Validate that the arrays are not empty        
        if not request.prompt.routines:
            raise HTTPException(
                status_code=400,
                detail="The routines array cannot be empty"
            )
        
        if async_processing and background_tasks:
            # Async processing with AppSync
            def process_async_ai_hybrid_generation(prompt_data, system_prompt, user_id, task_type):
                # Create a new connection for the background task
                db_task = SessionLocal()
                try:
                    # Create an event loop to execute asynchronous code
                    loop = asyncio.new_event_loop()
                    
                    # Execute the AI hybrid generation in the loop
                    result = loop.run_until_complete(
                        _process_ai_hybrid_generation_internal(db_task, user_id, prompt_data, system_prompt, task_type)
                    )
                    
                    return result
                except Exception as e:
                    raise
                finally:
                    db_task.close()
            
            # Add task to background
            background_tasks.add_task(
                process_async_ai_hybrid_generation,
                prompt_data=request.prompt,
                system_prompt=request.system_prompt,
                user_id=user_id,
                task_type="generate_hybrid"
            )
            
            return HybridResponse(
                success=True,
                message="Hybrid generation started in background",
                simple_content="Processing started. You will be notified when complete.",
                complex_content="",
                total_items=0
            )
        else:
            # Synchronous processing
            ai_service = AIService()
            result = await ai_service.generate_routines_content_hybrid(
                prompt_data=request.prompt,
                system_prompt=request.system_prompt
            )
            
            return HybridResponse(
                success=True,
                message="Hybrid content generated successfully",
                simple_content=result["simple_content"],
                complex_content=result["complex_content"],
                total_items=result["total_items"]
            )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error generating hybrid content: {str(e)}"
        )

@router.post("/generate-with-agent", response_model=AIResponse)
async def generate_text_with_agent(
    request: AIRequest, 
    async_processing: bool = False,
    background_tasks: BackgroundTasks = None,
    token: JWTLectureTokenPayload = Depends(require_token_types(allowed_types=["cognito"])), 
    db: Session = Depends(get_db)
):
    """
    Generate content using the Strands Agent
    
    Args:
        request (AIRequest): Request with prompt
        async_processing (bool): Whether to process asynchronously
        background_tasks (BackgroundTasks): Background tasks for async processing
        
    Returns:
        AIResponse: Response with the content generated by the agent
    """
    try:
        user = get_user_by_cognito_id(db, token.sub)
        user_id = user.id if user else None

        if user_id is None:
            raise HTTPException(status_code=401, detail="Unauthorized")
        
        if async_processing and background_tasks:
            # Async processing with AppSync
            def process_async_ai_agent_generation(prompt, user_id, task_type):
                # Create a new connection for the background task
                db_task = SessionLocal()
                try:
                    # Create an event loop to execute asynchronous code
                    loop = asyncio.new_event_loop()
                    
                    # Execute the AI agent generation in the loop
                    result = loop.run_until_complete(
                        _process_ai_agent_generation_internal(db_task, user_id, prompt, task_type)
                    )
                    
                    return result
                except Exception as e:
                    raise
                finally:
                    db_task.close()
            
            # Add task to background
            background_tasks.add_task(
                process_async_ai_agent_generation,
                prompt=request.prompt,
                user_id=user_id,
                task_type="generate_with_agent"
            )
            
            return AIResponse(
                success=True,
                message="Agent generation started in background",
                html_content="Processing started. You will be notified when complete."
            )
        else:
            # Synchronous processing
            ai_service = AIService()
            result = await ai_service.generate_text_with_agent(
                prompt=request.prompt
            )
            
            return AIResponse(
                success=True,
                message="Content generated successfully with Agent",
                html_content=result
            )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error generating content with Agent: {str(e)}"
        )

@router.get("/serve-iframe-content")
async def serve_iframe_content(content: str = "", token: JWTLectureTokenPayload = Depends(require_token_types(allowed_types=["cognito"]))):
    """
    Serve HTML content for iframes with complete styles
    
    Args:
        content: HTML content encoded in base64
        
    Returns:
        HTMLResponse: Full HTML content for the iframe
    """
    try:
        from fastapi.responses import HTMLResponse
        import base64
        
        # Decode the HTML content
        if content:
            try:
                html_content = base64.b64decode(content).decode('utf-8')
            except:
                html_content = content
        else:
            html_content = "<p>No content provided</p>"
        
        # Create full HTML with necessary styles and scripts
        full_html = f"""
        <!DOCTYPE html>
        <html lang="es">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>Interactive Content</title>
            <style>
                body {{
                    font-family: Arial, sans-serif;
                    margin: 0;
                    padding: 20px;
                    background-color: #ffffff;
                    color: #333333;
                    line-height: 1.6;
                }}
                * {{
                    box-sizing: border-box;
                }}
                h1, h2, h3, h4, h5, h6 {{
                    color: #2c3e50;
                    margin-top: 20px;
                    margin-bottom: 10px;
                }}
                p {{
                    margin-bottom: 15px;
                }}
                table {{
                    border-collapse: collapse;
                    width: 100%;
                    margin: 15px 0;
                    box-shadow: 0 2px 4px rgba(0,0,0,0.1);
                }}
                th, td {{
                    border: 1px solid #ddd;
                    padding: 12px;
                    text-align: left;
                }}
                th {{
                    background-color: #f8f9fa;
                    font-weight: bold;
                    color: #495057;
                }}
                tr:nth-child(even) {{
                    background-color: #f8f9fa;
                }}
                input, button, select, textarea {{
                    padding: 10px;
                    border: 1px solid #ddd;
                    border-radius: 6px;
                    font-size: 14px;
                    transition: border-color 0.3s ease;
                }}
                input:focus, textarea:focus, select:focus {{
                    outline: none;
                    border-color: #007bff;
                    box-shadow: 0 0 0 2px rgba(0,123,255,0.25);
                }}
                button {{
                    background-color: #007bff;
                    color: white;
                    cursor: pointer;
                    border: none;
                    transition: background-color 0.3s ease;
                }}
                button:hover {{
                    background-color: #0056b3;
                }}
                canvas {{
                    max-width: 100%;
                    height: auto;
                    border-radius: 8px;
                    box-shadow: 0 4px 6px rgba(0,0,0,0.1);
                }}
                .chart-container {{
                    position: relative;
                    height: 300px;
                    width: 100%;
                    margin: 20px 0;
                }}
                .form-group {{
                    margin-bottom: 15px;
                }}
                .form-group label {{
                    display: block;
                    margin-bottom: 5px;
                    font-weight: bold;
                    color: #495057;
                }}
                .alert {{
                    padding: 12px;
                    border-radius: 6px;
                    margin: 15px 0;
                }}
                .alert-info {{
                    background-color: #d1ecf1;
                    border: 1px solid #bee5eb;
                    color: #0c5460;
                }}
                .alert-success {{
                    background-color: #d4edda;
                    border: 1px solid #c3e6cb;
                    color: #155724;
                }}
                .alert-warning {{
                    background-color: #fff3cd;
                    border: 1px solid #ffeaa7;
                    color: #856404;
                }}
                .alert-danger {{
                    background-color: #f8d7da;
                    border: 1px solid #f5c6cb;
                    color: #721c24;
                }}
            </style>
        </head>
        <body>
            {html_content}
        </body>
        </html>
        """
        
        return HTMLResponse(content=full_html, media_type="text/html")
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error serving HTML content: {str(e)}"
        )

@router.delete("/generated-content/{content_id}")
async def delete_generated_content(
    content_id: str,
    token: JWTLectureTokenPayload = Depends(require_token_types(allowed_types=["cognito"])),
    db: Session = Depends(get_db)
):
    """
    Deletes a generated content and all its versions.
    
    Args:
        content_id: ID of the content to delete
        token: Authentication token of the user
        db: Database session
        
    Returns:
        dict: Response with the deletion status
    """
    try:
        # 1. Verify token and get user
        user = get_user_by_cognito_id(db, token.sub)
        if not user:
            raise HTTPException(status_code=401, detail="Unauthorized")
        
        # 2. Verify that the content exists and belongs to the user
        from database.crud import get_generated_content_by_id
        content = get_generated_content_by_id(db, content_id)
        
        if not content:
            raise HTTPException(
                status_code=404,
                detail="Content not found"
            )
        
        if str(content.user_id) != str(user.id):
            raise HTTPException(
                status_code=403,
                detail="You do not have permission to delete this content"
            )
        
        # 3. Delete the content using the service
        storage_service = ContentStorageService()
        success = await storage_service.delete_generated_content(db, content_id)
        
        if not success:
            raise HTTPException(
                status_code=500,
                detail="Error deleting content"
            )
        
        return {
            "success": True,
            "message": "Content deleted successfully",
            "content_id": content_id
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error deleting content: {str(e)}"
        ) 
