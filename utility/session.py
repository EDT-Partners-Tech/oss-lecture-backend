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
