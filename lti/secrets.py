# © [2025] EDT&Partners. Licensed under CC BY 4.0.

from dataclasses import dataclass
from utility.aws_clients import secrets_client
from utility.ssm_parameter_store import SSMParameterStore

ssm_client = SSMParameterStore()

lti_encryption_secret_arn = ssm_client.get_parameter("/lecture/global/LTI_ENCRYPTION_SECRET_ARN")
if not lti_encryption_secret_arn:
    raise ValueError("LTI_ENCRYPTION_SECRET_ARN environment variable not set")

lti_session_secret_arn = ssm_client.get_parameter("/lecture/global/LTI_SESSION_SECRET_ARN")
if not lti_session_secret_arn:
    raise ValueError("LTI_SESSION_SECRET_ARN environment variable not set")

@dataclass
class LTISecrets:
    encryption_secret: str
    session_tokens_secret: str

def get_lti_secrets() -> LTISecrets:
    response = secrets_client.get_secret_value(SecretId=lti_encryption_secret_arn)
    encryption_secret = response['SecretString']
    if 'SecretString' not in response:
        raise ValueError("SecretString not found in Secrets Manager response for LTI encryption secret")
    response = secrets_client.get_secret_value(SecretId=lti_session_secret_arn)
    if 'SecretString' not in response:
        raise ValueError("SecretString not found in Secrets Manager response for LTI session secret")
    session_secret = response['SecretString']
    return LTISecrets(encryption_secret, session_secret)
