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

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import Any, Dict, List

from database import crud
from database.schemas import LTIPlatformCreate, LTIPlatformUpdate, UserRole
from database.db import get_db
from utility.auth import require_token_types
from utility.lti_management_utils import ensure_group_has_lti_private_key
from utility.tokens import JWTLectureTokenPayload

router = APIRouter()

# LTI Platform Management Endpoints
@router.post("/platforms", response_model=Dict[str, Any], tags=["LTI Management"])
async def register_platform(
    platform: LTIPlatformCreate,
    db: Session = Depends(get_db),
    token: JWTLectureTokenPayload = Depends(require_token_types(allowed_types=["cognito"]))
):
    """Register a new LTI platform"""
    current_user = crud.get_user_by_cognito_id(db, token.sub)
    if not current_user or current_user.role != UserRole.admin:
        raise HTTPException(status_code=401, detail="Unauthorized")

    # Check if platform already exists for this group
    existing = crud.get_lti_platform(db, platform.client_id)
    if existing:
        raise HTTPException(status_code=400, detail="Platform with this client_id already exists for this group")

    # Prepare the group with a private key if it doesn't have one
    ensure_group_has_lti_private_key(db, current_user.group_id)

    # Create new platform
    db_platform = crud.create_lti_platform(db, platform, current_user.group_id)
    
    return {
        "status": "success",
        "platform": {
            "client_id": db_platform.client_id,
            "issuer": db_platform.issuer,
            "is_active": db_platform.is_active,
            "is_default": db_platform.is_default
        }
    }

@router.get("/platforms", response_model=List[Dict[str, Any]], tags=["LTI Management"])
async def list_platforms(
    active_only: bool = True,
    db: Session = Depends(get_db),
    token: JWTLectureTokenPayload = Depends(require_token_types(allowed_types=["cognito"]))
):
    """List all registered LTI platforms for the group"""
    current_user = crud.get_user_by_cognito_id(db, token.sub)
    if not current_user or current_user.role != UserRole.admin:
        raise HTTPException(status_code=401, detail="Unauthorized")
    
    platforms = crud.get_lti_platforms_by_group(db, current_user.group_id, active_only)
    return [{
        "client_id": p.client_id,
        "issuer": p.issuer,
        "platform_type": p.platform_type,
        "auth_login_url": p.auth_login_url,
        "auth_token_url": p.auth_token_url,
        "key_set_url": p.key_set_url,
        "deployment_ids": p.deployment_ids,
        "is_active": p.is_active,
        "is_default": p.is_default,
        "created_at": p.created_at,
        "updated_at": p.updated_at
    } for p in platforms]

@router.patch("/platforms/{client_id}", response_model=Dict[str, Any], tags=["LTI Management"])
async def update_platform(
    client_id: str,
    platform_update: LTIPlatformUpdate,
    db: Session = Depends(get_db),
    token: JWTLectureTokenPayload = Depends(require_token_types(allowed_types=["cognito"]))
):
    """Update an existing LTI platform"""
    current_user = crud.get_user_by_cognito_id(db, token.sub)
    if not current_user or current_user.role != UserRole.admin:
        raise HTTPException(status_code=401, detail="Unauthorized")
    
    platform = crud.update_lti_platform(db, client_id, current_user.group_id, platform_update)
    if not platform:
        raise HTTPException(status_code=404, detail="Platform not found")
    
    return {
        "status": "success",
        "platform": {
            "client_id": platform.client_id,
            "issuer": platform.issuer,
            "is_active": platform.is_active,
            "is_default": platform.is_default,
            "updated_at": platform.updated_at
        }
    }

@router.delete("/platforms/{client_id}", tags=["LTI Management"])
async def delete_platform(
    client_id: str,
    db: Session = Depends(get_db),
    token: JWTLectureTokenPayload = Depends(require_token_types(allowed_types=["cognito"]))
):
    """Delete an LTI platform"""
    current_user = crud.get_user_by_cognito_id(db, token.sub)
    if not current_user or current_user.role != UserRole.admin:
        raise HTTPException(status_code=401, detail="Unauthorized")
    
    if not crud.delete_lti_platform(db, client_id):
        raise HTTPException(status_code=404, detail="Platform not found")
    return {"status": "success"}