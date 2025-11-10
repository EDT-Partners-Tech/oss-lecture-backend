# © [2025] EDT&Partners. Licensed under CC BY 4.0.

from typing import List
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from database.crud import (
    get_third_party_integration,
    get_third_party_integrations,
    get_third_party_integration_by_service,
    update_third_party_integration,
    delete_third_party_integration
)
from database.schemas import (
    ThirdPartyIntegrationUpdate,
    ThirdPartyIntegrationResponse,
    ServiceValueResponse,
    AllowedServiceName
)
from database.db import get_db
from database.models import User
from utility.auth import require_token_types, verify_user_admin
from utility.tokens import JWTLectureTokenPayload
from constants import INTEGRATION_NOT_FOUND_MESSAGE


router = APIRouter()

@router.get("/services", response_model=List[str])
async def get_available_services():
    """
    Get list of available third-party services that can be integrated.
    """
    return [service.value for service in AllowedServiceName]

@router.get("/", response_model=List[ThirdPartyIntegrationResponse])
async def read_integrations(
    db: Session = Depends(get_db),
    token: JWTLectureTokenPayload = Depends(require_token_types(allowed_types=["cognito"]))
):
    """
    Get all third-party integrations.
    Only admin users can access these integrations.
    """
    verify_user_admin(db, token)
    return await get_third_party_integrations(db)

@router.get("/service/{service_name}", response_model=ServiceValueResponse)
async def read_integration_by_service(
    service_name: AllowedServiceName,
    db: Session = Depends(get_db),
    token: JWTLectureTokenPayload = Depends(require_token_types(allowed_types=["cognito"]))
):
    """
    Get a specific third-party integration service value by service name.
    Only admin users can access these integrations.
    """
    verify_user_admin(db, token)
    integration = await get_third_party_integration_by_service(db, service_name.value)
    if not integration:
        raise HTTPException(status_code=404, detail=INTEGRATION_NOT_FOUND_MESSAGE)
    return integration

@router.get("/public/service/{service_name}", response_model=ServiceValueResponse)
async def read_public_integration_by_service(
    service_name: AllowedServiceName,
    db: Session = Depends(get_db)
):
    """
    Get a specific third-party integration service value by service name.
    This endpoint is public and can be accessed without authentication.
    Currently only supports 'google' service for sign-in.
    """
    
    integration = await get_third_party_integration_by_service(db, service_name.value)
    if not integration:
        raise HTTPException(status_code=404, detail=INTEGRATION_NOT_FOUND_MESSAGE)
    return integration

@router.put("/{integration_id}", response_model=ServiceValueResponse)
async def update_integration(
    integration_id: UUID,
    integration_update: ThirdPartyIntegrationUpdate,
    db: Session = Depends(get_db),
    token: JWTLectureTokenPayload = Depends(require_token_types(allowed_types=["cognito"]))
):
    """
    Update a third-party integration.
    Only admin users can update integrations.
    """
    verify_user_admin(db, token)
    integration = await get_third_party_integration(db, integration_id)
    if not integration:
        raise HTTPException(status_code=404, detail=INTEGRATION_NOT_FOUND_MESSAGE)
    
    integration = await update_third_party_integration(db, integration_id, integration_update)
    return integration

@router.delete("/{integration_id}")
async def delete_integration(
    integration_id: UUID,
    db: Session = Depends(get_db),
    token: JWTLectureTokenPayload = Depends(require_token_types(allowed_types=["cognito"]))
):
    """
    Delete a third-party integration.
    Only admin users can delete integrations.
    """
    verify_user_admin(db, token)
    integration = await get_third_party_integration(db, integration_id)
    if not integration:
        raise HTTPException(status_code=404, detail=INTEGRATION_NOT_FOUND_MESSAGE)
    
    success = await delete_third_party_integration(db, integration_id)
    return {"message": "Integration deleted successfully"} 