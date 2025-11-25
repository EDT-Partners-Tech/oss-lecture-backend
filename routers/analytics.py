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

from typing import Optional, Tuple
from uuid import UUID
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from database.db import get_db
from database.models import UserRole, User
from database.crud import get_user_by_cognito_id, get_analytics_by_user_id, get_analytics_by_group_id, get_all_analytics
from utility.auth import require_token_types
from utility.tokens import JWTLectureTokenPayload
from icecream import ic

router = APIRouter()

def parse_date(date_str: Optional[str]) -> Optional[datetime]:
    if date_str is None:
        return None
    try:
        return datetime.strptime(date_str, "%Y-%m-%d")
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid date format. Use YYYY-MM-DD")

def get_date_range(from_date: Optional[str], to_date: Optional[str]) -> Tuple[Optional[datetime], Optional[datetime]]:
    """Helper function to parse and adjust date range for analytics queries."""
    from_date_dt = parse_date(from_date)
    to_date_dt = parse_date(to_date)

    if from_date_dt:
        from_date_dt = from_date_dt.replace(hour=0, minute=0, second=0, microsecond=0)
    if to_date_dt:
        to_date_dt = to_date_dt.replace(hour=23, minute=59, second=59, microsecond=999999)

    return from_date_dt, to_date_dt

def get_authenticated_user(db: Session, token: JWTLectureTokenPayload, require_admin: bool = False) -> User:
    """Helper function to get and validate the authenticated user."""
    current_user = get_user_by_cognito_id(db, token.sub)
    
    if require_admin and current_user.role != UserRole.admin:
        raise HTTPException(status_code=403, detail="Access denied")
        
    return current_user

@router.get("/user")
async def get_user_analytics(
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
    token: JWTLectureTokenPayload = Depends(require_token_types(allowed_types=["cognito"])),
    db: Session = Depends(get_db)
):
    """
    Get analytics for a specific user.
    Only admins or the user themselves can access this data.
    
    Parameters:
    - from_date: Optional start date for filtering analytics in YYYY-MM-DD format (inclusive)
    - to_date: Optional end date for filtering analytics in YYYY-MM-DD format (inclusive)
    """
    current_user = get_authenticated_user(db, token)
    from_date_dt, to_date_dt = get_date_range(from_date, to_date)
    
    analytics = get_analytics_by_user_id(db, current_user.id, from_date_dt, to_date_dt)
    return {"analytics": analytics}

@router.get("/group/")
async def get_group_analytics(
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
    token: JWTLectureTokenPayload = Depends(require_token_types(allowed_types=["cognito"])),
    db: Session = Depends(get_db)
):
    """
    Get analytics for the current user's group.
    Only admins can access this data.
    
    Parameters:
    - from_date: Optional start date for filtering analytics in YYYY-MM-DD format (inclusive)
    - to_date: Optional end date for filtering analytics in YYYY-MM-DD format (inclusive)
    """
    try:
        current_user = get_authenticated_user(db, token, require_admin=True)
        from_date_dt, to_date_dt = get_date_range(from_date, to_date)
        analytics = get_analytics_by_group_id(db, current_user.group_id, from_date_dt, to_date_dt)
        return {"analytics": analytics}

    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal Server Error: {str(e)}")

# TODO: Activate this endpoint for super admins
async def get_admin_analytics(
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
    user_id: Optional[UUID] = None,
    token: JWTLectureTokenPayload = Depends(require_token_types(allowed_types=["cognito"])),
    db: Session = Depends(get_db)
):
    """
    Get analytics data for all users and services.
    Only admins can access this data.
    
    Parameters:
    - from_date: Optional start date for filtering analytics in YYYY-MM-DD format (inclusive)
    - to_date: Optional end date for filtering analytics in YYYY-MM-DD format (inclusive)
    - user_id: Optional UUID to filter by specific user
    """
    get_authenticated_user(db, token, require_admin=True)
    from_date_dt, to_date_dt = get_date_range(from_date, to_date)
    
    analytics = get_all_analytics(db, from_date_dt, to_date_dt, user_id)
    return {"analytics": analytics}