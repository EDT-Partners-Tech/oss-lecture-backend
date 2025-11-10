# © [2025] EDT&Partners. Licensed under CC BY 4.0.

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
