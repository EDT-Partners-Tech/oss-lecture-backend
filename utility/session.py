# © [2025] EDT&Partners. Licensed under CC BY 4.0.

from typing import Dict
from threading import local

from utility.aws_clients import secrets_client
from utility.ssm_parameter_store import SSMParameterStore

ssm_client = SSMParameterStore()

session_storage = local()
session_secret_arn = ssm_client.get_parameter("/lecture/global/SESSION_SECRET_ARN")
if not session_secret_arn:
    raise ValueError("SESSION_SECRET_ARN environment variable not set")

def get_session_secret_key() -> str:
    response = secrets_client.get_secret_value(SecretId=session_secret_arn)
    secret = response['SecretString']
    if 'SecretString' not in response:
        raise ValueError("SecretString not found in Secrets Manager response for session secret")
    return secret

def get_session_data(request_id: str) -> Dict:
    if not hasattr(session_storage, 'data'):
        session_storage.data = {}
    return session_storage.data.setdefault(request_id, {})

def set_session_data(request_id: str, key: str, value: str):
    data = get_session_data(request_id)
    data[key] = value
