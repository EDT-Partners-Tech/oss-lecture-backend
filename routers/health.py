# © [2025] EDT&Partners. Licensed under CC BY 4.0.

"""
Router for health check endpoints
"""
from fastapi import APIRouter, HTTPException, Depends

from services.health_service import HealthService
from interfaces.health_interface import HealthResponse
from utility.auth import require_token_types
from utility.tokens import JWTLectureTokenPayload
from database.crud import get_user_by_cognito_id
from database.db import get_db
from sqlalchemy.orm import Session

router = APIRouter()

@router.get("/health", response_model=HealthResponse)
async def health_check(token: JWTLectureTokenPayload = Depends(require_token_types(allowed_types=["cognito"])), db: Session = Depends(get_db)):
    """
    Health check endpoint
    
    Returns:
        HealthResponse: Service health information
    """
    # Verify user token
    user = get_user_by_cognito_id(db, token.sub)
    user_id = user.id if user else None

    if user_id is None:
        raise HTTPException(status_code=401, detail="Unauthorized")

    try:
        health_service = HealthService()
        return await health_service.get_health_status()
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error in health check: {str(e)}"
        ) 