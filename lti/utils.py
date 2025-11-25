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

import base64
import uuid
from typing import Dict, Any
from datetime import datetime, timezone
from urllib.parse import urlparse, urlencode
from fastapi import Request
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse
from logging_config import setup_logging

# Configure logging
logger = setup_logging(module_name='lti_utils')


class SecurityUtils:
    """Utility functions for security operations"""
    
    @staticmethod
    def validate_jwk(key: Dict[str, Any]) -> bool:
        """Validate JWK parameters"""
        try:
            # Check required fields
            required_fields = ['kty', 'alg', 'use', 'n', 'e']
            if not all(field in key for field in required_fields):
                return False

            # Validate key type and algorithm
            if key['kty'] != 'RSA' or key['alg'] != 'RS256' or key['use'] != 'sig':
                return False

            # Validate modulus length (should be at least 2048 bits)
            n_bytes = base64.urlsafe_b64decode(key['n'] + '=' * (-len(key['n']) % 4))
            n_bits = len(n_bytes) * 8
            if n_bits < 2048:
                return False

            return True
        except Exception:
            return False
        
    @staticmethod
    def generate_unique_kid() -> str:
        """Generate a unique Key ID (kid) using timestamp and UUID"""
        timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
        unique_id = str(uuid.uuid4())[:8]
        return f"key-{timestamp}-{unique_id}"


class RequestWrapper:
    """Wrapper class to provide a sync interface for the parent class"""
    
    def __init__(self, request, form_data):
        self.request = request
        self._form_data = form_data
    
    @property
    def session(self):
        """Delegate session access to the original request"""
        return self.request.session
    
    @property
    def cookies(self):
        """Delegate cookies access to the original request"""
        return self.request.cookies
    
    @property
    def headers(self):
        """Delegate headers access to the original request"""
        return self.request.headers
    
    @property
    def query_params(self):
        """Delegate query_params access to the original request"""
        return self.request.query_params
    
    def get_param(self, param):
        """Get parameter from form data or query params"""
        if param in self._form_data:
            return self._form_data[param]
        return self.request.query_params.get(param)
    
    def get_request_param(self, param):
        """Get request parameter"""
        return self.get_param(param)
    
    def get_request_param_list(self, param):
        """Get request parameter as list"""
        if param in self._form_data:
            return [self._form_data[param]]
        return self.request.query_params.getlist(param)
    
    def get_request_headers(self):
        """Get request headers"""
        return dict(self.request.headers)
    
    def get_request_url(self):
        """Get request URL"""
        return str(self.request.url)
    
    def get_request_method(self):
        """Get request method"""
        return self.request.method
    
    def get_request_body(self):
        """Get request body - not needed for JWT validation"""
        return None


class TemplateHandler:
    """Handles template rendering"""
    
    def __init__(self, templates_dir: str):
        self.templates_dir = templates_dir
        self.templates = Jinja2Templates(directory=templates_dir)

    def render_template(self, template_name: str, context: dict) -> HTMLResponse:
        """Render template with context"""
        return self.templates.TemplateResponse(template_name, context)


def generate_request_id() -> str:
    """Generate a unique request ID"""
    return f"req_{datetime.now(timezone.utc).timestamp()}"

async def get_form_data(request: Request) -> dict:
    """Cache and return form data from request"""
    if not hasattr(request, '_cached_form_data'):
        try:
            form_data = await request.form()
            request._cached_form_data = dict(form_data)
            logger.info(f"Retrieved form data: {list(request._cached_form_data.keys()) if request._cached_form_data else 'None'}")
        except Exception as e:
            logger.error(f"Error getting form data: {str(e)}")
            request._cached_form_data = {}
    return request._cached_form_data

def build_redirect_url(base_url: str, params: dict) -> str:
    """Build a proper redirect URL with query parameters"""
    logger.info(f"Building redirect URL - Base URL: {base_url}, Params: {params}")
    
    # Parse the base URL to ensure it's valid
    parsed = urlparse(base_url)
    if not parsed.scheme or not parsed.netloc:
        logger.error(f"Invalid base URL: {base_url}")
        raise ValueError(f"Invalid base URL: {base_url}")
    
    # Build query string, filtering out None values
    query = urlencode({k: v for k, v in params.items() if v is not None})
    
    # Construct final URL
    separator = '&' if '?' in base_url else '?'
    final_url = f"{base_url}{separator}{query}"
    
    logger.info(f"Built redirect URL: {final_url}")
    return final_url

def get_safe_target_link_uri(request: Request) -> str:
    """Get a safe target_link_uri for redirects"""
    base_url = str(request.base_url).rstrip('/')
    target_uri = f"{base_url}/lti/launch"
    logger.info(f"Generated safe target link URI: {target_uri}")
    return target_uri