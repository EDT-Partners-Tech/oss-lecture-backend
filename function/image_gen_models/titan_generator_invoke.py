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
import asyncio
import boto3
import json
from icecream import ic
from botocore.exceptions import ClientError

AWS_IMAGE_MODELS_REGION = "us-east-1"

async def invoke_titan_image_generator(prompt: str, img_width: int, img_height: int) -> str:
    model_id = "amazon.titan-image-generator-v2:0"
    
    bedrock_client = boto3.client(service_name="bedrock-runtime", region_name=AWS_IMAGE_MODELS_REGION)

    body = json.dumps({
        "taskType": "TEXT_IMAGE",
        "textToImageParams": {
            "text": prompt
        },
        "imageGenerationConfig": {
            "numberOfImages": 1,
            "height": img_height,
            "width": img_width,
            "cfgScale": 8.0,
            "quality": "standard"
        }
    })

    try:
        response = await asyncio.to_thread(
            bedrock_client.invoke_model,
            modelId=model_id,
            body=body,
            contentType="application/json",
            accept="application/json"
        )

        if response:
            response_body = json.loads(response.get("body").read())
            base64_image = response_body['images'][0]
        else:
            raise ValueError("Empty response from Titan Image Generator")
    except ClientError as e:
        message = e.response["Error"]["Message"]
        ic(f"A client error occurred: {message}")
        raise ClientError(f"Error while invoking the Bedrock Model: {message}")
    except Exception as e:
        ic("Error ocurred while image generation:", e)
        raise e

    return base64_image
