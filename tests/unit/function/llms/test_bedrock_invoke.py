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
import io
import pytest
import json
from unittest.mock import patch, ANY
import boto3
import botocore.session
from botocore.stub import Stubber, ANY
from botocore.exceptions import ClientError

# Import module under test
from function.llms.bedrock_invoke import (
    invoke_bedrock_titan,
    invoke_bedrock_claude,
    invoke_bedrock_claude_async,
    invoke_bedrock_nova,
    invoke_bedrock_nova_async,
    invoke_bedrock_meta,
    invoke_bedrock_meta_async,
    invoke_bedrock_model,
    retrieve_and_generate,
    APPLICATION_JSON
)

# Mock database models
class MockModel:
    def __init__(self, identifier, provider, region, region_suffix, is_default=False, max_input_tokens=4096, inference=False):
        self.identifier = identifier
        self.provider = provider
        self.region = region
        self.region_suffix = region_suffix
        self.is_default = is_default
        self.max_input_tokens = max_input_tokens
        self.inference = inference

# Fixture to create mock models
@pytest.fixture
def mock_models():
    return {
        "anthropic.claude-3-5-sonnet-20240620-v1:0": MockModel(
            identifier="anthropic.claude-3-5-sonnet-20240620-v1:0",
            provider="Anthropic",
            region="us-east-1",
            region_suffix="eu",
            is_default=True,
            max_input_tokens=4096
        ),
        "amazon.nova-pro-v1:0": MockModel(
            identifier="amazon.nova-pro-v1:0",
            provider="Amazon",
            region="us-east-1",
            region_suffix="us",
            is_default=True,
            max_input_tokens=4096
        ),
        "meta.llama-3-70b-instruct-v1:0": MockModel(
            identifier="meta.llama-3-70b-instruct-v1:0",
            provider="Meta",
            region="us-east-1",
            region_suffix="meta",
            is_default=True,
            max_input_tokens=4096
        )
    }

# Fixture to mock database functions
@pytest.fixture
def mock_db_functions(mock_models):
    models = {
        "anthropic": {
            "models": ["anthropic.claude-3-5-sonnet-20240620-v1:0"],
            "region": "us-east-1",
            "region_suffix": "eu",
            "default": "anthropic.claude-3-5-sonnet-20240620-v1:0"
        },
        "amazon": {
            "models": ["amazon.nova-pro-v1:0"],
            "region": "us-east-1",
            "region_suffix": "us",
            "default": "amazon.nova-pro-v1:0"
        },
        "meta": {
            "models": ["meta.llama-3-70b-instruct-v1:0"],
            "region": "us-east-1",
            "region_suffix": "meta",
            "default": "meta.llama-3-70b-instruct-v1:0"
        }
    }
    
    inference_models = ["inference.anthropic.claude-3-5-sonnet-20240620-v1:0"]
    
    default_model_ids = {
        "claude": "anthropic.claude-3-5-sonnet-20240620-v1:0",
        "nova": "amazon.nova-pro-v1:0",
        "meta": "meta.llama-3-70b-instruct-v1:0"
    }
    
    with patch('function.llms.bedrock_invoke.get_models', return_value=models), \
         patch('function.llms.bedrock_invoke.get_model_by_id', side_effect=lambda id: mock_models.get(id)), \
         patch('function.llms.bedrock_invoke.get_inference_models', return_value=inference_models), \
         patch('function.llms.bedrock_invoke.get_default_model_ids', return_value=default_model_ids), \
         patch('function.llms.bedrock_invoke._check_prompt_length', return_value=None):
        yield

# Fixture to create a stubbed bedrock-runtime client
@pytest.fixture
def bedrock_runtime_stubber():
    session = boto3.Session(region_name="us-east-1")
    client = session.client("bedrock-runtime")
    stubber = Stubber(client)
    with stubber:
        yield stubber

# Fixture to create a stubbed bedrock-agent-runtime client
@pytest.fixture
def bedrock_agent_runtime_stubber():
    session = boto3.Session(region_name="us-east-1")
    client = session.client("bedrock-agent-runtime")
    stubber = Stubber(client)
    with stubber:
        yield stubber

# Fixture to create a stubbed STS client
@pytest.fixture
def sts_stubber():
    session = boto3.Session(region_name="us-east-1")
    client = session.client("sts")
    stubber = Stubber(client)
    with stubber:
        yield stubber

# Helper function to create a mock response
def create_mock_response(response_body, content_type=APPLICATION_JSON):
    stream_bytes = bytes(json.dumps(response_body), encoding='utf-8')
    return {
        'body': botocore.response.StreamingBody(
            raw_stream=io.BytesIO(stream_bytes),
            content_length=len(stream_bytes)
        ),
        'contentType': content_type
    }

# Tests for the invoke_bedrock_titan function
class TestInvokeBedrockTitan:
    def test_invoke_bedrock_titan_success(self, bedrock_runtime_stubber, mock_db_functions):
        expected_params = {
            'modelId': 'amazon.titan-text-express-v1',
            'contentType': APPLICATION_JSON,
            'accept': APPLICATION_JSON,
            'body': json.dumps({
                "inputText": "What is the capital of France?",
                "textGenerationConfig": {
                    "topP": 1,
                    "temperature": 0.3,
                    "stopSequences": [],
                    "maxTokenCount": 1024,
                }
            })
        }
        
        response = create_mock_response({"results": [{"outputText": "<p>This is a test response</p>"}]})
        bedrock_runtime_stubber.add_response('invoke_model', response, expected_params)
        
        with patch('function.llms.bedrock_invoke.create_bedrock_client', return_value=bedrock_runtime_stubber.client):
            result = invoke_bedrock_titan("What is the capital of France?")
            assert result == "This is a test response"
            assert "<p>" not in result

    def test_invoke_bedrock_titan_with_params(self, bedrock_runtime_stubber, mock_db_functions):
        expected_params = {
            'modelId': 'amazon.titan-text-express-v1',
            'contentType': APPLICATION_JSON,
            'accept': APPLICATION_JSON,
            'body': json.dumps({
                "inputText": "Custom prompt",
                "textGenerationConfig": {
                    "topP": 0.9,
                    "temperature": 0.8,
                    "stopSequences": [],
                    "maxTokenCount": 2048,
                }
            })
        }
        
        response = create_mock_response({"results": [{"outputText": "Custom temperature response"}]})
        bedrock_runtime_stubber.add_response('invoke_model', response, expected_params)
        
        with patch('function.llms.bedrock_invoke.create_bedrock_client', return_value=bedrock_runtime_stubber.client):
            result = invoke_bedrock_titan("Custom prompt", temperature=0.8, top_p=0.9, max_tokens=2048)
            assert result == "Custom temperature response"

    def test_invoke_bedrock_titan_error(self, bedrock_runtime_stubber, mock_db_functions):
        expected_params = {
            'modelId': 'amazon.titan-text-express-v1',
            'contentType': APPLICATION_JSON,
            'accept': APPLICATION_JSON,
            'body': json.dumps({
                "inputText": "Test prompt",
                "textGenerationConfig": {
                    "topP": 1,
                    "temperature": 0.3,
                    "stopSequences": [],
                    "maxTokenCount": 1024,
                }
            })
        }
        
        bedrock_runtime_stubber.add_client_error(
            'invoke_model', 
            service_error_code='ServiceUnavailable',
            service_message='Service unavailable',
            expected_params=expected_params
        )
        
        with patch('function.llms.bedrock_invoke.create_bedrock_client', return_value=bedrock_runtime_stubber.client):
            with pytest.raises(ClientError) as excinfo:
                invoke_bedrock_titan("Test prompt")
            assert "Service unavailable" in str(excinfo.value)

# Tests for the invoke_bedrock_claude function
class TestInvokeBedrockClaude:
    def test_invoke_bedrock_claude_success(self, bedrock_runtime_stubber, mock_db_functions):
        model_id = "anthropic.claude-3-5-sonnet-20240620-v1:0"
        expected_params = {
            'modelId': f"arn:aws:bedrock:us-east-1::foundation-model/{model_id}",
            'body': json.dumps({
                "anthropic_version": "bedrock-2023-05-31",
                "max_tokens": 4096,
                "system": "You are an AI assistant focused on clarity, accuracy, and helpfulness.",
                "messages": [{"role": "user", "content": "What is the capital of France?"}]
            })
        }
        
        response = create_mock_response({"content": [{"text": "Claude response"}]})
        bedrock_runtime_stubber.add_response('invoke_model', response, expected_params)
        
        with patch('function.llms.bedrock_invoke.create_bedrock_client', return_value=bedrock_runtime_stubber.client), \
             patch('function.llms.bedrock_invoke.get_model_region', return_value=("us-east-1", "eu")), \
             patch('function.llms.bedrock_invoke.is_inference_model', return_value=False), \
             patch('function.llms.bedrock_invoke.get_caller_identity', return_value='123456789012'):
            result = invoke_bedrock_claude("What is the capital of France?", model_id)
            assert result == "Claude response"

    @pytest.mark.asyncio
    async def test_invoke_bedrock_claude_async(self, bedrock_runtime_stubber, mock_db_functions):
        model_id = "anthropic.claude-3-5-sonnet-20240620-v1:0"
        expected_params = {
            'modelId': f"arn:aws:bedrock:us-east-1::foundation-model/{model_id}",
            'body': json.dumps({
                "anthropic_version": "bedrock-2023-05-31",
                "max_tokens": 4096,
                "system": "You are an AI assistant focused on clarity, accuracy, and helpfulness.",
                "messages": [{"role": "user", "content": "What is the capital of France?"}]
            })
        }
        
        response = create_mock_response({"content": [{"text": "Async Claude response"}]})
        bedrock_runtime_stubber.add_response('invoke_model', response, expected_params)
        
        async def mock_to_thread(func, *args, **kwargs):
            return func(*args, **kwargs)
            
        with patch('function.llms.bedrock_invoke.create_bedrock_client', return_value=bedrock_runtime_stubber.client), \
             patch('function.llms.bedrock_invoke.get_model_region', return_value=("us-east-1", "eu")), \
             patch('function.llms.bedrock_invoke.is_inference_model', return_value=False), \
             patch('function.llms.bedrock_invoke.get_caller_identity', return_value='123456789012'), \
             patch('asyncio.to_thread', side_effect=mock_to_thread):
            result = await invoke_bedrock_claude_async("What is the capital of France?", model_id)
            assert result == "Async Claude response"

    def test_invoke_bedrock_claude_client_error(self, bedrock_runtime_stubber, mock_db_functions):
        model_id = "anthropic.claude-3-5-sonnet-20240620-v1:0"
        expected_params = {
            'modelId': f"arn:aws:bedrock:us-east-1::foundation-model/{model_id}",
            'body': json.dumps({
                "anthropic_version": "bedrock-2023-05-31",
                "max_tokens": 4096,
                "system": "You are an AI assistant focused on clarity, accuracy, and helpfulness.",
                "messages": [{"role": "user", "content": "Test prompt"}]
            })
        }
        
        bedrock_runtime_stubber.add_client_error(
            'invoke_model',
            service_error_code='ValidationException',
            service_message='Invalid request',
            expected_params=expected_params
        )
        
        with patch('function.llms.bedrock_invoke.create_bedrock_client', return_value=bedrock_runtime_stubber.client), \
             patch('function.llms.bedrock_invoke.get_model_region', return_value=("us-east-1", "eu")), \
             patch('function.llms.bedrock_invoke.is_inference_model', return_value=False), \
             patch('function.llms.bedrock_invoke.get_caller_identity', return_value='123456789012'):
            with pytest.raises(ClientError) as excinfo:
                invoke_bedrock_claude("Test prompt", model_id)
            assert "ValidationException" in str(excinfo.value)
            assert "Invalid request" in str(excinfo.value)

# Tests for the invoke_bedrock_nova function
class TestInvokeBedrockNova:
    def test_invoke_bedrock_nova_success(self, bedrock_runtime_stubber, sts_stubber, mock_db_functions):
        model_id = "amazon.nova-pro-v1:0"
        sts_stubber.add_response(
            'get_caller_identity',
            {'Account': '123456789012', 'UserId': 'AROAEXAMPLE', 'Arn': 'arn:aws:iam::123456789012:role/test-role'},
            {}
        )
        
        expected_params = {
            'modelId': f"arn:aws:bedrock:us-east-1::foundation-model/{model_id}",
            'body': json.dumps({
                "schemaVersion": "messages-v1",
                "messages": [{"role": "user", "content": [{"text": "What is the capital of France?"}]}],
                "system": [{"text": "You are an AI assistant providing clear and accurate responses."}]
            })
        }
        
        response = create_mock_response({
            "output": {
                "message": {
                    "content": [{"text": "This is Nova's response"}]
                }
            }
        })
        bedrock_runtime_stubber.add_response('invoke_model', response, expected_params)
        
        with patch('function.llms.bedrock_invoke.create_bedrock_client', return_value=bedrock_runtime_stubber.client), \
             patch('boto3.client', return_value=sts_stubber.client), \
             patch('function.llms.bedrock_invoke.get_model_region', return_value=("us-east-1", "us")), \
             patch('function.llms.bedrock_invoke.is_inference_model', return_value=False), \
             patch('function.llms.bedrock_invoke.get_model_by_id', return_value=MockModel(
                 identifier=model_id,
                 provider="Amazon",
                 region="us-east-1",
                 region_suffix="us",
                 max_input_tokens=4096
             )), \
             patch('function.llms.bedrock_invoke.get_caller_identity', return_value='123456789012'):
            result = invoke_bedrock_nova("What is the capital of France?", model_id)
            assert result == "This is Nova's response"

    @pytest.mark.asyncio
    async def test_invoke_bedrock_nova_async(self, bedrock_runtime_stubber, sts_stubber, mock_db_functions):
        model_id = "amazon.nova-pro-v1:0"
        sts_stubber.add_response(
            'get_caller_identity',
            {'Account': '123456789012', 'UserId': 'AROAEXAMPLE', 'Arn': 'arn:aws:iam::123456789012:role/test-role'},
            {}
        )
        
        expected_params = {
            'modelId': f"arn:aws:bedrock:us-east-1::foundation-model/{model_id}",
            'body': json.dumps({
                "schemaVersion": "messages-v1",
                "messages": [{"role": "user", "content": [{"text": "What is the capital of France?"}]}],
                "system": [{"text": "You are an AI assistant providing clear and accurate responses."}]
            })
        }
        
        response = create_mock_response({
            "output": {
                "message": {
                    "content": [{"text": "Async Nova response"}]
                }
            }
        })
        bedrock_runtime_stubber.add_response('invoke_model', response, expected_params)
        
        async def mock_to_thread(func, *args, **kwargs):
            return func(*args, **kwargs)
            
        with patch('function.llms.bedrock_invoke.create_bedrock_client', return_value=bedrock_runtime_stubber.client), \
             patch('boto3.client', return_value=sts_stubber.client), \
             patch('function.llms.bedrock_invoke.get_model_region', return_value=("us-east-1", "us")), \
             patch('function.llms.bedrock_invoke.is_inference_model', return_value=False), \
             patch('function.llms.bedrock_invoke.get_model_by_id', return_value=MockModel(
                 identifier=model_id,
                 provider="Amazon",
                 region="us-east-1",
                 region_suffix="us",
                 max_input_tokens=4096
             )), \
             patch('function.llms.bedrock_invoke.get_caller_identity', return_value='123456789012'), \
             patch('asyncio.to_thread', side_effect=mock_to_thread):
            result = await invoke_bedrock_nova_async("What is the capital of France?", model_id)
            assert result == "Async Nova response"

# Tests for the invoke_bedrock_meta function
class TestInvokeBedrockMeta:
    def test_invoke_bedrock_meta_success(self, bedrock_runtime_stubber, sts_stubber, mock_db_functions):
        model_id = "meta.llama-3-70b-instruct-v1:0"
        sts_stubber.add_response(
            'get_caller_identity',
            {'Account': '123456789012', 'UserId': 'AROAEXAMPLE', 'Arn': 'arn:aws:iam::123456789012:role/test-role'},
            {}
        )
        
        expected_params = {
            'modelId': f"arn:aws:bedrock:us-east-1::foundation-model/{model_id}",
            'contentType': APPLICATION_JSON,
            'accept': APPLICATION_JSON,
            'body': json.dumps({
                "prompt": f"""<|begin_of_text|><|start_header_id|>user<|end_header_id|>
        What is the capital of France?
        <|eot_id|>
        <|start_header_id|>assistant<|end_header_id|>
    """,
                "max_gen_len": 4096,
                "temperature": 0.7
            })
        }
        
        response = create_mock_response({
            "generation": "This is Meta's response"
        })
        bedrock_runtime_stubber.add_response('invoke_model', response, expected_params)
        
        with patch('function.llms.bedrock_invoke.create_bedrock_client', return_value=bedrock_runtime_stubber.client), \
             patch('function.llms.bedrock_invoke.get_caller_identity', return_value='123456789012'), \
             patch('function.llms.bedrock_invoke.get_model_region', return_value=("us-east-1", "meta")), \
             patch('function.llms.bedrock_invoke.is_inference_model', return_value=False):
            result = invoke_bedrock_meta("What is the capital of France?", model_id)
            assert result == "This is Meta's response"

    @pytest.mark.asyncio
    async def test_invoke_bedrock_meta_async(self, bedrock_runtime_stubber, sts_stubber, mock_db_functions):
        model_id = "meta.llama-3-70b-instruct-v1:0"
        sts_stubber.add_response(
            'get_caller_identity',
            {'Account': '123456789012', 'UserId': 'AROAEXAMPLE', 'Arn': 'arn:aws:iam::123456789012:role/test-role'},
            {}
        )
        
        expected_params = {
            'modelId': f"arn:aws:bedrock:us-east-1::foundation-model/{model_id}",
            'contentType': APPLICATION_JSON,
            'accept': APPLICATION_JSON,
            'body': json.dumps({
                "prompt": f"""<|begin_of_text|><|start_header_id|>user<|end_header_id|>
        What is the capital of France?
        <|eot_id|>
        <|start_header_id|>assistant<|end_header_id|>
    """,
                "max_gen_len": 4096,
                "temperature": 0.7
            })
        }
        
        response = create_mock_response({
            "generation": "Async Meta response"
        })
        bedrock_runtime_stubber.add_response('invoke_model', response, expected_params)
        
        async def mock_to_thread(func, *args, **kwargs):
            return func(*args, **kwargs)
            
        with patch('function.llms.bedrock_invoke.create_bedrock_client', return_value=bedrock_runtime_stubber.client), \
             patch('function.llms.bedrock_invoke.get_caller_identity', return_value='123456789012'), \
             patch('function.llms.bedrock_invoke.get_model_region', return_value=("us-east-1", "meta")), \
             patch('function.llms.bedrock_invoke.is_inference_model', return_value=False), \
             patch('asyncio.to_thread', side_effect=mock_to_thread):
            result = await invoke_bedrock_meta_async("What is the capital of France?", model_id)
            assert result == "Async Meta response"

# Tests for the invoke_bedrock_model function
class TestInvokeBedrockModel:
    @pytest.mark.asyncio
    async def test_invoke_bedrock_model_claude(self, mock_db_functions):
        with patch('function.llms.bedrock_invoke.invoke_bedrock_claude_async', return_value="Claude response") as mock_claude:
            result = await invoke_bedrock_model("What is the capital of France?", "anthropic.claude-3-5-sonnet-20240620-v1:0")
            mock_claude.assert_called_once_with("What is the capital of France?", "anthropic.claude-3-5-sonnet-20240620-v1:0")
            assert result == "Claude response"
    
    @pytest.mark.asyncio
    async def test_invoke_bedrock_model_nova(self, mock_db_functions):
        with patch('function.llms.bedrock_invoke.invoke_bedrock_nova_async', return_value="Nova response") as mock_nova:
            result = await invoke_bedrock_model("What is the capital of France?", "amazon.nova-pro-v1:0")
            mock_nova.assert_called_once_with("What is the capital of France?", "amazon.nova-pro-v1:0")
            assert result == "Nova response"
    
    @pytest.mark.asyncio
    async def test_invoke_bedrock_model_meta(self, mock_db_functions):
        with patch('function.llms.bedrock_invoke.invoke_bedrock_meta_async', return_value="Meta response") as mock_meta:
            result = await invoke_bedrock_model("What is the capital of France?", "meta.llama-3-70b-instruct-v1:0")
            mock_meta.assert_called_once_with("What is the capital of France?", "meta.llama-3-70b-instruct-v1:0")
            assert result == "Meta response"
    
    @pytest.mark.asyncio
    async def test_invoke_bedrock_model_default(self, mock_db_functions):
        with patch('function.llms.bedrock_invoke.invoke_bedrock_claude_async', return_value="Default Claude response") as mock_claude:
            result = await invoke_bedrock_model("What is the capital of France?")
            mock_claude.assert_called_once_with("What is the capital of France?", "anthropic.claude-3-5-sonnet-20240620-v1:0")
            assert result == "Default Claude response"

# Tests for the retrieve_and_generate function
class TestRetrieveAndGenerate:
    def test_retrieve_and_generate_success(self, bedrock_agent_runtime_stubber, sts_stubber):
        kb_id = "AB1C2DE3FG"
        prompt = "What is the capital of France?"
        session_id = "existing-session-id"
        
        retrieve_expected_params = {
            'input': {'text': prompt},
            'retrieveAndGenerateConfiguration': {
                'type': 'KNOWLEDGE_BASE',
                'knowledgeBaseConfiguration': {
                    'knowledgeBaseId': kb_id,
                    'modelArn': 'arn:aws:bedrock:eu-central-1::foundation-model/anthropic.claude-3-5-sonnet-20240620-v1:0',
                    'retrievalConfiguration': {
                        'vectorSearchConfiguration': {
                            'numberOfResults': 12,
                            'overrideSearchType': "SEMANTIC"
                        }
                    },
                    'generationConfiguration': {
                        'inferenceConfig': {
                            'textInferenceConfig': {
                                'temperature': 0.5
                            }
                        }
                    }
                }
            },
            'sessionId': session_id
        }
        
        retrieve_response = {
            'sessionId': 'test-session-id',
            'output': {'text': 'This is the generated answer'},
            'citations': [
                {
                    'retrievedReferences': [
                        {
                            'content': {'text': 'Reference content 1'},
                            'metadata': {
                                'x-amz-bedrock-kb-source-uri': 'file1.pdf',
                                'x-amz-bedrock-kb-document-page-number': '5'
                            }
                        }
                    ]
                }
            ]
        }
        
        bedrock_agent_runtime_stubber.add_response('retrieve_and_generate', retrieve_response, retrieve_expected_params)
        
        with patch('function.llms.bedrock_invoke.get_caller_identity', return_value='123456789012'), \
             patch('function.llms.bedrock_invoke.get_default_model_ids', 
                   return_value={"claude": "anthropic.claude-3-5-sonnet-20240620-v1:0"}), \
             patch('function.llms.bedrock_invoke.get_model_region',
                   return_value=("eu-central-1", "eu")), \
             patch('function.llms.bedrock_invoke.is_inference_model', return_value=False), \
             patch('boto3.client', return_value=bedrock_agent_runtime_stubber.client):
            
            with bedrock_agent_runtime_stubber:
                result = retrieve_and_generate(
                    prompt=prompt,
                    kb_id=kb_id,
                    session_id=session_id
                )
                
                assert result["text"] == "This is the generated answer"
                assert result["session_id"] == "test-session-id"
                assert len(result["contexts"]) == 1
                assert result["contexts"][0]["text"] == "Reference content 1"
                assert result["contexts"][0]["document_name"] == "file1.pdf"
                assert result["contexts"][0]["page_number"] == "5"
    
    def test_retrieve_and_generate_empty_response(self, bedrock_agent_runtime_stubber, sts_stubber):
        kb_id = "AB1C2DE3FG"
        prompt = "What is the capital of France?"
        
        retrieve_expected_params = {
            'input': {'text': prompt},
            'retrieveAndGenerateConfiguration': {
                'type': 'KNOWLEDGE_BASE',
                'knowledgeBaseConfiguration': {
                    'knowledgeBaseId': kb_id,
                    'modelArn': 'arn:aws:bedrock:eu-central-1::foundation-model/anthropic.claude-3-5-sonnet-20240620-v1:0',
                    'retrievalConfiguration': {
                        'vectorSearchConfiguration': {
                            'numberOfResults': 12,
                            'overrideSearchType': "SEMANTIC"
                        }
                    },
                    'generationConfiguration': {
                        'inferenceConfig': {
                            'textInferenceConfig': {
                                'temperature': 0.5
                            }
                        }
                    }
                }
            }
        }
        
        retrieve_response = {
            'sessionId': 'test-session-id',
            'output': {'text': ''},
            'citations': []
        }
        
        bedrock_agent_runtime_stubber.add_response('retrieve_and_generate', retrieve_response, retrieve_expected_params)
        
        with patch('function.llms.bedrock_invoke.get_caller_identity', return_value='123456789012'), \
             patch('function.llms.bedrock_invoke.get_default_model_ids', 
                   return_value={"claude": "anthropic.claude-3-5-sonnet-20240620-v1:0"}), \
             patch('function.llms.bedrock_invoke.get_model_region',
                   return_value=("eu-central-1", "eu")), \
             patch('function.llms.bedrock_invoke.is_inference_model', return_value=False), \
             patch('boto3.client', return_value=bedrock_agent_runtime_stubber.client):
            
            with bedrock_agent_runtime_stubber:
                with pytest.raises(ValueError) as excinfo:
                    retrieve_and_generate(
                        prompt=prompt,
                        kb_id=kb_id
                    )
                assert "Unable to generate response" in str(excinfo.value)
    
    def test_retrieve_and_generate_claude_error_response(self, bedrock_agent_runtime_stubber, sts_stubber):
        kb_id = "AB1C2DE3FG"
        prompt = "What is the capital of France?"
        
        retrieve_expected_params = {
            'input': {'text': prompt},
            'retrieveAndGenerateConfiguration': {
                'type': 'KNOWLEDGE_BASE',
                'knowledgeBaseConfiguration': {
                    'knowledgeBaseId': kb_id,
                    'modelArn': 'arn:aws:bedrock:eu-central-1::foundation-model/anthropic.claude-3-5-sonnet-20240620-v1:0',
                    'retrievalConfiguration': {
                        'vectorSearchConfiguration': {
                            'numberOfResults': 12,
                            'overrideSearchType': "SEMANTIC"
                        }
                    },
                    'generationConfiguration': {
                        'inferenceConfig': {
                            'textInferenceConfig': {
                                'temperature': 0.5
                            }
                        }
                    }
                }
            }
        }
        
        retrieve_response = {
            'sessionId': 'test-session-id',
            'output': {'text': 'Sorry, I am unable to assist you with this request.'},
            'citations': []
        }
        
        bedrock_agent_runtime_stubber.add_response('retrieve_and_generate', retrieve_response, retrieve_expected_params)
        
        with patch('function.llms.bedrock_invoke.get_caller_identity', return_value='123456789012'), \
             patch('function.llms.bedrock_invoke.get_default_model_ids', 
                   return_value={"claude": "anthropic.claude-3-5-sonnet-20240620-v1:0"}), \
             patch('function.llms.bedrock_invoke.get_model_region',
                   return_value=("eu-central-1", "eu")), \
             patch('function.llms.bedrock_invoke.is_inference_model', return_value=False), \
             patch('boto3.client', return_value=bedrock_agent_runtime_stubber.client):
            
            with bedrock_agent_runtime_stubber:
                with pytest.raises(ValueError) as excinfo:
                    retrieve_and_generate(
                        prompt=prompt,
                        kb_id=kb_id
                    )
                assert "Unable to generate response" in str(excinfo.value)
    
    def test_retrieve_and_generate_api_error(self, bedrock_agent_runtime_stubber, sts_stubber):
        kb_id = "AB1C2DE3FG"
        prompt = "What is the capital of France?"
        
        retrieve_expected_params = {
            'input': {'text': prompt},
            'retrieveAndGenerateConfiguration': {
                'type': 'KNOWLEDGE_BASE',
                'knowledgeBaseConfiguration': {
                    'knowledgeBaseId': kb_id,
                    'modelArn': 'arn:aws:bedrock:eu-central-1::foundation-model/anthropic.claude-3-5-sonnet-20240620-v1:0',
                    'retrievalConfiguration': {
                        'vectorSearchConfiguration': {
                            'numberOfResults': 12,
                            'overrideSearchType': "SEMANTIC"
                        }
                    },
                    'generationConfiguration': {
                        'inferenceConfig': {
                            'textInferenceConfig': {
                                'temperature': 0.5
                            }
                        }
                    }
                }
            }
        }
        
        bedrock_agent_runtime_stubber.add_client_error(
            'retrieve_and_generate',
            service_error_code='BadRequestException',
            service_message='Invalid knowledge base ID',
            expected_params=retrieve_expected_params
        )
        
        with patch('function.llms.bedrock_invoke.get_caller_identity', return_value='123456789012'), \
             patch('function.llms.bedrock_invoke.get_default_model_ids', 
                   return_value={"claude": "anthropic.claude-3-5-sonnet-20240620-v1:0"}), \
             patch('function.llms.bedrock_invoke.get_model_region',
                   return_value=("eu-central-1", "eu")), \
             patch('function.llms.bedrock_invoke.is_inference_model', return_value=False), \
             patch('boto3.client', return_value=bedrock_agent_runtime_stubber.client):
            
            with bedrock_agent_runtime_stubber:
                with pytest.raises(ClientError) as excinfo:
                    retrieve_and_generate(
                        prompt=prompt,
                        kb_id=kb_id
                    )
                assert "Invalid knowledge base ID" in str(excinfo.value)