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
import jwt
import uuid
from datetime import datetime, timezone
from fastapi import HTTPException
from fastapi import APIRouter, Request, Depends
from fastapi.responses import JSONResponse, HTMLResponse
from pylti1p3.message_launch import MessageLaunch
from pylti1p3.names_roles import NamesRolesProvisioningService
from pylti1p3.grade import Grade
from sqlalchemy import cast
from sqlalchemy.orm import Session
from sqlalchemy.dialects.postgresql import JSONB
from pylti1p3.deep_link_resource import DeepLinkResource

from logging_config import setup_logging
from database.db import get_db
from database.models import Chatbot
from database.crud import get_courses_by_teacher_group, get_groups, get_lti_platforms_by_group, get_course_by_id
from lti.config import LTIToolConfigFromProvider, OpenIDConfig, LTIDBConfigProvider, LTIServiceConfig
from lti.services import handle_login, handle_launch, check_for_validation_request, SessionDataStorage, ExtendedMessageLaunch
from lti.utils import TemplateHandler
from utility.auth import require_token_types
from utility.tokens import LTIServicesTokenPayload

# Configure logging
logger = setup_logging(module_name='lti')

# Constants
PAGE_TITLE = 'LTI Tool'
CACHE_TIMEOUT = 600  # 10 minutes
BACKEND_DOMAIN_NAME = os.getenv("BACKEND_DOMAIN_NAME")

if not BACKEND_DOMAIN_NAME:
    raise ValueError("BACKEND_DOMAIN_NAME is not set")

LTI_TOOL_JWKS_URL = f"https://{BACKEND_DOMAIN_NAME}/lti/.well-known/jwks.json"

router = APIRouter()
template_handler = TemplateHandler(templates_dir="lti/templates")

@router.get("/login", tags=["LTI"])
async def login_get(request: Request):
    """Handles GET requests to the login endpoint"""
    try:
        return await check_for_validation_request(request)
    except Exception as e:
        logger.error(f"Error in login_get: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/login", tags=["LTI"])
async def login_post(request: Request, db: Session = Depends(get_db)):
    """Handles POST requests to the login endpoint"""
    form_data = await request.form()
    client_id = form_data.get("client_id")
    if not client_id:
        raise HTTPException(status_code=400, detail="client_id is required")
    
    config_provider = LTIDBConfigProvider(db, client_id, LTI_TOOL_JWKS_URL)
    tool_config = LTIToolConfigFromProvider(config_provider)

    try:
        response = await handle_login(request, form_data, tool_config)
        request.session['lti_client_id'] = client_id
        return response
    except Exception as e:
        logger.error(f"Error in login_post: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/launch")
async def launch_get(request: Request):
    """Handles the LTI launch request via GET"""
    try:
        return await check_for_validation_request(request)
    except Exception as e:
        logger.error(f"Error in launch_get: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/launch")
async def launch_post(request: Request, db: Session = Depends(get_db)):
    """Handles the LTI launch request via POST"""
    try:
        client_id = request.session.get('lti_client_id')
        # If client_id is not in session, try to extract it from the id_token
        if not client_id:
            try:
                form_data = await request.form()
                id_token = form_data.get('id_token')
                if id_token:
                    # Decode without verification to get the claims, we will verify the signature in the handle_launch function
                    decoded = jwt.decode(id_token, options={"verify_signature": False})
                    client_id = decoded.get('aud')  # 'aud' is the client_id in LTI 1.3
                    logger.info(f"Extracted client_id from id_token: {client_id}")
                    if not client_id:
                        raise HTTPException(status_code=400, detail="client_id is required")
            except HTTPException:
                raise
            except Exception as e:
                logger.warning(f"Failed to extract client_id from id_token: {str(e)}")

        config_provider = LTIDBConfigProvider(db, client_id, LTI_TOOL_JWKS_URL)
        tool_config = LTIToolConfigFromProvider(config_provider)
        
        return await handle_launch(request, tool_config, template_handler)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Launch error: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/.well-known/jwks.json")
async def get_jwks(request: Request, db: Session = Depends(get_db)):
    """Returns the JSON Web Key Set (JWKS) for all active LTI platforms"""
    try:
        jwks_keys = []
        for group in get_groups(db):
            active_lti_platforms = get_lti_platforms_by_group(db, group.id, active_only=True)
            if len(active_lti_platforms) > 0:
                # jwks are the same for all active LTI platforms in the same group (same private key)
                tool_config = LTIToolConfigFromProvider(LTIDBConfigProvider(db, active_lti_platforms[0].client_id, LTI_TOOL_JWKS_URL))
                group_jwks = tool_config.get_jwks()
                jwks_keys.extend(group_jwks)
        
        return {"keys": jwks_keys}
    except Exception as e:
        logger.error(f"JWKS Generation Failed: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/.well-known/openid-configuration")
async def get_openid_configuration(request: Request):
    """Returns the OpenID Connect configuration for the tool"""
    try:
        base_url = str(request.base_url).rstrip('/')
        config = OpenIDConfig.build_openid_config(base_url)
        return JSONResponse(content=config)
    except Exception as e:
        logger.error(f"OpenID Configuration Generation Failed: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/deep_link")
async def deep_link(
    request: Request, 
    db: Session = Depends(get_db), 
    lti_session_params: dict = Depends(require_token_types(allowed_types=["lti_deep_link"]))
):
    """Handles LTI Deep Linking requests with proper content item creation using pylti1p3"""
    try:
        if not lti_session_params:
            raise HTTPException(status_code=401, detail="Invalid LTI token")
        
        group_id = lti_session_params.get("group_id")
        if not group_id:
            raise HTTPException(status_code=400, detail="group_id is required")

        # Parse request body for resource configuration
        try:
            body = await request.json()
            resource_types = body.get('resource_types', [LTIServiceConfig.DEFAULT_SERVICE_TYPE])
            service_type = resource_types[0] if resource_types else LTIServiceConfig.DEFAULT_SERVICE_TYPE
            custom_params = body.get('custom_params', {})
        except Exception as e:
            service_type = LTIServiceConfig.DEFAULT_SERVICE_TYPE
            custom_params = {}
            logger.warning(f"Failed to parse JSON body, using defaults: {e}")
        
        # Get course_id from custom_params
        course_id = custom_params.get('course_id', LTIServiceConfig.DEFAULT_COURSE_ID)
        
        # Get launch_id from query params or session
        launch_id = request.query_params.get("launch_id")
        if not launch_id:
            storage = SessionDataStorage(request)
            launch_id = storage.get_session_data("current_launch_id")
            if not launch_id:
                logger.error("No launch_id found for deep linking")
                raise HTTPException(status_code=400, detail="Deep linking session not found. Please start the deep linking process again.")
        
        # Get the client_id from session or cached data
        client_id = request.session.get('lti_client_id')
        logger.info(f"Client ID from session: {client_id}")
        
        if not client_id:
            # Try to get client_id from cached launch data
            storage = SessionDataStorage(request)
            cached_data = storage.get_session_data(f"launch_data_{launch_id}")
            logger.info(f"Cached data for launch_id {launch_id}: {cached_data}")
            
            if cached_data:
                # Try explicit client_id field first, then jwt_body
                client_id = cached_data.get('client_id') or (cached_data.get('jwt_body', {}).get('aud'))
                # Store it in session for future use
                if client_id:
                    request.session['lti_client_id'] = client_id
                    logger.info(f"Retrieved and stored client_id from cached data: {client_id}")
            
            if not client_id:
                # Try to get from all session data to debug
                all_session_keys = storage.get_all_session_keys()
                logger.info(f"All session keys: {all_session_keys}")
                
                # Try to find any cached launch data
                for key in all_session_keys:
                    if key.startswith('launch_data_'):
                        data = storage.get_session_data(key)
                        logger.info(f"Found cached data in {key}: {data}")
                        if data and data.get('client_id'):
                            client_id = data['client_id']
                            request.session['lti_client_id'] = client_id
                            logger.info(f"Found client_id in {key}: {client_id}")
                            break
                
                if not client_id:
                    logger.error("client_id not found in session or cache")
                    raise HTTPException(status_code=400, detail="client_id not found in session")
        
        # Initialize LTI configuration
        config_provider = LTIDBConfigProvider(db, client_id, LTI_TOOL_JWKS_URL)
        tool_config = LTIToolConfigFromProvider(config_provider)
        
        # Initialize storage and services
        storage = SessionDataStorage(request)
        
        try:
            # Recreate the MessageLaunch from cache
            from lti.utils import RequestWrapper
            request_wrapper = RequestWrapper(request, {})
            
            message_launch = ExtendedMessageLaunch.from_cache(
                launch_id, 
                request_wrapper, 
                tool_config,
                launch_data_storage=storage
            )
            
            if not message_launch.is_deep_linking_request():
                raise HTTPException(status_code=400, detail="Not a deep linking request")
        except Exception as e:
            logger.error(f"Failed to retrieve message launch from cache: {str(e)}")
            raise HTTPException(status_code=500, detail=f"Deep linking session error: {str(e)}")
        
        launch_url = f"https://{BACKEND_DOMAIN_NAME}/lti/launch?service_type={service_type}&course_id={course_id}&group_id={group_id}"
        
        # Set title based on service type
        resource_title = LTIServiceConfig.get_service_title(service_type)
        
        # Create custom parameters for the JWT (these will be preserved in launches)
        resource_custom_params = LTIServiceConfig.get_custom_params(service_type, course_id, group_id)
        if service_type == LTIServiceConfig.LECTURE_ASSISTANT:
            resource_custom_params['system_prompt'] = custom_params.get('system_prompt', '')
        
        # Create the deep link resource using pylti1p3 library
        try:
            deep_link_resource = DeepLinkResource()
            deep_link_resource.set_url(launch_url) \
                             .set_custom_params(resource_custom_params) \
                             .set_title(resource_title)
            
            # Generate the response form using the pylti1p3 library
            deep_link = message_launch.get_deep_link()
            response_html = deep_link.output_response_form([deep_link_resource])
            
            # Return the auto-submit form
            return HTMLResponse(content=response_html, status_code=200)
            
        except Exception as e:
            logger.error(f"Failed to create deep link resource with pylti1p3: {str(e)}")
            raise HTTPException(status_code=500, detail=f"Failed to create deep link resource: {str(e)}")
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Deep link error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.get("/names-roles")
async def get_names_roles(request: Request, db: Session = Depends(get_db)):
    """Handles LTI Names and Roles Provisioning Service requests"""
    try:
        client_id = request.session.get('lti_client_id')
        
        if not client_id:
            raise HTTPException(status_code=400, detail="client_id is required")
        
        config_provider = LTIDBConfigProvider(db, client_id, LTI_TOOL_JWKS_URL)
        tool_config = LTIToolConfigFromProvider(config_provider)

        # Get group_id from request parameters
        group_id = request.query_params.get("group_id")
        if not group_id:
            raise HTTPException(status_code=400, detail="group_id is required")

        # Initialize storage services
        launch_data_storage = SessionDataStorage(request)
        
        # Create message launch
        launch = MessageLaunch(
            request=request,
            tool_config=tool_config,
            launch_data_storage=launch_data_storage,
            session_service=launch_data_storage
        )
        
        # Get names and roles
        nrps = NamesRolesProvisioningService(launch)
        members = nrps.get_members()
        return members
    except Exception as e:
        logger.error(f"Names and roles error: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/grade")
async def submit_grade(request: Request, db: Session = Depends(get_db)):
    """Submits a grade for an LTI assignment"""
    try:
        client_id = request.session.get('lti_client_id')
        
        if not client_id:
            raise HTTPException(status_code=400, detail="client_id is required")
        
        config_provider = LTIDBConfigProvider(db, client_id, LTI_TOOL_JWKS_URL)
        tool_config = LTIToolConfigFromProvider(config_provider)
        # Get grade data from request body
        try:
            body = await request.json()
            score_given = body.get('score_given', 0.0)
            score_maximum = body.get('score_maximum', 1.0)
            comment = body.get('comment', '')
            activity_progress = body.get('activity_progress', 'Completed')
            grading_progress = body.get('grading_progress', 'FullyGraded')
        except Exception:
            # Fallback to default values if no body provided
            score_given = LTIServiceConfig.DEFAULT_SCORE_GIVEN
            score_maximum = LTIServiceConfig.DEFAULT_SCORE_MAXIMUM
            comment = LTIServiceConfig.DEFAULT_COMMENT
            activity_progress = LTIServiceConfig.DEFAULT_ACTIVITY_PROGRESS
            grading_progress = LTIServiceConfig.DEFAULT_GRADING_PROGRESS

        # Initialize storage services
        launch_data_storage = SessionDataStorage(request)
        
        # Create message launch
        launch = MessageLaunch(
            request=request,
            tool_config=tool_config,
            launch_data_storage=launch_data_storage,
            session_service=launch_data_storage
        )
        
        # Create and submit grade
        grade = Grade(launch)
        grade.set_score_given(score_given)
        grade.set_score_maximum(score_maximum)
        grade.set_comment(comment)
        grade.set_activity_progress(activity_progress)
        grade.set_grading_progress(grading_progress)
        grade.set_timestamp(datetime.now(timezone.utc).isoformat())
        
        result = grade.submit()
        return result
    except Exception as e:
        logger.error(f"Grade submission error: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/deep_link/courses")
async def get_courses_by_group(
    db: Session = Depends(get_db),
    lti_session_params: dict = Depends(require_token_types(allowed_types=["lti_deep_link"])),
):
    """Get courses for a specific group with LTI session validation"""
    try:
        # Validate LTI session
        if not lti_session_params:
            raise HTTPException(status_code=401, detail="Invalid LTI token")
        
        group_id = lti_session_params.get("group_id")
        if not group_id:
            raise HTTPException(status_code=400, detail="group_id is required")
        
        group_uuid = uuid.UUID(group_id)
        courses = get_courses_by_teacher_group(db, group_uuid)

        courses_data = [
            {
                "id": str(course.id),
                "title": course.title,
                "status": "active"
            }
            for course in courses
        ]
        
        return {"courses": courses_data}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting courses by group: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/deep_link/config")
async def deep_link_config(request: Request, db: Session = Depends(get_db)):
    """Returns the deep linking configuration for the tool"""
    try:
        client_id = request.session.get('lti_client_id')
        
        if not client_id:
            raise HTTPException(status_code=400, detail="client_id is required")
        
        # Get group_id from request parameters
        group_id = request.query_params.get("group_id")
        if not group_id:
            raise HTTPException(status_code=400, detail="group_id is required")
        
        base_url = f"https://{BACKEND_DOMAIN_NAME}"
        
        # Define available resource types
        resource_types = LTIServiceConfig.get_all_resource_types(base_url)
        
        config = {
            "resource_types": resource_types,
            "deep_link_url": f"{base_url}/lti/deep_link",
            "group_id": group_id,
            "version": LTIServiceConfig.RESOURCE_VERSION,
            "supported_platforms": LTIServiceConfig.SUPPORTED_PLATFORMS
        }
        
        return JSONResponse(content=config)
        
    except Exception as e:
        logger.error(f"Deep link config error: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/deep_link/create_tool")
async def create_tool_from_ui(
    request: Request, 
    db: Session = Depends(get_db),
    lti_session_params: dict = Depends(require_token_types(allowed_types=["lti_deep_link"]))
):
    """Handles tool creation from the deep link UI without requiring full LTI session"""
    try:
        # Validate LTI session
        if not lti_session_params:
            raise HTTPException(status_code=401, detail="Invalid LTI token")
        
        group_id = lti_session_params.get("group_id")
        if not group_id:
            raise HTTPException(status_code=400, detail="group_id is required")

        # Get request body for configuration
        try:
            body = await request.json()
            resource_types = body.get('resource_types', [LTIServiceConfig.DEFAULT_SERVICE_TYPE])
            service_type = resource_types[0] if resource_types else LTIServiceConfig.DEFAULT_SERVICE_TYPE
            custom_params = body.get('custom_params', {})
        except Exception as e:
            service_type = LTIServiceConfig.DEFAULT_SERVICE_TYPE
            custom_params = {}
            logger.warning(f"Failed to parse JSON body, using defaults: {e}")
        
        # Get course_id from custom_params
        course_id = custom_params.get('course_id', LTIServiceConfig.DEFAULT_COURSE_ID)
        
        # Create a success response
        result = {
            "message": f"Successfully created {service_type} resource",
            "resource_type": service_type,
            "group_id": group_id,
            "course_id": course_id,
            "success": True,
            "launch_url": f"{request.base_url}lti/launch?service_type={service_type}&group_id={group_id}&course_id={course_id}"
        }
        
        logger.info(f"Created {service_type} tool for group {group_id}")
        return JSONResponse(content=result, status_code=200)
        
    except Exception as e:
        logger.error(f"Tool creation error: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))

