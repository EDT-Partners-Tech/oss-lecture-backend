# © [2025] EDT&Partners. Licensed under CC BY 4.0.

import uuid
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from unittest.mock import MagicMock, AsyncMock, patch
import pytest
from datetime import datetime

from database.models import UserRole, User, ThirdPartyIntegration
from database import crud
from utility.auth import oauth2_scheme
from routers import integrations
from routers.integrations import router, get_db
from database.schemas import (
    AllowedServiceName,
    ThirdPartyIntegrationUpdate,
)

app = FastAPI()
app.include_router(router)

@pytest.fixture(scope="function")
def client(mock_cognito_token_payload):
    app.dependency_overrides[get_db] = lambda: MagicMock()
    app.dependency_overrides[oauth2_scheme] = lambda: "fake-jwt-token"

    with patch("utility.auth.jose_jwt.get_unverified_claims") as mock_get_claims:
        mock_get_claims.return_value = {"cognito:username": "dummy_user_id"}

        mock_validator = AsyncMock()
        mock_validator.validate_token.return_value = mock_cognito_token_payload
    
        with patch.dict("utility.auth.VALIDATOR_MAP", {"cognito": mock_validator}):
            client = TestClient(app)
            yield client

    app.dependency_overrides.clear()

# Common test fixtures
@pytest.fixture
def mock_admin_user():
    admin = MagicMock(spec=User)
    admin.id = str(uuid.uuid4())
    admin.cognito_id = "mock_admin_id"
    admin.role = UserRole.admin
    admin.name = "Test Admin"
    admin.email = "admin@example.com"
    admin.is_active = True
    return admin

@pytest.fixture
def mock_non_admin_user():
    non_admin = MagicMock(spec=User)
    non_admin.id = str(uuid.uuid4())
    non_admin.cognito_id = "mock_user_id"
    non_admin.role = UserRole.student
    non_admin.name = "Test User"
    non_admin.email = "user@example.com"
    non_admin.is_active = True
    return non_admin

@pytest.fixture
def mock_integration():
    # Create a proper ThirdPartyIntegration model instance
    integration = MagicMock(spec=ThirdPartyIntegration)
    integration.id = uuid.uuid4()
    integration.service_name = AllowedServiceName.GOOGLE.value
    # service_value should be a dict according to schema
    integration.service_value = {
        "client_id": "test_client_id",
        "client_secret": "test_client_secret",
        "redirect_uri": "http://localhost:3000/auth/callback"
    }
    integration.is_active = True
    integration.created_at = datetime.now()
    integration.updated_at = datetime.now()
    
    # Add dict-like behavior for response serialization
    def to_dict():
        return {
            "id": str(integration.id),  # Convert UUID to string
            "service_name": integration.service_name,
            "service_value": integration.service_value,
            "is_active": integration.is_active,
            "created_at": integration.created_at.isoformat(),
            "updated_at": integration.updated_at.isoformat()
        }
    
    integration.dict = to_dict
    integration.__dict__.update(to_dict())
    
    # Add model_dump for Pydantic v2 compatibility
    integration.model_dump = to_dict
    
    return integration

@pytest.fixture
def non_admin_context(monkeypatch, mock_non_admin_user):
    """Fixture to monkeypatch for non-admin user context and set dependency override."""
    def raise_403_error(*args, **kwargs):
        raise HTTPException(status_code=403, detail="Not authorized")
    monkeypatch.setattr(crud, "get_user_by_cognito_id", 
                       lambda db, user_id: mock_non_admin_user)
    monkeypatch.setattr(integrations, "verify_user_admin", raise_403_error)

def test_get_available_services(client):
    """Test getting list of available services"""
    response = client.get("/services")
    assert response.status_code == 200
    services = response.json()
    assert isinstance(services, list)
    assert len(services) > 0
    assert AllowedServiceName.GOOGLE.value in services

def test_read_integrations_success(client, monkeypatch, mock_admin_user, mock_integration):
    """Test successful retrieval of all integrations by admin"""
    # Mock the user verification and database functions
    monkeypatch.setattr(crud, "get_user_by_cognito_id", 
                       lambda db, user_id: mock_admin_user)
    monkeypatch.setattr(integrations, "verify_user_admin", 
                       lambda db, user: None)  # No exception means admin is verified
    monkeypatch.setattr(integrations, "get_third_party_integrations", 
                       AsyncMock(return_value=[mock_integration]))
    
    response = client.get("/")
    assert response.status_code == 200
    integrations_list = response.json()
    assert isinstance(integrations_list, list)
    assert len(integrations_list) == 1
    assert integrations_list[0]["service_name"] == AllowedServiceName.GOOGLE.value

def test_read_integrations_non_admin(client, non_admin_context):
    """Test that non-admin users cannot access integrations"""
    response = client.get("/")
    assert response.status_code == 403
    assert "Not authorized" in response.json()["detail"]

def test_read_integration_by_service_success(client, monkeypatch, mock_admin_user, mock_integration):
    """Test successful retrieval of integration by service name"""
    # Mock the user verification and database functions
    monkeypatch.setattr(crud, "get_user_by_cognito_id", 
                       lambda db, user_id: mock_admin_user)
    monkeypatch.setattr(integrations, "verify_user_admin", 
                       lambda db, user: None)  # No exception means admin is verified
    monkeypatch.setattr(integrations, "get_third_party_integration_by_service", 
                       AsyncMock(return_value=mock_integration))
    
    response = client.get(f"/service/{AllowedServiceName.GOOGLE.value}")
    assert response.status_code == 200
    integration = response.json()
    assert "service_value" in integration
    assert isinstance(integration["service_value"], dict)
    assert integration["service_value"] == mock_integration.service_value

def test_read_integration_by_service_not_found(client, monkeypatch, mock_admin_user):
    """Test handling of non-existent integration service"""
    # Mock the user verification and database functions
    monkeypatch.setattr(crud, "get_user_by_cognito_id", 
                       lambda db, user_id: mock_admin_user)
    monkeypatch.setattr(integrations, "verify_user_admin", 
                       lambda db, user: None)  # No exception means admin is verified
    monkeypatch.setattr(integrations, "get_third_party_integration_by_service", 
                       AsyncMock(return_value=None))
    
    response = client.get(f"/service/{AllowedServiceName.GOOGLE.value}")
    assert response.status_code == 404
    assert "Integration not found" in response.json()["detail"]

def test_read_public_integration_by_service_success(client, monkeypatch, mock_integration):
    """Test successful public access to integration service"""
    monkeypatch.setattr(integrations, "get_third_party_integration_by_service", 
                       AsyncMock(return_value=mock_integration))
    
    response = client.get(f"/public/service/{AllowedServiceName.GOOGLE.value}")
    assert response.status_code == 200
    integration = response.json()
    assert "service_value" in integration
    assert isinstance(integration["service_value"], dict)
    assert integration["service_value"] == mock_integration.service_value

def test_read_public_integration_by_service_not_found(client, monkeypatch):
    """Test handling of non-existent public integration service"""
    monkeypatch.setattr(integrations, "get_third_party_integration_by_service", 
                       AsyncMock(return_value=None))
    
    response = client.get(f"/public/service/{AllowedServiceName.GOOGLE.value}")
    assert response.status_code == 404
    assert "Integration not found" in response.json()["detail"]

def test_update_integration_success(client, monkeypatch, mock_admin_user, mock_integration):
    """Test successful update of integration by admin"""
    # Mock the user verification and database functions
    monkeypatch.setattr(crud, "get_user_by_cognito_id", 
                       lambda db, user_id: mock_admin_user)
    monkeypatch.setattr(integrations, "verify_user_admin", 
                       lambda db, user: None)  # No exception means admin is verified
    monkeypatch.setattr(integrations, "get_third_party_integration", 
                       AsyncMock(return_value=mock_integration))
    monkeypatch.setattr(integrations, "update_third_party_integration", 
                       AsyncMock(return_value=mock_integration))
    
    # Create a proper update request that matches ThirdPartyIntegrationUpdate schema
    update_data = ThirdPartyIntegrationUpdate(
        service_value={
            "client_id": "new_client_id",
            "client_secret": "new_client_secret",
            "redirect_uri": "http://localhost:3000/auth/callback"
        }
    ).model_dump()
    
    response = client.put(f"/{mock_integration.id}", json=update_data)
    assert response.status_code == 200
    integration = response.json()
    assert "service_value" in integration
    assert isinstance(integration["service_value"], dict)
    assert integration["service_value"] == mock_integration.service_value

def test_update_integration_not_found(client, monkeypatch, mock_admin_user):
    """Test handling of update for non-existent integration"""
    # Mock the user verification and database functions
    monkeypatch.setattr(crud, "get_user_by_cognito_id", 
                       lambda db, user_id: mock_admin_user)
    monkeypatch.setattr(integrations, "verify_user_admin", 
                       lambda db, user: None)  # No exception means admin is verified
    monkeypatch.setattr(integrations, "get_third_party_integration", 
                       AsyncMock(return_value=None))
    
    # Create a proper update request that matches ThirdPartyIntegrationUpdate schema
    update_data = ThirdPartyIntegrationUpdate(
        service_value={
            "client_id": "new_client_id",
            "client_secret": "new_client_secret",
            "redirect_uri": "http://localhost:3000/auth/callback"
        }
    ).model_dump()
    
    response = client.put(f"/{uuid.uuid4()}", json=update_data)
    assert response.status_code == 404
    assert "Integration not found" in response.json()["detail"]

def test_update_integration_non_admin(client, non_admin_context):
    """Test that non-admin users cannot update integrations"""
    # Create a proper update request that matches ThirdPartyIntegrationUpdate schema
    update_data = ThirdPartyIntegrationUpdate(
        service_value={
            "client_id": "new_client_id",
            "client_secret": "new_client_secret",
            "redirect_uri": "http://localhost:3000/auth/callback"
        }
    ).model_dump()
    response = client.put(f"/{uuid.uuid4()}", json=update_data)
    assert response.status_code == 403
    assert "Not authorized" in response.json()["detail"]

def test_delete_integration_success(client, monkeypatch, mock_admin_user, mock_integration):
    """Test successful deletion of integration by admin"""
    # Mock the user verification and database functions
    monkeypatch.setattr(crud, "get_user_by_cognito_id", 
                       lambda db, user_id: mock_admin_user)
    monkeypatch.setattr(integrations, "verify_user_admin", 
                       lambda db, user: None)  # No exception means admin is verified
    monkeypatch.setattr(integrations, "get_third_party_integration", 
                       AsyncMock(return_value=mock_integration))
    monkeypatch.setattr(integrations, "delete_third_party_integration", 
                       AsyncMock(return_value=True))
    
    response = client.delete(f"/{mock_integration.id}")
    assert response.status_code == 200
    assert response.json()["message"] == "Integration deleted successfully"

def test_delete_integration_not_found(client, monkeypatch, mock_admin_user):
    """Test handling of deletion for non-existent integration"""
    # Mock the user verification and database functions
    monkeypatch.setattr(crud, "get_user_by_cognito_id", 
                       lambda db, user_id: mock_admin_user)
    monkeypatch.setattr(integrations, "verify_user_admin", 
                       lambda db, user: None)  # No exception means admin is verified
    monkeypatch.setattr(integrations, "get_third_party_integration", 
                       AsyncMock(return_value=None))
    
    response = client.delete(f"/{uuid.uuid4()}")
    assert response.status_code == 404
    assert "Integration not found" in response.json()["detail"]

def test_delete_integration_non_admin(client, non_admin_context):
    """Test that non-admin users cannot delete integrations"""
    response = client.delete(f"/{uuid.uuid4()}")
    assert response.status_code == 403
    assert "Not authorized" in response.json()["detail"]