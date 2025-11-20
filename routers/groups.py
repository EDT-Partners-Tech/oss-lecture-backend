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
import tempfile
from uuid import UUID
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy.orm import Session

from database.db import get_db
from database.models import UserRole
from database.schemas import SetGroupAdminRequest, GroupUpdate, ConfigureServicesRequest, ConfigureModelsRequest
from database.crud import db_upload_group_logo, get_user_by_cognito_id, get_group_by_id, get_services_by_ids,set_group_available_services, get_user, set_user_role, delete_group_from_db, update_group, get_ai_models_by_ids, set_group_available_models
from utility.auth import require_token_types
from utility.aws import upload_file_to_s3
from utility.tokens import JWTLectureTokenPayload

ERROR_GROUP_NOT_FOUND = "Group not found"
ERROR_ACCESS_DENIED = "Access denied"

router = APIRouter()

@router.patch("/{group_id}")
def update_group_details(
    group_id: UUID,
    request: GroupUpdate,
    token: JWTLectureTokenPayload = Depends(require_token_types(allowed_types=["cognito"])),
    db: Session = Depends(get_db)
):
    try:
        user = get_user_by_cognito_id(db, token.sub)
        group = get_group_by_id(db, group_id)

        if not group:
            raise HTTPException(status_code=404, detail=ERROR_GROUP_NOT_FOUND)
        
        if user.role != UserRole.admin or user.group_id != group_id:
            raise HTTPException(status_code=403, detail=ERROR_ACCESS_DENIED)
        
        updated_group = update_group(db, request, group)
        return {
            "group_id": updated_group.id,
            "group_name": updated_group.name
        }
    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal Server Error. Error details: {e}")

@router.post("/{group_id}/admin")
def set_group_admin(
    group_id: UUID,
    request: SetGroupAdminRequest,
    token: JWTLectureTokenPayload = Depends(require_token_types(allowed_types=["cognito"])),
    db: Session = Depends(get_db)
):
    try:
        user = get_user_by_cognito_id(db, token.sub)
        group = get_group_by_id(db, group_id)
        target_user = get_user(db, request.user_id)

        if not group:
            raise HTTPException(status_code=404, detail=ERROR_GROUP_NOT_FOUND)
        
        if not target_user:
            raise HTTPException(status_code=404, detail="Target user not found")
        
        if user.role != UserRole.admin or user.group_id != group_id:
            raise HTTPException(status_code=403, detail=ERROR_ACCESS_DENIED)
        
        if target_user.group_id != group_id:
            raise HTTPException(status_code=403, detail="Target user does not belong to the group")
        
        set_user_role(db, user, UserRole.teacher)
        set_user_role(db, target_user, UserRole.admin)

        return {
            "group_id": group.id,
            "new_admin_user_id": target_user.id,
        }
    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal Server Error. Error details: {e}")

@router.get("/{group_id}/services")
def get_group_services(
    group_id: UUID,
    token: JWTLectureTokenPayload = Depends(require_token_types(allowed_types=["cognito"])),
    db: Session = Depends(get_db)
):
    try:
        user = get_user_by_cognito_id(db, token.sub)
        group = get_group_by_id(db, group_id)

        if not group:
            raise HTTPException(status_code=404, detail=ERROR_GROUP_NOT_FOUND)
        
        if user.role != UserRole.admin or user.group_id != group_id:
            raise HTTPException(status_code=403, detail=ERROR_ACCESS_DENIED)
        
        return {"services": group.available_services}
    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal Server Error. Error details: {e}")

@router.get("/{group_id}/models")
def get_group_models(
    group_id: UUID,
    token: JWTLectureTokenPayload = Depends(require_token_types(allowed_types=["cognito"])),
    db: Session = Depends(get_db)
):
    try:
        user = get_user_by_cognito_id(db, token.sub)
        group = get_group_by_id(db, group_id)

        if not group:
            raise HTTPException(status_code=404, detail=ERROR_GROUP_NOT_FOUND)
        
        if user.role != UserRole.admin or user.group_id != group_id:
            raise HTTPException(status_code=403, detail=ERROR_ACCESS_DENIED)
        
        return {"models": group.available_models}
    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal Server Error. Error details: {e}")

@router.put("/{group_id}/services")
def configure_group_services(
    group_id: UUID,
    request: ConfigureServicesRequest,
    token: JWTLectureTokenPayload = Depends(require_token_types(allowed_types=["cognito"])),
    db: Session = Depends(get_db)
):
    try:
        user = get_user_by_cognito_id(db, token.sub)
        group = get_group_by_id(db, group_id)
        services = get_services_by_ids(db, request.services_ids)

        if not group:
            raise HTTPException(status_code=404, detail=ERROR_GROUP_NOT_FOUND)
        
        if not services:
            raise HTTPException(status_code=404, detail="Services not found. Check the services ids")
        
        if user.role != UserRole.admin or user.group_id != group_id:
            raise HTTPException(status_code=403, detail=ERROR_ACCESS_DENIED)
        
        updated_group = set_group_available_services(db, group_id, services)
        return {
            "updated_group_id": updated_group.id,
            "updated_services": [service.code for service in updated_group.available_services]
        }
    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal Server Error. Error details: {e}")
    
@router.put("/{group_id}/models")
def configure_group_models(
    group_id: UUID,
    request: ConfigureModelsRequest,
    token: JWTLectureTokenPayload = Depends(require_token_types(allowed_types=["cognito"])),
    db: Session = Depends(get_db)
):
    try:
        user = get_user_by_cognito_id(db, token.sub)
        group = get_group_by_id(db, group_id)
        models = get_ai_models_by_ids(db, request.models_ids)

        if not group:
            raise HTTPException(status_code=404, detail=ERROR_GROUP_NOT_FOUND)
        
        if not models:
            raise HTTPException(status_code=404, detail="Models not found. Check the models ids")
        
        if user.role != UserRole.admin or user.group_id != group_id:
            raise HTTPException(status_code=403, detail=ERROR_ACCESS_DENIED)
        
        updated_group = set_group_available_models(db, group_id, models)
        return {
            "updated_group_id": updated_group.id,
            "updated_models": [model.id for model in updated_group.available_models]
        }
    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal Server Error. Error details: {e}")

@router.delete("/{group_id}")
def delete_group(
    group_id: UUID,
    token: JWTLectureTokenPayload = Depends(require_token_types(allowed_types=["cognito"])),
    db: Session = Depends(get_db)
):
    try:
        user = get_user_by_cognito_id(db, token.sub)
        group = get_group_by_id(db, group_id)

        if not group:
            raise HTTPException(status_code=404, detail=ERROR_GROUP_NOT_FOUND)
        
        if user.role != UserRole.admin or user.group_id != group_id:
            raise HTTPException(status_code=403, detail=ERROR_ACCESS_DENIED)
        
        delete_group_from_db(db, group)
        return {
            "deleted_group_id": group.id
        }
    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal Server Error. Error details: {e}")
    
@router.post("/{group_id}/upload-logo/")
async def upload_group_logo(
    group_id: UUID,
    logo: UploadFile = File(...),
    token: JWTLectureTokenPayload = Depends(require_token_types(allowed_types=["cognito"])),
    db: Session = Depends(get_db)
):
    try:
        user = get_user_by_cognito_id(db, token.sub)
        group = get_group_by_id(db, group_id)

        if not group:
            raise HTTPException(status_code=404, detail=ERROR_GROUP_NOT_FOUND)
        
        if user.role != UserRole.admin or user.group_id != group_id:
            raise HTTPException(status_code=403, detail=ERROR_ACCESS_DENIED)
        
        # Create a temporary file path
        with tempfile.NamedTemporaryFile(delete=False) as temp_file:
            temp_file.write(await logo.read())
            temp_file_path = temp_file.name

        try:
            logo_s3_uri = await upload_file_to_s3('content', temp_file_path, f"groups/{group.id}/logo")
            await db_upload_group_logo(db, group_id, logo_s3_uri)
            return {
                "logo_s3_uri": logo_s3_uri
            }
        finally:
            # Clean up the temporary file
            os.unlink(temp_file_path)
    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal Server Error. Error details: {e}")

@router.delete("/{group_id}/remove-logo/")
async def remove_group_logo(
    group_id: UUID,
    token: JWTLectureTokenPayload = Depends(require_token_types(allowed_types=["cognito"])),
    db: Session = Depends(get_db)
):
    '''
    Remove the logo from the group
    '''
    try:
        user = get_user_by_cognito_id(db, token.sub)
        group = get_group_by_id(db, group_id)

        if not group:
            raise HTTPException(status_code=404, detail=ERROR_GROUP_NOT_FOUND)
        
        if user.role != UserRole.admin or user.group_id != group_id:
            raise HTTPException(status_code=403, detail=ERROR_ACCESS_DENIED)
        
        await db_upload_group_logo(db, group_id, None)
        return {
            "deleted_group_id": group.id
        }
    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal Server Error. Error details: {e}")