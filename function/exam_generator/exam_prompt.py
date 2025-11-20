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

from typing import Any, Dict, Optional
from utility.common import clean_document_for_prompt

def get_question_format():
    return  """[
    {
        "question": "What is the colour of the car in the book?",
        "options": ["Blue", "Green", "Yellow", "Grey"],
        "type": "mcq",
        "correct_answer": "Yellow",
        "reason": "In the book, the car is described multiple times as yellow, symbolizing energy and brightness."
    },
    {
        "question": "The Sky is blue?",
        "options": ["True", "False"],
        "type": "tf",
        "correct_answer": "True",
        "reason": "The sky appears blue because of the scattering of sunlight by the atmosphere."
    },
    {
        "question": "Explain the process of photosynthesis.",
        "type": "open",
        "reason": "The reasoning should cover the key steps of photosynthesis, including how plants convert sunlight into chemical energy, the role of chlorophyll, and the production of oxygen and glucose."
    }
    ]"""    
    
def build_prompt_document(number_mcq: int, number_tfq: int, number_open: int, source_text: str, custom_instructions: str = "") -> str:
    total_questions = number_mcq + number_tfq + number_open
    cleaned_text = clean_document_for_prompt(source_text)
    
    # Format custom instructions if provided
    custom_part = f"\nAdditional requirements: {custom_instructions}\n" if custom_instructions else ""
    
    return f"""Generate {total_questions} exam questions.

This is additional documentation to add value to the questions apart from the data you get from the knowledge bae:
{cleaned_text}

Required question breakdown:
- {number_tfq} True/False questions
- {number_mcq} Multiple Choice questions
- {number_open} Open-ended questions{custom_part}

Each question must use one of these exact formats:

For True/False questions:
{{
  "type": "tf",
  "question": "The question text",
  "options": ["True", "False"],
  "correct_answer" "True or False",
}}

For Multiple Choice questions:
{{
  "type": "mcq", 
  "question": "The question text",
  "options": ["Option 1", "Option 2", "Option 3", "Option 4"],
  "correct_answer" "The exact text of the correct option",
}}

For Open-ended questions:
{{
  "type": "open",
  "question": "The question text",
  "reason": "Explanation of what a good answer should include"
}}

Return your response as a single JSON array containing exactly {total_questions} questions using the formats above. The questions should be based directly on the provided text and not overlap in content."""

def get_question_format():
    return """[
    {
        "question": "Question text",
        "type": "tf", 
        "options": ["True", "False"],
        "correct_answer" "True",
        "reason": "Reasoning for question"
    },
    {
        "question": "Question text", 
        "type": "mcq",
        "options": ["Option 1", "Option 2", "Option 3", "Option 4"],
        "correct_answer" "Option 2",
        "reason": "Reasoning for question"
    },
    {
        "question": "Question text",
        "type": "open", 
        "reason": "Explanation of what a good answer should include"
    }
    ]"""

def build_prompt_agent(number_tf: int, number_mcq: int, number_open: int, custom_instructions="") -> str:
    total_questions = number_mcq + number_tf + number_open
    
    # Format custom instructions if provided
    custom_part = f"\nAdditional requirements: {custom_instructions}\n" if custom_instructions else ""
    
    return f"""Generate {total_questions} exam questions. {number_tf} True/False questions, {number_mcq} Multiple Choice questions and {number_open} Open-ended questions{custom_part}.
    Each question must use one of these exact formats:
    For True/False questions:
{{
  "type": "tf",
  "question": "The question text",
  "options": ["True", "False"],
  "correct_answer" "True or False",
  "reason": "Reasoning for question"
}}

For Multiple Choice questions:
{{
  "type": "mcq", 
  "question": "The question text",
  "options": ["Option 1", "Option 2", "Option 3", "Option 4"],
  "correct_answer" "The exact text of the correct option",
  "reason": "Reasoning for question"
}}

For Open-ended questions:
{{
  "type": "open",
  "question": "The question text",
  "reason": "Explanation of what a good answer should include"
}}

Return your response as a single JSON array containing exactly {total_questions} questions using the formats above. The questions should be based directly on the provided text and not overlap in content."""

def clean_document_for_prompt(text: str) -> str:
    """
    Cleans the input text to remove unnecessary formatting or characters.
    """
    return text.replace("\n", " ").strip()


def build_reload_prompt(question_data: Dict[str, Any], user_prompt: str) -> str:
    """
    Builds a prompt for regenerating a specific question based on user feedback.
    """
    return f"""<instruction>Given the following question:
{question_data}
Generate a new question based on the structure above, incorporating this feedback: {user_prompt}

Return the new question in the same JSON format, maintaining the question type unless explicitly requested to change. Allowed types:
{get_question_format()}
</instruction>"""