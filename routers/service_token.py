# © [2025] EDT&Partners. Licensed under CC BY 4.0.

import jwt
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from database.db import get_db
from database.models import UserRole
from database.crud import get_user_by_cognito_id, create_service_token as create_service_token_db, get_service_tokens_for_group, delete_service_token
from database.schemas import ServiceTokenCreate, ServiceTokenResponse, ServiceTokenWithSecret, ServiceTokenList
from utility.auth import require_token_types
from utility.tokens import generate_token_key_pair, JWTLectureTokenPayload
from icecream import ic

router = APIRouter()


def create_jwt_token(user_id: UUID, group_id: UUID, private_key: str, token_id: str, name: str, expires_in_days: int) -> str:
    """Create a JWT token for service authentication"""
    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(days=expires_in_days)
    
    payload = {
        "sub": str(user_id),
        "token_type": "service_api",
        "token_id": token_id,
        "token_name": name,
        "group_id": str(group_id),
        "iat": now,
        "exp": expires_at,
        "iss": "lecture-backend-api"
    }
    
    return jwt.encode(payload, private_key, algorithm="RS256")


@router.post("", response_model=ServiceTokenWithSecret, status_code=status.HTTP_201_CREATED)
async def create_service_token(
    token_data: ServiceTokenCreate,
    token: JWTLectureTokenPayload = Depends(require_token_types(allowed_types=["cognito"])),
    db: Session = Depends(get_db)
):
    """
    Create a new service token.
    
    This endpoint creates a JWT token that can be used for API authentication.
    The token will include the specified scopes and expiration time.
    
    **Note**: The actual token is only returned once during creation.
    """
    try:
        user = get_user_by_cognito_id(db, token.sub)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found"
            )
        
        # User must be admin of the group
        if user.role != UserRole.admin:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="User must be admin of the group"
            )
        
        ic(f"User {user.name} is admin of group {user.group_id} and is creating a new service token.")

        token_id = str(uuid4())
        private_key, public_key = generate_token_key_pair()
        ic(f"Generated new key pair successfully.")
        
        jwt_token = create_jwt_token(
            user_id=user.cognito_id,
            group_id=user.group_id,
            private_key=private_key,
            token_id=token_id,
            name=token_data.name,
            expires_in_days=token_data.expires_in_days
        )

        expires_at = datetime.now(timezone.utc) + timedelta(days=token_data.expires_in_days)
        
        service_token = await create_service_token_db(db, token_id, user.group_id, token_data.name, 
                                                      token_data.description, expires_at,
                                                      jwt_token[:10] + "..." + jwt_token[-10:],
                                                      public_key)

        ic(f"Created service token {service_token.id} for group {user.group_id}")
        
        return ServiceTokenWithSecret(
            id=str(service_token.id),
            name=service_token.name,
            description=service_token.description,
            created_at=service_token.created_at,
            expires_at=service_token.expires_at,
            last_used_at=service_token.last_used_at,
            is_active=service_token.is_active,
            token=jwt_token
        )
        
    except Exception as e:
        ic(f"Error creating service token: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create service token"
        )


@router.get("", response_model=ServiceTokenList)
async def list_service_tokens(
    active_only: bool = True,
    token: JWTLectureTokenPayload = Depends(require_token_types(allowed_types=["cognito"])),
    db: Session = Depends(get_db)
):
    """
    List all service tokens for the current user.
    
    By default, only returns active (non-revoked) tokens.
    Set active_only=false to include revoked tokens.
    """
    try:
        user = get_user_by_cognito_id(db, token.sub)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found"
            )
        
        if user.role != UserRole.admin:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="User must be admin of the group"
            )
        
        group_tokens = await get_service_tokens_for_group(db, user.group_id)

        tokens = []
        for token in group_tokens:
            if active_only and not token.is_active:
                continue
                
            tokens.append(ServiceTokenResponse(
                id=str(token.id),
                name=token.name,
                description=token.description,
                created_at=token.created_at,
                expires_at=token.expires_at,
                last_used_at=token.last_used_at,
                is_active=token.is_active
            ))
        
        return ServiceTokenList(tokens=tokens, total=len(tokens))
        
    except Exception as e:
        ic(f"Error listing service tokens: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to list service tokens"
        )


@router.delete("/{token_id}", status_code=status.HTTP_200_OK)
async def revoke_service_token(
    token_id: str,
    token: JWTLectureTokenPayload = Depends(require_token_types(allowed_types=["cognito"])),
    db: Session = Depends(get_db)
):
    """
    Revoke (deactivate) a service token.
    
    Once revoked, the token can no longer be used for authentication.
    This action cannot be undone.
    """
    try:
        user = get_user_by_cognito_id(db, token.sub)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found"
            )
        
        if user.role != UserRole.admin:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="User must be admin of the group"
            )
        
        group_tokens = await get_service_tokens_for_group(db, user.group_id)
        
        for token in group_tokens:
            if str(token.id) == token_id:
                if await delete_service_token(db, token_id):
                    ic(f"Revoked service token {token_id} for user {user.id}")
                    return {"message": "Token revoked successfully"}
                else:
                    raise HTTPException(
                        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                        detail="Failed to revoke service token"
                    )
        else:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Token not found"
            )
        
    except HTTPException:
        raise
    except Exception as e:
        ic(f"Error revoking service token: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to revoke service token"
        )
