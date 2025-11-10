# © [2025] EDT&Partners. Licensed under CC BY 4.0.

import json
import re
import uuid
from icecream import ic
import json_repair

from function.content_query.query_prompt import build_summary_prompt
from function.llms.bedrock_invoke import invoke_bedrock_model

parsed_documents = {}

def store_parsed_document(text):
    doc_id = str(uuid.uuid4())
    parsed_documents[doc_id] = text
    return doc_id

def get_parsed_document(doc_id):
    return parsed_documents.get(doc_id)


async def generate_summary_and_title(prompt: str) -> tuple:

    ic("Using Bedrock for completion")
    response = await invoke_bedrock_model(prompt)

    # Debugging: Print or log the raw response
    ic("Raw response:", response)

    # Check if response is None
    if response is None:
        raise ValueError("Received None as response from the completion service")

    try:
        clean_json_response = re.search(r"\{.*\}", response, re.DOTALL).group()
        response_dict = json.loads(json_repair.repair_json(clean_json_response))
        ic("Repaired JSON response:", response_dict)
        
        summary = response_dict.get("summary", "")
        title = response_dict.get("title", "")
        return response, summary, title

    except json.JSONDecodeError as e:
        print("Error decoding JSON response:", e)
        raise ValueError("Error decoding JSON response from the completion service") from e
    except Exception as e:
        print("Unexpected error:", e)
        raise
