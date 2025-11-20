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
import time
import asyncio
from typing import Optional
from uuid import UUID
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, BackgroundTasks
from fastapi.responses import JSONResponse
import json_repair
from pydantic import ValidationError
from requests import Session
from constants import EVALUATION_NOT_FOUND_MESSAGE, RUBRIC_NOT_FOUND_MESSAGE
from utility.auth import require_token_types
from database.db import get_db, SessionLocal
from utility.common import _clean_formatted_text, get_text_from_material_id, process_uploaded_files
from utility.aws import detect_language
from utility.service import handle_save_request
from utility.analytics import process_and_save_analytics
from database.crud import delete_evaluation_by_id, get_user_by_cognito_id, save_evaluation, save_rubric, get_rubrics, get_rubric_by_id, get_evaluations, get_evaluation_by_id, update_rubric, update_evaluation, update_evaluation_content, delete_rubric
from database.schemas import Rubric, RubricCreate, RubricUpdate, EvaluationCreate, EvaluationUpdate, PerformanceIndicator
from function.rubric.rubric_prompt import build_evaluation_prompt, build_rubric_creation_prompt
from function.llms.bedrock_invoke import invoke_bedrock_model
from utility.async_manager import AsyncManager
from utility.tokens import JWTLectureTokenPayload
from icecream import ic

router = APIRouter()

def _parse_rubric_data(rubric_data: str) -> RubricCreate:
    """Parse rubric data from JSON string."""
    try:
        data = json.loads(rubric_data)
        # Convert criteria array to dictionary format
        for indicator in data.get('indicators', []):
            criteria_dict = {}
            for criterion in indicator.get('criteria', []):
                criteria_dict[str(criterion['key'])] = criterion['description']
            indicator['criteria'] = criteria_dict
        
        print(f"Transformed data: {json.dumps(data, indent=2)}")
        return RubricCreate(**data)
    except (json.JSONDecodeError, ValidationError) as e:
        print(f"Error parsing data: {str(e)}")
        raise HTTPException(
            status_code=400,
            detail=f"Invalid rubric data format: {str(e)}"
        )

@router.post("/rubrics/")
async def create_rubric(
    files: list[UploadFile] = File(default=[], alias="files[]"),
    materials_id: Optional[list[UUID]] = Form(default=[], alias="materials[]"),
    rubric_data: Optional[str] = Form(None),
    async_processing: bool = Form(default=False),
    token: JWTLectureTokenPayload = Depends(require_token_types(allowed_types=["cognito"])),
    db: Session = Depends(get_db),
    background_tasks: BackgroundTasks = None
):
    try:
        start_time = time.time()
        print("\n=== Starting rubric creation ===")
        print(f"Files received: {[f.filename for f in files] if files else 'None'}")
        print(f"Rubric data received: {rubric_data}")

        # Initialize rubric_create and process files
        is_file = files and len(files) > 0
        rubric_create = _parse_rubric_data(rubric_data) if rubric_data else None
        source_text = await process_uploaded_files(files, False, True) if files else ""
        material_text = await get_text_from_material_id(db, materials_id) if materials_id else ""
        if material_text:
            source_text = material_text if not source_text else f"{source_text}\n\n{material_text}"

        # Save initial request to database
        user_id = get_user_by_cognito_id(db, token.sub).id
        request_id = handle_save_request(db, "Rubric Generation", user_id, "evaluations_service")

        if async_processing:
            # Asynchronous processing with BackgroundTasks
            if not background_tasks:
                raise HTTPException(status_code=500, detail="BackgroundTasks not available for asynchronous processing")
            
            # Start asynchronous processing
            background_tasks.add_task(
                _process_rubric_generation_async,
                files=files,
                materials_id=materials_id,
                rubric_data=rubric_data,
                source_text=source_text,
                user_id=user_id,
                request_id=request_id
            )
            
            return JSONResponse(content={
                "request_id": str(request_id),
                "status": "PROCESSING",
                "async": True
            })
        else:
            # Synchronous processing (original behavior)
            if source_text:
                unformatted_text = _clean_formatted_text(source_text)
                if not rubric_create:
                    language = detect_language(unformatted_text)
                    
                    creation_prompt = build_rubric_creation_prompt(source_text, language)
                    json_response = await invoke_bedrock_model(creation_prompt)
                    
                    ai_rubric = json.loads(json_response)
                    rubric_create = RubricCreate(**ai_rubric)
                else:
                    rubric_create.description = source_text if not rubric_create.description else f"{rubric_create.description}\n\n{source_text}"

            # Ensure we have a valid rubric to save
            if not rubric_create:
                raise HTTPException(status_code=400, detail="No rubric data provided")

            # Save rubric
            rubric = save_rubric(db, rubric_create, user_id)

            if is_file:
                processing_time = time.time() - start_time
                await process_and_save_analytics(db, request_id, 'default', creation_prompt, json_response, processing_time)
            
            return JSONResponse(content={"id": str(rubric.id), "name": rubric.name, "description": rubric.description})
    except HTTPException as http_error:
        raise http_error
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error creating rubric: {str(e)}")

@router.get("/rubrics/")
async def list_rubrics(
    token: JWTLectureTokenPayload = Depends(require_token_types(allowed_types=["cognito"])), 
    db: Session = Depends(get_db)
):
    try:
        user_id = get_user_by_cognito_id(db, token.sub).id
        rubrics = get_rubrics(db, user_id)
        return [{"id": r.id, "name": r.name, "description": r.description} for r in rubrics]
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error retrieving rubrics: {str(e)}")

@router.get("/rubrics/{rubric_id}", response_model=Rubric)
async def get_rubric(rubric_id: UUID, db: Session = Depends(get_db)):
    try:
        rubric = get_rubric_by_id(db, str(rubric_id))
        if not rubric:
            raise HTTPException(status_code=404, detail=RUBRIC_NOT_FOUND_MESSAGE)

        # Ensure criteria is parsed as a dictionary
        indicators = []
        for indicator in rubric.indicators:
            criteria = (
                json.loads(indicator.criteria)
                if isinstance(indicator.criteria, str)
                else indicator.criteria
            )
            indicators.append(
                PerformanceIndicator(
                    name=indicator.name,
                    weight=indicator.weight,
                    criteria=criteria,
                )
            )

        # Constructing the response
        response = {
            "id": rubric.id,
            "name": rubric.name,
            "description": rubric.description,
            "created_by": str(rubric.created_by),
            "indicators": indicators,
        }
        return response

    except HTTPException as http_error:
        raise http_error
    except ValidationError as e:
        raise HTTPException(status_code=422, detail=f"Validation error: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error retrieving rubric: {str(e)}")

@router.put("/rubrics/{rubric_id}")
async def update_one_rubric(
    rubric_id: UUID,
    rubric_data: RubricUpdate,
    token: JWTLectureTokenPayload = Depends(require_token_types(allowed_types=["cognito"])),
    db: Session = Depends(get_db)
):
    user_id = get_user_by_cognito_id(db, token.sub).id
    created_by = get_rubric_by_id(db, str(rubric_id)).created_by
    
    if user_id != created_by:
        raise HTTPException(status_code=403, detail="You are not authorized to update this rubric")
    
    try:
        updated_rubric = update_rubric(db, str(rubric_id), rubric_data)
        if not updated_rubric:
            raise HTTPException(status_code=404, detail=RUBRIC_NOT_FOUND_MESSAGE)
        return JSONResponse(content={"id": str(updated_rubric.id), "name": updated_rubric.name, "description": updated_rubric.description})
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error updating rubric: {str(e)}")

@router.delete("/rubrics/{rubric_id}")
async def delete_rubric_endpoint(
    rubric_id: UUID, 
    token: JWTLectureTokenPayload = Depends(require_token_types(allowed_types=["cognito"])), 
    db: Session = Depends(get_db)
):
    try:
        deleted_id = delete_rubric(db, str(rubric_id))
        if not deleted_id:
            raise HTTPException(status_code=404, detail=RUBRIC_NOT_FOUND_MESSAGE)
        return JSONResponse(content={"id": deleted_id})
    except HTTPException as http_error:
        raise http_error
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error deleting rubric: {str(e)}")

@router.post("/evaluate-exam/")
async def evaluate_exam(
    files: list[UploadFile] = File(default=[], alias="files[]"),
    rubric_id: UUID = Form(...),
    course_name: str = Form(...),
    student_name: str = Form(...),
    student_surname: str = Form(...),
    exam_description: str = Form(...),
    evaluation_id: Optional[int] = Form(None),
    custom_instructions: Optional[str] = Form(None),
    llm_id: Optional[str] = Form(None),
    async_processing: bool = Form(default=False),
    token: JWTLectureTokenPayload = Depends(require_token_types(allowed_types=["cognito"])),
    db: Session = Depends(get_db),
    background_tasks: BackgroundTasks = None
):
    try:
        start_time = time.time()
        print(f"Starting exam evaluation for student: {student_name} {student_surname}")
        
        if not files:
            raise HTTPException(status_code=400, detail="At least one file must be provided")
            
        source_text = await process_uploaded_files(files)
        detected_language = detect_language(source_text)

        # Step 2: Fetch rubric
        print("Step 2: Fetching rubric...")
        user_id = get_user_by_cognito_id(db, token.sub).id
        print(f"User ID: {user_id}")
        rubric = get_rubric_by_id(db, str(rubric_id))
        if not rubric:
            print(f"Rubric with ID {str(rubric_id)} not found")
            raise HTTPException(status_code=404, detail=RUBRIC_NOT_FOUND_MESSAGE)
        print(f"Found rubric: {rubric.name}")

        # Save initial request to database
        request_id = handle_save_request(db, f"{course_name}–{student_name} {student_surname}", user_id, "evaluations_service")

        if async_processing:
            # Asynchronous processing with BackgroundTasks
            if not background_tasks:
                raise HTTPException(status_code=500, detail="BackgroundTasks not available for asynchronous processing")
            
            # Start asynchronous processing
            background_tasks.add_task(
                _process_evaluation_generation_async,
                files=files,
                rubric_id=rubric_id,
                course_name=course_name,
                student_name=student_name,
                student_surname=student_surname,
                exam_description=exam_description,
                evaluation_id=evaluation_id,
                custom_instructions=custom_instructions,
                llm_id=llm_id,
                source_text=source_text,
                detected_language=detected_language,
                user_id=user_id,
                request_id=request_id
            )
            
            return JSONResponse(content={
                "request_id": str(request_id),
                "status": "PROCESSING",
                "async": True
            })
        else:
            # Synchronous processing (original behavior)
            # Step 3: Build evaluation prompt
            print("Step 3: Building evaluation prompt...")
            evaluation_prompt = build_evaluation_prompt(
                source_text, rubric, detected_language, custom_instructions
            )
            print(f"Prompt: {(evaluation_prompt)}")
            response = await invoke_bedrock_model(evaluation_prompt, llm_id)
            print("Received response from Bedrock")
            parsed_response = json.loads(json_repair.repair_json(response))
            print("Successfully parsed JSON response")

            # Step 4: Handle evaluation (new or re-evaluation)
            if evaluation_id:
                print(f"Step 4: Handling re-evaluation for evaluation ID: {evaluation_id}")
                existing_evaluation = get_evaluation_by_id(db, evaluation_id)
                if not existing_evaluation:
                    print(f"Evaluation with ID {evaluation_id} not found")
                    raise HTTPException(status_code=404, detail="Evaluation not found.")

                evaluation_data = EvaluationUpdate(
                    feedback=parsed_response.get("feedback", existing_evaluation.feedback),
                    criteria_evaluation=parsed_response.get(
                        "criteria_evaluation", existing_evaluation.criteria_evaluation
                    ),
                    overall_comments=parsed_response.get(
                        "overall_comments", existing_evaluation.overall_comments
                    ),
                    source_text=source_text,
                )
                updated_evaluation = update_evaluation(db, evaluation_id, evaluation_data)
                print("Successfully updated evaluation")
                return updated_evaluation

            # Step 5: Save new evaluation
            print("Step 5: Creating new evaluation...")
            evaluation_data = EvaluationCreate(
                rubric_id=str(rubric_id),
                course_name=course_name,
                student_name=student_name,
                student_surname=student_surname,
                exam_description=exam_description,
                feedback=parsed_response.get("feedback", ""),
                criteria_evaluation=parsed_response.get("criteria_evaluation", []),
                overall_comments=parsed_response.get("overall_comments", ""),
                source_text=source_text,
            )
            evaluation = save_evaluation(db, evaluation_data, user_id)
            print(f"Successfully created evaluation with ID: {evaluation.id}")

            model = llm_id if llm_id else "default"
            processing_time = time.time() - start_time
            await process_and_save_analytics(db, request_id, model, evaluation_prompt, response, processing_time)

            return {
                "evaluation": {
                    "id": evaluation.id,
                    "rubric_id": evaluation.rubric_id,
                    "course_name": evaluation.course_name,
                    "student_name": evaluation.student_name,
                    "student_surname": evaluation.student_surname,
                    "exam_description": evaluation.exam_description,
                    "feedback": evaluation.feedback,
                    "criteria_evaluation": evaluation.criteria_evaluation,
                    "overall_comments": evaluation.overall_comments,
                    "source_text": evaluation.source_text,
                }
            }
    except HTTPException as http_error:
        raise http_error
    except Exception as e:
        print(f"Error occurred during exam evaluation: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error evaluating exam: {str(e)}")

@router.post("/")
async def create_evaluation(
    rubric_id: UUID = Form(...),
    course_name: str = Form(...),
    student_name: str = Form(...),
    student_surname: str = Form(...),
    exam_description: str = Form(...),
    feedback: str = Form(...),
    criteria_evaluation: str = Form(...),
    overall_comments: Optional[str] = Form(None),
    source_text: str = Form(...),
    token: JWTLectureTokenPayload = Depends(require_token_types(allowed_types=["cognito"])),
    db: Session = Depends(get_db)
):
    try:
        user_id = get_user_by_cognito_id(db, token.sub).id
        parsed_criteria_evaluation = json.loads(criteria_evaluation)

        evaluation_data = EvaluationCreate(
            rubric_id=str(rubric_id),
            course_name=course_name,
            student_name=student_name,
            student_surname=student_surname,
            exam_description=exam_description,
            feedback=feedback,
            criteria_evaluation=parsed_criteria_evaluation,
            overall_comments=overall_comments,
            source_text=source_text,
        )

        evaluation = save_evaluation(db, evaluation_data, user_id)
        return {
            "id": evaluation.id,
            "rubric_id": evaluation.rubric_id,
            "course_name": evaluation.course_name,
            "student_name": evaluation.student_name,
            "student_surname": evaluation.student_surname,
            "exam_description": evaluation.exam_description,
            "feedback": evaluation.feedback,
            "criteria_evaluation": evaluation.criteria_evaluation,
            "overall_comments": evaluation.overall_comments,
            "source_text": evaluation.source_text,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error creating evaluation: {str(e)}")

@router.get("/")
async def list_evaluations(
    token: JWTLectureTokenPayload = Depends(require_token_types(allowed_types=["cognito"])), 
    db: Session = Depends(get_db)
):
    try:
        user_id = get_user_by_cognito_id(db, token.sub).id
        evaluations = get_evaluations(db, user_id)
        return [
            {
                "id": e.id,
                "rubric_id": e.rubric_id,
                "course_name": e.course_name,
                "student_name": e.student_name,
                "student_surname": e.student_surname,
                "exam_description": e.exam_description,
                "feedback": e.feedback,
                "criteria_evaluation": e.criteria_evaluation,
                "overall_comments": e.overall_comments,
                "source_text": e.source_text,
            }
            for e in evaluations
        ]
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error retrieving evaluations: {str(e)}")

@router.get("/{evaluation_id}")
async def get_evaluation(evaluation_id: UUID, db: Session = Depends(get_db)):
    try:
        evaluation = get_evaluation_by_id(db, str(evaluation_id))
        if not evaluation:
            raise HTTPException(status_code=404, detail=EVALUATION_NOT_FOUND_MESSAGE)
        
        # Load criteria evaluation as JSON if it's a string
        criteria_eval = (
            json.loads(evaluation.criteria_evaluation) 
            if isinstance(evaluation.criteria_evaluation, str)
            else evaluation.criteria_evaluation
        )
        
        rubric = get_rubric_by_id(db, str(evaluation.rubric_id))
        
        for indicator in criteria_eval:
            print(indicator)
            matching_indicator = next(
                (i for i in rubric.indicators if i.name == indicator['name']), 
                None
            )
            print(matching_indicator)
            if matching_indicator:
                indicator['weight'] = matching_indicator.weight

        return {
            "id": evaluation.id,
            "rubric_id": evaluation.rubric_id,
            "course_name": evaluation.course_name,
            "student_name": evaluation.student_name,
            "student_surname": evaluation.student_surname,
            "exam_description": evaluation.exam_description,
            "feedback": evaluation.feedback,
            "criteria_evaluation": criteria_eval,
            "overall_comments": evaluation.overall_comments,
            "source_text": evaluation.source_text,
        }
    except HTTPException as http_error:
        raise http_error
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error retrieving evaluation: {str(e)}")


@router.put("/{evaluation_id}")
async def update_evaluation(
    evaluation_id: UUID,
    course_name: Optional[str] = Form(None),
    student_name: Optional[str] = Form(None),
    student_surname: Optional[str] = Form(None),
    exam_description: Optional[str] = Form(None),
    feedback: Optional[str] = Form(None),
    criteria_evaluation: Optional[str] = Form(None),
    overall_comments: Optional[str] = Form(None),
    source_text: Optional[str] = Form(None),
    db: Session = Depends(get_db)
):
    try:
        parsed_criteria_evaluation = json.loads(criteria_evaluation) if criteria_evaluation else None

        evaluation_data = EvaluationUpdate(
            course_name=course_name,
            student_name=student_name,
            student_surname=student_surname,
            exam_description=exam_description,
            feedback=feedback,
            criteria_evaluation=parsed_criteria_evaluation,
            overall_comments=overall_comments,
            source_text=source_text,
        )

        updated_evaluation = update_evaluation(db, str(evaluation_id), evaluation_data)
        if not updated_evaluation:
            raise HTTPException(status_code=404, detail=EVALUATION_NOT_FOUND_MESSAGE)

        return {
            "id": updated_evaluation.id,
            "rubric_id": updated_evaluation.rubric_id,
            "course_name": updated_evaluation.course_name,
            "student_name": updated_evaluation.student_name,
            "student_surname": updated_evaluation.student_surname,
            "exam_description": updated_evaluation.exam_description,
            "feedback": updated_evaluation.feedback,
            "criteria_evaluation": updated_evaluation.criteria_evaluation,
            "overall_comments": updated_evaluation.overall_comments,
            "source_text": updated_evaluation.source_text,
        }
    except HTTPException as http_error:
        raise http_error
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error updating evaluation: {str(e)}")

@router.delete("/{evaluation_id}")
async def delete_evaluation(evaluation_id: UUID, db: Session = Depends(get_db)):
    try:
        deleted_id = delete_evaluation_by_id(db, evaluation_id)
        if not deleted_id:
            raise HTTPException(status_code=404, detail=EVALUATION_NOT_FOUND_MESSAGE)
        return {"id": deleted_id}
    except HTTPException as http_error:
        raise http_error
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error deleting evaluation: {str(e)}")


async def _process_rubric_generation_async(
    files: list[UploadFile],
    materials_id: Optional[list[UUID]],
    rubric_data: Optional[str],
    source_text: str,
    user_id: str,
    request_id: str
):
    """
    Asynchronous function to process rubric generation and send notifications
    """
    db = SessionLocal()
    app_sync = AsyncManager()
    app_sync.set_parameters()
    
    try:
        # First, save an empty rubric to provide immediate feedback to frontend
        empty_rubric_create = RubricCreate(
            name="",
            description="",
            indicators=[]
        )
        rubric = save_rubric(db, empty_rubric_create, user_id)
        
        # Notify start of processing with the rubric ID
        await app_sync.send_event_with_notification(
            db=db,
            user_id=str(user_id),
            service_id="rubric_generator",
            title="rubric_generator.processing.title",
            body="rubric_generator.processing.body",
            data={
                "request_id": str(request_id),
                "rubric_id": str(rubric.id),
                "stage": "processing"
            },
            notification_type="info",
            priority="normal"
        )

        # Process files and materials
        is_file = files and len(files) > 0
        rubric_create = _parse_rubric_data(rubric_data) if rubric_data else None
        
        if source_text:
            unformatted_text = _clean_formatted_text(source_text)
            if not rubric_create:
                language = detect_language(unformatted_text)
                
                creation_prompt = build_rubric_creation_prompt(source_text, language)
                json_response = await invoke_bedrock_model(creation_prompt)
                
                ai_rubric = json.loads(json_response)
                rubric_create = RubricCreate(**ai_rubric)
            else:
                rubric_create.description = source_text if not rubric_create.description else f"{rubric_create.description}\n\n{source_text}"

        # Ensure we have a valid rubric to save
        if not rubric_create:
            raise Exception("No rubric data provided")

        # Update the existing rubric with the generated content
        updated_rubric = update_rubric(db, str(rubric.id), RubricUpdate(
            name=rubric_create.name,
            description=rubric_create.description,
            indicators=rubric_create.indicators
        ))
        
        # Notify successful completion
        await app_sync.send_event_with_notification(
            db=db,
            user_id=str(user_id),
            service_id="rubric_generator",
            title="rubric_generator.completed.title",
            body="rubric_generator.completed.body",
            data={
                "request_id": str(request_id),
                "rubric_id": str(updated_rubric.id),
                "rubric_name": updated_rubric.name,
                "stage": "completed"
            },
            notification_type="success",
            priority="normal",
            actions=[
                {
                    "label": "notifications.buttons.view",
                    "action": "navigate",
                    "url": f"/rubrics/{updated_rubric.id}"
                }
            ]
        )
            
    except Exception as e:
        # General error in asynchronous processing
        try:
            await app_sync.send_event_with_notification(
                db=db,
                user_id=str(user_id),
                service_id="rubric_generator",
                title="rubric_generator.error.title",
                body="rubric_generator.error.body",
                data={
                    "request_id": str(request_id),
                    "rubric_id": str(rubric.id) if 'rubric' in locals() else None,
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


async def _process_evaluation_generation_async(
    files: list[UploadFile],
    rubric_id: UUID,
    course_name: str,
    student_name: str,
    student_surname: str,
    exam_description: str,
    evaluation_id: Optional[int],
    custom_instructions: Optional[str],
    llm_id: Optional[str],
    source_text: str,
    detected_language: str,
    user_id: str,
    request_id: str
):
    """
    Asynchronous function to process evaluation generation and send notifications
    """
    db = SessionLocal()
    app_sync = AsyncManager()
    app_sync.set_parameters()
    
    try:
        # First, save an empty evaluation to provide immediate feedback to frontend
        empty_evaluation_data = EvaluationCreate(
            rubric_id=str(rubric_id),
            course_name=course_name,
            student_name=student_name,
            student_surname=student_surname,
            exam_description=exam_description,
            feedback="",
            criteria_evaluation=[],
            overall_comments="",
            source_text=""
        )
        evaluation = save_evaluation(db, empty_evaluation_data, user_id)
        
        # Notify start of processing with the evaluation ID
        await app_sync.send_event_with_notification(
            db=db,
            user_id=str(user_id),
            service_id="evaluation_generator",
            title="evaluation_generator.processing.title",
            body="evaluation_generator.processing.body",
            data={
                "request_id": str(request_id),
                "evaluation_id": str(evaluation.id),
                "stage": "processing"
            },
            notification_type="info",
            priority="normal"
        )

        # Fetch rubric for processing
        rubric = get_rubric_by_id(db, str(rubric_id))
        if not rubric:
            raise Exception("Rubric not found")

        # Build evaluation prompt
        evaluation_prompt = build_evaluation_prompt(
            source_text, rubric, detected_language, custom_instructions
        )
        response = await invoke_bedrock_model(evaluation_prompt, llm_id)
        if not response:
            raise Exception("No response from model")
        parsed_response = json.loads(json_repair.repair_json(response))

        # Handle evaluation (new or re-evaluation)
        if evaluation_id:
            # Re-evaluation: update existing evaluation
            existing_evaluation = get_evaluation_by_id(db, evaluation_id)
            if not existing_evaluation:
                raise Exception("Evaluation not found")

            evaluation_data = EvaluationUpdate(
                feedback=parsed_response.get("feedback", existing_evaluation.feedback),
                criteria_evaluation=parsed_response.get(
                    "criteria_evaluation", existing_evaluation.criteria_evaluation
                ),
                overall_comments=parsed_response.get(
                    "overall_comments", existing_evaluation.overall_comments
                ),
                source_text=source_text,
            )
            updated_evaluation = update_evaluation(db, evaluation_id, evaluation_data)
            final_evaluation = updated_evaluation
        else:
            # New evaluation: update the empty evaluation with real content
            # Update the empty evaluation with real content using the new function
            updated_evaluation = update_evaluation_content(
                db=db,
                evaluation_id=str(evaluation.id),
                feedback=parsed_response.get("feedback", ""),
                criteria_evaluation=parsed_response.get("criteria_evaluation", []),
                overall_comments=parsed_response.get("overall_comments", ""),
                source_text=source_text
            )
            final_evaluation = updated_evaluation
        
        # Notify successful completion
        await app_sync.send_event_with_notification(
            db=db,
            user_id=str(user_id),
            service_id="evaluation_generator",
            title="evaluation_generator.completed.title",
            body="evaluation_generator.completed.body",
            data={
                "request_id": str(request_id),
                "evaluation_id": str(final_evaluation.id),
                "student_name": f"{student_name} {student_surname}",
                "course_name": course_name,
                "stage": "completed"
            },
            notification_type="success",
            priority="normal",
            actions=[
                {
                    "label": "notifications.buttons.view",
                    "action": "navigate",
                    "url": f"/evaluations/view/{final_evaluation.id}"
                }
            ]
        )
            
    except Exception as e:
        # General error in asynchronous processing
        try:
            await app_sync.send_event_with_notification(
                db=db,
                user_id=str(user_id),
                service_id="evaluation_generator",
                title="evaluation_generator.error.title",
                body="evaluation_generator.error.body",
                data={
                    "request_id": str(request_id),
                    "evaluation_id": str(evaluation.id) if 'evaluation' in locals() else None,
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

