# © [2025] EDT&Partners. Licensed under CC BY 4.0.

import pytest
from datetime import datetime, timedelta
from unittest.mock import Mock, patch, ANY
from sqlalchemy.orm import Session
from utility.analytics import (
    count_bedrock_tokens,
    calculate_cost,
    get_model_config,
    process_and_save_analytics,
    update_processing_time
)
from database.models import Request

@pytest.fixture
def mock_db():
    return Mock(spec=Session)

@pytest.fixture
def mock_request():
    request = Mock(spec=Request)
    request.id = 1
    request.created_at = datetime.now() - timedelta(seconds=5)
    return request

def test_count_bedrock_tokens():
    assert count_bedrock_tokens("") == 0
    assert count_bedrock_tokens("Hello world") == 2  # 11 chars / 6.0 + 1
    assert count_bedrock_tokens("Hello world", token_rate=4.0) == 3  # 11 / 4.0 + 1

@patch('utility.analytics.get_model_by_id')
def test_calculate_cost(mock_get_model_by_id):
    mock_model_data = Mock()
    mock_model_data.input_price = 0.001
    mock_model_data.output_price = 0.002
    mock_get_model_by_id.return_value = mock_model_data

    cost = calculate_cost("test-model", 1000, 500)
    assert cost == 0.002

    mock_get_model_by_id.return_value = None
    assert calculate_cost("non-existent", 1000, 500) == 0.0

@patch('utility.analytics.get_model_by_id')
def test_get_model_config(mock_get_model_by_id):
    mock_model_data = Mock()
    mock_model_data.provider = "test-provider"
    mock_model_data.token_rate = 4.0
    mock_get_model_by_id.return_value = mock_model_data

    config = get_model_config("test-model")
    assert config == {'type': 'test-provider', 'token_rate': 4.0}

    mock_get_model_by_id.return_value = None
    config = get_model_config("non-existent")
    assert config == {'type': 'non-existent', 'token_rate': 6.0}

@pytest.mark.asyncio
async def test_process_and_save_analytics_success():
    db_mock = Mock(spec=Session)

    model_data_mock = Mock()
    model_data_mock.input_price = 0.001
    model_data_mock.output_price = 0.002
    model_data_mock.token_rate = 6.0

    with patch('utility.analytics.get_default_model_ids', return_value={"claude": "test-model"}), \
         patch('utility.analytics.get_model_by_id', return_value=model_data_mock), \
         patch('utility.analytics.save_analytics') as mock_save_analytics:


        await process_and_save_analytics(
            db=db_mock,
            request_id=1,
            model="default",
            request_prompt="Hello world",
            response="Hi back",
            processing_time=1.23
        )

        assert mock_save_analytics.called
        args, kwargs = mock_save_analytics.call_args
        assert kwargs['model'] == "test-model"
        assert kwargs['status'] == "success"
        assert kwargs['error'] is None
        assert kwargs['processing_time'] == 1.23
        assert kwargs['request_token_count'] > 0
        assert kwargs['response_token_count'] > 0
        assert kwargs['estimated_cost'] > 0

@pytest.mark.asyncio
async def test_process_and_save_analytics_error():
    db_mock = Mock(spec=Session)

    with patch('utility.analytics.get_default_model_ids', return_value={"claude": "test-model"}), \
         patch('utility.analytics.get_model_by_id', side_effect=Exception("DB failure")), \
         patch('utility.analytics.save_analytics') as mock_save_analytics:

        await process_and_save_analytics(
            db=db_mock,
            request_id=2,
            model="default",
            request_prompt="Hello",
            response="Hi",
            processing_time=0.5
        )

        assert mock_save_analytics.called
        args, kwargs = mock_save_analytics.call_args
        assert kwargs['status'] == "error"
        assert kwargs['error'] == "DB failure"
        assert kwargs['request_token_count'] == 0
        assert kwargs['response_token_count'] == 0
        assert kwargs['estimated_cost'] == 0

def test_update_processing_time(mock_db, mock_request):
    mock_db.query.return_value.filter.return_value.first.return_value = mock_request

    processing_time = update_processing_time(mock_db, 1)
    assert isinstance(processing_time, float)
    assert processing_time > 0

    mock_db.query.return_value.filter.return_value.first.return_value = None
    assert update_processing_time(mock_db, 999) == 0.0
