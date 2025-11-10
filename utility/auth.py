# © [2025] EDT&Partners. Licensed under CC BY 4.0.

import os
from fastapi import Depends, HTTPException
from fastapi.security import OAuth2PasswordBearer
from constants import NOT_AUTHORIZED_MESSAGE
from database.models import UserRole
from requests import Session
from database.crud import get_course, get_user_by_cognito_id
from icecream import ic
from google.oauth2 import id_token
from google.auth.transport import requests as google_requests
from jose import jwt as jose_jwt
from typing import List, Union

from lti.secrets import get_lti_secrets
from database.db import get_db
from utility.tokens import CognitoJWTTokenValidator, LTIDeepLinkJWTTokenValidator, LTIServicesJWTTokenValidator, JWTTokenValidator, CognitoTokenPayload, JWTLectureTokenPayload, ServiceAPIAccessTokenValidator

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

# Load environment variables manually
COGNITO_USERPOOL_ID = os.getenv("COGNITO_USERPOOL_ID")
COGNITO_REGION = os.getenv("COGNITO_REGION")
COGNITO_APP_CLIENT_ID = os.getenv("COGNITO_APP_CLIENT_ID")

LTI_SESSION_TOKENS_SECRET = get_lti_secrets().session_tokens_secret
if not LTI_SESSION_TOKENS_SECRET:
    raise ValueError("LTI_SESSION_TOKENS_SECRET is not set")

VALIDATOR_MAP: dict[str, JWTTokenValidator] = {
    "cognito": CognitoJWTTokenValidator(user_pool_id=COGNITO_USERPOOL_ID, region=COGNITO_REGION, app_client_id=COGNITO_APP_CLIENT_ID),
    "lti_deep_link": LTIDeepLinkJWTTokenValidator(session_token_secret=LTI_SESSION_TOKENS_SECRET),
    "lti_services": LTIServicesJWTTokenValidator(session_token_secret=LTI_SESSION_TOKENS_SECRET),
    "service_api": ServiceAPIAccessTokenValidator()
}

def require_token_types(allowed_types: List[str]) -> callable:
    async def _dependency(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)) -> JWTLectureTokenPayload:
        token_key = None
        try:
            unverified_payload = jose_jwt.get_unverified_claims(token)
            token_type_claim = unverified_payload.get("token_type", None)
            if token_type_claim:
                token_key = token_type_claim
            elif "cognito:username" in unverified_payload:
                token_key = "cognito"
            else:
                ic("Unknown token format!")
                raise HTTPException(status_code=401, detail="Invalid token")
            
            if token_key not in allowed_types:
                ic(f"Token type {token_key} not in allowed types: {allowed_types}")
                raise HTTPException(status_code=403, detail=f"Token type '{token_key}' not allowed for this operation")
            
            validator = VALIDATOR_MAP.get(token_key, None)
            if validator:
                return await validator.validate_token(token, db)
            else:
                ic(f"No validator found for the token type: {token_key}!")
                raise HTTPException(status_code=500, detail="Internal server error")
        except Exception as e:
            ic(f"Error while validating token: {str(e)}")
            raise HTTPException(status_code=401, detail="Invalid or expired token")
    return _dependency


def verify_user_permission(db: Session, token: JWTLectureTokenPayload):
    user = get_user_by_cognito_id(db, token.sub)
    if user.role not in [UserRole.teacher, UserRole.admin]:
        raise HTTPException(status_code=403, detail=NOT_AUTHORIZED_MESSAGE)

def verify_user_admin(db: Session, token: JWTLectureTokenPayload):
    user = get_user_by_cognito_id(db, token.sub)
    if user.role not in [UserRole.admin]:
        raise HTTPException(status_code=403, detail=NOT_AUTHORIZED_MESSAGE)

def verify_user_owner(db: Session, token: JWTLectureTokenPayload, course_id: int):
    user_id = str(get_user_by_cognito_id(db, token.sub).id)
    course = get_course(db, course_id)
    
    if not course:
        raise HTTPException(status_code=404, detail="Course not found")

    course_teacher_id = str(course.teacher_id)
    
    if user_id != course_teacher_id:
        raise HTTPException(status_code=403, detail="Not authorized to update the course")
    
def verify_google_token(id_token_str: str):
    try:
        id_info = id_token.verify_oauth2_token(
            id_token_str,
            google_requests.Request(),
            audience=os.getenv("GOOGLE_CLIENT_ID")
        )
        return id_info
    except ValueError as e:
        ic(f"Google token invalid: {e}")
        raise HTTPException(status_code=401, detail="Invalid Google token")