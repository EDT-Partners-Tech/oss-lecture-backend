# © [2025] EDT&Partners. Licensed under CC BY 4.0.

import os
import re
import json
import boto3
import asyncio
from requests import Session
import tiktoken
from fastapi import HTTPException
from botocore.client import Config
from botocore.exceptions import ClientError
from icecream import ic
from database.db import get_db
from database.crud import get_ai_models_by_filters, get_default_ai_model, save_analytics
from functools import lru_cache
from typing import Optional
from utility.parameter_store import ParameterStore
from utility.service import handle_save_request
from constants import RETRIEVE_AND_GENERATE_TEMPERATURE
from utility.aws_clients import get_caller_identity, bedrock_agent_runtime_client
APPLICATION_JSON = "application/json"
parameter_store = ParameterStore()
parameter_store.load_parameters()
AWS_REGION_NAME = parameter_store.get_parameter('AWS_REGION_NAME')

if not AWS_REGION_NAME:
    raise ValueError("AWS_REGION_NAME environment variable is not set.")

@lru_cache(maxsize=1)
def get_models():
    """Cache models data to avoid frequent DB queries"""
    db = next(get_db())
    models = {}
    
    # Query all models from database
    all_models = get_ai_models_by_filters(db)
    
    # Group models by provider
    for model in all_models:
        if model.provider.lower() not in models:
            models[model.provider.lower()] = {
                "models": [],
                "region": model.region.name,
                "region_suffix": model.region.suffix
            }
        models[model.provider.lower()]["models"].append(model.identifier)
        
        # Set default model for the provider if this model is default
        if model.is_default:
            models[model.provider.lower()]["default"] = model.identifier
            
    return models

@lru_cache(maxsize=1)
def get_model_by_id(id: str):
    """Cache model data by ID to avoid frequent DB queries"""
    db = next(get_db())
    model = get_ai_models_by_filters(db, identifier=id)

    return model[0] if isinstance(model, list) and model else model

@lru_cache(maxsize=1)
def get_inference_models():
    """Cache inference models list"""
    db = next(get_db())
    models = get_ai_models_by_filters(db, inference=True)
    return [model.identifier for model in models]

@lru_cache(maxsize=1)
def get_default_model_ids(region: str = AWS_REGION_NAME):
    """Cache default model IDs"""
    db = next(get_db())
    claude_default = get_default_ai_model(db, provider="Anthropic", region=region)
    nova_default = get_default_ai_model(db, provider="Amazon", region=region)
    meta_default = get_default_ai_model(db, provider="Meta", region=region)
    
    return {
        "claude": claude_default.identifier if claude_default else None,
        "nova": nova_default.identifier if nova_default else None,
        "meta": meta_default.identifier if meta_default else None
    }
       
def _check_prompt_length(model_id: str, prompt: str, max_tokens: int = None):
    """
    Check if the prompt length is within the model's token limit.
    
    Args:
        model_id: The ID of the model being used
        prompt: The input prompt to check
        max_tokens: Optional override for model's max tokens
    """
    encoding = tiktoken.get_encoding("cl100k_base")
    
    if not max_tokens:
        model = get_model_by_id(model_id)
        max_tokens = model.get("max_input_tokens", 4096)
    
    tokens = len(encoding.encode(prompt))
    if tokens >= 0.9 * max_tokens:
        raise HTTPException(
            status_code=400, 
            detail=f"Prompt is too long for the model (using {tokens} tokens, limit is {max_tokens}). The content overflows the input window size."
        )

# Replace the constants with functions
def get_model_region(model_id):
    models = get_models()
    for provider, details in models.items():
        if model_id in details["models"]:
            ic(f"Details: region: {details['region']}, region_suffix: {details['region_suffix']}")
            return details["region"], details["region_suffix"]
    return None, None

def is_inference_model(model_id):
    return model_id in get_inference_models()

def create_bedrock_client(region=AWS_REGION_NAME):
    return boto3.client("bedrock-runtime", region_name=region)

def invoke_bedrock_titan(input_data, temperature=0.3, top_p=1, max_tokens=1024):
    bedrock_client = create_bedrock_client()
    
    payload_body = {
        "inputText": input_data,
        "textGenerationConfig": {
            "topP": top_p,
            "temperature": temperature,
            "stopSequences": [],
            "maxTokenCount": max_tokens,
        },
    }
    params = {
        "modelId": "amazon.titan-text-express-v1",
        "contentType": APPLICATION_JSON,
        "accept": APPLICATION_JSON,
        "body": json.dumps(payload_body)
    }
    
    # Call the API
    response = bedrock_client.invoke_model(**params)
    response_body = json.loads(response.get("body").read())
    parsed_response = response_body.get("results", [{}])[0].get("outputText", "")
    
    return re.sub(r'<[^>]+>', '', re.sub(r'\n+', '\n', parsed_response))


async def invoke_bedrock_claude_async(prompt: str, model_id=None):
    if not model_id:
        model_id = get_default_model_ids()["claude"]
    return await asyncio.to_thread(invoke_bedrock_claude, prompt, model_id)


def invoke_bedrock_claude(prompt: str, model_id=None):
    if not model_id:
        model_id = get_default_model_ids()["claude"]
    account_id = get_caller_identity()
    region, suffix = get_model_region(model_id)
    bedrock_client = create_bedrock_client(region)
    
    # print(f"model_arn: {model_id}")
    model = get_model_by_id(model_id)
    
    if not model:
        raise ValueError(f"Model not found for ID: {model_id}")

    system_prompt = "You are an AI assistant focused on clarity, accuracy, and helpfulness."
    max_tokens = model.max_input_tokens if hasattr(model, 'max_input_tokens') else 4096
    
    # Guardrail against input tokens overflow
    _check_prompt_length(model_id, prompt, max_tokens)

    body = json.dumps({
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens": max_tokens,
        "system": system_prompt,
        "messages": [{"role": "user", "content": prompt}],
    })

    if is_inference_model(model_id):
        model_arn = f"arn:aws:bedrock:{region}:{account_id}:inference-profile/{suffix}.{model_id}"
    else:
        model_arn = f"arn:aws:bedrock:{region}::foundation-model/{model_id}"

    ic(f"model_arn: {model_arn}")

    try:
        response = bedrock_client.invoke_model(body=body, modelId=model_arn)
        response_body = json.loads(response.get("body").read())
        content = response_body.get("content", [])
        return content[0].get("text", "") if content else None
    except ClientError as e:
        message = e.response["Error"]["Message"]
        ic(f"A client error occurred: {message}")
        raise ClientError(e.response, e.operation_name) from e



async def invoke_bedrock_nova_async(prompt: str, model_id=None):
    if not model_id:
        model_id = get_default_model_ids()["nova"]
    return await asyncio.to_thread(invoke_bedrock_nova, prompt, model_id)


def invoke_bedrock_nova(prompt: str, model_id=None):
    if not model_id:
        model_id = get_default_model_ids()["nova"]
    account_id = get_caller_identity()
    region, suffix = get_model_region(model_id)
    bedrock_client = create_bedrock_client(region)

    print(f"account_id: {account_id}")
    print(f"region: {region}")
    print(f"suffix: {suffix}")
    
    system_prompt = [{"text": "You are an AI assistant providing clear and accurate responses."}]
    user_message = {"role": "user", "content": [{"text": prompt}]}
    messages = [user_message]

    body = json.dumps({"schemaVersion": "messages-v1", "messages": messages, "system": system_prompt})

    model = get_model_by_id(model_id)
    max_tokens = model.max_input_tokens if hasattr(model, 'max_input_tokens') else 4096

    # _check_prompt_length(model_id, prompt, max_tokens)

    if is_inference_model(model_id):
        model_arn = f"arn:aws:bedrock:{region}:{account_id}:inference-profile/{suffix}.{model_id}"
    else:
        model_arn = f"arn:aws:bedrock:{region}::foundation-model/{model_id}"

    
    ic(f"model_arn: {model_arn}")
    
    try:
        response = bedrock_client.invoke_model(body=body, modelId=f"{model_arn}")
        response_body = response.get("body")
        if not response_body:
            ic("Empty response body")
            return None
        json_str = response_body.read().decode("utf-8")
        response_data = json.loads(json_str)
        content = response_data.get("output", {}).get("message", {}).get("content", [])
        return content[0].get("text", "") if content else None
    except Exception as e:
        ic(f"Error invoking model: {e}")
        return None

async def invoke_bedrock_meta_async(prompt: str, model_id=None):
    if not model_id:
        model_id = get_default_model_ids()["meta"]
    return await asyncio.to_thread(invoke_bedrock_meta, prompt, model_id)

def invoke_bedrock_meta(prompt: str, model_id=None, temperature=0.7):
    if not model_id:
        model_id = get_default_model_ids()["meta"]
    account_id = get_caller_identity()
    region, suffix = get_model_region(model_id)
    bedrock_client = create_bedrock_client(region)
    
    model = get_model_by_id(model_id)
    max_tokens = model.max_input_tokens if hasattr(model, 'max_input_tokens') else 4096
    
    formatted_prompt = f"""<|begin_of_text|><|start_header_id|>user<|end_header_id|>
        {prompt}
        <|eot_id|>
        <|start_header_id|>assistant<|end_header_id|>
    """

    body = json.dumps({
        "prompt": formatted_prompt,
        "max_gen_len": max_tokens,
        "temperature": temperature,
    })

    _check_prompt_length(model_id, prompt, max_tokens)

    if is_inference_model(model_id):
        model_arn = f"arn:aws:bedrock:{region}:{account_id}:inference-profile/{suffix}.{model_id}"
    else:
        model_arn = f"arn:aws:bedrock:{region}::foundation-model/{model_id}"

    ic(f"model_arn: {model_arn}")
    
    try:
        response = bedrock_client.invoke_model(
            body=body,
            modelId=f"{model_arn}",
            accept=APPLICATION_JSON,
            contentType=APPLICATION_JSON
        )
        response_body = response.get("body")
        if not response_body:
            ic("Empty response body")
            return None
            
        json_str = response_body.read().decode("utf-8")
        response_data = json.loads(json_str)
        
        # Meta models return the response in the 'generation' field
        return response_data.get("generation", "")
    except Exception as e:
        ic(f"Error invoking model: {e}")
        return None

async def invoke_bedrock_model(prompt: str, model_id=None):
    if not model_id:
        model_id = get_default_model_ids()["claude"]

    if model_id.startswith("amazon"):
        return await invoke_bedrock_nova_async(prompt, model_id)
    elif model_id.startswith("anthropic"):
        return await invoke_bedrock_claude_async(prompt, model_id)
    elif model_id.startswith("meta"):
        return await invoke_bedrock_meta_async(prompt, model_id)

def _create_filter_conditions(custom_query: dict) -> dict:
    """Crea las condiciones de filtrado para la búsqueda vectorial."""
    first_key = list(custom_query.keys())[0]
    starts_with_conditions = []
    
    for key, value in custom_query.items():
        if isinstance(value, list):
            starts_with_conditions.extend([
                {"startsWith": {"key": key if key != "_general" else first_key, "value": val}}
                for val in value
            ])
        else:
            starts_with_conditions.append({
                "startsWith": {
                    "key": key if key != "_general" else first_key,
                    "value": value
                }
            })
    
    return starts_with_conditions[0] if len(starts_with_conditions) == 1 else {"orAll": starts_with_conditions}

def get_retrieve_config(prompt_template: str, model_arn: str, kb_id: str, text_input: str = "", files: list[str] = [], temperature: float = RETRIEVE_AND_GENERATE_TEMPERATURE, custom_query: dict = None):
    config = {
        "type": "KNOWLEDGE_BASE",
        "knowledgeBaseConfiguration": {
            "knowledgeBaseId": kb_id,
            "modelArn": model_arn,
            "retrievalConfiguration": {
                "vectorSearchConfiguration": {"numberOfResults": 12, "overrideSearchType": "SEMANTIC"},
            },
            "generationConfiguration": {
                "inferenceConfig": {
                    "textInferenceConfig": {
                        "temperature": temperature
                    }
                }
            }
        },
    }

    if custom_query:
        config["knowledgeBaseConfiguration"]["retrievalConfiguration"]["vectorSearchConfiguration"]["filter"] = _create_filter_conditions(custom_query)
    
    if text_input and prompt_template:
        config["knowledgeBaseConfiguration"]["generationConfiguration"] = {
            "promptTemplate": {"textPromptTemplate": prompt_template},
        }
    
    if files:
        config["knowledgeBaseConfiguration"]["retrievalConfiguration"]["vectorSearchConfiguration"]["filter"] = {
            "in": {"key": "x-amz-bedrock-kb-source-uri", "value": files},
        }
         
    return config

def retrieve_and_generate(prompt: str, kb_id: str, session_id: str = "", model_id=None, text_input: str = "", files: list[str] = [], not_block_error: bool = True, temperature: float = RETRIEVE_AND_GENERATE_TEMPERATURE, custom_query: dict = None):
    if not model_id:
        model_id = get_default_model_ids()["claude"]
    
    if not model_id.startswith("arn"):
        account_id = get_caller_identity()
        region, suffix = get_model_region(model_id)
        
        if is_inference_model(model_id):
            model_arn = f"arn:aws:bedrock:{region}:{account_id}:inference-profile/{suffix}.{model_id}"
        else:
            model_arn = f"arn:aws:bedrock:{region}::foundation-model/{model_id}"
        
        ic(f"model_arn: {model_arn}")
    else:
        model_arn = model_id
        
    input_prompt = {"text": text_input or prompt}
    retrieve_config = get_retrieve_config(prompt, model_arn, kb_id, text_input, files, temperature, custom_query)

    bedrock_config = Config(connect_timeout=300, read_timeout=300, retries={"max_attempts": 6})
    bedrock_agent_client = boto3.client("bedrock-agent-runtime", region_name=region, config=bedrock_config)
    
    response = bedrock_agent_client.retrieve_and_generate(
        input=input_prompt,
        retrieveAndGenerateConfiguration=retrieve_config,
        **({"sessionId": session_id} if session_id else {})
    )
    
    session_id = response.get("sessionId")
    raw_text = response.get("output", {}).get("text", "")
    
    if not_block_error and (not raw_text or raw_text == "Sorry, I am unable to assist you with this request."):
        raise ValueError("Unable to generate response.")
    
    citations = response.get("citations", [])
    contexts = [
        {
            "text": ref["content"]["text"],
            "document_name": ref["metadata"].get("x-amz-bedrock-kb-source-uri", ""),
            "page_number": ref["metadata"].get("x-amz-bedrock-kb-document-page-number", ""),
        }
        for citation in citations
        for ref in citation.get("retrievedReferences", [])
    ]
    
    return {"text": raw_text, "contexts": contexts, "session_id": session_id}

def _get_document_format(file_name: str) -> str:
    """Determine document format based on file extension."""
    format_mapping = {
        '.pdf': 'pdf',
        '.csv': 'csv',
        '.doc': 'doc',
        '.docx': 'docx',
        '.xls': 'xls',
        '.xlsx': 'xlsx',
        '.html': 'html',
        '.txt': 'txt',
        '.md': 'md'
    }
    return format_mapping.get(os.path.splitext(file_name)[1].lower())

def _create_file_attachment(file_path: str) -> Optional[dict]:
    """Create a file attachment dictionary for the message."""
    try:
        with open(file_path, 'rb') as file:
            file_content = file.read()
            file_name = os.path.basename(file_path)
            document_format = _get_document_format(file_name)
            
            if not document_format:
                return None
                
            return {
                "document": {
                    "format": document_format,
                    "name": os.path.splitext(file_name)[0],
                    "source": {"bytes": file_content}
                }
            }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error reading file {file_path}: {str(e)}")

def _process_attachments(files: list[str], prompt: str) -> list:
    """Process file attachments and create message content."""
    if not files:
        return [{"role": "user", "content": [{"text": prompt}]}]
        
    message_content = [{"text": prompt}]
    
    for file_path in files:
        attachment = _create_file_attachment(file_path)
        if attachment:
            message_content.append(attachment)
            
    return [{"role": "user", "content": message_content}]

def _extract_response_text(response_body: dict) -> Optional[str]:
    """Extract text content from the response body."""
    if not response_body or 'output' not in response_body:
        return None
        
    message = response_body['output'].get('message', {})
    content_list = message.get('content', [])
    
    for content_item in content_list:
        if 'text' in content_item:
            return content_item['text']
            
    return None

async def invoke_bedrock_claude_with_converse(
    db: Session,
    user_id: str,
    type: str,
    prompt: str,
    system_prompt: str = "",
    files: list[str] = [],
    model_name=None,
    save_tokens: bool = True
):
    if not model_name:
        model_name = get_default_model_ids()["claude"]
    account_id = get_caller_identity()
    region, suffix = get_model_region(model_name)
    bedrock_client = create_bedrock_client(region)
    
    # print(f"model_arn: {model_id}")
    model = get_model_by_id(model_name)
    
    if not model:
        raise ValueError(f"Model not found for ID: {model_name}")

    max_tokens = model.max_input_tokens if hasattr(model, 'max_input_tokens') else 4096
    
    # Guardrail against input tokens overflow
    _check_prompt_length(model_name, prompt, max_tokens)

    if is_inference_model(model_name):
        model_arn = f"arn:aws:bedrock:{region}:{account_id}:inference-profile/{suffix}.{model_name}"
    else:
        model_arn = f"arn:aws:bedrock:{region}::foundation-model/{model_name}"

    ic(f"model_arn: {model_arn}")
    
    # if not model_name:
    #     model_name = get_default_model_ids()["claude"]

    _check_prompt_length(model_name, prompt, max_tokens=max_tokens)
    
    messages = _process_attachments(files, prompt)

    try:
        response = await asyncio.to_thread(
            bedrock_client.converse,
            modelId=model_arn,
            messages=messages,
            system=[{"text": system_prompt}]
        )
        
        if save_tokens:
            request_id = str(handle_save_request(db=db, title=type, user_id=user_id, service_code="comparison_engine"))
            
        try:
            response_body = json.loads(response.get('body').read())
        except (json.JSONDecodeError, AttributeError):
            response_body = response
            
        return _extract_response_text(response_body)
        
    except ClientError as e:
        message = e.response["Error"]["Message"]
        ic(f"A client error occurred: {message}")
        raise ClientError(f"Error while invoking the Bedrock Model: {message}")