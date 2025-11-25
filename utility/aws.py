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

import json
import os
from datetime import datetime, timezone
import re
import uuid
import asyncio
from typing import List, Dict, Any
from tempfile import NamedTemporaryFile
from dotenv import load_dotenv
from botocore.exceptions import ClientError, NoCredentialsError
from fastapi import HTTPException, UploadFile
import langcodes
from sqlalchemy.orm import Session
import requests
from database.crud import create_user, get_course, update_course_field, update_course_questions
from function.llms.bedrock_invoke import retrieve_and_generate
from icecream import ic
from database.schemas import InviteConfirm, UserCreate
from utility.async_manager import AsyncManager
from utility.exceptions import StepFunctionExecutionError, StepFunctionTimeoutError
from utility.decorators import RetryWithExponentialBackoff
from io import BytesIO
import time
from utility.aws_clients import (
    sts_client, transcribe_client, s3_client, cognito_client, ses_client,
    bedrock_agent_client, bedrock_agent_runtime_client, bedrock_client,
    opensearch_client, sf_client, iam_client, translate_client, textract_client,
    polly_client, comprehend_client, secrets_client, get_caller_identity
)
from utility.parameter_store import ParameterStore

# Load environment variables
load_dotenv()

# Initialize parameter store and load parameters
parameter_store = ParameterStore()
parameters = parameter_store.load_parameters()

# Get bucket names from parameters
lecture_buckets = {
    'audio': parameter_store.get_parameter('AWS_S3_AUDIO_BUCKET_NAME'),
    'content': parameter_store.get_parameter('AWS_S3_CONTENT_BUCKET_NAME'),
    'podcast': parameter_store.get_parameter('AWS_S3_PODCAST_BUCKET_NAME'),
    'comparison': parameter_store.get_parameter('AWS_S3_COMPARISON_BUCKET_NAME')
}

# Get other configuration from parameters
region_name = parameter_store.get_parameter('AWS_REGION_NAME')
polly_speech_engine = parameter_store.get_parameter('AWS_POLLY_SPEECH_ENGINE', 'generative')
user_pool_id = parameter_store.get_parameter('COGNITO_USERPOOL_ID')
client_id = parameter_store.get_parameter('COGNITO_APP_CLIENT_ID')

def get_secret(secret_arn: str) -> str:
    response = secrets_client.get_secret_value(SecretId=secret_arn)
    return response['SecretString']

def get_caller_identity() -> str:
    response = sts_client.get_caller_identity()
    return response['Account']

def generate_text_translation(text: str, source_lang: str, target_lang: str) -> str:
    try:
        response = translate_client.translate_text(
            Text=text,
            SourceLanguageCode=source_lang,
            TargetLanguageCode=target_lang
        )
        return response['TranslatedText']
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to translate text: {str(e)}")

def generate_presigned_url(bucket: str, object_key: str, expiration: int = 3600) -> str:
    bucket_name = lecture_buckets[bucket]
    try:
        # Replace http(s):// with s3:// using regex
        object_key = re.sub(r'^https?://', 's3://', object_key)

        object_key = object_key.replace('.s3.amazonaws.com', '')
        clean_key = object_key.replace(f's3://{bucket_name}/', '')
        response = s3_client.generate_presigned_url(
            'get_object',
            Params={'Bucket': bucket_name, 'Key': clean_key},
            ExpiresIn=expiration
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to generate presigned URL: {str(e)}")
    
    return response

def create_s3_subdirectory(bucket_name: str, directory: str):
    try:
        s3_client.put_object(Bucket=bucket_name, Key=(directory))
    except NoCredentialsError:
        raise HTTPException(status_code=403, detail="S3 credentials are not available")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error creating S3 subdirectory: {str(e)}")

async def setup_s3_directory(course_id: str, s3_bucket: str):
    try:
        s3_directory = f"materials/{course_id}/"
        create_s3_subdirectory(s3_bucket, s3_directory)
        ic("S3 subdirectory created", s3_directory)
    except Exception as e:
        ic("Error creating S3 subdirectory", e)
        raise HTTPException(status_code=500, detail=f"Error creating S3 subdirectory: {str(e)}")


def upload_to_s3(bucket: str, file_path: str, object_name: str) -> str:
    bucket_name = lecture_buckets[bucket]

    ic(file_path, object_name, bucket_name)  # Log file_path, object_name, and bucket name for debugging

    if not isinstance(file_path, str) or not isinstance(object_name, str):
        raise TypeError(f"Expected string for file_path and object_name, got {type(file_path)} and {type(object_name)}")

    try:
        # Upload the file to S3
        s3_client.upload_file(file_path, bucket_name, object_name)
        ic("File uploaded successfully to S3")
        
        # Return the S3 URI of the uploaded file
        return f's3://{bucket_name}/{object_name}'

    except Exception as e:
        ic("S3 upload error", e)
        raise


async def delete_from_s3(bucket: str, s3_uri: str) -> None:
    bucket_name = lecture_buckets[bucket]
    try:
        object_key = s3_uri.replace(f's3://{bucket_name}/', '')
        s3_client.delete_object(Bucket=bucket_name, Key=object_key)
    except ClientError as e:
        raise HTTPException(status_code=500, detail=f"Failed to delete file from S3: {str(e)}")


async def synthesize_speech(text: str, voice_id: str, language_code: str) -> str:
    response = await asyncio.to_thread(
        polly_client.synthesize_speech,
        Text=text,
        VoiceId=voice_id,
        OutputFormat='mp3',
        LanguageCode=language_code,
        Engine=polly_speech_engine
    )
    
    with NamedTemporaryFile(delete=False, suffix=".mp3") as temp_audio_file:
        for chunk in response['AudioStream'].iter_chunks():
            temp_audio_file.write(chunk)
        temp_audio_file_path = temp_audio_file.name
    
    return temp_audio_file_path


async def get_polly_voices(language_code: str) -> List[str]:
    response = await asyncio.to_thread(
        polly_client.describe_voices,
        Engine=polly_speech_engine,
        LanguageCode=language_code
    )
    return [voice['Id'] for voice in response['Voices']]


def start_transcription(s3_uri: str, job_name: str, language_code: str) -> dict:
    response = transcribe_client.start_transcription_job(
        TranscriptionJobName=job_name,
        Media={'MediaFileUri': s3_uri},
        MediaFormat='mp3',
        LanguageCode=language_code
    )
    return response

async def fetch_transcription_job(job_name: str) -> dict:
    response = transcribe_client.get_transcription_job(TranscriptionJobName=job_name)
    return response['TranscriptionJob']

async def update_transcription_status(transcription, current_status: str) -> None:
    transcription.status = current_status
    if current_status == "COMPLETED":
        transcription.completed_at = datetime.now(timezone.utc)

async def fetch_and_save_transcript(transcription, transcript_uri: str, db: Session) -> None:
    transcript_response = requests.get(transcript_uri)
    if transcript_response.status_code == 200:
        transcript_json = transcript_response.json()
        transcription.transcription_text = transcript_json['results']['transcripts'][0]['transcript']
        db.commit()
    else:
        raise RuntimeError(f"Failed to fetch transcript: {transcript_response.status_code}")

def create_cognito_and_db_user(user: InviteConfirm, db: Session) -> str:
    try:
        response = cognito_client.admin_create_user(
            UserPoolId=user_pool_id,
            Username=user["email"],
            UserAttributes=[
                {"Name": "email", "Value": user["email"]},
                {"Name": "given_name", "Value": user["given_name"]},
                {"Name": "family_name", "Value": user["family_name"]},
                {"Name": "locale", "Value": user["locale"]},
                {"Name": "email_verified", "Value": "true"}
            ],
            MessageAction='SUPPRESS',
            DesiredDeliveryMediums=['EMAIL']
        )
        
        cognito_id = response['User']['Username']
        
        # Set the user's password
        cognito_client.admin_set_user_password(
            UserPoolId=user_pool_id,
            Username=user["email"],
            Password=user["password"],
            Permanent=True
        )
        
        # After successful Cognito user creation, add user to the DB
        user_data = UserCreate(
            cognito_id=cognito_id,
            name=user["given_name"] + ' ' + user["family_name"],
            email=user["email"],
            role=user["role"]
        )
        create_user(db, user_data)
        
        return "User created successfully. Password has been set."

    except ClientError as e:
        # Log the error and raise it
        print(f"Client error: {e}")
        raise e

    
    
def send_invite_email(email: str, invite_url: str, course_name: str) -> None:
    try:
        # The email body with the invite code embedded in the URL
        body_html = f"""
        <html>
        <head></head>
        <body>
          <h1>You have been invited to join the course: {course_name}</h1>
          <p>Please click the link below to confirm your invitation:</p>
          <p><a href="{invite_url}">Confirm Invitation</a></p>
        </body>
        </html>
        """

        # Send the email
        response = ses_client.send_email(
            Source="mkhaled@edtpartners.com",
            Destination={
                "ToAddresses": [email],
            },
            Message={
                "Subject": {
                    "Data": f"Invitation to join {course_name}",
                    "Charset": "UTF-8"
                },
                "Body": {
                    "Html": {
                        "Data": body_html,
                        "Charset": "UTF-8"
                    }
                }
            }
        )

        print(f"Invite email sent! Message ID: {response['MessageId']}")

    except ClientError as e:
        print(f"Error sending invite email: {str(e)}")
        raise

@RetryWithExponentialBackoff(max_retries=5, initial_delay=1, max_delay=32)
async def generate_course_summary(db: Session, course_id: str, knowledge_base_id: str):
    try:
        model_id='anthropic.claude-3-7-sonnet-20250219-v1:0'
        prompt="""Human: You are a teacher writing a course description, and output it between the <summary_output> tags.
        
        Based on the search results provided, generate a concise summary of the course materials based on the following instructions:
        
        <instructions>
            - The summary should be in the same language as the search results
            - The summary should be clear, concise, and relevant to the course content
            - The summary should not contain any irrelevant or shallow information
        </instructions>

        <search_results>
        $search_results$
        </search_results>
        
        <summary_output>
        
        </summary_output>
                    
        Assistant:
        """
        text_input = "Please generate a summary of the course materials."
        
        # Execute the synchronous retrieve_and_generate function in a thread pool
        response = await asyncio.to_thread(
            retrieve_and_generate,
            prompt=prompt,
            kb_id=knowledge_base_id,
            model_id=model_id,
            text_input=text_input
        )
        ic(response)
        # Extract text between summary_output tags
        response_text = response.get("text", "")
        start_tag = "<summary_output>"
        end_tag = "</summary_output>"
        start_idx = response_text.find(start_tag) + len(start_tag)
        end_idx = response_text.find(end_tag)
        
        if start_idx >= 0 and end_idx >= 0:
            summary = response_text[start_idx:end_idx].strip()
        else:
            summary = response_text
        
        # Step 2: Update the course description in the database
        update_course_field(db, course_id, "description", summary)
        
        return summary
        
    except Exception as e:
        if isinstance(e, ClientError) and e.response['Error']['Code'] == 'ThrottlingException':
            raise  # Let the decorator handle the retry
        print(f"Error generating course summary: {e}")
        raise

@RetryWithExponentialBackoff(max_retries=5, initial_delay=1, max_delay=32)
async def generate_course_questions(db: Session, course_id: str, knowledge_base_id: str):
    try:
        model_id='anthropic.claude-3-7-sonnet-20250219-v1:0'
        prompt = """Human: You are a teacher writing questions for a course, and output them between the <questions_output> tags.
        
        Based on the search results provided, generate 5 questions based on the following instructions:
        <instructions>
            - The questions should be in the same language as the search results, the questions should be:
            - The questions should be based on the content of the search results, ignoring questions about course syllabus, course structure, or course requirements
            - The questions should be in the form of a question, not a statement, and end with a question mark
            - The questions should be clear and concise, and not contain any irrelevant or shallow information
        </instructions>
            
        <search_results>
        $search_results$
        </search_results>
        
        <questions_output>
        
        </questions_output>
            
        Assistant:
        """
        text_input = "Please generate questions related to the course content."
        
        # Execute the synchronous retrieve_and_generate function in a thread pool
        response = await asyncio.to_thread(
            retrieve_and_generate,
            prompt=prompt,
            kb_id=knowledge_base_id,
            model_id=model_id,
            text_input=text_input
        )
        ic(response)
        
        response_text = response.get("text", "")
        
        # Extract content between tags if they exist
        start_tag = "<questions_output>"
        end_tag = "</questions_output>"
        start_idx = response_text.find(start_tag) + len(start_tag)
        end_idx = response_text.find(end_tag)
        
        if start_idx >= 0 and end_idx >= 0:
            questions_text = response_text[start_idx:end_idx].strip()
        else:
            questions_text = response_text.strip()
            
        # Split text into lines and clean up each question
        raw_questions = [q.strip() for q in questions_text.split('\n') if q.strip()]
        questions = []
        
        for q in raw_questions:
            # Remove numbering and leading characters
            q = re.sub(r'^\d+[\.\)-]\s*', '', q.strip())
            q = re.sub(r'^[-•]\s*', '', q.strip())
            
            # Remove any HTML tags
            q = re.sub(r'<[^>]+>', '', q)
            
            # Ensure it's a proper question
            if q and not q.endswith('?'):
                q += '?'
            
            if q and len(q) > 5:  # Basic validation to ensure it's a real question
                questions.append(q)
        
        # Limit to 5 questions and remove duplicates while preserving order
        seen = set()
        questions = [q for q in questions if not (q in seen or seen.add(q))][:5]
        
        if not questions:
            raise ValueError("No valid questions were generated")
            
        ic(questions)
        
        update_course_questions(db, course_id, questions)
        return questions
        
    except Exception as e:
        if isinstance(e, ClientError) and e.response['Error']['Code'] == 'ThrottlingException':
            raise  # Let the decorator handle the retry
        print(f"Error generating course questions: {e}")
        raise

async def get_ingestion_summary(knowledge_base_id: str, data_source_id: str, ingestion_job_id: str):
    # For each ingestion job, check the status
    try:
        response = bedrock_agent_client.get_ingestion_job(
            knowledgeBaseId=knowledge_base_id,
            dataSourceId=data_source_id,
            ingestionJobId=ingestion_job_id
        )
        return response.get("ingestionJob", {})
    except Exception as e:
        print(f"Error getting ingestion job status: {e}")
        raise

async def start_ingestion_job(knowledge_base_id: str, data_source_id: str):
    try:
        # Client token ensures idempotency for job requests
        client_token = str(uuid.uuid4())

        # Call the ingestion job API
        response = bedrock_agent_client.start_ingestion_job(
            clientToken=client_token,
            dataSourceId=data_source_id,
            knowledgeBaseId=knowledge_base_id,
            description="Ingesting data for knowledge base synchronization"
        )
        ic("Ingestion job started", response)
        return response.get("ingestionJob")

    except Exception as e:
        ic("Error starting ingestion job", e)
        raise HTTPException(status_code=500, detail=f"Error starting ingestion job: {str(e)}")

async def run_preprocessing_job(input_data: dict) -> dict:
    try:
        # Start the Step Functions execution
        account_number = get_caller_identity()
        state_machine_arn = f"arn:aws:states:{region_name}:{account_number}:stateMachine:TestPreprocessingTranscriptions"
        response = sf_client.start_execution(
            stateMachineArn=state_machine_arn,
            input=json.dumps(input_data)
        )
        execution_arn = response['executionArn']
        ic("Preprocessing execution started:", execution_arn)
        result = await wait_for_preprocessing_job(execution_arn, n_of_jobs=len(input_data['files']))
        ic("Preprocessing job completed:", result)
        return result
    except Exception as e:
        ic(f"Error while running preprocessing job: {e}")
        raise HTTPException(status_code=500, detail=f"Error running preprocessing job: {str(e)}")

async def wait_for_preprocessing_job(execution_arn: str, n_of_jobs: int, heartbeat_minutes: int = 5):
    # Heartbeat comes in minutes
    max_retries = heartbeat_minutes*4*n_of_jobs
    ic("Polling preprocessing step function for completion. Max retries:", max_retries)
    for _ in range(max_retries):
        # Poll each 15 seconds
        delay = 15
        try:
            response = get_execution_details(execution_arn)
            status = response['execution_status']
            if status == 'SUCCEEDED':
                return response['execution_output']
            elif status in ['FAILED', 'TIMED_OUT', 'ABORTED']:
                raise StepFunctionExecutionError()
            else:
                await asyncio.sleep(delay)
        except ClientError as e:
            error_code = e.response.get('Error', {}).get('Code', 'Unknown')
            error_message = e.response.get('Error', {}).get('Message', 'No message')
            raise StepFunctionExecutionError(f"AWS Error {error_code}: {error_message}")
    raise StepFunctionTimeoutError()

def _generate_resource_names(course_id: str):
    suffix = str(course_id).replace("-", "")[:8]
    truncated_course_id = str(course_id)[:13]
    return {
        'suffix': suffix,
        'truncated_course_id': truncated_course_id,
        'iam_policies': [
            f"AmazonBedrockFoundationModelPolicyForKnowledgeBase_{suffix}",
            f"AmazonBedrockS3PolicyForKnowledgeBase_{suffix}",
            f"AmazonBedrockKnowledgeBasePolicy_{suffix}",
            f"AmazonBedrockOSSPolicyForKnowledgeBase_{suffix}"
        ],
        'execution_role': f"AmazonBedrockExecutionRoleForKnowledgeBase_{suffix}",
        'encryption_policy': f"bedrock-rag-sp-{suffix}",
        'network_policy': f"bedrock-rag-np-{suffix}",
        'access_policy': f"bedrock-rag-ap-{suffix}",
        'vector_store': f"bedrock-rag-{truncated_course_id}",
        's3_directory': f"materials/{course_id}/"
    }

def _delete_data_sources(knowledge_base_id: str):
    try:
        response = bedrock_agent_client.list_data_sources(knowledgeBaseId=knowledge_base_id)
        for ds in response['dataSourceSummaries']:
            # First get the current data source configuration
            current_ds = bedrock_agent_client.get_data_source(
                knowledgeBaseId=knowledge_base_id,
                dataSourceId=ds["dataSourceId"]
            )
            
            # Update the data source with the correct parameters
            bedrock_agent_client.update_data_source(
                knowledgeBaseId=knowledge_base_id,
                dataSourceId=ds["dataSourceId"],
                dataDeletionPolicy='RETAIN',
                dataSourceConfiguration=current_ds['dataSource']['dataSourceConfiguration'],
                vectorIngestionConfiguration=current_ds['dataSource']['vectorIngestionConfiguration'],
                name=current_ds['dataSource']['name']
            )
            time.sleep(1)
            
            # Now delete the data source
            response = bedrock_agent_client.delete_data_source(
                dataSourceId=ds["dataSourceId"], 
                knowledgeBaseId=ds["knowledgeBaseId"]
            )
            ic(f"Data source deletion status: {response['status']} for data source: {response['dataSourceId']}")
    except Exception as e:
        ic(f"Error deleting data sources: {e}")
        raise

def _delete_iam_resources(execution_role: str, iam_policies: list):
    try:
        # Detach admin policy
        try:
            iam_client.detach_role_policy(
                RoleName=execution_role, 
                PolicyArn="arn:aws:iam::aws:policy/AdministratorAccess"
            )
        except ClientError as e:
            if e.response["Error"]["Code"] != "NoSuchEntity":
                raise e

        account_number = sts_client.get_caller_identity().get('Account')
        # Delete policies
        for policy_name in iam_policies:
            try:
                iam_client.detach_role_policy(
                    RoleName=execution_role,
                    PolicyArn=f"arn:aws:iam::{account_number}:policy/{policy_name}"
                )
                iam_client.delete_policy(
                    PolicyArn=f"arn:aws:iam::{account_number}:policy/{policy_name}"
                )
            except ClientError as e:
                if e.response["Error"]["Code"] != "NoSuchEntity":
                    raise e

        # Delete role
        response = iam_client.delete_role(RoleName=execution_role)
    except Exception as e:
        ic(f"Error during IAM cleanup: {e}")

def _delete_security_policies(resource_names: dict):
    for policy_name, policy_type in [
        (resource_names['encryption_policy'], "encryption"),
        (resource_names['network_policy'], "network"),
    ]:
        try:
            opensearch_client.delete_security_policy(name=policy_name, type=policy_type)
        except ClientError as e:
            if e.response["Error"]["Code"] != "ResourceNotFoundException":
                raise e

def _delete_access_policy(resource_names: dict):
    try:
        opensearch_client.delete_access_policy(
            name=resource_names['access_policy'], 
            type="data"
        )
    except ClientError as e:
        if e.response["Error"]["Code"] != "ResourceNotFoundException":
            raise e

def _find_collection(collection_name: str):
    next_token = None
    while True:
        list_params = {"nextToken": next_token} if next_token else {}
        response = opensearch_client.list_collections(**list_params)
        
        for collection in response.get("collectionSummaries", []):
            if collection.get("name") == collection_name:
                return collection
                
        next_token = response.get("nextToken")
        if not next_token:
            return None

def _wait_for_collection_status(collection_name: str):
    for _ in range(6):
        collection_details = opensearch_client.batch_get_collection(
            names=[collection_name]
        ).get("collectionDetails", [{}])[0]
        if collection_details.get("status") in ["ACTIVE", "FAILED"]:
            return collection_details
        time.sleep(10)
    return None

def _delete_opensearch_resources(resource_names: dict):
    # Delete security policies
    _delete_security_policies(resource_names)
    
    # Delete access policy
    _delete_access_policy(resource_names)
    
    # Delete collection
    collection = _find_collection(resource_names['vector_store'])
    if collection:
        collection_id = collection.get("id")
        collection_status = collection.get("status")
        
        if collection_status not in ["ACTIVE", "FAILED"]:
            collection_details = _wait_for_collection_status(resource_names['vector_store'])
            if not collection_details:
                return
                
        try:
            response = opensearch_client.delete_collection(id=collection_id)
            ic(f"OpenSearch collection deletion status: {response['deleteCollectionDetail']['status']} for collection: {response['deleteCollectionDetail']['name']}")
        except ClientError as e:
            if e.response["Error"]["Code"] != "ResourceNotFoundException":
                raise e

def _delete_knowledge_base(knowledge_base_id: str):
    try:
        response = bedrock_agent_client.delete_knowledge_base(knowledgeBaseId=knowledge_base_id)
        ic(f"Knowledge base deletion response: {response}")
    except ClientError as e:
        if e.response["Error"]["Code"] != "ResourceNotFoundException":
            raise e

def _delete_s3_directory(directory: str, bucket: str = lecture_buckets["content"]):
    try:
        print(f"Deleting S3 directory: {directory} in bucket: {bucket}")
        objects = s3_client.list_objects_v2(Bucket=bucket, Prefix=directory)
        if "Contents" in objects:
            delete_objects = [{"Key": obj["Key"]} for obj in objects["Contents"]]
            s3_client.delete_objects(Bucket=bucket, Delete={"Objects": delete_objects})
            ic(f"Deleted {len(delete_objects)} objects from S3 bucket {bucket} in directory {directory}")
    except ClientError as e:
        print(f"Delete S3 directory: Error deleting S3 directory: {e}")
        if e.response["Error"]["Code"] != "NoSuchBucket":
            raise e

def _handle_aws_error(e: ClientError, resource_type: str) -> None:
    error_code = e.response["Error"]["Code"]
    if error_code not in ["ResourceNotFoundException", "NoSuchEntity", "NoSuchBucket"]:
        raise HTTPException(status_code=500, detail=f"Failed to delete {resource_type}: {str(e)}")

async def delete_resources(db: Session, course_id: str):
    try:
        resource_names = _generate_resource_names(course_id)
        course = get_course(db, course_id)
        if not course:
            raise HTTPException(status_code=404, detail=f"Course not found with ID {course_id}")
            
        knowledge_base_id = course.knowledge_base_id
        
        # Delete data sources
        if knowledge_base_id:
            try:
                _delete_data_sources(knowledge_base_id)
            except ClientError as e:
                _handle_aws_error(e, "data sources")

        # Delete IAM resources
        try:
            _delete_iam_resources(resource_names['execution_role'], resource_names['iam_policies'])
        except ClientError as e:
            _handle_aws_error(e, "IAM resources")

        # Delete OpenSearch resources
        try:
            _delete_opensearch_resources(resource_names)
        except ClientError as e:
            _handle_aws_error(e, "OpenSearch resources")

        # Delete knowledge base
        if knowledge_base_id:
            try:
                _delete_knowledge_base(knowledge_base_id)
            except ClientError as e:
                _handle_aws_error(e, "knowledge base")

        # Delete S3 directory
        try:
            _delete_s3_directory(resource_names['s3_directory'])
        except ClientError as e:
            _handle_aws_error(e, "S3 directory")
        
        ic("Resource cleanup completed successfully.")
        return {"status": "success", "message": "All resources deleted successfully"}
        
    except HTTPException:
        raise
    except Exception as e:
        ic(f"Unexpected error during resource cleanup for course_id {course_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Unexpected error during resource cleanup: {str(e)}")

def get_ingestion_job_status(job_id: str, knowledge_base_id: str, data_source_id: str):
    try:
        response = bedrock_agent_client.get_ingestion_job(
            knowledgeBaseId=knowledge_base_id,
            dataSourceId=data_source_id,
            ingestionJobId=job_id
        )
        return response.get("status")
    except Exception as e:
        print(f"Error getting ingestion job status: {e}")
        raise

def start_step_function(input_data):
    try:
        # Start the Step Functions execution
        account_number = sts_client.get_caller_identity().get('Account')
        state_machine_arn = f"arn:aws:states:{region_name}:{account_number}:stateMachine:CreateKnowledgeBaseInfrastructure"
        response = sf_client.start_execution(
            stateMachineArn=state_machine_arn,
            input=json.dumps(input_data)
        )
                
        return response
    except Exception as e:
        print(f"Error starting execution: {e}")
        return None


def get_execution_details(execution_arn):
    """
    Retrieve details about the current state in a Step Functions execution:
    - Name of the current state
    - Status of the state machine (running, succeeded, etc.)
    - Output data (if available)
    """
    try:
        # Fetch execution status
        execution_status = sf_client.describe_execution(executionArn=execution_arn)
        overall_status = execution_status['status']

        # Parse output if the execution is completed
        output = None
        if overall_status == 'SUCCEEDED':
            output = json.loads(execution_status.get('output', '{}'))

        # Fetch execution history to get state details
        execution_history = sf_client.get_execution_history(
            executionArn=execution_arn,
            maxResults=100,
            reverseOrder=True  # Get most recent events first
        )

        # Identify the most recent active state
        events = execution_history['events']
        current_state = None
        state_status = None
        for event in events:
            # Check for a state entering event
            if 'stateEnteredEventDetails' in event:
                current_state = event['stateEnteredEventDetails']['name']
                state_status = "IN_PROGRESS"
                break
            # If we see a state exiting event, update status
            elif 'stateExitedEventDetails' in event:
                current_state = event['stateExitedEventDetails']['name']
                state_status = "SUCCEEDED"
                break

        # Return all collected information
        return {
            "execution_status": overall_status,
            "current_state": current_state,
            "state_status": state_status,
            "execution_output": output,
        }

    except Exception as e:
        print(f"Error fetching execution details: {e}")
        raise e

def extract_text_from_image(image_bytes: BytesIO) -> str:
    try:
        # Call Amazon Textract
        response = textract_client.detect_document_text(
            Document={
                'Bytes': image_bytes.getvalue()
            }
        )
        
        # Extract text from the response
        extracted_text = ""
        for item in response['Blocks']:
            if item['BlockType'] == 'LINE':
                extracted_text += item['Text'] + "\n"
                
        return extracted_text.strip()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to extract text from image: {str(e)}")

def detect_language(text: str) -> str:
    """
    Detects the dominant language of a given text using AWS Comprehend.
    
    Args:
        text (str): The input text to detect language for. Only first 30 words are used.
        
    Returns:
        str: The detected language name
        
    Raises:
        HTTPException: If language detection fails
    """
    
    text = " ".join(re.sub(r'[^a-zA-Z\s]', '', text).split()[:30])
    print(f"Detecting language for: {text}")
    try:
        response = comprehend_client.detect_dominant_language(Text=text)
        lang_code = response['Languages'][0]['LanguageCode']
        print(f"Detected language code: {lang_code}")
        lang_name = langcodes.Language.get(lang_code).display_name('en')
        print(f"Detected language: {lang_name}")
        return lang_name
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to detect language: {str(e)}")

async def upload_file_to_s3(bucket: str, file_path: str, object_name: str) -> str:
    # Check if bucket is a key in lecture_buckets, otherwise use it directly
    bucket_name = lecture_buckets.get(bucket, bucket)

    ic(file_path, object_name, bucket_name)  # Log file_path, object_name, and bucket name for debugging

    if not isinstance(file_path, str) or not isinstance(object_name, str):
        raise TypeError(f"Expected string for file_path and object_name, got {type(file_path)} and {type(object_name)}")

    try:
        # Upload the file to S3
        s3_client.upload_file(file_path, bucket_name, object_name)
        ic("File uploaded successfully to S3")
        
        # Return the S3 URI of the uploaded file
        return f's3://{bucket_name}/{object_name}'

    except Exception as e:
        ic("S3 upload error", e)
        raise

async def get_s3_object(s3_uri: str) -> bytes:
    try:
        bucket_name = s3_uri.split('/')[2]
        object_key = s3_uri.replace(f's3://{bucket_name}/', '')
        s3_data = s3_client.get_object(Bucket=bucket_name, Key=object_key)
        return s3_data
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get file from S3: {str(e)}")


async def get_s3_buckets() -> list:
    """
    Returns a list of available S3 bucket names by querying AWS S3 directly.
    
    Returns:
        list: A list of bucket names that the authenticated user has access to
    """
    try:
        response = s3_client.list_buckets()
        return [bucket['Name'] for bucket in response['Buckets']]
    except Exception as e:
        raise Exception(f"Failed to fetch S3 buckets: {str(e)}")


async def generate_file_translation(blob_file: UploadFile, source_lang: str, target_lang: str) -> str:
    try:
        # blob_file to base64
        blob_file.file.seek(0)
        file_content = await blob_file.read()

        # Get the content type
        content_type = blob_file.content_type

        response = translate_client.translate_document(
            Document={
                'Content': file_content,
                'ContentType': content_type
            },
            SourceLanguageCode=source_lang,
            TargetLanguageCode=target_lang
        )
        
        return response['TranslatedDocument']['Content']
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to translate file: {str(e)}")

# Extract text from image with AWS Textract
def extract_text_from_image_with_textract(img_path: str) -> str:
    with open(img_path, "rb") as image:
        response = textract_client.detect_document_text(
            Document={'Bytes': image.read()}
        )

    # Create a return with the format of the response of reader.readtext(img)
    text = ""
    for item in response['Blocks']:
        if item['BlockType'] == 'LINE':
            text += item['Text'] + " "
    return text.strip()

# Invoke AWS Bedrock agent
def invoke_bedrock_agent(
    agent_id: str, 
    agent_alias_id: str, 
    input_text: str, 
    session_id: str,
    files: List[Dict[str, Any]] = None,
    conversation_history: Dict[str, Any] = None,
    memory_id: str = None,
    stream: bool = False,
    invocationId: str = None,
    returnControlInvocationResults: List[Dict[str, Any]] = None
) -> dict:
    """
    Invoke the Bedrock agent with support for S3 files.
    
    Args:
        agent_id: Agent ID
        agent_alias_id: Agent alias ID
        input_text: Input text
        session_id: Session ID
        files: List of S3 files in the format:
            [
                {
                    "name": str,
                    "source": {
                        "s3Location": {
                            "uri": str
                        },
                        "sourceType": "S3"
                    },
                    "useCase": "CHAT"
                }
            ]
    """
    session_state = {}
    if files:
        session_state["files"] = files
    
    if conversation_history:
        session_state["conversationHistory"] = conversation_history.get("conversationHistory", [])

    if invocationId:
        session_state["invocationId"] = invocationId

    if returnControlInvocationResults:
        session_state["returnControlInvocationResults"] = returnControlInvocationResults

    # Prepare the base parameters for the invocation
    invoke_params = {
        "agentId": agent_id,
        "agentAliasId": agent_alias_id,
        "inputText": input_text,
        "sessionId": session_id,
        "endSession": False,
        "streamingConfigurations": {
            "streamFinalResponse": stream
        }
    }
    
    # Add sessionState only if it exists
    if session_state:
        invoke_params["sessionState"] = session_state
    
    # Add memoryId only if it exists
    if memory_id:
        invoke_params["memoryId"] = memory_id
    
    # Invoke the agent with the configured parameters
    response = bedrock_agent_runtime_client.invoke_agent(**invoke_params)
    return response

async def get_app_sync_api_events():
    app_sync_settings = AsyncManager()
    app_sync_settings.set_parameters()
    return app_sync_settings.get_settings()

async def get_guardrails() -> None:
    guardrails = bedrock_client.list_guardrails()["guardrails"]
    detailed_guardrails = []

    for gr in guardrails:
        response = bedrock_client.get_guardrail(
            guardrailIdentifier=gr["id"],
            guardrailVersion=gr.get("version", "DRAFT")  # DRAFT is default if missing
        )
        
        # Extract relevant policies
        guardrail_info = {
            "name": gr["name"],
            "id": gr["id"],
            "status": gr["status"],
            "version": response["version"],
            "topicPolicy": response.get("topicPolicy", {}),
            "wordPolicy": response.get("wordPolicy", {}),
            "contentPolicy": response.get("contentPolicy", {}),
            "sensitiveInformationPolicy": response.get("sensitiveInformationPolicy", {}),
            "regexMatchPolicy": response.get("regexMatchPolicy", {}),
            "contextualGroundingPolicy": response.get("contextualGroundingPolicy", {}),
        }
        detailed_guardrails.append(guardrail_info)


    return detailed_guardrails