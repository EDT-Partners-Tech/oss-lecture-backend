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

"""
Global pytest configuration and fixtures for lecture-backend tests.

This module provides global fixtures that set up the test environment,
including environment variables and common mock configurations.
"""

import os
import pytest
from typing import Generator
from unittest.mock import patch, Mock

# Set up environment variables immediately when module is imported
# This prevents import-time errors from modules that check environment variables
def setup_immediate_env():
    """Set up environment variables immediately to prevent import-time errors."""
    test_env_vars = {
        # AWS Core Configuration
        "AWS_REGION_NAME": "eu-central-1",
        "AWS_DEFAULT_REGION": "eu-central-1", 
        "AWS_ACCESS_KEY_ID": "test-access-key-id",
        "AWS_SECRET_ACCESS_KEY": "test-secret-access-key",
        
        # Database Configuration
        "DATABASE_URL": "postgresql://test_user:test_pass@localhost:5432/test_db",
        "DATABASE_SECRET": "arn:aws:secretsmanager:eu-central-1:123456789:secret:test-db-secret",
        "ENVIRONMENT": "test",
        
        # S3 Buckets
        "AWS_S3_AUDIO_BUCKET_NAME": "test-audio-bucket",
        "AWS_S3_CONTENT_BUCKET_NAME": "test-content-bucket", 
        "AWS_S3_PODCAST_BUCKET_NAME": "test-podcast-bucket",
        "AWS_S3_COMPARISON_BUCKET_NAME": "test-comparison-bucket",
        "AWS_S3_BUCKET_NAME": "test-bucket",
        
        # Cognito Configuration
        "COGNITO_USERPOOL_ID": "eu-central-1_test123456",
        "COGNITO_REGION": "eu-central-1",
        "COGNITO_APP_CLIENT_ID": "test-client-id-123456789",
        
        # Session and Security
        "SESSION_SECRET": "arn:aws:secretsmanager:eu-central-1:123456789:secret:test-session-secret",
        
        # OpenAI
        "OPENAI_API_KEY": "sk-test-openai-key-123456789",
        
        # Google OAuth
        "GOOGLE_CLIENT_ID": "test-google-client-id.apps.googleusercontent.com",
        
        # Application URLs and Domains
        "REACT_APP_URL": "https://test-frontend.example.com",
        "BACKEND_DOMAIN_NAME": "test-backend.example.com",
        
        # Feature Flags
        "USE_WEBSOCKET": "false",
        
        # Logging
        "LOG_LEVEL": "DEBUG",
        
        # AWS Polly
        "AWS_POLLY_SPEECH_ENGINE": "generative",
 
        # LTI
        "LTI_SECRET": "test-lti-secret",
    }
    
    for key, value in test_env_vars.items():
        if key not in os.environ:
            os.environ[key] = value


# Call immediately when module is imported
setup_immediate_env()

# Mock SSM Parameter Store
ssm_patcher = patch('utility.aws_clients.ssm_client')
mock_ssm = ssm_patcher.start()
mock_ssm.get_parameter.return_value = {
    'Parameter': {
        'Value': 'arn:aws:secretsmanager:eu-central-1:123456789:secret:test-lti-secrets'
    }
}

# Mock Secrets Manager  
secrets_patcher = patch('utility.aws_clients.secrets_client')
mock_secrets = secrets_patcher.start()
mock_secrets.get_secret_value.return_value = {
    'SecretString': '{"encryption_secret": "test-encryption-secret", "session_tokens_secret": "test-session-tokens-secret", "session_key": "test-session-key"}'
}

# Mock parameter store class
param_store_patcher = patch('utility.parameter_store.ParameterStore')
mock_param_store_class = param_store_patcher.start()
mock_param_store = Mock()
mock_param_store.get_parameter.return_value = "test-parameter-value"
mock_param_store.load_parameters.return_value = {}
mock_param_store_class.return_value = mock_param_store

# Patch Fernet to avoid errors when running tests
fernet_patcher = patch('cryptography.fernet.Fernet')
mock_fernet = fernet_patcher.start()
mock_fernet.return_value = Mock()
mock_fernet.return_value.encrypt.return_value = b'test-encrypted-value'
mock_fernet.return_value.decrypt.return_value = b'test-decrypted-value'

@pytest.fixture(scope="session", autouse=True)
def setup_test_environment() -> Generator[None, None, None]:
    """
    Global fixture that ensures the test environment is properly set up.
    
    This fixture runs automatically for all tests and ensures that all required
    environment variables remain set throughout the test session.
    """
    # Store original environment to restore later
    original_env = dict(os.environ)
    
    try:
        # Ensure our test environment is still in place
        setup_immediate_env()
        
        # Yield control to run tests
        yield
        
    finally:
        # Stop all patches
        ssm_patcher.stop()
        secrets_patcher.stop()
        param_store_patcher.stop()
        
        # Restore original environment
        os.environ.clear()
        os.environ.update(original_env)

@pytest.fixture(scope="function")
def mock_cognito_token_payload():
    from utility.tokens import CognitoTokenPayload
    return CognitoTokenPayload(**{
        "sub": "test-cognito-id",
        "email": "test@example.com",
        "token_use": "id",
        "iss": "https://cognito-idp.eu-central-1.amazonaws.com/eu-central-1_1234567890",
        "cognito:username": "Test User"
    })