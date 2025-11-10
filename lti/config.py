# © [2025] EDT&Partners. Licensed under CC BY 4.0.

import os
import json 
import base64
import requests
from abc import ABC, abstractmethod
from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any, Tuple
from pydantic import BaseModel
from jose import jwk
from pylti1p3.tool_config import ToolConfAbstract
from sqlalchemy.orm import Session

from database import crud
from lti.utils import SecurityUtils
from logging_config import setup_logging

# Configure logging
logger = setup_logging(module_name='lti_config')

ENVIRONMENT = os.getenv("ENVIRONMENT", "production")

class PlatformConfig(BaseModel):
    """Configuration for an LTI platform"""
    client_id: str
    auth_login_url: str
    auth_token_url: str
    key_set_url: str
    tool_jwks_url: str
    deployment_ids: List[str]
    custom_params: Optional[Dict[str, Any]] = None


class LTIConfigProvider(ABC):
    @abstractmethod
    def get_lti_config(self) -> Dict[str, PlatformConfig]:
        pass

    @abstractmethod
    def get_tool_private_key(self) -> str:
        pass


class LTIToolConfigFromProvider(ToolConfAbstract):
    """LTI Tool configuration that loads from a LTIConfigProvider"""
    
    def __init__(self, config_provider: LTIConfigProvider):
        self._config_provider = config_provider
        self._lti_config: Optional[Dict[str, PlatformConfig]] = None
        self._private_key: Optional[str] = None
        self._platform_config = None
        self._key_cache_ttl = timedelta(hours=1)
        self._jwks_cache = None
        self._jwks_cache_time = None

    def _load_lti_config(self) -> Dict[str, PlatformConfig]:
        """Load LTI configuration from LTIConfigProvider"""
        if self._lti_config is None:
            self._lti_config = self._config_provider.get_lti_config()
        return self._lti_config
    
    def _load_private_key(self) -> str:
        """Load private key from LTIConfigProvider"""
        if self._private_key is None:
            self._private_key = self._config_provider.get_tool_private_key()
        return self._private_key

    def _load_platform_config(self) -> Dict[str, Any]:
        """Load platform configuration"""
        if self._platform_config is None:
            lti_config = self._load_lti_config()
            # TODO: handle multiple platforms for the same tool
            self._platform_config = list(lti_config.values())[0].model_dump()
            self._platform_config['issuer'] = list(lti_config.keys())[0]
        return self._platform_config
    
    def _fetch_platform_public_key(self, issuer: str, client_id: str, kid: Optional[str] = None) -> Tuple[str, str]:
        """Fetch platform's public key from its JWKS endpoint"""
        logger.info(f"Fetching platform public key - Issuer: {issuer}, Client ID: {client_id}, KID: {kid}")
        
        try:
            # Load platform configuration
            platform_config = self._load_platform_config()
            logger.info(f"Loaded platform config: {platform_config.get('issuer')}")
            
            # Validate issuer and client_id
            if platform_config.get('issuer') != issuer:
                logger.error(f"Issuer mismatch: expected {platform_config.get('issuer')}, got {issuer}")
                raise Exception(f"Issuer mismatch: expected {platform_config.get('issuer')}, got {issuer}")
            if platform_config.get('client_id') != client_id:
                logger.error(f"Client ID mismatch: expected {platform_config.get('client_id')}, got {client_id}")
                raise Exception(f"Client ID mismatch: expected {platform_config.get('client_id')}, got {client_id}")
            
            # Get JWKS URL
            key_set_url = platform_config.get('key_set_url')
            if not key_set_url:
                logger.error("No key_set_url found in platform configuration")
                raise Exception("No key_set_url found in platform configuration")
            
            logger.info(f"Fetching JWKS from: {key_set_url}")
            
            # Create a session with SSL verification disabled for development
            session = requests.Session()
            if ENVIRONMENT == "production":
                session.verify = True
            else:
                session.verify = False
                # Suppress SSL warnings
                import urllib3
                urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
            
            # Fetch JWKS
            try:
                response = session.get(key_set_url, timeout=10)
                response.raise_for_status()
                jwks = response.json()
                logger.info(f"Successfully fetched JWKS with {len(jwks.get('keys', []))} keys")
            except requests.exceptions.RequestException as e:
                logger.error(f"Failed to fetch JWKS: {str(e)}")
                raise Exception(f"Failed to fetch JWKS: {str(e)}")
            finally:
                session.close()
            
            if not jwks or 'keys' not in jwks:
                logger.error("Invalid JWKS response: no keys found")
                raise Exception("Invalid JWKS response: no keys found")
            
            # Find the key with matching kid
            selected_key = None
            if kid:
                logger.info(f"Looking for key with KID: {kid}")
                for key in jwks['keys']:
                    key_kid = key.get('kid')
                    if key_kid == kid:
                        selected_key = key
                        logger.info(f"Found exact KID match: {key_kid}")
                        break
                    
                    # Try normalized comparison
                    if key_kid and kid:
                        if key_kid.strip().lower() == kid.strip().lower():
                            selected_key = key
                            logger.info(f"Found normalized KID match: {key_kid}")
                            break
            else:
                # No kid provided, use first valid key
                logger.info("No KID provided, using first valid key")
                for key in jwks['keys']:
                    if SecurityUtils.validate_jwk(key):
                        selected_key = key
                        logger.info(f"Selected first valid key with KID: {key.get('kid')}")
                        break
            
            if not selected_key:
                logger.error(f"No valid key found for kid: {kid}")
                raise Exception(f"No valid key found for kid: {kid}")
            
            # Validate the selected key
            if not SecurityUtils.validate_jwk(selected_key):
                logger.error("Selected key failed validation")
                raise Exception("Selected key failed validation")
            
            # Convert JWK to PEM
            try:
                jwk_obj = jwk.construct(selected_key)
                public_key = jwk_obj.to_pem().decode('utf-8')
                logger.info(f"Successfully converted JWK to PEM for KID: {selected_key.get('kid')}")
                return public_key, selected_key.get('kid', '')
            except Exception as e:
                logger.error(f"Failed to convert JWK to PEM: {str(e)}")
                raise Exception(f"Failed to convert JWK to PEM: {str(e)}")
            
        except Exception as e:
            logger.error(f"Error fetching platform public key: {str(e)}")
            raise Exception(f"Error fetching platform public key: {str(e)}")
        
    def get_expected_issuer(self) -> str:
        return self._load_platform_config()['issuer']
    
    def get_expected_audience(self) -> str:
        return self._load_platform_config()['client_id']

    def get_public_key(self, issuer: str, client_id: str, *args, **kwargs) -> str:
        """Get the public key for the platform
        
        Args:
            issuer: The issuer of the JWT
            client_id: The client ID
            *args: Additional positional arguments (first one is treated as kid if present)
            **kwargs: Additional keyword arguments (ignored)
            
        Returns:
            str: The public key in PEM format
        """
        try:
            # Get kid from args if present
            kid = args[0] if args else None
            logger.info(f"Getting public key - Issuer: {issuer}, Client ID: {client_id}, KID: {kid}")
            key, _ = self._fetch_platform_public_key(issuer, client_id, kid)
            logger.info("Successfully retrieved public key")
            return key
        except Exception as e:
            logger.error(f"Failed to get public key: {str(e)}")
            raise Exception(f'Failed to get public key: {str(e)}')
        
    def get_registration_by_issuer(self, issuer: str, **kwargs) -> Dict[str, Any]:
        """Get registration by issuer"""
        logger.info(f"Getting registration by issuer: {issuer}")
        platform = self._load_platform_config()
        if not platform or platform['issuer'] != issuer:
            logger.error(f"No platform found for issuer: {issuer}")
            return None

        registration = {
            "client_id": platform['client_id'],
            "issuer": platform['issuer'],
            "auth_login_url": platform['auth_login_url'],
            "auth_token_url": platform['auth_token_url'],
            "key_set_url": platform['key_set_url'],
            "tool_jwks_url": platform['tool_jwks_url'],
            "deployment_ids": platform['deployment_ids']
        }
        logger.info(f"Found registration for issuer {issuer}: {registration}")
        return registration

    def get_registration_by_client_id(self, client_id: str, **kwargs) -> Dict[str, Any]:
        """Get registration by client_id"""
        platform = self._load_platform_config()
        if not platform or platform['client_id'] != client_id:
            return None

        return {
            "client_id": platform['client_id'],
            "issuer": platform['issuer'],
            "auth_login_url": platform['auth_login_url'],
            "auth_token_url": platform['auth_token_url'],
            "key_set_url": platform['key_set_url'],
            "tool_jwks_url": platform['tool_jwks_url'],
            "deployment_ids": platform['deployment_ids']
        }

    def get_jwks(self) -> List[Dict[str, Any]]:
        """Get the JWKS for the tool"""
        try:
            # Check cache first
            if (self._jwks_cache is not None and self._jwks_cache_time is not None and 
                datetime.now() - self._jwks_cache_time < self._key_cache_ttl):
                return self._jwks_cache

            # Generate JWKS from private key
            private_key = self._load_private_key()
            if not private_key:
                raise Exception("No private key available for JWKS generation")
                
            # Convert private key to JWK format
            from cryptography.hazmat.primitives import serialization
            from cryptography.hazmat.backends import default_backend
            import hashlib
            
            # Load the private key
            private_key_obj = serialization.load_pem_private_key(
                private_key.encode(),
                password=None,
                backend=default_backend()
            )
            
            # Get the public key
            public_key_obj = private_key_obj.public_key()
            public_numbers = public_key_obj.public_numbers()
            
            # Generate deterministic kid based on private key hash
            private_key_hash = hashlib.sha256(private_key.encode()).hexdigest()[:16]
            kid = f"key-{private_key_hash}"
            
            # Create JWK
            jwk_dict = {
                "kty": "RSA",
                "alg": "RS256",
                "use": "sig",
                "n": base64.urlsafe_b64encode(public_numbers.n.to_bytes((public_numbers.n.bit_length() + 7) // 8, 'big')).decode('utf-8').rstrip('='),
                "e": base64.urlsafe_b64encode(public_numbers.e.to_bytes((public_numbers.e.bit_length() + 7) // 8, 'big')).decode('utf-8').rstrip('='),
                "kid": kid
            }
            
            # Cache the JWKS
            self._jwks_cache = [jwk_dict]
            self._jwks_cache_time = datetime.now()
            
            return self._jwks_cache
            
        except Exception as e:
            logger.error(f"Error generating JWKS: {str(e)}")
            raise Exception(f"Error generating JWKS: {str(e)}")


class LTIFileConfigProvider(LTIConfigProvider):
    def __init__(self, config_json_path: str, private_key_path: str):
        self._config_json_path = config_json_path
        self._private_key_path = private_key_path
        self._lti_config: Optional[Dict[str, PlatformConfig]] = None
        self._private_key_content: Optional[str] = None

    def get_lti_config(self) -> Dict[str, PlatformConfig]:
        if self._lti_config is None:
            with open(self._config_json_path, 'r') as f:
                self._lti_config = json.load(f)
        return self._lti_config

    def get_tool_private_key(self) -> str:
        if self._private_key_content is None:
            with open(self._private_key_path, 'r') as f:
                self._private_key_content = f.read()
            if not self._private_key_content.startswith('-----BEGIN PRIVATE KEY-----'):
                raise Exception('Invalid private key format')
        return self._private_key_content


class LTIDBConfigProvider(LTIConfigProvider):
    def __init__(self, db: Session, client_id: str, tool_jwks_url: str):
        self._db = db
        self._client_id = client_id
        self._tool_jwks_url = tool_jwks_url
    
    def get_lti_config(self) -> Dict[str, PlatformConfig]:
        platform = crud.get_lti_platform(self._db, self._client_id)
        if not platform:
            logger.error(f"No LTI platform found for client_id {self._client_id}")
            raise Exception(f"No LTI platform found for client_id {self._client_id}")
        
        config = {
            platform.issuer: PlatformConfig(
                client_id=platform.client_id,
                auth_login_url=platform.auth_login_url,
                auth_token_url=platform.auth_token_url,
                key_set_url=platform.key_set_url,
                tool_jwks_url=self._tool_jwks_url,
                deployment_ids=platform.deployment_ids,
                custom_params=platform.custom_params
            )
        }
        return config
    
    def get_tool_private_key(self) -> str:
        platform = crud.get_lti_platform(self._db, self._client_id)
        if not platform:
            logger.error(f"No LTI platform found for client_id {self._client_id}")
            raise Exception(f"No LTI platform found for client_id {self._client_id}")
        
        group = crud.get_group_by_id(self._db, platform.group_id)
        if not group or not group.lti_private_key:
            logger.error(f"No private key found for group {platform.group_id}")
            raise Exception(f"No private key found for group {platform.group_id}")
        
        return group.lti_private_key


class OpenIDConfig():
    @staticmethod
    def build_openid_config(base_url: str) -> dict:
        """Build OpenID Connect configuration"""
        return {
            "issuer": base_url,
            "authorization_endpoint": f"{base_url}/login",
            "token_endpoint": f"{base_url}/token",
            "jwks_uri": f"{base_url}/.well-known/jwks.json",
            "scopes_supported": [
                "openid",
                "https://purl.imsglobal.org/spec/lti-nrps/scope/contextmembership.readonly",
                "https://purl.imsglobal.org/spec/lti-ags/scope/lineitem",
                "https://purl.imsglobal.org/spec/lti-ags/scope/lineitem.readonly",
                "https://purl.imsglobal.org/spec/lti-ags/scope/result.readonly",
                "https://purl.imsglobal.org/spec/lti-ags/scope/score"
            ],
            "response_types_supported": ["id_token"],
            "subject_types_supported": ["public", "pairwise"],
            "id_token_signing_alg_values_supported": ["RS256"],
            "claims_supported": [
                "sub",
                "iss",
                "name",
                "given_name",
                "family_name",
                "email",
                "https://purl.imsglobal.org/spec/lti/claim/context",
                "https://purl.imsglobal.org/spec/lti/claim/custom",
                "https://purl.imsglobal.org/spec/lti/claim/deployment_id",
                "https://purl.imsglobal.org/spec/lti/claim/launch_presentation",
                "https://purl.imsglobal.org/spec/lti/claim/lis",
                "https://purl.imsglobal.org/spec/lti/claim/message_type",
                "https://purl.imsglobal.org/spec/lti/claim/resource_link",
                "https://purl.imsglobal.org/spec/lti/claim/roles",
                "https://purl.imsglobal.org/spec/lti/claim/tool_platform",
                "https://purl.imsglobal.org/spec/lti/claim/version"
            ],
            "token_endpoint_auth_methods_supported": ["private_key_jwt"],
            "token_endpoint_auth_signing_alg_values_supported": ["RS256"]
        }


class LTIServiceConfig:
    """Centralized configuration for LTI services and their mappings"""
    
    # Service type constants
    LECTURE_ASSISTANT = 'lecture_assistant'
    QUIZ_GENERATOR = 'quiz_generator'
    PODCAST_GENERATOR = 'podcast_generator'
    CONTENT_ASSISTANT = 'content_assistant'
    
    # Default service type
    DEFAULT_SERVICE_TYPE = LECTURE_ASSISTANT
    
    # Service title mappings
    SERVICE_TITLES = {
        LECTURE_ASSISTANT: 'AI Assistant (Chat)',
        QUIZ_GENERATOR: 'Quiz Generator',
        PODCAST_GENERATOR: 'AI Podcast Generator',
        CONTENT_ASSISTANT: 'AI Content Assistant'
    }
    
    # Template mappings for each service
    SERVICE_TEMPLATES = {
        LECTURE_ASSISTANT: 'chat.html',
        QUIZ_GENERATOR: 'quiz_generator.html',
        PODCAST_GENERATOR: 'podcast.html',  # Default to chat template for now
        CONTENT_ASSISTANT: 'chat.html'   # Default to chat template for now
    }
    
    # Service descriptions
    SERVICE_DESCRIPTIONS = {
        LECTURE_ASSISTANT: 'Interactive AI-powered assistant for enhanced learning',
        QUIZ_GENERATOR: 'Generate comprehensive exam questions and assessments from course content',
        PODCAST_GENERATOR: 'Generate AI-powered podcasts from course content',
        CONTENT_ASSISTANT: 'AI-powered content creation and analysis tools'
    }
    
    # Service features
    SERVICE_FEATURES = {
        LECTURE_ASSISTANT: ['chat', 'voice', 'analytics', 'adaptive'],
        QUIZ_GENERATOR: ['auto_generation', 'multiple_formats', 'auto_grading', 'analytics'],
        PODCAST_GENERATOR: ['pdf_upload', 'audio_generation', 'transcription'],
        CONTENT_ASSISTANT: ['content_analysis', 'summarization', 'key_points']
    }
    
    # Icon and thumbnail URLs (relative paths)
    SERVICE_ICONS = {
        LECTURE_ASSISTANT: '/static/lti-icon.png',
        QUIZ_GENERATOR: '/static/quiz-icon.png',
        PODCAST_GENERATOR: '/static/podcast-icon.png',
        CONTENT_ASSISTANT: '/static/content-icon.png'
    }
    
    SERVICE_THUMBNAILS = {
        LECTURE_ASSISTANT: '/static/lti-thumbnail.png',
        QUIZ_GENERATOR: '/static/quiz-thumbnail.png',
        PODCAST_GENERATOR: '/static/podcast-thumbnail.png',
        CONTENT_ASSISTANT: '/static/content-thumbnail.png'
    }
    
    # Supported platforms
    SUPPORTED_PLATFORMS = ['moodle', 'canvas', 'blackboard']
    
    # Resource version
    RESOURCE_VERSION = '1.0'
    
    # Default values
    DEFAULT_COURSE_ID = 'default-course'
    DEFAULT_GROUP_ID = 'demo_group'
    
    # Grade submission defaults
    DEFAULT_SCORE_GIVEN = 0.95
    DEFAULT_SCORE_MAXIMUM = 1.0
    DEFAULT_COMMENT = "Grade submitted"
    DEFAULT_ACTIVITY_PROGRESS = "Completed"
    DEFAULT_GRADING_PROGRESS = "FullyGraded"
    
    @classmethod
    def get_service_title(cls, service_type: str) -> str:
        """Get the title for a service type"""
        return cls.SERVICE_TITLES.get(service_type, 'AI Learning Tool')
    
    @classmethod
    def get_service_template(cls, service_type: str) -> str:
        """Get the template for a service type"""
        return cls.SERVICE_TEMPLATES.get(service_type, 'chat.html')
    
    @classmethod
    def get_service_description(cls, service_type: str) -> str:
        """Get the description for a service type"""
        return cls.SERVICE_DESCRIPTIONS.get(service_type, 'AI-powered learning tool')
    
    @classmethod
    def get_service_features(cls, service_type: str) -> list:
        """Get the features for a service type"""
        return cls.SERVICE_FEATURES.get(service_type, [])
    
    @classmethod
    def get_service_icon(cls, service_type: str, base_url: str = '') -> str:
        """Get the icon URL for a service type"""
        icon_path = cls.SERVICE_ICONS.get(service_type, '/static/lti-icon.png')
        return f"{base_url}{icon_path}" if base_url else icon_path
    
    @classmethod
    def get_service_thumbnail(cls, service_type: str, base_url: str = '') -> str:
        """Get the thumbnail URL for a service type"""
        thumbnail_path = cls.SERVICE_THUMBNAILS.get(service_type, '/static/lti-thumbnail.png')
        return f"{base_url}{thumbnail_path}" if base_url else thumbnail_path
    
    @classmethod
    def get_all_resource_types(cls, base_url: str = '') -> dict:
        """Get all resource types configuration"""
        resource_types = {}
        for service_type in [cls.LECTURE_ASSISTANT, cls.QUIZ_GENERATOR, cls.PODCAST_GENERATOR, cls.CONTENT_ASSISTANT]:
            resource_types[service_type] = {
                "title": cls.get_service_title(service_type),
                "description": cls.get_service_description(service_type),
                "icon_url": cls.get_service_icon(service_type, base_url),
                "thumbnail_url": cls.get_service_thumbnail(service_type, base_url),
                "features": cls.get_service_features(service_type)
            }
        return resource_types
    
    @classmethod
    def get_custom_params(cls, service_type: str, course_id: str, group_id: str) -> dict:
        """Get custom parameters for a service type"""
        return {
            "service_type": service_type,
            "course_id": course_id,
            "group_id": group_id,
            "custom_service_type": service_type,
            "custom_course_id": course_id,
            "custom_group_id": group_id,
            "resource_version": cls.RESOURCE_VERSION,
            "deep_link_created": "true"
        }
    
    @classmethod
    def is_valid_service_type(cls, service_type: str) -> bool:
        """Check if a service type is valid"""
        return service_type in cls.SERVICE_TITLES
    
    @classmethod
    def get_template_map(cls) -> dict:
        """Get the template mapping for service types"""
        return cls.SERVICE_TEMPLATES