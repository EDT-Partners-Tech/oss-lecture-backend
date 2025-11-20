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
import secrets
import boto3
from fastapi import APIRouter, Request, HTTPException, Depends
from sqlalchemy.orm import Session
from utility.auth import verify_google_token
from database.db import get_db
from icecream import ic
from database.crud import create_user_with_domain_group, get_user_by_email
from database.schemas import UserCreate
import jwt

router = APIRouter()

COGNITO_USERPOOL_ID = os.getenv("COGNITO_USERPOOL_ID")
COGNITO_REGION = os.getenv("COGNITO_REGION")
COGNITO_APP_CLIENT_ID = os.getenv("COGNITO_APP_CLIENT_ID")

@router.post("/google")
async def google_login(request: Request, db: Session = Depends(get_db)):
    body = await request.json()
    id_token_str = body.get("idToken")
    
    try:
        # Verify Google token
        id_info = verify_google_token(id_token_str)
        email = id_info["email"]
        sub = id_info["sub"]
        given_name = id_info.get("given_name", "")
        family_name = id_info.get("family_name", "")
        locale = id_info.get("locale", "en-US")

        cognito_client = boto3.client("cognito-idp", region_name=COGNITO_REGION)
        
        # Generate secure password
        password = f"GOOGLE_{sub}_{secrets.token_urlsafe(32)}"

        try:
            # Check if user exists
            cognito_client.admin_get_user(
                UserPoolId=COGNITO_USERPOOL_ID,
                Username=email
            )
        except cognito_client.exceptions.UserNotFoundException:
            # Create user in Cognito
            cognito_user = cognito_client.admin_create_user(
                UserPoolId=COGNITO_USERPOOL_ID,
                Username=email,
                UserAttributes=[
                    {"Name": "email", "Value": email},
                    {"Name": "email_verified", "Value": "true"},
                    {"Name": "given_name", "Value": given_name},
                    {"Name": "family_name", "Value": family_name},
                    {"Name": "locale", "Value": locale}
                ],
                MessageAction="SUPPRESS"
            )
            ic(f"Cognito user: {cognito_user}")
            user = UserCreate(
                cognito_id=cognito_user["User"]["Username"],
                email=email,
                name=f"{given_name} {family_name}",
                role="teacher"
            )
            create_user_with_domain_group(db=db, user=user)

        # Set/update password
        cognito_client.admin_set_user_password(
            UserPoolId=COGNITO_USERPOOL_ID,
            Username=email,
            Password=password,
            Permanent=True
        )

        # Now authenticate
        try:
            response = cognito_client.admin_initiate_auth(
                UserPoolId=COGNITO_USERPOOL_ID,
                ClientId=COGNITO_APP_CLIENT_ID,
                AuthFlow="ADMIN_NO_SRP_AUTH",
                AuthParameters={
                    "USERNAME": email,
                    "PASSWORD": password
                }
            )

            return {
                "accessToken": response["AuthenticationResult"]["AccessToken"],
                "idToken": response["AuthenticationResult"]["IdToken"],
                "refreshToken": response["AuthenticationResult"]["RefreshToken"]
            }

        except Exception as auth_error:
            ic(f"Authentication error: {str(auth_error)}")
            raise HTTPException(
                status_code=401,
                detail="Authentication failed"
            )

    except Exception as e:
        ic(f"Unexpected error: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=str(e)
        )

def handle_password_reset_required(cognito_client, username: str) -> dict:
    """
    Handles both PasswordResetRequiredException and new user password setup.
    For imported users or users requiring password reset, this will:
    1. Set an initial temporary password
    2. Force a password change requirement
    3. Return a NEW_PASSWORD_REQUIRED challenge with session
    
    Args:
        cognito_client: The Cognito client instance
        username: The username of the user requiring password setup/reset
        
    Returns:
        dict: Challenge response containing challengeName, username, and session
        
    Raises:
        HTTPException: If the password setup/reset flow fails
    """
    try:
        # First check if user exists and get their status
        try:
            user_response = cognito_client.admin_get_user(
                UserPoolId=COGNITO_USERPOOL_ID,
                Username=username
            )
            user_status = user_response["UserStatus"]
        except cognito_client.exceptions.UserNotFoundException:
            raise HTTPException(status_code=404, detail="User not found")

        # Generate a secure temporary password
        temp_password = f"Temp_{secrets.token_urlsafe(16)}"

        # Set the temporary password
        cognito_client.admin_set_user_password(
            UserPoolId=COGNITO_USERPOOL_ID,
            Username=username,
            Password=temp_password,
            Permanent=False  # This forces a password change
        )

        # Try to authenticate to get a session
        try:
            auth_response = cognito_client.admin_initiate_auth(
                UserPoolId=COGNITO_USERPOOL_ID,
                ClientId=COGNITO_APP_CLIENT_ID,
                AuthFlow="ADMIN_NO_SRP_AUTH",
                AuthParameters={
                    "USERNAME": username,
                    "PASSWORD": temp_password
                }
            )
        except cognito_client.exceptions.NotAuthorizedException:
            # If authentication fails, try one more time with a different temp password
            # This handles the case where the user might have a password but it's not working
            temp_password = f"Temp_{secrets.token_urlsafe(16)}"
            cognito_client.admin_set_user_password(
                UserPoolId=COGNITO_USERPOOL_ID,
                Username=username,
                Password=temp_password,
                Permanent=False
            )
            auth_response = cognito_client.admin_initiate_auth(
                UserPoolId=COGNITO_USERPOOL_ID,
                ClientId=COGNITO_APP_CLIENT_ID,
                AuthFlow="ADMIN_NO_SRP_AUTH",
                AuthParameters={
                    "USERNAME": username,
                    "PASSWORD": temp_password
                }
            )

        # This should trigger NEW_PASSWORD_REQUIRED with a session
        if "ChallengeName" in auth_response and auth_response["ChallengeName"] == "NEW_PASSWORD_REQUIRED":
            return {
                "challengeName": "NEW_PASSWORD_REQUIRED",
                "username": username,
                "session": auth_response["Session"]
            }
        
        raise HTTPException(
            status_code=403,
            detail="Unable to set up password change requirement. Please contact your administrator."
        )
    except Exception as e:
        ic(f"Password setup/reset error: {str(e)}")
        raise HTTPException(
            status_code=403,
            detail="Password setup/reset failed. Please contact your administrator."
        )

@router.post("/login")
async def login(request: Request, db: Session = Depends(get_db)):
    body = await request.json()
    username = body.get("username")
    password = body.get("password")

    ic(f"Login attempt for username: {username}")

    if not username or not password:
        ic("Missing username or password")
        raise HTTPException(status_code=400, detail="Username and password are required")

    cognito_client = boto3.client("cognito-idp", region_name=COGNITO_REGION)

    # First check user status before attempting authentication
    try:
        ic("Checking user status in Cognito")
        user_response = cognito_client.admin_get_user(
            UserPoolId=COGNITO_USERPOOL_ID,
            Username=username
        )
        ic(f"Full user response: {user_response}")
        
        # Get the user status directly from the response
        user_status = user_response.get("UserStatus")  # This is at the top level of the response
        ic(f"Found user status: {user_status}")
        
        # Check for both RESET_REQUIRED and FORCE_CHANGE_PASSWORD statuses
        if user_status in ["RESET_REQUIRED", "FORCE_CHANGE_PASSWORD"]:
            ic(f"User has {user_status} status, initiating password reset flow")
            return handle_password_reset_required(cognito_client, username)
            
    except cognito_client.exceptions.UserNotFoundException:
        ic("User not found in Cognito")
        raise HTTPException(status_code=404, detail="User not found")
    except Exception as e:
        ic(f"Error checking user status. Full error: {str(e)}")
        ic(f"Error type: {type(e)}")
        # Continue with normal auth flow even if status check fails

    try:
        ic("Attempting admin_initiate_auth with Cognito")
        response = cognito_client.admin_initiate_auth(
            UserPoolId=COGNITO_USERPOOL_ID,
            ClientId=COGNITO_APP_CLIENT_ID,
            AuthFlow="ADMIN_NO_SRP_AUTH",
            AuthParameters={
                "USERNAME": username,
                "PASSWORD": password
            }
        )

        # If no challenge, return tokens directly
        if "AuthenticationResult" in response:
            ic("Authentication successful, returning tokens")
            
            # Get the sub from the ID token
            id_token = response["AuthenticationResult"]["IdToken"]
            try:
                # Decode without verification to get the sub
                unverified_payload = jwt.decode(id_token, options={"verify_signature": False})
                sub = unverified_payload.get("sub")
                ic(f"User's sub from ID token: {sub}")
                
                # Get user from DB and print their cognito_id
                db_user = get_user_by_email(db, username)
                if db_user:
                    ic(f"User's cognito_id in DB: {db_user.cognito_id}")
                else:
                    ic("User not found in database")
            except Exception as e:
                ic(f"Error decoding token or querying DB: {str(e)}")
            
            return {
                "accessToken": response["AuthenticationResult"]["AccessToken"],
                "idToken": response["AuthenticationResult"]["IdToken"],
                "refreshToken": response["AuthenticationResult"]["RefreshToken"]
            }

        # Handle password change challenge
        if response.get("ChallengeName") == "NEW_PASSWORD_REQUIRED":
            ic("NEW_PASSWORD_REQUIRED challenge received")
            return {
                "challengeName": "NEW_PASSWORD_REQUIRED",
                "username": username,
                "session": response.get("Session")
            }

        ic(f"Unexpected authentication flow: {response}")
        raise HTTPException(status_code=400, detail="Unexpected authentication flow")

    except cognito_client.exceptions.NotAuthorizedException as e:
        ic(f"NotAuthorizedException: {str(e)}")
        # Try one more time to get user status after auth failure
        try:
            user_response = cognito_client.admin_get_user(
                UserPoolId=COGNITO_USERPOOL_ID,
                Username=username
            )
            ic(f"User response after auth failure: {user_response}")
            user_status = user_response.get("UserStatus")  # This is at the top level of the response
            
            # Check for both statuses again after auth failure
            if user_status in ["RESET_REQUIRED", "FORCE_CHANGE_PASSWORD"]:
                ic(f"User has {user_status} status after auth failure, initiating password reset")
                return handle_password_reset_required(cognito_client, username)
        except Exception as status_error:
            ic(f"Error checking status after auth failure: {str(status_error)}")
        
        raise HTTPException(status_code=401, detail="Invalid username or password")
    except cognito_client.exceptions.PasswordResetRequiredException as e:
        ic(f"PasswordResetRequiredException: {str(e)}")
        return handle_password_reset_required(cognito_client, username)
    except Exception as e:
        ic(f"Unexpected error during login: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/password-challenge")
async def password_challenge(request: Request):
    body = await request.json()
    username = body.get("username")
    new_password = body.get("newPassword")
    session = body.get("session")

    if not all([username, new_password, session]):
        raise HTTPException(status_code=400, detail="Missing fields")

    cognito_client = boto3.client("cognito-idp", region_name=COGNITO_REGION)

    try:
        challenge_response = cognito_client.admin_respond_to_auth_challenge(
            UserPoolId=COGNITO_USERPOOL_ID,
            ClientId=COGNITO_APP_CLIENT_ID,
            ChallengeName="NEW_PASSWORD_REQUIRED",
            Session=session,
            ChallengeResponses={
                "USERNAME": username,
                "NEW_PASSWORD": new_password
            }
        )

        return {
            "accessToken": challenge_response["AuthenticationResult"]["AccessToken"],
            "idToken": challenge_response["AuthenticationResult"]["IdToken"],
            "refreshToken": challenge_response["AuthenticationResult"]["RefreshToken"]
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/confirm-password-reset")
async def confirm_password_reset(request: Request):
    body = await request.json()
    username = body.get("username")
    confirmation_code = body.get("confirmationCode")
    new_password = body.get("newPassword")

    if not all([username, confirmation_code, new_password]):
        raise HTTPException(status_code=400, detail="Missing required fields")

    cognito_client = boto3.client("cognito-idp", region_name=COGNITO_REGION)

    try:
        response = cognito_client.confirm_forgot_password(
            ClientId=COGNITO_APP_CLIENT_ID,
            Username=username,
            ConfirmationCode=confirmation_code,
            Password=new_password
        )

        # After successful password reset, try to login
        auth_response = cognito_client.admin_initiate_auth(
            UserPoolId=COGNITO_USERPOOL_ID,
            ClientId=COGNITO_APP_CLIENT_ID,
            AuthFlow="ADMIN_NO_SRP_AUTH",
            AuthParameters={
                "USERNAME": username,
                "PASSWORD": new_password
            }
        )

        return {
            "accessToken": auth_response["AuthenticationResult"]["AccessToken"],
            "idToken": auth_response["AuthenticationResult"]["IdToken"],
            "refreshToken": auth_response["AuthenticationResult"]["RefreshToken"]
        }

    except cognito_client.exceptions.CodeMismatchException:
        raise HTTPException(status_code=400, detail="Invalid confirmation code")
    except cognito_client.exceptions.ExpiredCodeException:
        raise HTTPException(status_code=400, detail="Confirmation code has expired")
    except cognito_client.exceptions.InvalidPasswordException:
        raise HTTPException(status_code=400, detail="Password does not meet requirements")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

