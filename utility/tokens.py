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

import jwt
import time
import requests
import json
from abc import ABC, abstractmethod
from fastapi import HTTPException
from typing import Union, Optional
from icecream import ic
from pydantic import BaseModel, Field
from jose import jwt as jose_jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.backends import default_backend
from sqlalchemy.orm import Session

from database.crud import get_service_token_by_id_and_group_id, update_service_token_last_used_at

class JWTLectureTokenPayload(BaseModel):
    sub: str
    token_type: str


class CognitoTokenPayload(JWTLectureTokenPayload):
    sub: str
    email: str
    token_type: str = "cognito"
    token_use: str
    iss: str
    cognito_username: str = Field(..., alias="cognito:username")
    custom_avatar: Optional[str] = Field(None, alias="custom:avatar")


class LTIDeepLinkTokenPayload(JWTLectureTokenPayload):
    sub: str
    token_type: str = "lti_deep_link"
    course_id: str
    group_id: str


class LTIServicesTokenPayload(JWTLectureTokenPayload):
    sub: str
    iss: str
    token_type: str = "lti_services"
    course_id: str
    lti_params: Optional[dict] = {}


class ServiceAPIAccessTokenPayload(JWTLectureTokenPayload):
    token_type: str = "service_api"
    token_id: str
    token_name: str
    group_id: str


class JWTTokenValidator(ABC):
    @abstractmethod
    async def validate_token(self, token: str, db: Session) -> Union[CognitoTokenPayload, JWTLectureTokenPayload]:
        pass


class CognitoJWTTokenValidator(JWTTokenValidator):
    def __init__(self, user_pool_id: str, region: str, app_client_id: str, jwks_cache_duration: int = 3600):
        self.jwks_cache = {}
        self.jwks_cache_time = {}
        self.jwks_cache_duration = jwks_cache_duration
        self.region = region
        self.user_pool_id = user_pool_id
        self.app_client_id = app_client_id

    def _get_jwks_url(self, user_pool_id: str = None) -> str:
        """Get JWKS URL for a specific user pool or the default one."""
        pool_id = user_pool_id or self.user_pool_id
        return f"https://cognito-idp.{self.region}.amazonaws.com/{pool_id}/.well-known/jwks.json"

    def _get_jwks(self, user_pool_id: str = None):
        """Get JWKS for a specific user pool or the default one."""
        current_time = time.time()
        pool_id = user_pool_id or self.user_pool_id
        
        # Return cached JWKS if it's still valid
        if (pool_id in self.jwks_cache and 
            pool_id in self.jwks_cache_time and 
            (current_time - self.jwks_cache_time[pool_id]) < self.jwks_cache_duration):
            return self.jwks_cache[pool_id]
        
        try:
            jwks_url = self._get_jwks_url(pool_id)
            response = requests.get(jwks_url)
            response.raise_for_status()
            jwks = response.json().get("keys", [])
            if not jwks:
                ic(f"No keys found in JWKS response for pool {pool_id}")
                raise ValueError(f"No keys found in JWKS response for pool {pool_id}")
            
            # Update cache
            self.jwks_cache[pool_id] = jwks
            self.jwks_cache_time[pool_id] = current_time
            return jwks
        except requests.RequestException as e:
            ic(f"Failed to fetch JWKS for pool {pool_id}: {e}")
            raise HTTPException(
                status_code=401,
                detail="Failed to fetch public keys",
                headers={"WWW-Authenticate": "Bearer"},
            ) from e

    def _get_public_key(self, kid, user_pool_id: str = None):
        try:
            jwks = self._get_jwks(user_pool_id)        
            
            for key in jwks:
                if key["kid"] == kid:
                    key_json = json.dumps(key)
                    return jwt.algorithms.RSAAlgorithm.from_jwk(key_json)
            
            raise ValueError(f"Public key not found for kid: {kid}")
        except Exception as e:
            ic(f"Error in get_public_key: {str(e)}")
            raise

    async def validate_token(self, token: str, db: Session) -> CognitoTokenPayload:
        try:
            # Get token header without verification
            header = jwt.get_unverified_header(token)
            
            # Try to decode token without verification to get more info
            try:
                unverified_payload = jwt.decode(token, options={"verify_signature": False})
                token_issuer = unverified_payload.get('iss')
                token_audience = unverified_payload.get('aud')
                token_subject = unverified_payload.get('sub')
                
                # Extract user pool ID from issuer
                if token_issuer:
                    # Format: https://cognito-idp.{region}.amazonaws.com/{user-pool-id}
                    user_pool_id = token_issuer.split('/')[-1]
                else:
                    user_pool_id = None
                
                
            except Exception as e:
                user_pool_id = None
                token_audience = None
            
            # Fetch public key and verify token
            kid = header["kid"]
            public_key = self._get_public_key(kid, user_pool_id)

            # Use the token's issuer for verification if available
            issuer = token_issuer if token_issuer else f"https://cognito-idp.{self.region}.amazonaws.com/{self.user_pool_id}"
            
            # Verify the token with the correct audience
            try:
                payload = jwt.decode(
                    token,
                    public_key,
                    algorithms=["RS256"],
                    audience=token_audience,  # Use the token's audience
                    issuer=issuer
                )
                return CognitoTokenPayload(**payload)
            except jwt.InvalidTokenError as e:
                if "Audience doesn't match" in str(e):
                    # If audience verification fails, try with our app client ID
                    payload = jwt.decode(
                        token,
                        public_key,
                        algorithms=["RS256"],
                        audience=self.app_client_id,  # Try with our app client ID
                        issuer=issuer,
                        options={"verify_aud": False}  # Disable audience verification
                    )
                    return payload
                raise
            
        except jwt.ExpiredSignatureError as e:
            ic("Token has expired")
            raise HTTPException(
                status_code=401,
                detail="Token has expired",
                headers={"WWW-Authenticate": "Bearer"},
            ) from e
        except jwt.InvalidTokenError as e:
            ic(f"Invalid token: {e}")
            raise HTTPException(
                status_code=401,
                detail=f"Invalid token: {e}",
                headers={"WWW-Authenticate": "Bearer"},
            ) from e
        except ValueError as e:
            ic(f"Error retrieving public key: {e}")
            raise HTTPException(
                status_code=401,
                detail=f"Error retrieving public key: {e}",
                headers={"WWW-Authenticate": "Bearer"},
            ) from e
        except Exception as e:
            ic(f"Unexpected error during token validation: {str(e)}")
            raise HTTPException(
                status_code=401,
                detail=f"Token validation failed: {str(e)}",
                headers={"WWW-Authenticate": "Bearer"},
            ) from e


class LTIDeepLinkJWTTokenValidator(JWTTokenValidator):
    def __init__(self, session_token_secret: str):
        self.secret = session_token_secret

    async def validate_token(self, token: str, db: Session) -> LTIDeepLinkTokenPayload:
        try:
            payload = jwt.decode(token, self.secret, algorithms=["HS256"])
            user_id = payload.get("sub")
            course_id = payload.get("course_id")
            group_id = payload.get("group_id")
            if not user_id or not course_id or not group_id:
                raise HTTPException(status_code=401, detail="Invalid LTI session token credentials")
            return {
                "user_id": user_id,
                "course_id": course_id,
                "group_id": group_id
            }
        except Exception as e:
            ic(f"Error in validate_lti_session_token: {str(e)}")
            raise HTTPException(status_code=401, detail="Invalid LTI session token credentials")


class LTIServicesJWTTokenValidator(JWTTokenValidator):
    def __init__(self, session_token_secret: str):
        self.secret = session_token_secret

    async def validate_token(self, token: str, db: Session) -> LTIServicesTokenPayload:
        try:
            payload = jwt.decode(token, self.secret, algorithms=["HS256"])
            user_id = payload.get("sub")
            iss = payload.get("iss")
            course_id = payload.get("course_id")
            lti_params = payload.get("lti_params", {})
            if not user_id or not course_id:
                raise HTTPException(status_code=401, detail="Invalid LTI session token credentials")
            return LTIServicesTokenPayload(
                sub=user_id,
                iss=iss,
                course_id=course_id,
                lti_params=lti_params
            )
        except Exception as e:
            ic(f"Error in validate_lti_session_token: {str(e)}")
            raise HTTPException(status_code=401, detail="Invalid LTI session token credentials")
        

class ServiceAPIAccessTokenValidator(JWTTokenValidator):
    async def validate_token(self, token: str, db: Session) -> ServiceAPIAccessTokenPayload:
        try:
            unverified_payload = jose_jwt.get_unverified_claims(token)
            group_id = unverified_payload.get("group_id")
            token_id = unverified_payload.get("token_id")
            token_name = unverified_payload.get("token_name")
            if not group_id or not token_id or not token_name:
                raise HTTPException(status_code=401, detail="Invalid service token credentials")
            
            # Check if the token is registered and active
            target_token = await get_service_token_by_id_and_group_id(db, token_id, group_id)
            if not target_token:
                ic(f"Service token not found for group {group_id} and token {token_id}!")
                raise HTTPException(status_code=401, detail="Invalid service token credentials")
            if not target_token.is_active:
                ic(f"Service token {token_id} is not active!")
                raise HTTPException(status_code=401, detail="Service token is not active")
            
            # Validate the token with the public key
            public_key = target_token.public_key
            payload = jwt.decode(token, public_key, algorithms=["RS256"])
            # Decode OK
            await update_service_token_last_used_at(db, token_id)
            return ServiceAPIAccessTokenPayload(**payload)
        
        except jwt.ExpiredSignatureError as e:
            ic(f"Service token {token_id} has expired!")
            raise HTTPException(status_code=401, detail="Service token has expired")
        except jwt.InvalidSignatureError as e:
            ic(f"Invalid service token signature: {e}")
            raise HTTPException(status_code=401, detail="Invalid service token signature")
        except jwt.InvalidTokenError as e:
            ic(f"Invalid service token: {e}")
            raise HTTPException(status_code=401, detail="Invalid service token credentials")
        except Exception as e:
            ic(f"Error in validate_service_token: {str(e)}")
            raise HTTPException(
                status_code=401, 
                detail="Invalid service token credentials"
            )

def generate_token_key_pair() -> str:
    """
    Generate a new RSA key pair for JWT token authentication.
    
    Returns:
        str: The private key in PEM format as a string
        str: The public key in PEM format as a string
    """
    try:
        # Generate private key
        private_key = rsa.generate_private_key(
            public_exponent=65537,
            key_size=2048,
            backend=default_backend()
        )

        # Get private key in PEM format
        private_pem = private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption()
        ).decode('utf-8')

        # Public key in PEM format
        public_pem = private_key.public_key().public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo
        ).decode('utf-8')

        return private_pem, public_pem
    
    except Exception as e:
        ic(f"Error generating token key pair: {e}")
        raise RuntimeError(f"Failed to generate token key pair: {e}")
