# © [2025] EDT&Partners. Licensed under CC BY 4.0.

import pytest
import uuid
from unittest.mock import MagicMock, patch
from sqlalchemy.orm import Session
from utility.service import get_service_id_by_code, handle_save_request, _service_cache

@pytest.fixture
def mock_db():
    """Fixture to create a mock database session"""
    db = MagicMock(spec=Session)
    return db

@pytest.fixture
def mock_service():
    """Fixture to create a mock service object"""
    service = MagicMock()
    service.id = 1
    service.name = "Test Service"
    service.code = "test_service_code"
    return service

def test_get_service_id_by_code_success(mock_db, mock_service):
    """Test get_service_id_by_code with a valid service code"""
    # Setup
    mock_db.query.return_value.filter.return_value.first.return_value = mock_service
    
    # Clear cache to ensure fresh test
    _service_cache.clear()
    
    # Execute
    service_id = get_service_id_by_code(mock_db, "test_service_code")
    
    # Assert
    assert service_id == 1
    mock_db.query.assert_called_once()
    
    # Check that the result was cached
    assert "test_service_code" in _service_cache
    assert _service_cache["test_service_code"] == 1

def test_get_service_id_by_code_cached(mock_db, mock_service):
    """Test get_service_id_by_code with an already cached service code"""
    # Setup - Add the service to cache
    _service_cache.clear()
    _service_cache["test_service_code"] = 1
    
    # Execute
    service_id = get_service_id_by_code(mock_db, "test_service_code")
    
    # Assert
    assert service_id == 1
    # Database should not be queried when using cached value
    mock_db.query.assert_not_called()

def test_get_service_id_by_code_case_insensitive(mock_db, mock_service):
    """Test get_service_id_by_code handles case insensitivity properly"""
    # Setup
    mock_db.query.return_value.filter.return_value.first.return_value = mock_service
    
    # Clear cache
    _service_cache.clear()
    
    # Execute with uppercase
    service_id = get_service_id_by_code(mock_db, "TEST_SERVICE_CODE")
    
    # Assert
    assert service_id == 1
    assert "test_service_code" in _service_cache  # Should be stored lowercase
    
    # Database should be queried once
    mock_db.query.assert_called_once()

def test_get_service_id_by_code_whitespace(mock_db, mock_service):
    """Test get_service_id_by_code handles whitespace properly"""
    # Setup
    mock_db.query.return_value.filter.return_value.first.return_value = mock_service
    
    # Clear cache
    _service_cache.clear()
    
    # Execute with whitespace
    service_id = get_service_id_by_code(mock_db, "  test_service_code  ")
    
    # Assert
    assert service_id == 1
    assert "test_service_code" in _service_cache  # Should be stored without whitespace
    
    # Database should be queried once
    mock_db.query.assert_called_once()

def test_get_service_id_by_code_not_found(mock_db):
    """Test get_service_id_by_code raises an error when service is not found"""
    # Setup
    mock_db.query.return_value.filter.return_value.first.return_value = None
    
    # Clear cache
    _service_cache.clear()
    
    # Execute and Assert
    with pytest.raises(ValueError, match="Service with code 'nonexistent_code' not found"):
        get_service_id_by_code(mock_db, "nonexistent_code")
    
    # Database should be queried once
    mock_db.query.assert_called_once()

def test_handle_save_request_success(mock_db, mock_service):
    """Test handle_save_request with valid inputs"""
    # Setup
    mock_db.query.return_value.filter.return_value.first.return_value = mock_service
    mock_request = MagicMock()
    mock_request.id = uuid.uuid4()
    
    # Mock the save_request function
    with patch("utility.service.save_request", return_value=mock_request) as mock_save_request:
        # Clear cache
        _service_cache.clear()
        
        # Execute
        request_id = handle_save_request(mock_db, "Test Title", "user123", "test_service_code")
        
        # Assert
        assert request_id == mock_request.id
        mock_save_request.assert_called_once_with(mock_db, "Test Title", "user123", 1)

def test_handle_save_request_service_not_found(mock_db):
    """Test handle_save_request when service is not found"""
    # Setup
    mock_db.query.return_value.filter.return_value.first.return_value = None
    
    # Clear cache
    _service_cache.clear()
    
    # Mock print to capture error message
    with patch("builtins.print") as mock_print:
        # Execute
        result = handle_save_request(mock_db, "Test Title", "user123", "nonexistent_code")
        
        # Assert
        assert result is None
        mock_print.assert_called_once()
        # Check if the error message contains expected text
        error_message = mock_print.call_args[0][0]
        assert "Error while saving request data" in error_message
        assert "not found" in error_message

def test_handle_save_request_db_error(mock_db, mock_service):
    """Test handle_save_request when database operation fails"""
    # Setup
    mock_db.query.return_value.filter.return_value.first.return_value = mock_service
    
    # Mock save_request to raise an exception
    with patch("utility.service.save_request", side_effect=Exception("Database error")) as mock_save_request:
        # Clear cache
        _service_cache.clear()
        
        # Execute
        result = handle_save_request(mock_db, "Test Title", "user123", "test_service_code")
        
        # Assert
        assert result is None
        mock_save_request.assert_called_once()
