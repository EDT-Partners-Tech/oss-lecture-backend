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

import os
import json
import time
import uuid
import aiofiles
import asyncio
from datetime import datetime
from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, UploadFile, Response
from sqlalchemy.orm import Session
from icecream import ic

from function.podcast_generator.utils import SupportedPodcastLanguage
from tasks.pdf2podcast_task import process_generate_podcast
from utility.auth import require_token_types
from utility.tokens import JWTLectureTokenPayload
from utility.aws import generate_presigned_url, delete_from_s3
from utility.service import handle_save_request, get_service_id_by_code
from utility.common import extract_text_from_pdf
from utility.analytics import process_and_save_analytics, update_processing_time
from utility.async_manager import AsyncManager
from database.db import get_db, SessionLocal
from database.schemas import PodcastCreate, PodcastStatus
from database.crud import get_request_by_id, save_podcast_to_db, get_podcast_status, get_podcast_details, get_user_by_cognito_id, get_requests_by_user_service, find_podcast_by_request_id

PODCAST_EMPTY_MESSAGE = "Podcast not found."

router = APIRouter()

@router.post("/generate", status_code=202)
async def pdf_to_podcast(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    language: SupportedPodcastLanguage = Form(SupportedPodcastLanguage.ENGLISH),
    async_processing: bool = Form(default=False),
    token: JWTLectureTokenPayload = Depends(require_token_types(allowed_types=["cognito"])),
    db: Session = Depends(get_db)
):
    try:
        start_time = time.time()
        if file:
            ic("Extracting text from PDF file")
            async with aiofiles.tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as temp_file:
                await temp_file.write(await file.read())
                temp_file_path = temp_file.name
            text = await extract_text_from_pdf(temp_file_path)
            os.remove(temp_file_path)
        else:
            raise ValueError("A PDF file is required to generate a podcast")
        
        user_id = get_user_by_cognito_id(db, token.sub).id
        request_id = handle_save_request(db, f"Podcast generation for {file.filename}", user_id, "podcast_generator")

        # Save in-progress podcast log
        podcast_log = PodcastCreate(request_id=request_id, language=language)
        podcast_id = save_podcast_to_db(db, podcast_log)

        if async_processing:
            # Start the async process using BackgroundTasks
            ic(f"Starting async processing for podcast generation: {podcast_id}")
            
            # Define the task with a simpler approach using synchronous functions
            def process_async_podcast_generation(text, language, podcast_id, user_id, token):
                # Create a new connection for the background task
                db_task = SessionLocal()
                try:
                    ic(f"Executing async podcast generation for podcast_id: {podcast_id}")
                    
                    # Create an event loop to execute asynchronous code
                    loop = asyncio.new_event_loop()
                    
                    # Execute the podcast generation in the loop
                    result = loop.run_until_complete(
                        _process_podcast_generation_internal(db_task, text, language, podcast_id, user_id, token)
                    )
                    
                    ic(f"Async podcast generation completed for podcast_id: {podcast_id}")
                    return result
                except Exception as e:
                    ic(f"Error in async podcast generation: {str(e)}")
                    raise
                finally:
                    db_task.close()
            
            # Add the task to the BackgroundTasks
            background_tasks.add_task(
                process_async_podcast_generation,
                text=text,
                language=language,
                podcast_id=podcast_id,
                user_id=user_id,
                token=token
            )
            
            return {"podcast_id": podcast_id, "status": PodcastStatus.PROCESSING}
        
        # Original synchronous process
        background_tasks.add_task(
            process_generate_podcast,
            text=text,
            language=language,
            db=db,
            podcast_id=podcast_id
        )

        processing_time = time.time() - start_time
        await process_and_save_analytics(db=db, request_id=request_id, model="default", request_prompt="", response="", processing_time=processing_time)

        return {"podcast_id": podcast_id, "status": PodcastStatus.PROCESSING}
    
    except Exception as e:
        ic(f"Error generating podcast: {str(e)}")
        if isinstance(e, ValueError):
            raise HTTPException(status_code=400, detail=str(e))
        raise HTTPException(status_code=500, detail=f"Error generating podcast: {str(e)}")

# New function to execute the internal podcast generation processing
async def _process_podcast_generation_internal(db, text, language, podcast_id, user_id, token):
    """
    Internal function to process the podcast generation
    """
    app_sync = AsyncManager()
    app_sync.set_parameters()
    
    try:
        # Notify the start of processing
        await app_sync.send_event_with_notification(
            db=db,
            user_id=str(user_id),
            service_id="podcast_generation",
            title="podcast_generation.processing.title",
            body="podcast_generation.processing.body",
            data={
                "podcast_id": str(podcast_id),
                "stage": "processing"
            },
            notification_type="info",
            priority="normal"
        )

        # Process the podcast generation
        await process_generate_podcast(
            text=text,
            language=language,
            db=db,
            podcast_id=podcast_id
        )

        # Get podcast details after completion
        podcast = get_podcast_details(db, podcast_id)

        # Notify the completion
        await app_sync.send_event_with_notification(
            db=db,
            user_id=str(user_id),
            service_id="podcast_generation",
            title="podcast_generation.completed.title",
            body="podcast_generation.completed.body",
            data={
                "podcast_id": str(podcast_id),
                "title": podcast.title if podcast else "Podcast",
                "stage": "completed"
            },
            notification_type="success",
            priority="normal",
            actions=[
                {
                    "label": "notifications.buttons.view",
                    "action": "navigate",
                    "url": f"/podcast/{podcast_id}"
                }
            ]
        )
        
        return {"podcast_id": podcast_id, "status": PodcastStatus.COMPLETED}
    except Exception as e:
        # Notify the error
        await app_sync.send_event_with_notification(
            db=db,
            user_id=str(user_id),
            service_id="podcast_generation",
            title="podcast_generation.error.title",
            body="podcast_generation.error.body",
            data={
                "podcast_id": str(podcast_id),
                "stage": "error",
                "error": str(e)
            },
            notification_type="error",
            priority="high"
        )
        raise

@router.get("/status/{podcast_id}")
async def podcast_status(
    podcast_id: uuid.UUID,
    token: JWTLectureTokenPayload = Depends(require_token_types(allowed_types=["cognito"])), 
    db: Session = Depends(get_db)
):
    status = get_podcast_status(db, podcast_id)
    
    if status == PodcastStatus.COMPLETED:
        podcast = get_podcast_details(db, podcast_id)
        update_processing_time(db, podcast.request_id)
        
    if not status:
        raise HTTPException(status_code=404, detail=PODCAST_EMPTY_MESSAGE)

    return {"podcast_id": podcast_id, "status": status}


@router.delete("/{podcast_id}")
async def delete_podcast(
    podcast_id: uuid.UUID,
    token: JWTLectureTokenPayload = Depends(require_token_types(allowed_types=["cognito"])), 
    db: Session = Depends(get_db)
):
    user_id = get_user_by_cognito_id(db, token.sub).id
    podcast = get_podcast_details(db, podcast_id)
    if not podcast:
        raise HTTPException(status_code=404, detail=PODCAST_EMPTY_MESSAGE)
    
    linked_request = get_request_by_id(db, podcast.request_id, user_id)
    if not linked_request:
        raise HTTPException(status_code=403, detail="Access denied")
    
    try:
        # Clean podcast related files from S3
        if podcast.audio_s3_uri:
            await delete_from_s3('podcast', podcast.audio_s3_uri)
        if podcast.image_s3_uri:
            await delete_from_s3('podcast', podcast.image_s3_uri)
        db.delete(podcast)
        db.commit()
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Error deleting podcast: {str(e)}")
    
    return Response(status_code=204)