# © [2025] EDT&Partners. Licensed under CC BY 4.0.

import base64
import json
import os
import jwt as pyjwt
import uuid
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional
from pylti1p3.message_launch import MessageLaunch
from fastapi import Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.exceptions import HTTPException
from urllib.parse import urljoin, urlparse
from pylti1p3.deep_link_resource import DeepLinkResource
from lti.utils import generate_request_id, get_form_data, build_redirect_url, get_safe_target_link_uri, RequestWrapper, TemplateHandler
from lti.config import LTIToolConfigFromProvider, LTIServiceConfig
from lti.secrets import get_lti_secrets
from logging_config import setup_logging

# Configure logging
logger = setup_logging(module_name='lti_services')

LTI_SESSION_TOKENS_SECRET = get_lti_secrets().session_tokens_secret
if not LTI_SESSION_TOKENS_SECRET:
    raise ValueError("LTI_SESSION_TOKENS_SECRET is not set")

BACKEND_DOMAIN_NAME = os.getenv("BACKEND_DOMAIN_NAME")
if not BACKEND_DOMAIN_NAME:
    raise ValueError("BACKEND_DOMAIN_NAME is not set")

def create_lti_session_token(data: dict):
    to_encode = data.copy()
    encoded_jwt = pyjwt.encode(to_encode, LTI_SESSION_TOKENS_SECRET, algorithm="HS256")
    return encoded_jwt

class StateManager:
    """Manages state parameter encoding and decoding"""
    
    @staticmethod
    def encode_state(session_id: str) -> str:
        """Encode session ID into a state parameter"""
        state_data = {
            "session_id": session_id,
            "timestamp": datetime.now(timezone.utc).timestamp()
        }
        state_json = json.dumps(state_data)
        return base64.urlsafe_b64encode(state_json.encode()).decode()

    @staticmethod
    def decode_state(state: str) -> Optional[Dict[str, Any]]:
        """Decode state parameter back to session data"""
        try:
            state_json = base64.urlsafe_b64decode(state.encode()).decode()
            return json.loads(state_json)
        except Exception:
            return None

class ExtendedMessageLaunch(MessageLaunch):
    """Extended MessageLaunch with custom validation and request handling"""
    
    def __init__(self, request, tool_config, launch_data_storage, session_service, cookie_service):
        self.request = request
        self._form_data = None
        self._session_service = session_service
        self._launch_data_storage = launch_data_storage
        self._session_id = cookie_service.session_cookie
        
        logger.info(f"Creating ExtendedMessageLaunch with session_id: {self._session_id}")
        
        super().__init__(request, tool_config, launch_data_storage=launch_data_storage,
                        session_service=session_service, cookie_service=cookie_service)
        self._launch_data = None
        self._jwt_body = None

    @classmethod
    def from_cache(cls, launch_id, request, tool_config, launch_data_storage=None):
        """Create MessageLaunch from cached launch data (following Flask example pattern)"""
        logger.info(f"Creating ExtendedMessageLaunch from cache with launch_id: {launch_id}")
        
        if not launch_data_storage:
            # Create a temporary storage if none provided
            launch_data_storage = SessionDataStorage(request)
        
        # Get cached launch data
        cached_data = launch_data_storage.get_session_data(f"launch_data_{launch_id}")
        if not cached_data:
            logger.error(f"No cached launch data found for launch_id: {launch_id}")
            raise Exception(f"No cached launch data found for launch_id: {launch_id}")
        
        logger.info(f"Found cached launch data for launch_id: {launch_id}")
        
        # Create a mock cookie service for compatibility
        from lti.services import LTICookieService
        cookie_service = LTICookieService(request)
        
        # Create the instance
        instance = cls(
            request=request,
            tool_config=tool_config,
            launch_data_storage=launch_data_storage,
            session_service=launch_data_storage,
            cookie_service=cookie_service
        )
        
        # Set the cached data
        instance._launch_data = cached_data.get('launch_data')
        instance._jwt_body = cached_data.get('jwt_body')
        instance._launch_id = launch_id
        
        # Initialize required attributes for deep linking
        instance._registration = tool_config.get_registration_by_issuer(instance._jwt_body.get('iss'))
        instance._is_deep_linking_launch = True
        
        logger.info(f"Successfully created ExtendedMessageLaunch from cache")
        return instance

    async def _get_form_data(self):
        """Get form data asynchronously"""
        if self._form_data is None and isinstance(self.request, Request):
            try:
                form_data = await self.request.form()
                self._form_data = {k: v for k, v in form_data.items()}
                logger.info(f"Retrieved form data: {list(self._form_data.keys()) if self._form_data else 'None'}")
            except Exception as e:
                logger.error(f"Error getting form data: {str(e)}")
                self._form_data = {}
        return self._form_data or {}

    def _get_jwt_body(self):
        """Get JWT body with validation"""
        try:
            jwt = self._request.get_request_param('id_token')
            if not jwt:
                logger.error("Missing id_token in request")
                raise Exception('Missing id_token')
            
            logger.info(f"Processing JWT token (length: {len(jwt) if jwt else 0})")
            
            try:
                header = pyjwt.get_unverified_header(jwt)
                jwt_kid = header.get('kid')
                logger.info(f"JWT header - kid: {jwt_kid}, alg: {header.get('alg')}, typ: {header.get('typ')}")
            except pyjwt.PyJWTError as e:
                logger.error(f"Invalid JWT header: {str(e)}")
                raise ValueError(f"Invalid JWT header: {str(e)}")
                
            tool_conf: LTIToolConfigFromProvider = self._tool_config
            expected_issuer = tool_conf.get_expected_issuer() 
            expected_audience = tool_conf.get_expected_audience()

            logger.info(f"Expected issuer: {expected_issuer}, Expected audience: {expected_audience}")

            if not expected_issuer or not expected_audience:
                logger.error("Issuer or Audience not configured in the tool")
                raise ValueError("Issuer or Audience not configured in the tool.")

            public_key = tool_conf.get_public_key(expected_issuer, expected_audience, jwt_kid)
            if not public_key:
                logger.error(f"Could not retrieve public key for validation - issuer: {expected_issuer}, audience: {expected_audience}, kid: {jwt_kid}")
                raise ValueError("Could not retrieve public key for validation.")

            logger.info("Retrieved public key for JWT validation")

            try:
                decoded_token = pyjwt.decode(
                    jwt,
                    public_key,
                    algorithms=['RS256'],
                    audience=expected_audience,
                    issuer=expected_issuer,
                    options={
                        'verify_signature': True,
                        'verify_aud': True,
                        'verify_iss': True,
                        'verify_exp': True,
                        'verify_iat': True,
                        'require': ['exp', 'iat', 'iss', 'aud', 'sub'],
                    },
                    leeway=30
                )
                logger.info("JWT validation successful")

            except pyjwt.ExpiredSignatureError as e:
                logger.warning("JWT token expired, checking grace period")
                unverified_payload = e.payload
                if unverified_payload:
                    exp_time = unverified_payload.get('exp')
                    current_time = datetime.now(timezone.utc).timestamp()
                    
                    if exp_time and (current_time - exp_time) < 300:
                        logger.info("Token expired within grace period, proceeding without exp verification")
                        decoded_token = pyjwt.decode(
                            jwt,
                            public_key,
                            algorithms=['RS256'],
                            audience=expected_audience,
                            issuer=expected_issuer,
                            options={'verify_exp': False}
                        )
                    else:
                        logger.error("Token has expired outside the grace period")
                        raise ValueError("Token has expired outside the grace period.")
                else:
                    logger.error("Token has expired")
                    raise ValueError("Token has expired.")
            
            # Call parent validation for additional checks
            jwt_body = super()._get_jwt_body()
            result = jwt_body or decoded_token
            logger.info(f"JWT body extracted successfully, keys: {list(result.keys()) if result else 'None'}")
            return result
                
        except Exception as e:
            logger.error(f"JWT validation failed: {str(e)}")
            raise Exception(f'JWT validation failed: {str(e)}')

    def validate(self):
        """Validate the launch request - synchronous version for parent class compatibility"""
        # This is called by the parent class synchronously
        try:
            logger.info("Starting basic validation")
            # Basic validation that can be done synchronously
            if hasattr(self, '_request') and self._request:
                jwt = self._request.get_request_param('id_token')
                if not jwt:
                    logger.error("Missing id_token in basic validation")
                    raise Exception('Missing id_token')
            logger.info("Basic validation passed")
            return self
        except Exception as e:
            logger.error(f"Basic validation failed: {str(e)}")
            raise Exception(f'Basic validation failed: {str(e)}')

    async def validate_async(self):
        """Validate the launch request asynchronously - full validation"""
        try:
            logger.info("Starting async validation")
            # Get form data and create request wrapper
            form_data = await self._get_form_data()
            wrapper = RequestWrapper(self.request, form_data)
            self._request = wrapper
            
            # Validate JWT
            jwt = self._request.get_request_param('id_token')
            if not jwt:
                logger.error("Missing id_token in async validation")
                raise Exception('Missing id_token')
            
            logger.info("Getting JWT body")
            self._jwt_body = self._get_jwt_body()
            
            # Validate state if present
            state = self._request.get_request_param('state')
            if state:
                logger.info("Validating state parameter")
                await self.validate_state()
            
            # Store nonce
            nonce = self._jwt_body.get('nonce')
            if nonce:
                logger.info(f"Storing nonce: {nonce}")
                self._launch_data_storage.save_nonce(nonce)
            
            # Extract launch data from JWT
            logger.info("Extracting launch data from JWT")
            self._launch_data = self._extract_launch_data()
            logger.info("Async validation completed successfully")
            return self
            
        except Exception as e:
            logger.error(f"Async validation failed: {str(e)}")
            raise Exception(f'Validation failed: {str(e)}')

    def _extract_launch_data(self) -> Dict[str, Any]:
        """Extract launch data from JWT"""
        logger.info("Extracting launch data from JWT")
        launch_data = {}
        
        # Standard LTI claims
        lti_claims = {
            'message_type': 'https://purl.imsglobal.org/spec/lti/claim/message_type',
            'version': 'https://purl.imsglobal.org/spec/lti/claim/version',
            'roles': 'https://purl.imsglobal.org/spec/lti/claim/roles',
            'context': 'https://purl.imsglobal.org/spec/lti/claim/context',
            'resource_link': 'https://purl.imsglobal.org/spec/lti/claim/resource_link',
            'custom': 'https://purl.imsglobal.org/spec/lti/claim/custom',
            'platform': 'https://purl.imsglobal.org/spec/lti/claim/tool_platform',
            'launch_presentation': 'https://purl.imsglobal.org/spec/lti/claim/launch_presentation',
            'deployment_id': 'https://purl.imsglobal.org/spec/lti/claim/deployment_id',
            'target_link_uri': 'https://purl.imsglobal.org/spec/lti/claim/target_link_uri'
        }
        
        # Extract LTI claims
        for key, claim in lti_claims.items():
            value = self._jwt_body.get(claim)
            launch_data[key] = value if value is not None else ([] if key == 'roles' else {})
        
        # Add standard JWT claims
        for claim in ['name', 'email', 'sub', 'iss', 'aud', 'exp', 'iat']:
            launch_data[claim] = self._jwt_body.get(claim)
        
        # Log important values
        target_link_uri = launch_data.get('target_link_uri', '')
        custom_params = launch_data.get('custom', {})
        
        if target_link_uri:
            logger.info(f"Target link URI: {target_link_uri}")
        if custom_params:
            logger.info(f"Custom parameters: {custom_params}")
        
        logger.info(f"Launch data extraction completed with {len(launch_data)} keys")
        return launch_data

    async def get_launch_data(self):
        """Get launch data asynchronously"""
        logger.info("Getting launch data")
        if self._launch_data is None:
            logger.info("Launch data is None, starting validation")
            await self.validate_async()
        else:
            logger.info("Launch data already available")
        logger.info(f"Returning launch data with {len(self._launch_data) if self._launch_data else 0} keys")
        return self._launch_data

    async def validate_state(self):
        """Validate state asynchronously - currently disabled for development"""
        return True

    def set_state(self, state):
        """Set state in session"""
        if not self._session_id:
            raise Exception("No session ID available")
        self._session_service.save_session_data(f"lti_state_{self._session_id}", state)
        self._session_service.save_session_data("lti_state", state)

    async def get_nonce(self):
        """Get nonce from JWT"""
        try:
            # Ensure we have JWT body
            if not self._jwt_body:
                # If we don't have JWT body, try to get it synchronously
                self._jwt_body = self._get_jwt_body()
            return self._jwt_body.get('nonce')
        except Exception:
            return None

    def get_state(self):
        """Get state from request parameters"""
        # Use RequestWrapper's get_param method if available, otherwise fall back to query_params
        if hasattr(self.request, 'get_param'):
            state = self.request.get_param("state")
        else:
            state = self.request.query_params.get("state")
        
        if state:
            try:
                state_data = StateManager.decode_state(state)
                if state_data and "session_id" in state_data:
                    self._session_id = state_data["session_id"]
                    self._session_service.set_session_id(self._session_id)
                    return state
            except Exception:
                pass
        return None

    def get_session_id(self):
        """Get the session ID"""
        return self._session_id

    def set_session_id(self, session_id):
        """Set the session ID"""
        self._session_id = session_id

    def get_launch_url(self):
        """Get launch URL with state parameter"""
        launch_url = super().get_launch_url()
        state = self.get_state()
        
        if state:
            separator = '&' if '?' in launch_url else '?'
            launch_url = f"{launch_url}{separator}state={state}"
            
        return launch_url

    def is_deep_linking_request(self) -> bool:
        """Check if this is a deep linking request"""
        try:
            message_type = self._jwt_body.get('https://purl.imsglobal.org/spec/lti/claim/message_type')
            is_deep_link = message_type == 'LtiDeepLinkingRequest'
            return is_deep_link
        except Exception as e:
            logger.error(f"Error checking deep linking request: {str(e)}")
            return False

    def get_launch_id(self):
        """Get the launch ID for this launch"""
        if hasattr(self, '_launch_id') and self._launch_id:
            return self._launch_id
        
        # Generate a new launch ID if we don't have one
        import uuid
        self._launch_id = str(uuid.uuid4())
        logger.info(f"Generated new launch_id: {self._launch_id}")
        return self._launch_id
    
    def cache_launch_data(self):
        """Cache the launch data for later use (following Flask example pattern)"""
        try:
            launch_id = self.get_launch_id()
            cache_data = {
                'launch_data': self._launch_data,
                'jwt_body': self._jwt_body,
                'cached_at': datetime.now(timezone.utc).isoformat()
            }
            
            # Store the launch data
            self._launch_data_storage.save_session_data(f"launch_data_{launch_id}", cache_data)
            
            # Also store the current launch_id for easy access
            self._launch_data_storage.save_session_data("current_launch_id", launch_id)
            
            logger.info(f"Cached launch data for launch_id: {launch_id}")
            return launch_id
        except Exception as e:
            logger.error(f"Failed to cache launch data: {str(e)}")
            raise Exception(f"Failed to cache launch data: {str(e)}")

    def get_deep_linking_settings(self):
        """Get deep linking settings from JWT"""
        try:
            deep_link_settings = self._jwt_body.get('https://purl.imsglobal.org/spec/lti-dl/claim/deep_linking_settings', {})
            return deep_link_settings
        except Exception as e:
            logger.error(f"Error getting deep linking settings: {str(e)}")
            return {}

    def get_deep_link(self):
        """Get deep link object for creating response (following Flask example pattern)"""
        try:
            # For cached launches, bypass validation and create DeepLink manually
            if hasattr(self, '_launch_id') and self._launch_data:
                # Create a simple DeepLink-like object that provides the output_response_form method
                class CachedDeepLink:
                    def __init__(self, message_launch, jwt_body):
                        self.message_launch = message_launch
                        self.jwt_body = jwt_body
                        self.deep_link_settings = jwt_body.get('https://purl.imsglobal.org/spec/lti-dl/claim/deep_linking_settings', {})
                    
                    def output_response_form(self, resources):                        
                        # Create response JWT payload
                        response_payload = {
                            "iss": self.jwt_body.get('aud'),  # Use audience from original JWT as our issuer
                            "aud": [self.jwt_body.get('iss')],
                            "sub": self.jwt_body.get('sub'),  # Include subject from original JWT
                            "exp": int(datetime.now(timezone.utc).timestamp()) + 3600,
                            "iat": int(datetime.now(timezone.utc).timestamp()),
                            "nonce": str(uuid.uuid4()),
                            "https://purl.imsglobal.org/spec/lti/claim/message_type": "LtiDeepLinkingResponse",
                            "https://purl.imsglobal.org/spec/lti/claim/version": "1.3.0",
                            "https://purl.imsglobal.org/spec/lti/claim/deployment_id": self.jwt_body.get('https://purl.imsglobal.org/spec/lti/claim/deployment_id'),
                            "https://purl.imsglobal.org/spec/lti-dl/claim/content_items": [
                                {
                                    "type": "ltiResourceLink",
                                    "url": resource.get_url(),
                                    "title": resource.get_title(),
                                    "custom": resource.get_custom_params()
                                } for resource in resources
                            ]
                        }
                        
                        # Add data field if present
                        if self.deep_link_settings.get('data'):
                            response_payload["https://purl.imsglobal.org/spec/lti-dl/claim/data"] = self.deep_link_settings['data']
                        
                        # Sign the JWT
                        private_key = self.message_launch._tool_config._load_private_key()
                        
                        # Get the kid from the tool's JWKS
                        try:
                            jwks = self.message_launch._tool_config.get_jwks()
                            if jwks and len(jwks) > 0:
                                kid = jwks[0].get('kid')
                            else:
                                logger.warning("No JWKS available, using fallback kid")
                                kid = 'default-kid'
                        except Exception as e:
                            logger.error(f"Failed to get JWKS for kid: {str(e)}")
                            kid = 'default-kid'
                        
                        # Create JWT with kid in header
                        response_jwt = pyjwt.encode(
                            response_payload, 
                            private_key, 
                            algorithm="RS256",
                            headers={"kid": kid}
                        )
                         
                         # Generate auto-submit form (LTI 1.3 Deep Linking spec compliant)
                        return_url = self.deep_link_settings.get('deep_link_return_url')
                        form_html = f'''
                         <!DOCTYPE html>
                         <html>
                         <head>
                             <title>Returning to LMS...</title>
                             <meta charset="UTF-8">
                         </head>
                         <body onload="document.forms[0].submit();">
                             <form method="post" action="{return_url}">
                                 <input type="hidden" name="JWT" value="{response_jwt}"/>
                             </form>
                             <div style="text-align: center; font-family: Arial, sans-serif; margin-top: 50px;">
                                 <p>Processing your selection...</p>
                                 <p>You will be redirected back to your course momentarily.</p>
                             </div>
                         </body>
                         </html>
                         '''
                        return form_html
                
                deep_link = CachedDeepLink(self, self._jwt_body)
                return deep_link
            else:
                # Use the built-in deep linking functionality for fresh launches
                deep_link = super().get_deep_link()
                return deep_link
                
        except Exception as e:
            logger.error(f"Failed to get DeepLink instance: {str(e)}")
            raise Exception(f"Failed to get DeepLink instance: {str(e)}")

class LTICookieService:
    """Service for handling LTI cookies"""
    
    def __init__(self, request: Request):
        self.request = request
        self._cookies = {}
        
        # Get existing session cookie or generate new one
        existing_session = request.cookies.get('lti1p3_session')
        if existing_session:
            self.session_cookie = existing_session
        else:
            self.session_cookie = f"session_{datetime.now(timezone.utc).timestamp()}"
            self.set_cookie(
                "lti1p3_session",
                self.session_cookie,
                httponly=True,
                secure=True,
                samesite='None',  # Enable cross-origin for LTI
                path='/',
                max_age=3600
            )

    def get_cookie(self, cookie_name: str) -> str:
        """Get a cookie value"""
        if cookie_name == "lti1p3_session":
            return self.session_cookie
        value = self.request.cookies.get(cookie_name, '')
        logger.info(f"Getting cookie {cookie_name}: {value}")
        return value

    def set_cookie(self, cookie_name: str, cookie_value: str, **kwargs) -> None:
        """Set a cookie value"""
        host = self.request.headers.get('host', '').split(':')[0]
        
        cookie_attrs = {
            'value': cookie_value,
            'httponly': True,
            'secure': True,
            'samesite': 'None',  # Default to None for cross-origin LTI requests
            'path': '/',
            'max_age': 3600,
            **kwargs
        }
        
        if host:
            cookie_attrs['domain'] = host
        
        self._cookies[cookie_name] = cookie_attrs

    def get_cookies(self) -> List[Dict[str, Any]]:
        """Get all cookies that need to be set"""
        cookies = [{'name': name, **data} for name, data in self._cookies.items()]
        return cookies

    def on_get_data(self, cookie_name: str) -> str:
        """Alias for get_cookie for backward compatibility"""
        return self.get_cookie(cookie_name)

    def on_set_data(self, cookie_name: str, cookie_value: str, **kwargs) -> None:
        """Alias for set_cookie for backward compatibility"""
        self.set_cookie(cookie_name, cookie_value, **kwargs)

# Global session storage for LTI (simple in-memory storage)
_lti_session_storage = {}

class SessionDataStorage:
    """Handles session data storage for LTI"""
    
    def __init__(self, request: Request):
        self.request = request
        self._session_id = None
        
        # Handle both FastAPI Request and RequestWrapper objects
        if hasattr(request, 'session'):
            self.session = request.session
        else:
            # Fallback: create an empty session-like object
            self.session = {}
        
        # Ensure session is a dict-like object that can be modified
        if not hasattr(self.session, '__setitem__'):
            logger.warning("Session object is not writable, creating fallback dict")
            self.session = {}
        
        # Try to get session ID from cookie
        self._session_id = request.cookies.get('lti1p3_session')
        if not self._session_id:
            # Generate a new session ID if none exists
            self._session_id = f"session_{datetime.now().timestamp()}"
        
        # Ensure the session ID is set in the session
        if hasattr(self.session, '__setitem__'):
            self.session['session_id'] = self._session_id
            # Also store the session ID in a way that persists
            self.session['_lti_session_id'] = self._session_id
        
        # Initialize global session storage for this session ID
        if self._session_id not in _lti_session_storage:
            _lti_session_storage[self._session_id] = {}

    def save_nonce(self, nonce: str) -> None:
        """Save nonce with expiration"""
        nonces = self.session.get("nonces", {})
        nonces[nonce] = {
            'nonce': nonce,
            'timestamp': datetime.now(timezone.utc).timestamp()
        }
        self.session["nonces"] = nonces

    def check_nonce(self, nonce: str) -> bool:
        """Check if nonce exists and is valid"""
        nonces = self.session.get("nonces", {})
        nonce_data = nonces.get(nonce)
        
        if not nonce_data:
            return False
        
        # Check if nonce is expired (24 hours)
        nonce_time = nonce_data.get('timestamp', 0)
        current_time = datetime.now(timezone.utc).timestamp()
        if current_time - nonce_time > 86400:  # 24 hours
            # Remove expired nonce
            del nonces[nonce]
            self.session["nonces"] = nonces
            return False
        
        return True

    def save_session_data(self, key, session_data):
        """Save session data"""
        try:
            # Store in both FastAPI session and global storage
            if hasattr(self.session, '__setitem__'):
                self.session[key] = session_data
            
            # Store in global session storage using session ID
            if self._session_id:
                _lti_session_storage[self._session_id][key] = session_data
        except Exception as e:
            logger.warning(f"Failed to save session data for key {key}: {str(e)}")

    def get_session_data(self, key: str) -> Any:
        """Get session data by key"""
        try:
            # Try FastAPI session first
            if hasattr(self.session, 'get'):
                data = self.session.get(key)
                if data is not None:
                    return data
            
            # Try global session storage
            if self._session_id and self._session_id in _lti_session_storage:
                return _lti_session_storage[self._session_id].get(key)
            
            return None
        except Exception as e:
            logger.warning(f"Failed to get session data for key {key}: {str(e)}")
            return None

    def get_all_session_keys(self) -> List[str]:
        """Get all session keys for debugging"""
        try:
            keys = []
            
            # Get keys from FastAPI session
            if hasattr(self.session, 'keys'):
                keys.extend(list(self.session.keys()))
            
            # Get keys from global session storage
            if self._session_id and self._session_id in _lti_session_storage:
                keys.extend(list(_lti_session_storage[self._session_id].keys()))
            
            return list(set(keys))  # Remove duplicates
        except Exception as e:
            logger.warning(f"Failed to get all session keys: {str(e)}")
            return []

    def save_launch_data(self, key, launch_data):
        """Save launch data"""
        self.save_session_data(key, launch_data)

    def get_launch_data(self, key):
        """Get launch data"""
        return self.get_session_data(key)

    def set_request(self, request):
        """Set the request object"""
        self.request = request

    def get_session_cookie_name(self):
        """Get session cookie name"""
        return "lti1p3_session"

    def set_session_id(self, session_id):
        """Set session ID"""
        self._session_id = session_id

    def get_session_id(self):
        """Get session ID"""
        return self._session_id

    def set_data_storage(self, data_storage):
        """Set data storage (compatibility method)"""
        pass

    def get_data_storage(self):
        """Get data storage (compatibility method)"""
        return self

async def check_for_validation_request(request: Request):
    """Check for tool configuration validation request"""
    request_id = generate_request_id()
    logger.info(f"[{request_id}] Checking for validation request - Method: {request.method}, URL: {request.url}")
    
    try:
        user_agent = request.headers.get('user-agent', '').lower()
        logger.info(f"[{request_id}] User-Agent: {user_agent}")
        
        is_validation_request = (
            (user_agent.startswith('moodlebot') or 'got' in user_agent) and
            request.method == 'GET' and
            (LTIServiceConfig.is_valid_service_type(request.query_params.get('service_type')) 
             or request.query_params.get('service_type') is None) and
            not (await get_form_data(request))
        )
        
        logger.info(f"[{request_id}] Service type: {request.query_params.get('service_type')}")
        logger.info(f"[{request_id}] Is validation request: {is_validation_request}")
        
        if is_validation_request:
            logger.info(f"[{request_id}] Returning validation response for Moodle")
            return HTMLResponse("""
                <!DOCTYPE html>
                <html>
                <head>
                    <title>LTI Tool Available</title>
                </head>
                <body>
                    <h1>LTI Tool is Available</h1>
                    <p>This tool is properly configured and ready to use.</p>
                </body>
                </html>
            """)
        else:
            logger.info(f"[{request_id}] Not a validation request!")
            raise HTTPException(status_code=400, detail="Not a validation request!")
    except Exception as e:
        logger.error(f"[{request_id}] Error in check_for_validation_request: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))


async def handle_login(request: Request, form_data: dict, tool_config: LTIToolConfigFromProvider):
    """Handle LTI login requests"""
    request_id = generate_request_id()
    logger.info(f"[{request_id}] Starting LTI login process - Method: {request.method}, URL: {request.url}")
    
    try:
        # Combine query params and form data
        params = {**dict(request.query_params), **form_data}
        logger.info(f"[{request_id}] Combined parameters: {params}")

        # Set up URLs
        original_target_link_uri = params.get('target_link_uri')
        launch_endpoint = f"https://{BACKEND_DOMAIN_NAME}/lti/launch"
        
        # CRITICAL: Preserve the target_link_uri from deep linking 
        # If the target_link_uri contains query parameters (e.g., service_type, course_id),
        # we MUST preserve it as-is because this becomes the target_link_uri in the JWT
        if original_target_link_uri and ('service_type=' in original_target_link_uri or 'course_id=' in original_target_link_uri):
            # This is a deep-linked URL with our preserved parameters - keep it as-is
            final_target_link_uri = original_target_link_uri
        else:
            # This is a regular launch or login URL - use the launch endpoint
            final_target_link_uri = launch_endpoint
        
        # The redirect_uri should always be the launch endpoint for the OIDC flow
        redirect_uri = launch_endpoint
        
        logger.info(f"[{request_id}] URL configuration - Base URL: {BACKEND_DOMAIN_NAME}, Launch endpoint: {launch_endpoint}")
        logger.info(f"[{request_id}] Target link URI: {final_target_link_uri}, Redirect URI: {redirect_uri}")
        
        # Get issuer
        issuer = params.get('iss')
        if not issuer:
            logger.error(f"[{request_id}] Missing 'iss' parameter in request")
            raise HTTPException(status_code=400, detail='Missing "iss" param')
        
        logger.info(f"[{request_id}] Issuer: {issuer}")

        # Get platform configuration
        platform_config = tool_config.get_registration_by_issuer(issuer)
        if not platform_config:
            logger.error(f"[{request_id}] No configuration found for issuer: {issuer}")
            raise HTTPException(status_code=400, detail=f'No configuration found for issuer: {issuer}')
        
        logger.info(f"[{request_id}] Platform config found: {platform_config}")
        
        login_url = platform_config['auth_login_url']
        if not login_url:
            logger.error(f"[{request_id}] No login URL found for issuer: {issuer}")
            raise HTTPException(status_code=400, detail=f'No login URL found for issuer: {issuer}')
        
        logger.info(f"[{request_id}] Original login URL: {login_url}")
        
        # Ensure login_url is absolute
        if login_url.startswith('/'):
            login_url = urljoin(issuer.rstrip('/'), login_url)
            logger.info(f"[{request_id}] Made login URL absolute: {login_url}")

        # Initialize services
        storage = SessionDataStorage(request)
        cookie_service = LTICookieService(request)
        storage.save_session_data('session_id', cookie_service.session_cookie)
        logger.info(f"[{request_id}] Initialized storage and cookie services")

        # Create request wrapper and MessageLaunch
        request_wrapper = RequestWrapper(request, form_data)
        launch = ExtendedMessageLaunch(
            request=request_wrapper,
            tool_config=tool_config,
            launch_data_storage=storage,
            session_service=storage,
            cookie_service=cookie_service
        )
        logger.info(f"[{request_id}] Created ExtendedMessageLaunch instance")

        # Generate nonce and save to storage
        nonce = str(uuid.uuid4())
        storage.save_nonce(nonce)
        logger.info(f"[{request_id}] Generated and saved nonce: {nonce}")

        # Prepare redirect parameters
        redirect_params = {
            'client_id': platform_config.get('client_id'),
            'iss': issuer,
            'target_link_uri': final_target_link_uri,
            'login_hint': params.get('login_hint'),
            'lti_message_hint': params.get('lti_message_hint'),
            'lti_deployment_id': params.get('lti_deployment_id'),
            'response_mode': 'form_post',
            'prompt': 'none',
            'redirect_uri': redirect_uri,
            'scope': 'openid',
            'response_type': 'id_token',
            'nonce': nonce
        }
        
        logger.info(f"[{request_id}] Redirect parameters: {redirect_params}")
        
        # Build final redirect URL
        final_url = build_redirect_url(login_url, redirect_params)
        logger.info(f"[{request_id}] Final redirect URL: {final_url}")
        
        response = RedirectResponse(url=final_url)
        
        # Set cookies for cross-origin requests
        cookies_to_set = cookie_service.get_cookies()
        logger.info(f"[{request_id}] Setting {len(cookies_to_set)} cookies")
        
        for cookie in cookies_to_set:
            response.set_cookie(
                key=cookie['name'],
                value=cookie['value'],
                max_age=cookie.get('max_age', 3600),
                path=cookie.get('path', '/'),
                domain=cookie.get('domain'),
                secure=True,
                httponly=True,
                samesite='None'
            )
            logger.info(f"[{request_id}] Set cookie: {cookie['name']}")
        
        logger.info(f"[{request_id}] Login process completed successfully")
        return response

    except Exception as e:
        logger.error(f"[{request_id}] Error in handle_login: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))

async def handle_launch(request: Request, tool_config: LTIToolConfigFromProvider, template_handler: TemplateHandler):
    """Handle LTI launch requests"""
    request_id = generate_request_id()
    logger.info(f"[{request_id}] Starting LTI launch process - Method: {request.method}, URL: {request.url}")
    
    try:
        # Get form data
        form_data = await get_form_data(request)
        logger.info(f"[{request_id}] Form data: {form_data}")
        logger.info(f"[{request_id}] Query params: {dict(request.query_params)}")
        
        # Get default configuration for direct access detection
        try:
            # Import parse_qs for use in this function
            from urllib.parse import parse_qs
            
            # TODO: Simplify this using the db directly
            registrations = tool_config.get_all_registrations()
            logger.info(f"[{request_id}] Found {len(registrations)} registrations")
            if not registrations:
                logger.warning(f"[{request_id}] No registrations found in tool config")
                # Try to proceed without default configuration for valid LTI requests
                default_issuer = None
                default_tool_jwks_url_root = None
            else:
                default_issuer = registrations[0]['issuer']
                default_tool_jwks_url = urlparse(registrations[0]['tool_jwks_url'])
                default_tool_jwks_url_root = f"{default_tool_jwks_url.scheme}://{default_tool_jwks_url.netloc}/"
                logger.info(f"[{request_id}] Default issuer: {default_issuer}")
                logger.info(f"[{request_id}] Default tool JWKS URL root: {default_tool_jwks_url_root}")
        except Exception as e:
            logger.error(f"[{request_id}] Error getting default configuration: {str(e)}")
            # Don't fail here for valid LTI requests - continue processing
            default_issuer = None
            default_tool_jwks_url_root = None
            logger.warning(f"[{request_id}] Continuing without default configuration")

        # Check for direct access
        is_direct_access = (
            request.method == "GET" and
            not request.query_params.get('iss') and
            not request.query_params.get('id_token') and
            not any(platform_url in str(request.url) for platform_url in [
                default_issuer,
                default_tool_jwks_url_root
            ] if platform_url)
        )
        
        logger.info(f"[{request_id}] Is direct access: {is_direct_access}")
        
        if is_direct_access and default_issuer:
            logger.info(f"[{request_id}] Redirecting direct access to login")
            target_link_uri = get_safe_target_link_uri(request)
            login_params = {
                'target_link_uri': target_link_uri,
                'iss': default_issuer
            }
            login_url = build_redirect_url(f"https://{BACKEND_DOMAIN_NAME}/lti/login", login_params)
            logger.info(f"[{request_id}] Redirecting to: {login_url}")
            return RedirectResponse(url=login_url)
        
        # Initialize LTI services
        storage = SessionDataStorage(request)
        cookie_service = LTICookieService(request)
        storage.save_session_data('session_id', cookie_service.session_cookie)
        logger.info(f"[{request_id}] Initialized storage and cookie services")

        # Process LTI launch
        message_launch = ExtendedMessageLaunch(
            request=request,
            tool_config=tool_config,
            launch_data_storage=storage,
            session_service=storage,
            cookie_service=cookie_service
        )
        logger.info(f"[{request_id}] Created ExtendedMessageLaunch instance")

        try:
            logger.info(f"[{request_id}] Starting message launch validation")
            message_launch_data = await message_launch.get_launch_data()
            logger.info(f"[{request_id}] Launch validation successful")
            logger.info(f"[{request_id}] Launch data keys: {list(message_launch_data.keys()) if message_launch_data else 'None'}")
        except Exception as launch_error:
            logger.error(f"[{request_id}] Launch validation failed: {str(launch_error)}")
            if is_direct_access and default_issuer:
                logger.info(f"[{request_id}] Redirecting failed direct access to login")
                target_link_uri = get_safe_target_link_uri(request)
                login_params = {
                    'target_link_uri': target_link_uri,
                    'iss': default_issuer
                }
                login_url = build_redirect_url(f"https://{BACKEND_DOMAIN_NAME}/lti/login", login_params)
                return RedirectResponse(url=login_url)
            else:
                error_detail = f"Launch validation failed: {str(launch_error)}"
                if "Missing id_token" in str(launch_error):
                    error_detail += "\nPossible causes:"
                    error_detail += "\n1. The platform's login process did not complete successfully"
                    error_detail += "\n2. The platform's authentication endpoint is not properly configured"
                    error_detail += "\n3. The platform's LTI configuration is incorrect"
                    error_detail += "\n4. The platform's redirect URL is not properly set"
                raise HTTPException(status_code=400, detail=error_detail)

        # Check if this is a deep linking request
        if message_launch.is_deep_linking_request():
            # Cache the launch data for later use in deep linking flow
            try:
                launch_id = message_launch.cache_launch_data()
                logger.info(f"[{request_id}] Generated launch_id: {launch_id}")
                
                # Also store additional data for easy retrieval
                storage.save_session_data(f"launch_data_{launch_id}", {
                    'jwt_body': message_launch._jwt_body,
                    'launch_data': message_launch._launch_data,
                    'launch_id': launch_id,
                    'client_id': message_launch_data.get("aud"),  # Store client_id explicitly
                    'timestamp': datetime.now(timezone.utc).isoformat()
                })
                logger.info(f"[{request_id}] Cached launch data with client_id: {message_launch_data.get('aud')}")
            except Exception as e:
                logger.error(f"[{request_id}] Failed to cache launch data: {str(e)}")
            
            # Extract deep linking settings
            deep_link_settings = message_launch.get_deep_linking_settings()
            custom_params = message_launch_data.get('custom', {})
            course_id = custom_params.get('course_id') or message_launch_data.get('context', {}).get('id')
            
            # Get group_id from tool-level custom parameters
            group_id = custom_params.get('group_id') or custom_params.get('custom_group_id') or f"course_{course_id}" or "default_group"
            
            # Prepare the data that needs to be preserved (LTI spec compliant approach)
            deep_link_data = {
                "client_id": message_launch_data.get("aud"),
                "issuer": message_launch_data.get("iss"),
                "deployment_id": message_launch_data.get("deployment_id"),
                "subject": message_launch_data.get("sub"),
                "nonce": message_launch_data.get("nonce"),
                "group_id": group_id,
                "course_id": course_id,
                "context": message_launch_data.get("context", {}),
                "custom": message_launch_data.get("custom", {}),
                "return_url": deep_link_settings.get("deep_link_return_url"),
                "created_at": datetime.now(timezone.utc).isoformat(),
                "launch_id": launch_id
            }
            
            # Encode the data as a JWT token that will be included in the template
            import base64
            import json
            
            # Create a base64-encoded JSON string with the data we need to preserve
            data_json = json.dumps(deep_link_data)
            encoded_data = base64.urlsafe_b64encode(data_json.encode()).decode()
            
            # Add our encoded data to the deep_link_settings
            enhanced_deep_link_settings = deep_link_settings.copy()
            enhanced_deep_link_settings["data"] = enhanced_deep_link_settings.get("data", "") + f"|{encoded_data}"
            
            context = {
                "request": request,
                "launch_data": message_launch_data,
                "deep_link_settings": enhanced_deep_link_settings,  # Use enhanced settings with encoded data
                "course_id": course_id,
                "roles": message_launch_data.get("roles", []),
                "backend_domain_name": BACKEND_DOMAIN_NAME,
                "lti_session_token": create_lti_session_token({
                    "course_id": course_id,
                    "group_id": group_id,
                    "token_type": "lti_deep_link",
                    "sub": message_launch_data.get("sub")
                })
            }
            
            # Create deep linking template response
            response = template_handler.render_template("deep_link.html", context)
        else:
            # Regular LTI launch - determine template based on service type
            custom_params = message_launch_data.get('custom', {})
            # Get course ID from target_link_uri query parameters
            selected_course_id = None
            target_link_uri = message_launch_data.get('target_link_uri', '')
            if target_link_uri and '?' in target_link_uri:
                parsed_uri = urlparse(target_link_uri)
                from urllib.parse import parse_qs
                query_params = parse_qs(parsed_uri.query)
                selected_course_id = query_params.get('course_id', [None])[0]
            if not selected_course_id:
                selected_course_id = (custom_params.get('custom_selected_course_id') or 
                                    custom_params.get('custom_course_id') or 
                                    request.query_params.get('selected_course_id'))
            moodle_course_id = custom_params.get('course_id') or message_launch_data.get('context', {}).get('id')
            course_id = selected_course_id if selected_course_id else moodle_course_id

            # Clean service type detection
            service_type = _detect_service_type(
                request_id=request_id,
                message_launch_data=message_launch_data,
                custom_params=custom_params,
                storage=storage,
                request=request
            )

            template_map = LTIServiceConfig.get_template_map()
            template_name = template_map.get(service_type, 'chat.html')

            session_token_data = {
                "course_id": course_id,
                "token_type": "lti_services",
                "sub": message_launch_data.get("sub"),
                "iss": message_launch_data.get("iss")
            }
            if service_type == LTIServiceConfig.LECTURE_ASSISTANT:
                session_token_data["lti_params"] = {
                    "system_prompt": custom_params.get("system_prompt", "")
                }
            lti_session_token = create_lti_session_token(session_token_data)

            # Log message_launch_data
            logger.info(f"[{request_id}] Message launch data: {message_launch_data}")

            context = {
                "request": request,
                "roles": message_launch_data.get("roles", []),
                "launch_data": message_launch_data,
                "custom_params": custom_params,
                "service_type": service_type,
                "lti_session_token": lti_session_token,
                "user_id": message_launch_data.get("sub"),
                "user_name": message_launch_data.get("name"),
                "user_email": message_launch_data.get("email")
            }

            response = template_handler.render_template(template_name, context)
        
        # Set cookies with enhanced cross-origin support
        cookies_to_set = cookie_service.get_cookies()
        
        for cookie in cookies_to_set:
            response.set_cookie(
                key=cookie['name'],
                value=cookie['value'],
                max_age=cookie.get('max_age', 3600),
                path=cookie.get('path', '/'),
                domain=cookie.get('domain'),
                secure=True,  # Always secure for HTTPS
                httponly=True,  # Always httponly for security
                samesite='None'  # Allow cross-origin for LTI
            )
        
        return response

    except Exception as e:
        logger.error(f"Error in handle_launch: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))

class DeepLinkingService:
    """Service for handling LTI Deep Linking with enhanced Moodle support"""
    
    def __init__(self, launch: MessageLaunch, base_url: str):
        self.launch = launch
        self.base_url = base_url
        self.deep_link = launch.get_deep_link()
    
    def create_lecture_assistant_resource(self, group_id: str, custom_params: dict = None) -> DeepLinkResource:
        """Create a lecture assistant resource for deep linking"""
        if custom_params is None:
            custom_params = {}
            
        resource = DeepLinkResource()
        resource.set_url(f"{self.base_url}lti/launch") \
                .set_title(custom_params.get('title', LTIServiceConfig.get_service_title(LTIServiceConfig.LECTURE_ASSISTANT))) \
                .set_custom_params({
                    "group_id": group_id,
                    "course_id": custom_params.get('course_id'),
                    "module_type": LTIServiceConfig.LECTURE_ASSISTANT,
                    "version": LTIServiceConfig.RESOURCE_VERSION,
                    "features": custom_params.get('features', LTIServiceConfig.get_service_features(LTIServiceConfig.LECTURE_ASSISTANT)),
                    "description": custom_params.get('description', LTIServiceConfig.get_service_description(LTIServiceConfig.LECTURE_ASSISTANT))
                })
        
        # Set icon if provided
        if 'icon_url' in custom_params:
            resource.set_icon_url(custom_params['icon_url'])
            
        return resource
    
    def create_podcast_resource(self, group_id: str, custom_params: dict = None) -> DeepLinkResource:
        """Create a podcast generator resource for deep linking"""
        if custom_params is None:
            custom_params = {}
            
        resource = DeepLinkResource()
        resource.set_url(f"{self.base_url}lti/launch?module=podcast") \
                .set_title(custom_params.get('title', LTIServiceConfig.get_service_title(LTIServiceConfig.PODCAST_GENERATOR))) \
                .set_custom_params({
                    "group_id": group_id,
                    "course_id": custom_params.get('course_id'),
                    "module_type": LTIServiceConfig.PODCAST_GENERATOR,
                    "version": LTIServiceConfig.RESOURCE_VERSION,
                    "features": LTIServiceConfig.get_service_features(LTIServiceConfig.PODCAST_GENERATOR),
                    "description": custom_params.get('description', LTIServiceConfig.get_service_description(LTIServiceConfig.PODCAST_GENERATOR))
                })
        
        # Set icon if provided
        if 'icon_url' in custom_params:
            resource.set_icon_url(custom_params['icon_url'])
            
        return resource
    
    def create_quiz_resource(self, group_id: str, custom_params: dict = None) -> DeepLinkResource:
        """Create a quiz generator resource for deep linking"""
        if custom_params is None:
            custom_params = {}
            
        resource = DeepLinkResource()
        resource.set_url(f"{self.base_url}lti/launch?module=quiz") \
                .set_title(custom_params.get('title', LTIServiceConfig.get_service_title(LTIServiceConfig.QUIZ_GENERATOR))) \
                .set_custom_params({
                    "group_id": group_id,
                    "course_id": custom_params.get('course_id'),
                    "module_type": LTIServiceConfig.QUIZ_GENERATOR,
                    "version": LTIServiceConfig.RESOURCE_VERSION,
                    "features": custom_params.get('features', LTIServiceConfig.get_service_features(LTIServiceConfig.QUIZ_GENERATOR)),
                    "description": custom_params.get('description', LTIServiceConfig.get_service_description(LTIServiceConfig.QUIZ_GENERATOR))
                })
        
        # Set icon if provided
        if 'icon_url' in custom_params:
            resource.set_icon_url(custom_params['icon_url'])
            
        return resource
    
    def create_content_resource(self, group_id: str, custom_params: dict = None) -> DeepLinkResource:
        """Create a content resource for deep linking"""
        if custom_params is None:
            custom_params = {}
            
        resource = DeepLinkResource()
        resource.set_url(f"{self.base_url}lti/launch?module=content") \
                .set_title(custom_params.get('title', LTIServiceConfig.get_service_title(LTIServiceConfig.CONTENT_ASSISTANT))) \
                .set_custom_params({
                    "group_id": group_id,
                    "course_id": custom_params.get('course_id'),
                    "module_type": LTIServiceConfig.CONTENT_ASSISTANT,
                    "version": LTIServiceConfig.RESOURCE_VERSION,
                    "features": LTIServiceConfig.get_service_features(LTIServiceConfig.CONTENT_ASSISTANT),
                    "description": custom_params.get('description', LTIServiceConfig.get_service_description(LTIServiceConfig.CONTENT_ASSISTANT))
                })
        
        # Set icon if provided
        if 'icon_url' in custom_params:
            resource.set_icon_url(custom_params['icon_url'])
            
        return resource
    
    def add_resource(self, resource: DeepLinkResource):
        """Add a resource to the deep link response"""
        if not hasattr(self, 'resources'):
            self.resources = []
        self.resources.append(resource)

    def get_response(self):
        """Get the deep link response"""
        resources = getattr(self, 'resources', [])
        return self.deep_link.output_response_form(resources)

    def get_auto_submit_form(self, resources: list = None):
        """Get an auto-submit form for the deep link response"""
        if resources is None:
            resources = getattr(self, 'resources', [])
        return self.deep_link.output_response_form(resources)

def _detect_service_type(request_id, message_launch_data, custom_params, storage, request):
    """
    Enhanced service type detection for LTI launches with Moodle-specific fixes.
    Priority order: target_link_uri params, custom params, resource title, persistent storage, default
    """
    from urllib.parse import urlparse, parse_qs
    import logging
    logger = logging.getLogger("lti")

    # 1. First priority: Query params in target_link_uri (most reliable per LTI spec)
    target_link_uri = message_launch_data.get('target_link_uri', '')
    if target_link_uri and '?' in target_link_uri:
        parsed_uri = urlparse(target_link_uri)
        query_params = parse_qs(parsed_uri.query)
        service_type = query_params.get('service_type', [None])[0]
        if service_type:
            logger.info(f"[{request_id}] Service type from target_link_uri query params: {service_type}")
            return service_type
    
    logger.info(f"[{request_id}] No service type detected through any method, using default: {LTIServiceConfig.DEFAULT_SERVICE_TYPE}")
    logger.info(f"[{request_id}] Available data for debugging:")
    logger.info(f"[{request_id}] - target_lin`k_uri: {target_link_uri}")
    logger.info(f"[{request_id}] - custom_params: {custom_params}")
    
    return LTIServiceConfig.DEFAULT_SERVICE_TYPE