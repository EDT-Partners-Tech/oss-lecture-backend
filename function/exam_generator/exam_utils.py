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
import fitz
from icecream import ic

def extract_text_from_pdf(file_path: str) -> str:
    document = fitz.open(file_path)
    text = ""
    for page_num in range(len(document)):
        page = document.load_page(page_num)
        text += page.get_text()
    return text


def format_response(response):
    try:
        return _handle_bedrock_response(response)
    except Exception as e:
        ic(f"Error formatting response: {e}")
        raise

def _handle_bedrock_response(response):
    if isinstance(response, list):
        return response
    else:
        raise ValueError("Bedrock response should be a list of dictionaries")

def _extract_questions(response_json):
    if isinstance(response_json, dict):
        questions = response_json.get('questions')
        if isinstance(questions, list) and all(isinstance(item, dict) for item in questions):
            return questions
        else:
            raise ValueError("The 'questions' key should contain a list of dictionaries")
    else:
        raise ValueError("OpenAI response is not a dictionary")
