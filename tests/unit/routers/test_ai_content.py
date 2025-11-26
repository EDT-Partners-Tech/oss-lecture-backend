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

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from unittest.mock import Mock, patch, AsyncMock
import uuid
from database.db import get_db
from routers.ai_content import router
from utility.auth import oauth2_scheme

app = FastAPI()
app.include_router(router, prefix="/api/v1/ai-content", tags=["ai-content"])

# Mock data
MOCK_USER = {
    "sub": "test-cognito-id",
    "email": "test@example.com"
}

MOCK_GENERATED_CONTENT = {
    "id": str(uuid.uuid4()),
    "user_id": str(uuid.uuid4()),
    "content_type": "ai_html",
    "title": "Test Content",
    "content_s3_uri": "s3://test-bucket/test-content.html",
    "status": "completed"
}

MOCK_GENERATED_CONTENT_VERSIONS = [
    {
        "id": str(uuid.uuid4()),
        "content_id": MOCK_GENERATED_CONTENT["id"],
        "version_number": 1,
        "content_s3_uri": "s3://test-bucket/test-content-v1.html",
        "is_active": True
    },
    {
        "id": str(uuid.uuid4()),
        "content_id": MOCK_GENERATED_CONTENT["id"],
        "version_number": 2,
        "content_s3_uri": "s3://test-bucket/test-content-v2.html",
        "is_active": False
    }
]

@pytest.fixture
def mock_db():
    return Mock()

@pytest.fixture
def mock_auth():
    with patch("routers.ai_content.get_current_user") as mock:
        mock.return_value = MOCK_USER
        yield mock

@pytest.fixture
def client(mock_db, mock_cognito_token_payload):
    app.dependency_overrides[get_db] = lambda: mock_db
    app.dependency_overrides[oauth2_scheme] = lambda: "fake-jwt-token"

    with patch("utility.auth.jose_jwt.get_unverified_claims") as mock_get_claims:
        
        # Mock the unverified claims to return cognito format
        mock_get_claims.return_value = {"cognito:username": "test-user"}
        
        # Mock the validator to return our test token data
        mock_validator = AsyncMock()
        mock_validator.validate_token.return_value = mock_cognito_token_payload

        with patch.dict("utility.auth.VALIDATOR_MAP", {"cognito": mock_validator}):
            # Create test client
            client = TestClient(app)
            yield client

    app.dependency_overrides.clear()

@pytest.mark.asyncio
async def test_delete_generated_content_not_found(client, mock_db):
    """Test deletion of non-existent content"""
    content_id = str(uuid.uuid4())
    
    # Mock user
    mock_user = Mock()
    mock_user.id = MOCK_GENERATED_CONTENT["user_id"]
    
    # Configure mocks
    with patch("routers.ai_content.get_user_by_cognito_id", return_value=mock_user), \
         patch("routers.ai_content.get_generated_content_by_id", return_value=None):
        
        response = client.delete(f"/generated-content/{content_id}")
        
        assert response.status_code == 404
        data = response.json()
        assert data["detail"] == "Contenido no encontrado"

@pytest.mark.asyncio
async def test_delete_generated_content_unauthorized(client, mock_db):
    """Test deletion of content by unauthorized user"""
    content_id = str(uuid.uuid4())
    
    # Mock user
    mock_user = Mock()
    mock_user.id = str(uuid.uuid4())  # Different user ID
    
    # Mock content
    mock_content = Mock()
    mock_content.user_id = MOCK_GENERATED_CONTENT["user_id"]  # Different from user
    
    # Configure mocks
    with patch("routers.ai_content.get_user_by_cognito_id", return_value=mock_user), \
         patch("routers.ai_content.get_generated_content_by_id", return_value=mock_content):
        
        response = client.delete(f"/generated-content/{content_id}")
        
        assert response.status_code == 403
        data = response.json()
        assert data["detail"] == "No tienes permisos para eliminar este contenido"

@pytest.mark.asyncio
async def test_delete_generated_content_service_error(client, mock_db):
    """Test deletion when service fails"""
    content_id = str(uuid.uuid4())
    
    # Mock user
    mock_user = Mock()
    mock_user.id = MOCK_GENERATED_CONTENT["user_id"]
    
    # Mock content
    mock_content = Mock()
    mock_content.user_id = MOCK_GENERATED_CONTENT["user_id"]
    
    # Configure mocks
    with patch("routers.ai_content.get_user_by_cognito_id", return_value=mock_user), \
         patch("routers.ai_content.get_generated_content_by_id", return_value=mock_content), \
         patch("services.content_storage_service.ContentStorageService.delete_generated_content", new_callable=AsyncMock, return_value=False):
        
        response = client.delete(f"/generated-content/{content_id}")
        
        assert response.status_code == 500
        data = response.json()
        assert data["detail"] == "Error al eliminar el contenido"

@pytest.mark.asyncio
async def test_get_bedrock_models_success(client, mock_db):
    """Test successful retrieval of Bedrock models"""
    # Mock user
    mock_user = Mock()
    mock_user.id = str(uuid.uuid4())
    
    # Mock AWS service response
    mock_models = [
        {
            "name": "Claude 3 Sonnet",
            "modelId": "anthropic.claude-3-sonnet-20240229-v1:0",
            "provider": "anthropic",
        },
        {
            "name": "Claude 3 Haiku",
            "modelId": "anthropic.claude-3-haiku-20240307-v1:0",
            "provider": "anthropic",
        }
    ]
    
    # Configure mocks
    with patch("routers.ai_content.get_user_by_cognito_id", return_value=mock_user), \
         patch("services.aws_service.AWSService.list_bedrock_models", return_value=mock_models):
        
        response = client.get("/bedrock-models")
        
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["message"] == "Modelos de Bedrock obtenidos exitosamente"
        assert len(data["models"]) == 2
        assert data["models"][0]["name"] == "Claude 3 Sonnet"
        assert data["models"][0]["modelId"] == "anthropic.claude-3-sonnet-20240229-v1:0"
        assert data["models"][0]["provider"] == "anthropic"

@pytest.mark.asyncio
async def test_get_bedrock_models_unauthorized(client, mock_db):
    """Test Bedrock models endpoint with unauthorized user"""
    # Configure mocks
    with patch("routers.ai_content.get_user_by_cognito_id", return_value=None):
        
        response = client.get("/bedrock-models")
        
        assert response.status_code == 401
        data = response.json()
        assert data["detail"] == "Usuario no autorizado"

@pytest.mark.asyncio
async def test_get_bedrock_models_service_error(client, mock_db):
    """Test Bedrock models endpoint when AWS service fails"""
    # Mock user
    mock_user = Mock()
    mock_user.id = str(uuid.uuid4())
    
    # Configure mocks
    with patch("routers.ai_content.get_user_by_cognito_id", return_value=mock_user), \
         patch("services.aws_service.AWSService.list_bedrock_models", side_effect=Exception("AWS Error")):
        
        response = client.get("/bedrock-models")
        
        assert response.status_code == 500
        data = response.json()
        assert "Error obteniendo modelos de Bedrock" in data["detail"]
