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

import boto3
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

region_name = os.getenv('AWS_REGION_NAME')

# Initialize AWS session
session = boto3.Session(region_name=region_name)

# Initialize all AWS clients
sts_client = session.client('sts')
transcribe_client = session.client('transcribe')
s3_client = session.client('s3')
cognito_client = session.client('cognito-idp')
ses_client = session.client('ses')
bedrock_client = session.client('bedrock')
bedrock_runtime_client = session.client('bedrock-runtime')
bedrock_agent_client = session.client('bedrock-agent')
bedrock_agent_runtime_client = session.client('bedrock-agent-runtime')
opensearch_client = session.client('opensearchserverless')
sf_client = session.client('stepfunctions')
iam_client = session.client('iam')
translate_client = session.client('translate')
textract_client = session.client('textract')
polly_client = session.client('polly')
comprehend_client = session.client('comprehend')
secrets_client = session.client("secretsmanager")
ssm_client = session.client('ssm')

def get_caller_identity() -> str:
    response = sts_client.get_caller_identity()
    return response['Account'] 