# © [2025] EDT&Partners. Licensed under CC BY 4.0.

import os
from typing import Dict, List
import boto3
from utility.aws_clients import textract_client, s3_client, bedrock_client

class AWSService:
    def __init__(self, region_name: str = None):
        self.s3_bucket = os.getenv('AWS_S3_CONTENT_BUCKET_NAME')
        self.s3_prefix = 'content_generator/'
        self.s3_client = s3_client
        self.textract_client = textract_client
        self.region_name = region_name or os.getenv("AWS_REGION_NAME", "eu-central-1")
        if region_name:
            session = boto3.Session(region_name=region_name)
            self.bedrock_client = session.client('bedrock')
        else:
            self.bedrock_client = bedrock_client

    def upload_file_to_s3(self, file_path: str, filename: str) -> str:
        """
        Uploads a local file to S3 and returns the S3 key.
        """
        s3_key = f"{self.s3_prefix}{filename}"
        self.s3_client.upload_file(file_path, self.s3_bucket, s3_key)
        return s3_key
    
    def get_file_from_s3(self, s3_key: str) -> str:
        """
        Gets a file from S3 and returns the file content.
        """
        response = self.s3_client.get_object(Bucket=self.s3_bucket, Key=s3_key)
        return response['Body'].read().decode('utf-8')

    def start_textract_analysis(self, s3_key: str) -> str:
        """
        Starts the Textract analysis and returns the job_id.
        """
        response = self.textract_client.start_document_analysis(
            DocumentLocation={
                'S3Object': {
                    'Bucket': self.s3_bucket,
                    'Name': s3_key
                }
            },
            FeatureTypes=["TABLES"]
        )
        return response['JobId']

    def get_textract_result(self, job_id: str) -> Dict:
        """
        Gets the result of the Textract analysis.
        """
        response = self.textract_client.get_document_analysis(JobId=job_id)
        return response

    def extract_all_from_textract(self, textract_response: Dict) -> Dict:
        """
        Extracts the correlated text and tables structure by page, maintaining the order of appearance.
        """
        blocks = textract_response.get('Blocks', [])
        block_map = {block['Id']: block for block in blocks}
        # Group blocks by page
        pages = {}
        for block in blocks:
            if 'Page' in block:
                page_num = block['Page']
                if page_num not in pages:
                    pages[page_num] = []
                pages[page_num].append(block)
        # Process each page
        aws_texttract_document = []
        for page_num in sorted(pages.keys()):
            page_blocks = pages[page_num]
            # Get the PAGE block for the order of the children
            page_block = next((b for b in page_blocks if b['BlockType'] == 'PAGE'), None)
            contents = []
            if page_block and 'Relationships' in page_block:
                for rel in page_block['Relationships']:
                    if rel['Type'] == 'CHILD':
                        for child_id in rel['Ids']:
                            child = block_map.get(child_id)
                            if not child:
                                print(f"Warning: child_id {child_id} not found in block_map")
                                continue
                            if child['BlockType'] == 'LINE':
                                contents.append({"text": child['Text']})
                            elif child['BlockType'] == 'TABLE':
                                # Extract the table as a matrix
                                cells = []
                                for trel in child.get('Relationships', []):
                                    if trel['Type'] == 'CHILD':
                                        cells = [block_map[cell_id] for cell_id in trel['Ids'] if cell_id in block_map and block_map[cell_id]['BlockType'] == 'CELL']
                                max_row = max((cell['RowIndex'] for cell in cells), default=0)
                                max_col = max((cell['ColumnIndex'] for cell in cells), default=0)
                                table_matrix = [['' for _ in range(max_col)] for _ in range(max_row)]
                                for cell in cells:
                                    row = cell['RowIndex'] - 1
                                    col = cell['ColumnIndex'] - 1
                                    cell_text = ''
                                    for crel in cell.get('Relationships', []):
                                        if crel['Type'] == 'CHILD':
                                            for cchild_id in crel['Ids']:
                                                cchild = block_map.get(cchild_id)
                                                if cchild and cchild['BlockType'] == 'WORD':
                                                    cell_text += cchild['Text'] + ' '
                                    table_matrix[row][col] = cell_text.strip()
                                contents.append({"table": table_matrix})
            aws_texttract_document.append({
                "page": page_num,
                "contents": contents
            })
        return {
            "documents": [
                {
                    "aws_texttract_document": aws_texttract_document
                }
            ]
        }

    async def list_bedrock_models(self) -> List[Dict]:
        """
        Lists all Bedrock models available in the account.
        
        Returns:
            List[Dict]: List of models with name, modelId and provider
        """
        try:
            models = []
            
            # Get all Bedrock models
            response = self.bedrock_client.list_foundation_models()
            
            for model in response.get('modelSummaries', []):
                model_info = {
                    "name": f"{model.get('modelName', '')}",
                    "arn": model.get('modelArn', ''),
                    "modelId": model.get('modelId', ''),
                    "provider": model.get('providerName', '')
                }

                models.append(model_info)
            
            return models
            
        except Exception as e:
            # print(f"Error listing Bedrock models: {str(e)}")
            raise e 
    
    def model_supported(self) -> List[Dict]:
        """
        Returns the model and the region name
        """
        return [
            {
                "name": "Claude 3.7 Sonnet",
                "arn": "arn:aws:bedrock:eu-central-1::foundation-model/eu.anthropic.claude-3-7-sonnet-20250219-v1:0",
                "modelId": "eu.anthropic.claude-3-7-sonnet-20250219-v1:0",
                "model_region": "eu-central-1",
                "provider": "Anthropic"
            },
            {
                "name": "gpt-oss-120b",
                "arn": "arn:aws:bedrock:us-west-2::foundation-model/openai.gpt-oss-120b-1:0",
                "modelId": "openai.gpt-oss-120b-1:0",
                "model_region": "us-west-2",
                "provider": "OpenAI"
            },
            {
                "name": "gpt-oss-20b (beta)",
                "arn": "arn:aws:bedrock:us-west-2::foundation-model/openai.gpt-oss-20b-1:0",
                "modelId": "openai.gpt-oss-20b-1:0",
                "model_region": "us-west-2",
                "provider": "OpenAI"
            },
            # {
            #     "name": "Nova Canvas",
            #     "arn": "arn:aws:bedrock:us-west-2::foundation-model/amazon.nova-canvas-v1:0",
            #     "modelId": "amazon.nova-canvas-v1:0",
            #     "model_region": "us-east-1",
            #     "provider": "Amazon"
            # },
            # {
            #     "name": "Nova Reel",
            #     "arn": "arn:aws:bedrock:us-west-2::foundation-model/amazon.nova-reel-v1:0",
            #     "modelId": "amazon.nova-reel-v1:0",
            #     "model_region": "us-east-1",
            #     "provider": "Amazon"
            # },
            {
                "name": "Nova Micro",
                "arn": "arn:aws:bedrock:us-west-2::foundation-model/amazon.nova-micro-v1:0",
                "modelId": "amazon.nova-micro-v1:0",
                "model_region": "us-east-1",
                "provider": "Amazon"
            },
            {
                "name": "Nova Lite",
                "arn": "arn:aws:bedrock:us-west-2::foundation-model/amazon.nova-lite-v1:0",
                "modelId": "amazon.nova-lite-v1:0",
                "model_region": "us-east-1",
                "provider": "Amazon"
            },
            {
                "name": "Nova Pro",
                "arn": "arn:aws:bedrock:us-west-2::foundation-model/amazon.nova-pro-v1:0",
                "modelId": "amazon.nova-pro-v1:0",
                "model_region": "us-east-1",
                "provider": "Amazon"
            },
            {
                "name": "Claude 3 Sonnet",
                "arn": "arn:aws:bedrock:eu-central-1::foundation-model/anthropic.claude-3-sonnet-20240229-v1:0",
                "modelId": "anthropic.claude-3-sonnet-20240229-v1:0",
                "model_region": "eu-central-1",
                "provider": "Anthropic"
            },
            # {
            #     "name": "Claude Instant",
            #     "arn": "arn:aws:bedrock:eu-central-1::foundation-model/anthropic.claude-instant-v1",
            #     "modelId": "anthropic.claude-instant-v1",
            #     "model_region": "eu-central-1",
            #     "provider": "Anthropic"
            # },
            # {
            #     "name": "Llama 3.2 1B Instruct",
            #     "arn": "arn:aws:bedrock:us-east-1::foundation-model/meta.llama3-2-1b-instruct-v1:0",
            #     "modelId": "meta.llama3-2-1b-instruct-v1:0",
            #     "model_region": "us-east-1",
            #     "provider": "Meta"
            # },
            # {
            #     "name": "Llama 3.2 3B Instruct",
            #     "arn": "arn:aws:bedrock:us-east-1::foundation-model/meta.llama3-2-3b-instruct-v1:0",
            #     "modelId": "meta.llama3-2-3b-instruct-v1:0",
            #     "model_region": "us-east-1",
            #     "provider": "Meta"
            # },
            # {
            #     "name": "Llama 3.3 70B Instruct",
            #     "arn": "arn:aws:bedrock:us-east-1::foundation-model/meta.llama3-3-70b-instruct-v1:0",
            #     "modelId": "meta.llama3-3-70b-instruct-v1:0",
            #     "model_region": "us-east-1",
            #     "provider": "Meta"
            # },
            # {
            #     "name": "Llama 3.2 3B Instruct",
            #     "arn": "arn:aws:bedrock:us-east-1::foundation-model/meta.llama3-2-3b-instruct-v1:0",
            #     "modelId": "meta.llama3-2-3b-instruct-v1:0",
            #     "model_region": "us-east-1",
            #     "provider": "Meta"
            # },
            # {
            #     "name": "Llama 3.1 70B Instruct",
            #     "arn": "arn:aws:bedrock:us-east-1::foundation-model/meta.llama3-1-70b-instruct-v1:0",
            #     "modelId": "meta.llama3-1-70b-instruct-v1:0",
            #     "model_region": "us-east-1",
            #     "provider": "Meta"
            # }
            
        ]