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
import tempfile
import os
import time
import uuid
from fastapi.responses import FileResponse
import pypandoc
from fastapi import APIRouter, BackgroundTasks, File, HTTPException, UploadFile
from pydantic import BaseModel
from typing import List
from database.crud import delete_comparison_engine_by_id, delete_comparison_rule_by_id, get_comparison_config_by_id, get_comparison_document_by_document_id, get_comparison_engine_documents_by_user_id, get_comparison_engine_document_by_id, get_comparison_rule_by_id, get_comparison_rules_by_user_id_and_type, get_user_by_cognito_id, save_comparison_document_data, save_comparison_engine, save_comparison_rule, update_comparison_engine, update_comparison_rule_by_id
from database.db import get_db
from sqlalchemy.orm import Session
from database.schemas import ComparisonEngineCreateRequest, ComparisonEngineResponse, ComparisonRuleCreateRequest
from function.llms.bedrock_invoke import invoke_bedrock_claude_with_converse
from utility.auth import require_token_types
from utility.aws import get_s3_object, upload_file_to_s3
from utility.analytics import process_and_save_analytics, update_processing_time
from fastapi import APIRouter, HTTPException, Depends
from utility.service import handle_save_request
from utility.common import convert_large_language_to_code
from utility.tokens import JWTLectureTokenPayload
from utility.prompt_utility import  build_comparation_prompt_for_converse, build_instruction_prompt, build_instruction_prompt_for_converse_resume
import re

router = APIRouter()

DOCUMENT_NOT_FOUND = "Document not found"

async def prepare_rules_data(db: Session, rules_ids: List[str]) -> str:
    rules_data = ""
    for rule_id in rules_ids:
        rule = await get_comparison_rule_by_id(db, rule_id)
        if rules_data == "":
            rules_data = """
            - You must always follow these rules to get a better result in the comparison.\n
            - The result must be in a JSON format and you never return anything else.\n
            - *markdown_code*: Include a natural language description of how the rules were taken into account for the evaluation.\n
            <COMPARISON_RULES>\n"""
        rules_data += f"<GLOBAL_RULE_NAME>{rule.name}</GLOBAL_RULE_NAME>\n"
        rules_data += f"<GLOBAL_RULE_DESCRIPTION>{rule.description}</GLOBAL_RULE_DESCRIPTION>\n"
        for internal_rule in rule.data['rules']:
            rules_data += "<RULE>\n"
            rules_data += f"<RULE_NAME>{internal_rule['name']}</RULE_NAME>\n"
            rules_data += f"<RULE_DESCRIPTION>{internal_rule['description']}</RULE_DESCRIPTION>\n"
            rules_data += f"<RULE_PRIORITY>{internal_rule['priority']}</RULE_PRIORITY>\n"
            rules_data += f"<RULE_IS_MANDATORY>{internal_rule['isMandatory']}</RULE_IS_MANDATORY>\n"

            for internal_sub_rule in internal_rule['subRules']:
                rules_data += "<SUB_RULE>\n"
                rules_data += f"<SUB_RULE_NAME>{internal_sub_rule['name']}</SUB_RULE_NAME>\n"
                rules_data += f"<SUB_RULE_DESCRIPTION>{internal_sub_rule['description']}</SUB_RULE_DESCRIPTION>\n"
                rules_data += f"<SUB_RULE_PRIORITY>{internal_sub_rule['priority']}</SUB_RULE_PRIORITY>\n"
                rules_data += f"<SUB_RULE_IS_MANDATORY>{internal_sub_rule['isMandatory']}</SUB_RULE_IS_MANDATORY>\n"
                rules_data += "</SUB_RULE>\n"
            rules_data += "</RULE>\n"
    if rules_data != "":
        rules_data += "</COMPARISON_RULES>\n"
    return rules_data

async def prepare_weights(db: Session, config_id: str) -> str:
    if not config_id:
        return ""
    
    config = await get_comparison_config_by_id(db, config_id)
    weights = getattr(config, 'threshold', "")

    try:
        weights = json.loads(weights)
        if isinstance(weights, dict):
            return "\n".join([f"- {k}: {v}" for k, v in weights.items()])
    except Exception:
        pass
    return ""

async def process_comparison(db: Session, user_id, request: ComparisonEngineCreateRequest, type: str = "resume"):
    try:
        start_time = time.time()
        document1_s3 = await get_comparison_document_by_document_id(db, id = request.document1_id, fields=['title', 's3_uri', 'language'])
        document2_s3 = await get_comparison_document_by_document_id(db, id = request.document2_id, fields=['title', 's3_uri', 'language'])
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching S3 URIs from database: {str(e)}")

    document1_data = await get_s3_object(document1_s3.get("s3_uri"))
    document2_data = await get_s3_object(document2_s3.get("s3_uri"))

    rules_data = await prepare_rules_data(db, request.rules_ids)
    weights = await prepare_weights(db, request.config_id)

    converse_prompt = build_comparation_prompt_for_converse(
        document1_s3.get('title', ""),
        document2_s3.get('title', ""),
        request.language,
        rules_data=rules_data
    )

    bedrock_instruction = (build_instruction_prompt_for_converse_resume(language=request.language, rules_data=rules_data) 
                         if type == "resume" 
                         else build_instruction_prompt(rules_data, weights, language=request.language))

    temp_file_extension1 = document1_s3.get("s3_uri").split(".")[-1] if document1_s3.get("s3_uri") else "txt"
    temp_file_extension2 = document2_s3.get("s3_uri").split(".")[-1] if document2_s3.get("s3_uri") else "txt"

    with tempfile.NamedTemporaryFile(suffix=f".{temp_file_extension1}", delete=False) as temp_file1, \
         tempfile.NamedTemporaryFile(suffix=f".{temp_file_extension2}", delete=False) as temp_file2:
        temp_file1.write(document1_data['Body'].read())
        temp_file2.write(document2_data['Body'].read())
        temp_file_path1 = temp_file1.name
        temp_file_path2 = temp_file2.name

    files = [temp_file_path1, temp_file_path2]
    bedrock_raw_response = await invoke_bedrock_claude_with_converse(
        db, user_id, "Comparison Engine: " + type, 
        converse_prompt, bedrock_instruction, 
        files=files, model_name=request.model
    )

    os.remove(temp_file_path1)
    os.remove(temp_file_path2)

    # Remove all text up to the first curly brace
    if bedrock_raw_response:
        brace_index = bedrock_raw_response.find('{')
        if brace_index != -1:
            bedrock_raw_response = bedrock_raw_response[brace_index:]

    if bedrock_raw_response.startswith("```json"):
        bedrock_raw_response = bedrock_raw_response.replace("```json", "").replace("```", "")
    elif bedrock_raw_response.endswith("```"):
        bedrock_raw_response = bedrock_raw_response[:-3]

    comparison_engine_data = {
        "id": request.process_id,
        "name": request.name,
        "description": request.description,
        "type": type,
        "status": "SUCCESS",
        "content": bedrock_raw_response if bedrock_raw_response else "",
        "user_id": user_id,
    }

    comparison_engine_id = await update_comparison_engine(db=db, comparison_engine_data=comparison_engine_data)
    
    request_id = handle_save_request(db, request.name, user_id, "comparison_engine")
    processing_time = time.time() - start_time
    await process_and_save_analytics(db, request_id, 'default', bedrock_instruction, bedrock_raw_response, processing_time)
    
    if comparison_engine_id is None:
        raise HTTPException(status_code=500, detail="Error saving comparison engine data to the database")

@router.get("/{type}/", response_model=List[ComparisonEngineResponse])
async def get_comparison_engine_list(
    type: str,
    token: JWTLectureTokenPayload = Depends(require_token_types(allowed_types=["cognito"])),
    db: Session = Depends(get_db)):
    """
    Retrieve a document by its ID.
    """
    cognito_id = token.sub
    
    user = get_user_by_cognito_id(db, cognito_id)
    
    if not user:
        raise HTTPException(
            status_code=404,
            detail=f"User with cognito_id {cognito_id} not found"
        )
    
    # Get user ID from the UUID's user
    user_id = user.id

    # Convert UUID to string
    user_id = str(user_id)

    try:
        data = await get_comparison_engine_documents_by_user_id(db, user_id=user_id, type=type)
        if data is None:
            raise HTTPException(status_code=404, detail=DOCUMENT_NOT_FOUND)

        return data
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/data/{comparison_id}/")
async def get_comparison_engine(
    comparison_id: str,
    token: JWTLectureTokenPayload = Depends(require_token_types(allowed_types=["cognito"])),
    db: Session = Depends(get_db)):
    """
    Retrieve a comparison register by its ID.
    """
    cognito_id = token.sub
    
    user = get_user_by_cognito_id(db, cognito_id)
    
    if not user:
        raise HTTPException(
            status_code=404,
            detail=f"User with cognito_id {cognito_id} not found"
        )

    try:
        # 1. Get Comparison Engine data
        data = await get_comparison_engine_document_by_id(db, id=comparison_id)
        if data is None:
            raise HTTPException(status_code=404, detail=DOCUMENT_NOT_FOUND)
        
        if data.status == "PROCESSING":
            return {
                "status": data.status,
                "message": "Comparison is still processing"
            }

        # 2. Reduce multiple spaces to a single space, except for newlines
        bedrock_response = re.sub(r'[^\S\n]+', ' ', data.content)

        # 3. Split using "markdown_code" as separator
        bedrock_response = bedrock_response.split(",\n \"markdown_code\": \"")
        markdown = bedrock_response[1] if len(bedrock_response) > 1 else ""

        # 4. Remove the last '}' character from markdown
        markdown = markdown[:-3]
        
        # 5. Replace \\n with \n
        markdown = markdown.replace("\\n", "\n")

        # 6. Add final character if need it
        bedrock_response = bedrock_response[0] + '}' if len(bedrock_response) > 1 else bedrock_response[0]

        # 7. Parse the JSON response
        json_response = json.loads(bedrock_response)

        # 8. Create the result
        result = {
            **json_response,
            "markdown_code": markdown
        }
        
        return {
            "result": result,
            "status": data.status,
            "message": "Comparison successfully"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/{comparison_id}/")
async def delete_comparison_engine(
    comparison_id: str,
    token: JWTLectureTokenPayload = Depends(require_token_types(allowed_types=["cognito"])),
    db: Session = Depends(get_db)):
    """
    Delete a comparison register by its ID.
    """
    cognito_id = token.sub
    
    user = get_user_by_cognito_id(db, cognito_id)
    
    if not user:
        raise HTTPException(
            status_code=404,
            detail=f"User with cognito_id {cognito_id} not found"
        )

    try:
        # 1. Get Comparison Engine data
        data = await get_comparison_engine_document_by_id(db, id=comparison_id)
        if data is None:
            raise HTTPException(status_code=404, detail=DOCUMENT_NOT_FOUND)

        # 2. Delete the comparison engine document
        await delete_comparison_engine_by_id(db, id=comparison_id)

        return {
            "message": "Comparison successfully deleted"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))



@router.post("/document-status")
async def compare_resume_status(
    request: ComparisonEngineCreateRequest,
    background_tasks: BackgroundTasks,
    token: JWTLectureTokenPayload = Depends(require_token_types(allowed_types=["cognito"])),
    db: Session = Depends(get_db)):
    """
    Initiates the comparison process between two documents stored in S3.
    It extracts text, analyzes content using AWS Comprehend, and compares the documents.
    """
    try:
        cognito_id = token.sub
    
        user = get_user_by_cognito_id(db, cognito_id)
        if not user:
            raise HTTPException(
                status_code=404,
                detail=f"User with cognito_id {cognito_id} not found"
            )
        
        # Get user ID from the UUID's user
        user_id = user.id

        background_tasks.add_task(process_comparison, db, user_id, request, "document")
        
        # 1. Save ComparisonEngine data to the database
        comparison_engine_data = {
            "id": request.process_id,
            "name": request.name,
            "description": request.description,
            "type": "document",
            "status": "PROCESSING",
            "content": {},
            "user_id": user_id,
        }

        # 2. Save the comparison engine data to the database using save_comparison_engine
        await save_comparison_engine(db=db, comparison_engine_data=comparison_engine_data)

        # 3. Return the response
        return {
            "message": "Comparison start successfully"
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/resume-status")
async def compare_resume_status(
    request: ComparisonEngineCreateRequest,
    background_tasks: BackgroundTasks,
    token: JWTLectureTokenPayload = Depends(require_token_types(allowed_types=["cognito"])),
    db: Session = Depends(get_db)):
    """
    Initiates the comparison process between two documents stored in S3.
    It extracts text, analyzes content using AWS Comprehend, and compares the documents.
    """
    try:
        cognito_id = token.sub
    
        user = get_user_by_cognito_id(db, cognito_id)
        if not user:
            raise HTTPException(
                status_code=404,
                detail=f"User with cognito_id {cognito_id} not found"
            )
        
        # Get user ID from the UUID's user
        user_id = user.id

        background_tasks.add_task(process_comparison, db, user_id, request, "resume")
        
        # 1. Save ComparisonEngine data to the database
        comparison_engine_data = {
            "id": request.process_id,
            "name": request.name,
            "description": request.description,
            "type": "resume",
            "status": "PROCESSING",
            "content": {},
            "user_id": user_id,
        }

        # 2. Save the comparison engine data to the database using save_comparison_engine
        await save_comparison_engine(db=db, comparison_engine_data=comparison_engine_data)

        # 3. Return the response
        return {
            "message": "Comparison start successfully"
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/upload/")
async def upload_files(
    files: List[UploadFile] = File(...),
    token: JWTLectureTokenPayload = Depends(require_token_types(allowed_types=["cognito"])),
    db: Session = Depends(get_db)):
    """
    Upload one or more files to S3, extract text, and save data.
    """
    # Check if the user is authenticated
    cognito_id = token.sub
    
    user = get_user_by_cognito_id(db, cognito_id)
    
    if not user:
        raise HTTPException(
            status_code=404,
            detail=f"User with cognito_id {cognito_id} not found"
        )
    
    # Get user ID from the UUID's user
    user_id = user.id

    # Create a uuid processor
    process_uuid = str(uuid.uuid4())

    try:
        uploaded_files = []
        for file in files:
            original_filename = file.filename
            file_extension = os.path.splitext(original_filename)[1]
            
            # 1. Extract text from the file
            file_content = await file.read()
            with tempfile.NamedTemporaryFile(delete=False, suffix=file_extension) as temp_file:
                temp_file.write(file_content)
                temp_file_path = temp_file.name

            # 2. Generate UUID for filenames
            uuid_filename = str(uuid.uuid4())
            original_file_s3_key = f"{uuid_filename}{file_extension}"

            # 3. Save the original file to S3 with UUID name
            original_file_s3_uri = await upload_file_to_s3(
                bucket='comparison', 
                file_path=temp_file_path,
                object_name=original_file_s3_key
            )

            # 4. Delete the temporary file
            os.remove(temp_file_path)

            # 5. Detect language of the text
            language = ""

            # 6. Save document data to the database
            document_data = {
                "title": original_filename,
                "type": file_extension,
                "s3_uri": original_file_s3_uri,
                "language": convert_large_language_to_code(language) if language else "",
                "comparison_engine_id": process_uuid,
            }
            
            document_id = await save_comparison_document_data(db=db, document_data=document_data, user_id=user_id)

            uploaded_files.append({
                "id": document_id,
                "filename": original_filename, 
                "s3_uri": original_file_s3_uri,
                "language": language
            })

        return {"message": "Files uploaded successfully", "files": uploaded_files, "process_id": process_uuid}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    
@router.get("/rules/{type}/")
async def get_comparison_rules(
    type: str,
    token: JWTLectureTokenPayload = Depends(require_token_types(allowed_types=["cognito"])),
    db: Session = Depends(get_db)):
    """
    Retrieve a document by its ID.
    """
    cognito_id = token.sub
    
    user = get_user_by_cognito_id(db, cognito_id)
    
    if not user:
        raise HTTPException(
            status_code=404,
            detail=f"User with cognito_id {cognito_id} not found"
        )
    
    # Get user ID from the UUID's user
    user_id = user.id

    # Convert UUID to string
    user_id = str(user_id)

    try:
        data = await get_comparison_rules_by_user_id_and_type(db, user_id=user_id, type=type)
        if data is None:
            raise HTTPException(status_code=404, detail=DOCUMENT_NOT_FOUND)

        return data
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/rule/data/{id}/")
async def get_comparison_rules(
    id: str,
    token: JWTLectureTokenPayload = Depends(require_token_types(allowed_types=["cognito"])),
    db: Session = Depends(get_db)):
    """
    Retrieve a document by its ID.
    """
    cognito_id = token.sub
    
    user = get_user_by_cognito_id(db, cognito_id)
    
    if not user:
        raise HTTPException(
            status_code=404,
            detail=f"User with cognito_id {cognito_id} not found"
        )
    
    # Get user ID from the UUID's user
    user_id = user.id

    # Convert UUID to string
    user_id = str(user_id)

    try:
        data = await get_comparison_rule_by_id(db, id=id)
        if data is None:
            raise HTTPException(status_code=404, detail=DOCUMENT_NOT_FOUND)

        return data
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/rule/{type}/")
async def create_comparison_rule(
    type: str,
    request: ComparisonRuleCreateRequest,
    token: JWTLectureTokenPayload = Depends(require_token_types(allowed_types=["cognito"])),
    db: Session = Depends(get_db)):
    """
    Create a new comparison rule.
    """
    cognito_id = token.sub
    
    user = get_user_by_cognito_id(db, cognito_id)
    
    if not user:
        raise HTTPException(
            status_code=404,
            detail=f"User with cognito_id {cognito_id} not found"
        )

    try:
        # 1. Create the comparison rule
        rule_data = {
            "name": request.name,
            "description": request.description,
            "data": request.data,
            "type": type,
            "user_id": user.id
        }
        
        rule_id = await save_comparison_rule(db=db, comparison_rule_data=rule_data)

        return {
            "message": "Comparison rule created successfully",
            "rule_id": rule_id
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.put("/rule/{rule_id}/")
async def update_comparison_rule(
    rule_id: str,
    request: ComparisonRuleCreateRequest,
    token: JWTLectureTokenPayload = Depends(require_token_types(allowed_types=["cognito"])),
    db: Session = Depends(get_db)):
    """
    Update a comparison rule.
    """
    cognito_id = token.sub
    
    user = get_user_by_cognito_id(db, cognito_id)
    
    if not user:
        raise HTTPException(
            status_code=404,
            detail=f"User with cognito_id {cognito_id} not found"
        )
    
    try:
        # 1. Update the comparison rule
        await update_comparison_rule_by_id(db, id=rule_id, rule_data=request)

        return {
            "message": "Comparison rule updated successfully"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/rule/{rule_id}/")
async def delete_comparison_rule(
    rule_id: str,
    token: JWTLectureTokenPayload= Depends(require_token_types(allowed_types=["cognito"])),
    db: Session = Depends(get_db)):
    """
    Delete a comparison register by its ID.
    """
    cognito_id = token.sub
    
    user = get_user_by_cognito_id(db, cognito_id)
    
    if not user:
        raise HTTPException(
            status_code=404,
            detail=f"User with cognito_id {cognito_id} not found"
        )

    try:
        # 1. Get Comparison Engine data
        data = await get_comparison_rule_by_id(db, id=rule_id)
        if data is None:
            raise HTTPException(status_code=404, detail=DOCUMENT_NOT_FOUND)

        # 2. Delete the comparison engine document
        await delete_comparison_rule_by_id(db, id=rule_id)

        return {
            "message": "Comparison successfully deleted"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


class ConvertFileRequest(BaseModel):
    input_data: str
    input_format: str
    output_format: str

@router.post("/convert/")
async def convert_file(
    request: ConvertFileRequest,
    token: JWTLectureTokenPayload = Depends(require_token_types(allowed_types=["cognito"])),
    db: Session = Depends(get_db)
):
    """
    Convert a file to another format using pypandoc.
    The file returned will have the appropriate extension and filename.
    """
    cognito_id = token.sub
    user = get_user_by_cognito_id(db, cognito_id)
    if not user:
        raise HTTPException(
            status_code=404,
            detail=f"User with cognito_id {cognito_id} not found"
        )

    # Validate output format
    valid_formats = ["docx", "latex", "html", "jira", "markdown", "rst", "textile", "json", "epub", "epub3", "epub3-zip", "docbook"]
    if request.output_format not in valid_formats:
        raise HTTPException(
            status_code=400,
            detail="Invalid format. Supported formats are: docx"
        )

    EPUB_MEDIA_TYPE = "application/epub+zip"
    temp_input_file_path = None
    output_file_path = None
    try:
        # Determine the file extension based on the input format
        input_extension = request.input_format
        
        # Create temporary file for the input data
        with tempfile.NamedTemporaryFile(delete=False, suffix=f".{input_extension}") as temp_file:
            temp_file.write(request.input_data.encode('utf-8'))
            temp_input_file_path = temp_file.name

        # Create temporary file for the output
        with tempfile.NamedTemporaryFile(delete=False, suffix=f".{request.output_format}") as temp_file:
            output_file_path = temp_file.name
        
        # Convert the file using pypandoc
        pypandoc.convert_file(temp_input_file_path, request.output_format, format=request.input_format, outputfile=output_file_path)

        # Define the filename and media type for the response
        filename = f"documento.{request.output_format}"
        if request.output_format == "docx":
            media_type = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        elif request.output_format == "latex":
            media_type = "application/x-latex"
        elif request.output_format == "html":
            media_type = "text/html"
        elif request.output_format == "jira":
            media_type = "text/x-jira"
        elif request.output_format == "markdown":
            media_type = "text/markdown"
        elif request.output_format == "rst":
            media_type = "text/x-rst"
        elif request.output_format == "textile":
            media_type = "text/x-textile"
        elif request.output_format == "json":
            media_type = "application/json"
        elif request.output_format == "epub":
            media_type = EPUB_MEDIA_TYPE
        elif request.output_format == "epub3":
            media_type = EPUB_MEDIA_TYPE
        elif request.output_format == "epub3-zip":
            media_type = EPUB_MEDIA_TYPE
        elif request.output_format == "docbook":
            media_type = "application/docbook+xml"

        # Return the file using FileResponse
        return FileResponse(
            path=output_file_path,
            filename=filename,
            media_type=media_type
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
