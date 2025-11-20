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
Router for HTML content endpoints
"""
from fastapi import APIRouter, HTTPException, Depends, BackgroundTasks
from typing import Optional
import asyncio
import uuid

from sqlalchemy.orm import Session
from database.crud import get_user_by_cognito_id
from database.db import get_db, SessionLocal
from database.schemas import (
    GenerateStructureRequest, AddHeadTagsRequest, AddScriptRequest,
    ReplaceElementRequest, AddIdentificationRequest, WrapElementRequest,
    CleanVoidRequest, HTMLResponse
)

from services.html_service import HTMLService
from utility.auth import require_token_types
from utility.tokens import JWTLectureTokenPayload
from utility.async_manager import AsyncManager

router = APIRouter()

# Internal function to process HTML structure generation with notifications
async def _process_html_structure_generation_internal(db, user_id, title, task_type):
    """
    Internal function to process HTML structure generation with notifications
    """
    app_sync = AsyncManager()
    app_sync.set_parameters()
    
    try:
        # Notify the start of processing
        await app_sync.send_event_with_notification(
            db=db,
            user_id=str(user_id),
            service_id="html_structure_generation",
            title="html_structure.processing.title",
            body="html_structure.processing.body",
            data={
                "task_type": task_type,
                "title": title,
                "stage": "processing"
            },
            notification_type="info",
            priority="normal"
        )

        # Process the HTML structure generation
        html_service = HTMLService()
        result = html_service.generate_initial_structure()

        # Notify the completion
        await app_sync.send_event_with_notification(
            db=db,
            user_id=str(user_id),
            service_id="html_structure_generation",
            title="html_structure.completed.title",
            body="html_structure.completed.body",
            data={
                "task_type": task_type,
                "title": title,
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
            service_id="html_structure_generation",
            title="html_structure.error.title",
            body="html_structure.error.body",
            data={
                "task_type": task_type,
                "title": title,
                "stage": "error",
                "error": str(e)
            },
            notification_type="error",
            priority="high"
        )
        raise

# Internal function to process HTML head tags with notifications
async def _process_html_head_tags_internal(db, user_id, html_content, tags, task_type):
    """
    Internal function to process HTML head tags with notifications
    """
    app_sync = AsyncManager()
    app_sync.set_parameters()
    
    try:
        # Notify the start of processing
        await app_sync.send_event_with_notification(
            db=db,
            user_id=str(user_id),
            service_id="html_head_tags",
            title="html_head_tags.processing.title",
            body="html_head_tags.processing.body",
            data={
                "task_type": task_type,
                "stage": "processing",
                "tags_count": len(tags) if tags else 0
            },
            notification_type="info",
            priority="normal"
        )

        # Process the HTML head tags
        html_service = HTMLService()
        result = html_service.add_head_tags(html_content, tags)

        # Notify the completion
        await app_sync.send_event_with_notification(
            db=db,
            user_id=str(user_id),
            service_id="html_head_tags",
            title="html_head_tags.completed.title",
            body="html_head_tags.completed.body",
            data={
                "task_type": task_type,
                "stage": "completed",
                "tags_count": len(tags) if tags else 0
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
            service_id="html_head_tags",
            title="html_head_tags.error.title",
            body="html_head_tags.error.body",
            data={
                "task_type": task_type,
                "stage": "error",
                "error": str(e)
            },
            notification_type="error",
            priority="high"
        )
        raise

# Internal function to process HTML add script with notifications
async def _process_html_add_script_internal(db, user_id, html_content, script, position, task_type):
    """
    Internal function to process HTML add script with notifications
    """
    app_sync = AsyncManager()
    app_sync.set_parameters()
    
    try:
        # Notify the start of processing
        await app_sync.send_event_with_notification(
            db=db,
            user_id=str(user_id),
            service_id="html_add_script",
            title="html_add_script.processing.title",
            body="html_add_script.processing.body",
            data={
                "task_type": task_type,
                "stage": "processing",
                "position": position
            },
            notification_type="info",
            priority="normal"
        )

        # Process the HTML add script
        html_service = HTMLService()
        result = html_service.add_script(html_content, script, position)

        # Notify the completion
        await app_sync.send_event_with_notification(
            db=db,
            user_id=str(user_id),
            service_id="html_add_script",
            title="html_add_script.completed.title",
            body="html_add_script.completed.body",
            data={
                "task_type": task_type,
                "stage": "completed",
                "position": position
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
            service_id="html_add_script",
            title="html_add_script.error.title",
            body="html_add_script.error.body",
            data={
                "task_type": task_type,
                "stage": "error",
                "error": str(e)
            },
            notification_type="error",
            priority="high"
        )
        raise

# Internal function to process HTML replace element with notifications
async def _process_html_replace_element_internal(db, user_id, html_content, element_id, new_content, task_type):
    """
    Internal function to process HTML replace element with notifications
    """
    app_sync = AsyncManager()
    app_sync.set_parameters()
    
    try:
        # Notify the start of processing
        await app_sync.send_event_with_notification(
            db=db,
            user_id=str(user_id),
            service_id="html_replace_element",
            title="html_replace_element.processing.title",
            body="html_replace_element.processing.body",
            data={
                "task_type": task_type,
                "stage": "processing",
                "element_id": element_id
            },
            notification_type="info",
            priority="normal"
        )

        # Process the HTML replace element
        html_service = HTMLService()
        result = html_service.replace_element_by_id(html_content, element_id, new_content)

        # Notify the completion
        await app_sync.send_event_with_notification(
            db=db,
            user_id=str(user_id),
            service_id="html_replace_element",
            title="html_replace_element.completed.title",
            body="html_replace_element.completed.body",
            data={
                "task_type": task_type,
                "stage": "completed",
                "element_id": element_id
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
            service_id="html_replace_element",
            title="html_replace_element.error.title",
            body="html_replace_element.error.body",
            data={
                "task_type": task_type,
                "stage": "error",
                "error": str(e)
            },
            notification_type="error",
            priority="high"
        )
        raise

# Internal function to process HTML validation with notifications
async def _process_html_validation_internal(db, user_id, html_content, task_type):
    """
    Internal function to process HTML validation with notifications
    """
    app_sync = AsyncManager()
    app_sync.set_parameters()
    
    try:
        # Notify the start of processing
        await app_sync.send_event_with_notification(
            db=db,
            user_id=str(user_id),
            service_id="html_validation",
            title="html_validation.processing.title",
            body="html_validation.processing.body",
            data={
                "task_type": task_type,
                "stage": "processing"
            },
            notification_type="info",
            priority="normal"
        )

        # Process the HTML validation
        html_service = HTMLService()
        result = html_service.validate_html(html_content)

        # Notify the completion
        await app_sync.send_event_with_notification(
            db=db,
            user_id=str(user_id),
            service_id="html_validation",
            title="html_validation.completed.title",
            body="html_validation.completed.body",
            data={
                "task_type": task_type,
                "stage": "completed",
                "is_valid": result
            },
            notification_type="success" if result else "warning",
            priority="normal"
        )
        
        return result
    except Exception as e:
        # Notify the error
        await app_sync.send_event_with_notification(
            db=db,
            user_id=str(user_id),
            service_id="html_validation",
            title="html_validation.error.title",
            body="html_validation.error.body",
            data={
                "task_type": task_type,
                "stage": "error",
                "error": str(e)
            },
            notification_type="error",
            priority="high"
        )
        raise

# Internal function to process HTML add identification with notifications
async def _process_html_add_identification_internal(db, user_id, html_content, identification_data, task_type):
    """
    Internal function to process HTML add identification with notifications
    """
    app_sync = AsyncManager()
    app_sync.set_parameters()
    
    try:
        # Notify the start of processing
        await app_sync.send_event_with_notification(
            db=db,
            user_id=str(user_id),
            service_id="html_add_identification",
            title="html_add_identification.processing.title",
            body="html_add_identification.processing.body",
            data={
                "task_type": task_type,
                "stage": "processing"
            },
            notification_type="info",
            priority="normal"
        )

        # Process the HTML add identification
        html_service = HTMLService()
        result = html_service.add_identification_to_elements(html_content, identification_data)

        # Notify the completion
        await app_sync.send_event_with_notification(
            db=db,
            user_id=str(user_id),
            service_id="html_add_identification",
            title="html_add_identification.completed.title",
            body="html_add_identification.completed.body",
            data={
                "task_type": task_type,
                "stage": "completed"
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
            service_id="html_add_identification",
            title="html_add_identification.error.title",
            body="html_add_identification.error.body",
            data={
                "task_type": task_type,
                "stage": "error",
                "error": str(e)
            },
            notification_type="error",
            priority="high"
        )
        raise

# Internal function to process HTML wrap element with notifications
async def _process_html_wrap_element_internal(db, user_id, html_content, element_selector, task_type):
    """
    Internal function to process HTML wrap element with notifications
    """
    app_sync = AsyncManager()
    app_sync.set_parameters()
    
    try:
        # Notify the start of processing
        await app_sync.send_event_with_notification(
            db=db,
            user_id=str(user_id),
            service_id="html_wrap_element",
            title="html_wrap_element.processing.title",
            body="html_wrap_element.processing.body",
            data={
                "task_type": task_type,
                "stage": "processing",
                "element_selector": element_selector
            },
            notification_type="info",
            priority="normal"
        )

        # Process the HTML wrap element
        html_service = HTMLService()
        result = html_service.wrap_element_with_void_divs(html_content, element_selector)

        # Notify the completion
        await app_sync.send_event_with_notification(
            db=db,
            user_id=str(user_id),
            service_id="html_wrap_element",
            title="html_wrap_element.completed.title",
            body="html_wrap_element.completed.body",
            data={
                "task_type": task_type,
                "stage": "completed",
                "element_selector": element_selector
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
            service_id="html_wrap_element",
            title="html_wrap_element.error.title",
            body="html_wrap_element.error.body",
            data={
                "task_type": task_type,
                "stage": "error",
                "error": str(e)
            },
            notification_type="error",
            priority="high"
        )
        raise

# Internal function to process HTML clean void with notifications
async def _process_html_clean_void_internal(db, user_id, html_content, task_type):
    """
    Internal function to process HTML clean void with notifications
    """
    app_sync = AsyncManager()
    app_sync.set_parameters()
    
    try:
        # Notify the start of processing
        await app_sync.send_event_with_notification(
            db=db,
            user_id=str(user_id),
            service_id="html_clean_void",
            title="html_clean_void.processing.title",
            body="html_clean_void.processing.body",
            data={
                "task_type": task_type,
                "stage": "processing"
            },
            notification_type="info",
            priority="normal"
        )

        # Process the HTML clean void
        html_service = HTMLService()
        result = html_service.clean_void_duplicates(html_content)

        # Notify the completion
        await app_sync.send_event_with_notification(
            db=db,
            user_id=str(user_id),
            service_id="html_clean_void",
            title="html_clean_void.completed.title",
            body="html_clean_void.completed.body",
            data={
                "task_type": task_type,
                "stage": "completed"
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
            service_id="html_clean_void",
            title="html_clean_void.error.title",
            body="html_clean_void.error.body",
            data={
                "task_type": task_type,
                "stage": "error",
                "error": str(e)
            },
            notification_type="error",
            priority="high"
        )
        raise

