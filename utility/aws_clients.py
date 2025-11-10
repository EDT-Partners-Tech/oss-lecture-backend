# © [2025] EDT&Partners. Licensed under CC BY 4.0.

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