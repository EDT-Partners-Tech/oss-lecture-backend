# © [2025] EDT&Partners. Licensed under CC BY 4.0.

import uuid
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from unittest.mock import MagicMock, AsyncMock, patch
import os

from routers import groups
from routers.groups import router, get_db
from utility.auth import oauth2_scheme
from database.models import UserRole

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

# --- Test Update Group Details ---

def test_update_group_details_success(client, monkeypatch):
    """Test successful group update"""
    # Generate test data
    group_id = uuid.uuid4()
    update_data = {
        "name": "Updated Group Name",
        "description": "Updated description"
    }
    
    # Create mock objects
    FakeUser = type("FakeUser", (), {"role": UserRole.admin, "group_id": group_id})
    FakeGroup = type("FakeGroup", (), {"id": group_id, "name": "Updated Group Name"})
    
    # Setup mocks
    monkeypatch.setattr(groups, "get_user_by_cognito_id", lambda db, sub: FakeUser())
    monkeypatch.setattr(groups, "get_group_by_id", lambda db, gid: FakeGroup())
    monkeypatch.setattr(groups, "update_group", lambda db, request, group: FakeGroup())
    
    # Call the endpoint
    response = client.patch(f"/{group_id}", json=update_data)
    
    # Verify response
    assert response.status_code == 200
    assert response.json()["group_name"] == "Updated Group Name"
    assert str(group_id) in response.json()["group_id"]

def test_update_group_not_found(client, monkeypatch):
    """Test updating a non-existent group"""
    # Generate test data
    group_id = uuid.uuid4()
    update_data = {
        "name": "Updated Group Name",
        "description": "Updated description"
    }
    
    # Setup mocks to return None for the group
    monkeypatch.setattr(groups, "get_user_by_cognito_id", lambda db, sub: type("FakeUser", (), {"role": UserRole.admin})())
    monkeypatch.setattr(groups, "get_group_by_id", lambda db, gid: None)
    
    # Call the endpoint
    response = client.patch(f"/{group_id}", json=update_data)
    
    # Verify response
    assert response.status_code == 404
    assert "Group not found" in response.json()["detail"]

def test_update_group_not_admin(client, monkeypatch):
    """Test updating a group when user is not an admin"""
    # Generate test data
    group_id = uuid.uuid4()
    update_data = {
        "name": "Updated Group Name",
        "description": "Updated description"
    }
    
    # Create mock objects with teacher role
    FakeUser = type("FakeUser", (), {"role": UserRole.teacher, "group_id": group_id})
    FakeGroup = type("FakeGroup", (), {"id": group_id})
    
    # Setup mocks
    monkeypatch.setattr(groups, "get_user_by_cognito_id", lambda db, sub: FakeUser())
    monkeypatch.setattr(groups, "get_group_by_id", lambda db, gid: FakeGroup())
    
    # Call the endpoint
    response = client.patch(f"/{group_id}", json=update_data)
    
    # Verify response
    assert response.status_code == 403
    assert "Access denied" in response.json()["detail"]

def test_update_group_different_group(client, monkeypatch):
    """Test updating a group when user is in a different group"""
    # Generate test data
    group_id = uuid.uuid4()
    different_group_id = uuid.uuid4()
    update_data = {
        "name": "Updated Group Name",
        "description": "Updated description"
    }
    
    # Create mock objects with different group_id
    FakeUser = type("FakeUser", (), {"role": UserRole.admin, "group_id": different_group_id})
    FakeGroup = type("FakeGroup", (), {"id": group_id})
    
    # Setup mocks
    monkeypatch.setattr(groups, "get_user_by_cognito_id", lambda db, sub: FakeUser())
    monkeypatch.setattr(groups, "get_group_by_id", lambda db, gid: FakeGroup())
    
    # Call the endpoint
    response = client.patch(f"/{group_id}", json=update_data)
    
    # Verify response
    assert response.status_code == 403
    assert "Access denied" in response.json()["detail"]

# --- Test Set Group Admin ---

def test_set_group_admin_success(client, monkeypatch):
    """Test successful admin role transfer"""
    # Generate test data
    group_id = uuid.uuid4()
    user_id = uuid.uuid4()
    request_data = {
        "user_id": str(user_id)
    }
    
    # Create mock objects
    FakeUser = type("FakeUser", (), {"role": UserRole.admin, "group_id": group_id})
    FakeTargetUser = type("FakeTargetUser", (), {"id": user_id, "group_id": group_id})
    FakeGroup = type("FakeGroup", (), {"id": group_id})
    
    # Setup mocks
    monkeypatch.setattr(groups, "get_user_by_cognito_id", lambda db, sub: FakeUser())
    monkeypatch.setattr(groups, "get_group_by_id", lambda db, gid: FakeGroup())
    monkeypatch.setattr(groups, "get_user", lambda db, uid: FakeTargetUser())
    monkeypatch.setattr(groups, "set_user_role", lambda db, user, role: None)
    
    # Call the endpoint
    response = client.post(f"/{group_id}/admin", json=request_data)
    
    # Verify response
    assert response.status_code == 200
    assert str(group_id) in response.json()["group_id"]
    assert str(user_id) in response.json()["new_admin_user_id"]

def test_set_group_admin_different_groups(client, monkeypatch):
    """Test admin role transfer with different group_id for target user"""
    # Generate test data
    group_id = uuid.uuid4()
    user_id = uuid.uuid4()
    request_data = {
        "user_id": str(user_id)
    }
    
    # Create mock objects
    FakeUser = type("FakeUser", (), {"role": UserRole.admin, "group_id": group_id})
    FakeTargetUser = type("FakeTargetUser", (), {"id": user_id, "group_id": uuid.uuid4()})
    FakeGroup = type("FakeGroup", (), {"id": group_id})
    
    # Setup mocks
    monkeypatch.setattr(groups, "get_user_by_cognito_id", lambda db, sub: FakeUser())
    monkeypatch.setattr(groups, "get_group_by_id", lambda db, gid: FakeGroup())
    monkeypatch.setattr(groups, "get_user", lambda db, uid: FakeTargetUser())
    monkeypatch.setattr(groups, "set_user_role", lambda db, user, role: None)
    
    # Call the endpoint
    response = client.post(f"/{group_id}/admin", json=request_data)
    
    # Verify response
    assert response.status_code == 403
    assert "Target user does not belong to the group" in response.json()["detail"]

def test_set_group_admin_group_not_found(client, monkeypatch):
    """Test setting admin for a non-existent group"""
    # Generate test data
    group_id = uuid.uuid4()
    user_id = uuid.uuid4()
    request_data = {
        "user_id": str(user_id)
    }
    
    # Setup mocks to return None for the group
    monkeypatch.setattr(groups, "get_user_by_cognito_id", lambda db, sub: type("FakeUser", (), {"role": UserRole.admin})())
    monkeypatch.setattr(groups, "get_group_by_id", lambda db, gid: None)
    
    # Call the endpoint
    response = client.post(f"/{group_id}/admin", json=request_data)
    
    # Verify response
    assert response.status_code == 404
    assert "Group not found" in response.json()["detail"]

def test_set_group_admin_target_user_not_found(client, monkeypatch):
    """Test setting admin for a non-existent target user"""
    # Generate test data
    group_id = uuid.uuid4()
    user_id = uuid.uuid4()
    request_data = {
        "user_id": str(user_id)
    }
    
    # Setup mocks to return None for the target user
    FakeUser = type("FakeUser", (), {"role": UserRole.admin, "group_id": group_id})
    FakeGroup = type("FakeGroup", (), {"id": group_id})
    
    monkeypatch.setattr(groups, "get_user_by_cognito_id", lambda db, sub: FakeUser())
    monkeypatch.setattr(groups, "get_group_by_id", lambda db, gid: FakeGroup())
    monkeypatch.setattr(groups, "get_user", lambda db, uid: None)
    
    # Call the endpoint
    response = client.post(f"/{group_id}/admin", json=request_data)
    
    # Verify response
    assert response.status_code == 404
    assert "Target user not found" in response.json()["detail"]

def test_set_group_admin_not_admin(client, monkeypatch):
    """Test setting admin when current user is not an admin"""
    # Generate test data
    group_id = uuid.uuid4()
    user_id = uuid.uuid4()
    request_data = {
        "user_id": str(user_id)
    }
    
    # Create mock objects with teacher role (non-admin)
    FakeUser = type("FakeUser", (), {"role": UserRole.teacher, "group_id": group_id})
    FakeTargetUser = type("FakeTargetUser", (), {"id": user_id})
    FakeGroup = type("FakeGroup", (), {"id": group_id})
    
    # Setup mocks
    monkeypatch.setattr(groups, "get_user_by_cognito_id", lambda db, sub: FakeUser())
    monkeypatch.setattr(groups, "get_group_by_id", lambda db, gid: FakeGroup())
    monkeypatch.setattr(groups, "get_user", lambda db, uid: FakeTargetUser())
    
    # Call the endpoint
    response = client.post(f"/{group_id}/admin", json=request_data)
    
    # Verify response
    assert response.status_code == 403
    assert "Access denied" in response.json()["detail"]

def test_set_group_internal_error(client, monkeypatch):
    """Test internal server error during admin role transfer"""
    # Generate test data
    group_id = uuid.uuid4()
    user_id = uuid.uuid4()
    request_data = {
        "user_id": str(user_id)
    }
    
    # Create mock objects
    FakeUser = type("FakeUser", (), {"role": UserRole.admin, "group_id": group_id})
    FakeTargetUser = type("FakeTargetUser", (), {"id": user_id})
    FakeGroup = type("FakeGroup", (), {"id": group_id})
    
    # Setup mocks
    monkeypatch.setattr(groups, "get_user_by_cognito_id", lambda db, sub: FakeUser())
    monkeypatch.setattr(groups, "get_group_by_id", lambda db, gid: FakeGroup())
    monkeypatch.setattr(groups, "get_user", lambda db, uid: FakeTargetUser())
    
    # Set up mock to throw exception
    def mock_set_user_role(db, user, role):
        raise Exception("Database connection error")
    
    monkeypatch.setattr(groups, "set_user_role", mock_set_user_role)
    
    # Call the endpoint
    response = client.post(f"/{group_id}/admin", json=request_data)
    
    # Verify response
    assert response.status_code == 500
    assert "Internal Server Error" in response.json()["detail"]

# --- Test Get Group Services ---

def test_get_group_services_success(client, monkeypatch):
    """Test successful retrieval of group services"""
    # Generate test data
    group_id = uuid.uuid4()
    
    # Create mock objects
    FakeUser = type("FakeUser", (), {"role": UserRole.admin, "group_id": group_id})
    FakeGroup = type("FakeGroup", (), {"id": group_id, "available_services": ["service1", "service2"]})
    
    # Setup mocks
    monkeypatch.setattr(groups, "get_user_by_cognito_id", lambda db, sub: FakeUser())
    monkeypatch.setattr(groups, "get_group_by_id", lambda db, gid: FakeGroup())
    
    # Call the endpoint
    response = client.get(f"/{group_id}/services")
    
    # Verify response
    assert response.status_code == 200
    assert response.json()["services"] == ["service1", "service2"]

def test_get_group_services_group_not_found(client, monkeypatch):
    """Test getting services for a non-existent group"""
    # Generate test data
    group_id = uuid.uuid4()
    
    # Setup mocks to return None for the group
    monkeypatch.setattr(groups, "get_user_by_cognito_id", lambda db, sub: type("FakeUser", (), {"role": UserRole.admin})())
    monkeypatch.setattr(groups, "get_group_by_id", lambda db, gid: None)
    
    # Call the endpoint
    response = client.get(f"/{group_id}/services")
    
    # Verify response
    assert response.status_code == 404
    assert "Group not found" in response.json()["detail"]

# --- Test Get Group Models ---

def test_get_group_models_success(client, monkeypatch):
    """Test successful retrieval of group models"""
    # Generate test data
    group_id = uuid.uuid4()
    
    # Create mock objects
    FakeUser = type("FakeUser", (), {"role": UserRole.admin, "group_id": group_id})
    FakeGroup = type("FakeGroup", (), {"id": group_id, "available_models": ["model1", "model2"]})
    
    # Setup mocks
    monkeypatch.setattr(groups, "get_user_by_cognito_id", lambda db, sub: FakeUser())
    monkeypatch.setattr(groups, "get_group_by_id", lambda db, gid: FakeGroup())
    
    # Call the endpoint
    response = client.get(f"/{group_id}/models")
    
    # Verify response
    assert response.status_code == 200
    assert response.json()["models"] == ["model1", "model2"]

def test_get_group_models_group_not_found(client, monkeypatch):
    """Test getting models for a non-existent group"""
    # Generate test data
    group_id = uuid.uuid4()
    
    # Setup mocks to return None for the group
    monkeypatch.setattr(groups, "get_user_by_cognito_id", lambda db, sub: type("FakeUser", (), {"role": UserRole.admin})())
    monkeypatch.setattr(groups, "get_group_by_id", lambda db, gid: None)
    
    # Call the endpoint
    response = client.get(f"/{group_id}/models")
    
    # Verify response
    assert response.status_code == 404
    assert "Group not found" in response.json()["detail"]

# --- Test Configure Group Services ---

def test_configure_group_services_success(client, monkeypatch):
    """Test successful configuration of group services"""
    # Generate test data
    group_id = uuid.uuid4()
    request_data = {
        "services_ids": [str(uuid.uuid4()), str(uuid.uuid4())]
    }
    
    # Create mock objects
    FakeUser = type("FakeUser", (), {"role": UserRole.admin, "group_id": group_id})
    FakeGroup = type("FakeGroup", (), {"id": group_id})
    FakeService = type("FakeService", (), {"code": "service_code"})
    FakeUpdatedGroup = type("FakeUpdatedGroup", (), {
        "id": group_id,
        "available_services": [FakeService(), FakeService()]
    })
    
    # Setup mocks
    monkeypatch.setattr(groups, "get_user_by_cognito_id", lambda db, sub: FakeUser())
    monkeypatch.setattr(groups, "get_group_by_id", lambda db, gid: FakeGroup())
    monkeypatch.setattr(groups, "get_services_by_ids", lambda db, sids: [FakeService(), FakeService()])
    monkeypatch.setattr(groups, "set_group_available_services", lambda db, gid, services: FakeUpdatedGroup())
    
    # Call the endpoint
    response = client.put(f"/{group_id}/services", json=request_data)
    
    # Verify response
    assert response.status_code == 200
    assert str(group_id) in response.json()["updated_group_id"]
    assert response.json()["updated_services"] == ["service_code", "service_code"]

def test_configure_group_services_group_not_found(client, monkeypatch):
    """Test configuring services for a non-existent group"""
    # Generate test data
    group_id = uuid.uuid4()
    request_data = {
        "services_ids": [str(uuid.uuid4())]
    }
    
    # Setup mocks to return None for the group
    monkeypatch.setattr(groups, "get_user_by_cognito_id", lambda db, sub: type("FakeUser", (), {"role": UserRole.admin})())
    monkeypatch.setattr(groups, "get_group_by_id", lambda db, gid: None)
    
    # Call the endpoint
    response = client.put(f"/{group_id}/services", json=request_data)
    
    # Verify response
    assert response.status_code == 404
    assert "Group not found" in response.json()["detail"]

def test_configure_group_services_services_not_found(client, monkeypatch):
    """Test configuring with non-existent services"""
    # Generate test data
    group_id = uuid.uuid4()
    request_data = {
        "services_ids": [str(uuid.uuid4())]
    }
    
    # Setup mocks to return None for services
    FakeUser = type("FakeUser", (), {"role": UserRole.admin, "group_id": group_id})
    FakeGroup = type("FakeGroup", (), {"id": group_id})
    
    monkeypatch.setattr(groups, "get_user_by_cognito_id", lambda db, sub: FakeUser())
    monkeypatch.setattr(groups, "get_group_by_id", lambda db, gid: FakeGroup())
    monkeypatch.setattr(groups, "get_services_by_ids", lambda db, sids: None)
    
    # Call the endpoint
    response = client.put(f"/{group_id}/services", json=request_data)
    
    # Verify response
    assert response.status_code == 404
    assert "Services not found" in response.json()["detail"]

# --- Test Configure Group Models ---

def test_configure_group_models_success(client, monkeypatch):
    """Test successful configuration of group models"""
    # Generate test data
    group_id = uuid.uuid4()
    model_id = 111
    request_data = {
        "models_ids": [model_id]
    }
    
    # Create mock objects
    FakeUser = type("FakeUser", (), {"role": UserRole.admin, "group_id": group_id})
    FakeGroup = type("FakeGroup", (), {"id": group_id})
    FakeModel = type("FakeModel", (), {"id": model_id})
    FakeUpdatedGroup = type("FakeUpdatedGroup", (), {
        "id": group_id,
        "available_models": [FakeModel()]
    })
    
    # Setup mocks
    monkeypatch.setattr(groups, "get_user_by_cognito_id", lambda db, sub: FakeUser())
    monkeypatch.setattr(groups, "get_group_by_id", lambda db, gid: FakeGroup())
    monkeypatch.setattr(groups, "get_ai_models_by_ids", lambda db, mids: [FakeModel()])
    monkeypatch.setattr(groups, "set_group_available_models", lambda db, gid, models: FakeUpdatedGroup())
    
    # Call the endpoint
    response = client.put(f"/{group_id}/models", json=request_data)
    
    # Verify response
    assert response.status_code == 200
    assert str(group_id) in response.json()["updated_group_id"]
    assert model_id == response.json()["updated_models"][0]

def test_configure_group_models_models_not_found(client, monkeypatch):
    """Test configuring with non-existent models"""
    # Generate test data
    group_id = uuid.uuid4()
    request_data = {
        "models_ids": [111]
    }
    
    # Setup mocks to return None for models
    FakeUser = type("FakeUser", (), {"role": UserRole.admin, "group_id": group_id})
    FakeGroup = type("FakeGroup", (), {"id": group_id})
    
    monkeypatch.setattr(groups, "get_user_by_cognito_id", lambda db, sub: FakeUser())
    monkeypatch.setattr(groups, "get_group_by_id", lambda db, gid: FakeGroup())
    monkeypatch.setattr(groups, "get_ai_models_by_ids", lambda db, mids: None)
    
    # Call the endpoint
    response = client.put(f"/{group_id}/models", json=request_data)
    
    # Verify response
    assert response.status_code == 404
    assert "Models not found" in response.json()["detail"]

# --- Test Delete Group ---

def test_delete_group_success(client, monkeypatch):
    """Test successful group deletion"""
    # Generate test data
    group_id = uuid.uuid4()
    
    # Create mock objects
    FakeUser = type("FakeUser", (), {"role": UserRole.admin, "group_id": group_id})
    FakeGroup = type("FakeGroup", (), {"id": group_id})
    
    # Setup mocks
    monkeypatch.setattr(groups, "get_user_by_cognito_id", lambda db, sub: FakeUser())
    monkeypatch.setattr(groups, "get_group_by_id", lambda db, gid: FakeGroup())
    monkeypatch.setattr(groups, "delete_group_from_db", lambda db, group: None)
    
    # Call the endpoint
    response = client.delete(f"/{group_id}")
    
    # Verify response
    assert response.status_code == 200
    assert str(group_id) in response.json()["deleted_group_id"]

def test_delete_group_not_found(client, monkeypatch):
    """Test deleting a non-existent group"""
    # Generate test data
    group_id = uuid.uuid4()
    
    # Setup mocks to return None for the group
    monkeypatch.setattr(groups, "get_user_by_cognito_id", lambda db, sub: type("FakeUser", (), {"role": UserRole.admin})())
    monkeypatch.setattr(groups, "get_group_by_id", lambda db, gid: None)
    
    # Call the endpoint
    response = client.delete(f"/{group_id}")
    
    # Verify response
    assert response.status_code == 404
    assert "Group not found" in response.json()["detail"]

def test_delete_group_not_admin(client, monkeypatch):
    """Test deleting a group when user is not an admin"""
    # Generate test data
    group_id = uuid.uuid4()
    
    # Create mock objects with teacher role
    FakeUser = type("FakeUser", (), {"role": UserRole.teacher, "group_id": group_id})
    FakeGroup = type("FakeGroup", (), {"id": group_id})
    
    # Setup mocks
    monkeypatch.setattr(groups, "get_user_by_cognito_id", lambda db, sub: FakeUser())
    monkeypatch.setattr(groups, "get_group_by_id", lambda db, gid: FakeGroup())
    
    # Call the endpoint
    response = client.delete(f"/{group_id}")
    
    # Verify response
    assert response.status_code == 403
    assert "Access denied" in response.json()["detail"]

def test_upload_group_logo_success(client, monkeypatch):
    """Test successful logo upload"""
    # Generate test data
    group_id = uuid.uuid4()
    logo_s3_uri = "s3://bucket/groups/123/logo"
    
    # Create mock objects
    FakeUser = type("FakeUser", (), {"role": UserRole.admin, "group_id": group_id})
    FakeGroup = type("FakeGroup", (), {"id": group_id})
    
    # Setup mocks
    monkeypatch.setattr(groups, "get_user_by_cognito_id", lambda db, sub: FakeUser())
    monkeypatch.setattr(groups, "get_group_by_id", lambda db, gid: FakeGroup())
    
    async def mock_upload_file_to_s3(bucket, file_path, s3_path):
        return logo_s3_uri
    
    async def mock_db_upload_group_logo(db, gid, uri):
        return None
    
    monkeypatch.setattr(groups, "upload_file_to_s3", mock_upload_file_to_s3)
    monkeypatch.setattr(groups, "db_upload_group_logo", mock_db_upload_group_logo)
    
    # Create a test file
    with open("test_logo.png", "wb") as f:
        f.write(b"test logo content")
    
    try:
        # Call the endpoint
        with open("test_logo.png", "rb") as f:
            response = client.post(
                f"/{group_id}/upload-logo",
                files={"logo": ("test_logo.png", f, "image/png")}
            )
        
        # Verify response
        assert response.status_code == 200
        assert response.json()["logo_s3_uri"] == logo_s3_uri
    finally:
        # Clean up test file
        os.remove("test_logo.png")

def test_upload_group_logo_group_not_found(client, monkeypatch):
    """Test uploading logo for a non-existent group"""
    # Generate test data
    group_id = uuid.uuid4()
    
    # Setup mocks to return None for the group
    monkeypatch.setattr(groups, "get_user_by_cognito_id", lambda db, sub: type("FakeUser", (), {"role": UserRole.admin})())
    monkeypatch.setattr(groups, "get_group_by_id", lambda db, gid: None)
    
    # Create a test file
    with open("test_logo.png", "wb") as f:
        f.write(b"test logo content")
    
    try:
        # Call the endpoint
        with open("test_logo.png", "rb") as f:
            response = client.post(
                f"/{group_id}/upload-logo",
                files={"logo": ("test_logo.png", f, "image/png")}
            )
        
        # Verify response
        assert response.status_code == 404
        assert "Group not found" in response.json()["detail"]
    finally:
        # Clean up test file
        os.remove("test_logo.png")

def test_upload_group_logo_not_admin(client, monkeypatch):
    """Test uploading logo when user is not an admin"""
    # Generate test data
    group_id = uuid.uuid4()
    
    # Create mock objects with teacher role
    FakeUser = type("FakeUser", (), {"role": UserRole.teacher, "group_id": group_id})
    FakeGroup = type("FakeGroup", (), {"id": group_id})
    
    # Setup mocks
    monkeypatch.setattr(groups, "get_user_by_cognito_id", lambda db, sub: FakeUser())
    monkeypatch.setattr(groups, "get_group_by_id", lambda db, gid: FakeGroup())
    
    # Create a test file
    with open("test_logo.png", "wb") as f:
        f.write(b"test logo content")
    
    try:
        # Call the endpoint
        with open("test_logo.png", "rb") as f:
            response = client.post(
                f"/{group_id}/upload-logo",
                files={"logo": ("test_logo.png", f, "image/png")}
            )
        
        # Verify response
        assert response.status_code == 403
        assert "Access denied" in response.json()["detail"]
    finally:
        # Clean up test file
        os.remove("test_logo.png")

# --- Test Remove Group Logo ---

def test_remove_group_logo_success(client, monkeypatch):
    """Test successful logo removal"""
    # Generate test data
    group_id = uuid.uuid4()
    
    # Create mock objects
    FakeUser = type("FakeUser", (), {"role": UserRole.admin, "group_id": group_id})
    FakeGroup = type("FakeGroup", (), {"id": group_id})
    
    # Setup mocks
    monkeypatch.setattr(groups, "get_user_by_cognito_id", lambda db, sub: FakeUser())
    monkeypatch.setattr(groups, "get_group_by_id", lambda db, gid: FakeGroup())
    
    async def mock_db_upload_group_logo(db, gid, uri):
        return None
    
    monkeypatch.setattr(groups, "db_upload_group_logo", mock_db_upload_group_logo)
    
    # Call the endpoint
    response = client.delete(f"/{group_id}/remove-logo")
    
    # Verify response
    assert response.status_code == 200
    assert str(group_id) in response.json()["deleted_group_id"]

def test_remove_group_logo_group_not_found(client, monkeypatch):
    """Test removing logo for a non-existent group"""
    # Generate test data
    group_id = uuid.uuid4()
    
    # Setup mocks to return None for the group
    monkeypatch.setattr(groups, "get_user_by_cognito_id", lambda db, sub: type("FakeUser", (), {"role": UserRole.admin})())
    monkeypatch.setattr(groups, "get_group_by_id", lambda db, gid: None)
    
    # Call the endpoint
    response = client.delete(f"/{group_id}/remove-logo")
    
    # Verify response
    assert response.status_code == 404
    assert "Group not found" in response.json()["detail"]

def test_remove_group_logo_not_admin(client, monkeypatch):
    """Test removing logo when user is not an admin"""
    # Generate test data
    group_id = uuid.uuid4()
    
    # Create mock objects with teacher role
    FakeUser = type("FakeUser", (), {"role": UserRole.teacher, "group_id": group_id})
    FakeGroup = type("FakeGroup", (), {"id": group_id})
    
    # Setup mocks
    monkeypatch.setattr(groups, "get_user_by_cognito_id", lambda db, sub: FakeUser())
    monkeypatch.setattr(groups, "get_group_by_id", lambda db, gid: FakeGroup())
    
    # Call the endpoint
    response = client.delete(f"/{group_id}/remove-logo")
    
    # Verify response
    assert response.status_code == 403
    assert "Access denied" in response.json()["detail"]
