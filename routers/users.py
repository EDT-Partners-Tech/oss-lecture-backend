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

import tempfile
import uuid
import os
from fastapi import APIRouter, Depends, HTTPException, status, File, UploadFile
from sqlalchemy.orm import Session
from typing import List
from constants import USER_NOT_FOUND_MESSAGE
from database import crud
from database.db import get_db
from database.models import UserRole, Group
from database.schemas import UserCreate, UserResponse, UserUpdate, GroupCreate, GroupResponse
from routers.groups import ERROR_ACCESS_DENIED
from utility.auth import require_token_types
from utility.tokens import JWTLectureTokenPayload, CognitoTokenPayload
from utility.aws import generate_presigned_url, upload_file_to_s3, get_app_sync_api_events

router = APIRouter()


# Create User
@router.post("/", status_code=status.HTTP_201_CREATED)
def create_user(user: UserCreate, db: Session = Depends(get_db)):
    try:
        new_user = crud.create_user_with_domain_group(db=db, user=user)
        return new_user
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal Server Error. Error details: {e}")

@router.get("/me")
async def get_user_details(
    db: Session = Depends(get_db), 
    token: CognitoTokenPayload = Depends(require_token_types(allowed_types=["cognito"]))
):
    try:
        user = crud.get_user_by_cognito_id(db, token.sub)
        user_group: Group = user.group

        # Get user logo from "custom:avatar"
        user_logo_s3_uri = token.custom_avatar
        if user_logo_s3_uri:
            user_logo_s3_uri = generate_presigned_url('content', user_logo_s3_uri, 604800)
            user.logo_s3_uri = user_logo_s3_uri
        else:
            user.logo_s3_uri = None

        # Get group logo
        group_logo_s3_uri = user_group.logo_s3_uri

        # Use generate_presigned_url
        if group_logo_s3_uri and group_logo_s3_uri != "":
            group_logo_s3_uri = generate_presigned_url('content', group_logo_s3_uri, 604800)
            user_group.logo_s3_uri = group_logo_s3_uri
        else:
            group_logo_s3_uri = None
        
        try:
            app_sync_settings = await get_app_sync_api_events()
        except Exception as e:
            print(f"Error getting app sync client: {e}")
        
        # Convert group to safe response format (excludes _lti_private_key)
        group_response = GroupResponse.model_validate(user_group)
        
        return {
            "user_id": user.id,
            "user_name": user.name,
            "role": user.role,
            "picture": user_logo_s3_uri,
            "custom:avatar": user_logo_s3_uri,
            "group": group_response,
            "app_sync_settings": app_sync_settings if app_sync_settings else None
        }
    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal Server Error. Error details: {e}")

# Get Users by Course - Accessible by Teachers
@router.get("/course/{course_id}", response_model=List[UserResponse])
def get_users_by_course(
    course_id: uuid.UUID, 
    db: Session = Depends(get_db), 
    token: JWTLectureTokenPayload = Depends(require_token_types(allowed_types=["cognito"]))
):
    user = crud.get_user_by_cognito_id(db, token.sub)
    if user.role not in [UserRole.teacher, UserRole.admin]:
        raise HTTPException(status_code=403, detail="Not authorized to access users in this course")
    
    users = crud.get_users_by_course(db, course_id=course_id)
    return users

# Update User - Accessible by the User themselves
@router.put("/{user_id}",)
def update_user(
    user_id: int, 
    user_update: UserUpdate, 
    db: Session = Depends(get_db), 
    token: JWTLectureTokenPayload = Depends(require_token_types(allowed_types=["cognito"]))
):
    db_user = crud.get_user(db, user_id=user_id)
    if db_user is None:
        raise HTTPException(status_code=404, detail=USER_NOT_FOUND_MESSAGE)
    
    if token.sub != db_user.id:
        raise HTTPException(status_code=403, detail="Not authorized to update this user")
    
    updated_user = crud.update_user(db, user_id=user_id, user_update=user_update)
    if updated_user is None:
        raise HTTPException(status_code=400, detail="Failed to update user")
    
    return updated_user

# Delete User - Accessible by Teachers
@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_user(
    user_id: int, 
    db: Session = Depends(get_db), 
    token: JWTLectureTokenPayload = Depends(require_token_types(allowed_types=["cognito"]))
):
    user = crud.get_user_by_cognito_id(db, token.sub)
    if user.role not in [UserRole.teacher, UserRole.admin]:
        raise HTTPException(status_code=403, detail="Not authorized to delete a user")
    
    success = crud.delete_user(db, user_id=user_id)
    if not success:
        raise HTTPException(status_code=404, detail=USER_NOT_FOUND_MESSAGE)

@router.post("/upload-logo/")
async def upload_group_logo(
    logo: UploadFile = File(...),
    token: JWTLectureTokenPayload = Depends(require_token_types(allowed_types=["cognito"])),
    db: Session = Depends(get_db)
):
    try:
        user = crud.get_user_by_cognito_id(db, token.sub)
        
        if not user:
            raise HTTPException(status_code=403, detail=ERROR_ACCESS_DENIED)
        
        # Create a temporary file path
        with tempfile.NamedTemporaryFile(delete=False) as temp_file:
            temp_file.write(await logo.read())
            temp_file_path = temp_file.name

        try:
            logo_s3_uri = await upload_file_to_s3('content', temp_file_path, f"profile/{user.id}/logo")
            presigned_url = generate_presigned_url('content', logo_s3_uri, 604800)
            return {
                "logo_s3_uri": logo_s3_uri,
                "presigned_url": presigned_url
            }
        finally:
            # Clean up the temporary file
            os.unlink(temp_file_path)
    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal Server Error. Error details: {e}")