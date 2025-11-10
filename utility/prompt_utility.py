# © [2025] EDT&Partners. Licensed under CC BY 4.0.

from typing import Any, Dict
from utility.common import clean_document_for_prompt
from icecream import ic 

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
    
        
def build_prompt_document(number_mcq: str, number_tfq: str, number_open: str, source_text: str, custom_instructions: str = "") -> str:
    total_questions = number_mcq + number_tfq + number_open
    cleaned_text = clean_document_for_prompt(source_text)
    
    # Format custom instructions if provided
    custom_part = f"\nAdditional requirements: {custom_instructions}\n" if custom_instructions else ""
    
    return f"""Human: You are a teacher preparing an exam for your students. I will provide you with source text from which you need to generate exam questions.

    <task>
    Generate {total_questions} exam questions. {number_tfq} True/False questions, {number_mcq} Multiple Choice questions and {number_open} Open-ended questions
    </task>

This is additional documentation to add value to the questions apart from the data you get from the knowledge base:
{cleaned_text}

Required question breakdown:
- {number_tfq} True/False questions
- {number_mcq} Multiple Choice questions
- {number_open} Open-ended questions

{custom_part}

Each question must use one of these exact formats:

<format>
For True/False questions:
    {{
        "type": "tf",
        "question": "The question text",
        "options": ["True", "False"],
        "correct_answer": "True or False",
        "reason": "Reasoning for question"
    }}

    For Multiple Choice questions:
    {{
        "type": "mcq", 
        "question": "The question text",
        "options": ["Option 1", "Option 2", "Option 3", "Option 4"],
        "correct_answer": "The exact text of the correct option",
        "reason": "Reasoning for question"
    }}

    For Open-ended questions:
    {{
        "type": "open",
        "question": "The question text",
        "reason": "Explanation of what a good answer should include"
    }}
</format>

Return your response as a single JSON array containing exactly {total_questions} questions using the formats above. The questions should be based directly on the provided text and not overlap in content."""



def build_prompt_agent(number_tf: int, number_mcq: int, number_open: int, custom_instructions="", questions="", language="") -> str:
    total_questions = number_mcq + number_tf + number_open

    # Format custom instructions if provided
    custom_part = f"<user_question>\n{custom_instructions}\n</user_question>" if custom_instructions else ""
    translation_part = f" to {language}." if language else " in the same language as the provided search results content."
    questions_part = f"\n<existing_questions>\n{questions}\n</existing_questions>\nPlease generate questions different from the ones listed above." if questions else ""

    return f"""Human: You are a teacher preparing an exam for your students. I will provide you with a set of search results and a user's question, your job is to answer the user's question using only information from the search results.
    
    <task>
    Generate {total_questions} exam questions. {number_tf} True/False questions, {number_mcq} Multiple Choice questions and {number_open} Open-ended questions
    </task>
    
    <format>
    For Multiple Choice questions:
    {{
        "type": "mcq", 
        "question": "The question text",
        "options": ["Option 1", "Option 2", "Option 3", "Option 4"],
        "correct_answer": "The exact text of the correct option",
        "reason": "Reasoning for question"
    }}

    For True/False questions:
    {{
        "type": "tf",
        "question": "The question text",
        "options": ["True", "False"],
        "correct_answer": "True or False",
        "reason": "Reasoning for question"
    }}

    For Open-ended questions:
    {{
        "type": "open",
        "question": "The question text",
        "reason": "Explanation of what a good answer should include"
    }}
    </format>
    {questions_part}
    
    <instruction>
    Important: Generate all questions, options, answers and reasoning {translation_part}
    
    1. True/False Questions:
        - Craft each true/false question based on factual statements or key concepts from the content.
        - Ensure each question spans a wide range of topics to cover the content comprehensively.
        - Translate "True/False" for non English content and use "True/False" for English content.

    2. Multiple-Choice Questions (MCQs):
        - Formulate each MCQ to assess understanding of significant themes, events, or facts.
        - Include 4 options per MCQ, making sure one is correct and the others are plausible but incorrect.
        - Diversify the content areas and pages/topics for each MCQ to avoid overlap and repetition.
        
    3. Open-Ended Questions:
        - Develop open-ended questions that require detailed responses and critical thinking.
        - Ensure each question is clear, concise, and directly related to the content.
    </instruction>

    <search_results>
    $search_results$
    </search_results>
    
    {custom_part}
    
    Assistant:
    """


def clean_document_for_prompt(text: str) -> str:
    """
    Cleans the input text to remove unnecessary formatting or characters.
    """
    return text.replace("\n", " ").strip()


def build_reload_prompt(question_data: Dict[str, Any], user_prompt: str) -> str:
    """
    Builds a prompt for regenerating a specific question based on user feedback.
    """
    return f"""Human: You are a teacher reviewing a question and feedback from a student. I will provide you with a set of search results and a user's feedback, your task is to generate a new version of the question incorporating the feedback.

    <search_results>
    $search_results$
    </search_results>
Given the following question:

<question>
{question_data}
</question>
Generate a new question based on the structure above, incorporating this feedback: 
<feedback>
{user_prompt}
</feedback>

Return the new question in the same JSON format, maintaining the question type unless explicitly requested to change. Allowed question format types:
    <format>
    For True/False questions:
    {{
        "type": "tf",
        "question": "The question text",
        "options": ["True", "False"],
        "correct_answer": "True or False",
        "reason": "Reasoning for question"
    }}

    For Multiple Choice questions:
    {{
        "type": "mcq", 
        "question": "The question text",
        "options": ["Option 1", "Option 2", "Option 3", "Option 4"],
        "correct_answer": "The exact text of the correct option",
        "reason": "Reasoning for question"
    }}

    For Open-ended questions:
    {{
        "type": "open",
        "question": "The question text",
        "reason": "Explanation of what a good answer should include"
    }}
    </format>
"""

def build_relevance_prompt(custom_instructions: str) -> str:
    """
    Builds a prompt for generating instructions or references relevant to the knowledge base content as bullet points.
    """
    return f"""
    Rewrite the response by following the {{custom_instructions}} to ensure alignment with the knowledge base data.
<instructions>
    <step>Analyze the provided knowledge base content to identify key purposes, concepts, and entities relevant to the custom instructions.</step>
    <step>Generate a response that is accurate, contextually relevant, and directly aligned with the dataset.</step>
    <step>Ensure the response addresses the custom instructions: {custom_instructions}.</step>
    <step>Present the output as a clear and concise list of bullet points without additional explanation or repetition of the original input.</step>
</instructions>
    """

def build_key_points_prompt(source_text: str) -> str:
    """
    Builds a prompt for extracting key points from the provided text as bullet points.
    """
    return f"""Human:
    Extract the key points from the provided text while adhering to the following instructions:
<instructions>
    <step>Read the provided text carefully to identify the most important ideas, facts, or arguments.</step>
    <step>Summarize these key points concisely, focusing on clarity and relevance to the source text.</step>
    <step>Exclude unnecessary details, redundancy, or direct quotes unless critical for context.</step>
    <step>Present the extracted information as a structured list of bullet points that capture the essence of the text.</step>
</instructions>
    Source Text: {source_text}
    Assistant:
    """
    
def build_summary_prompt(transcript: str, language="English") -> str:
    return (
        f"Human: Please summarize the following transcript. Highlight the key notes and topics discussed in the text:\n\n"
        f"{transcript}\n\n"
        f"Provide the summary and action points in {language}. Assistant:"
    )


def build_text_processing_prompt(action, tones, audiences, full_text, selected_text=None):
    action_prompts = {"summarize": "Summarize", "expand": "Expand on", "rephrase": "Rephrase", "format": "Format"}
    base_prompt = f"{action_prompts[action]} this text"
    
    if tones:
        base_prompt += f" with a {', '.join(tones).lower()} tone"
    if audiences:
        base_prompt += f" for {', '.join(audiences).lower()} audience"

    common_instructions = (
        f" and return as HTML only the {action}ed text wrapped within <response></response> tags without any additional explanation. "
        f"Ensure the output includes valid HTML formatting (e.g., <strong> for bold, <em> for italic, <h1>, <h2> for headings, <ul>, <ol> for lists, and <blockquote> for quotes)."
    )

    text_context = f" Full text: \"{full_text}\" Selected text: \"{selected_text}\"" if selected_text else full_text
    return base_prompt + common_instructions + text_context

def build_instruction_prompt(
        rules_data: str,
        weights: str,
        language: str,
        ) -> str:
    '''
    Builds a prompt for comparing two documents. The prompt includes the text of each document and their respective key phrases and entities.
    '''
    return f'''
    Your task is to act as a rule-based comparison engine to analyze two provided documents.
    Follow these instructions only, without suggesting additional solutions or using inferences not permitted by these rules:

    1. **Topics and Keywords:**
       - Extract important topics or keywords from each document.
       - Clearly indicate which topics are present in both and which appear only in one of the documents.
       - Try to identify all topics and/or keywords in each document.
       - Consider the rules for evaluation.
       - All types in the similarities and differences must match exactly.

    2. **Difficulty Level:**
       - Indicate if a difficulty level is explicitly mentioned (e.g., "introductory", "intermediate", "advanced").
       - If not explicitly mentioned, clearly indicate it ("not explicitly mentioned") and refrain from making detailed inferences not based on explicit text.

    3. **Results and Learning Objectives:**
       - Extract and compare objectives explicitly mentioned in both documents.
       - Clearly indicate which objectives are present in one document but not in the other.
       - Try to identify all objectives or competencies in each document.
       - Consider the rules for evaluation.

    4. **Teaching Methodologies or Formats:**
       - If teaching formats or methodologies are explicitly mentioned ("practical work", "theoretical", "project-based", "lectures", etc.), compare them clearly.

    5. **Prerequisites and Required Knowledge:**
       - Explicitly validate whether requirements mentioned in one document appear as covered in the other ("Met"/"Not Met").
       - If no explicit requirements are mentioned, clearly indicate "Not mentioned".

    6. **Key phrases:**
        - These are the keywords of each document.
        - Identify the similarities and differences between the documents based on these keywords.
        - All "key_phrases" from document A and document B must be listed.
        - Consider the rules for evaluation.
        - Key phrases can be more than one per document, and they can overlap or be exclusive.
    
    7. **Entities:**
        - These are the entities extracted in each document.
        - Identify the similarities and differences between the documents based on these entities.
        - All "entities" from document A and document B must be listed.
        
    8. **Language:**
        - The response must be in the language with code: {language}.

    9. **Document Name:**
        - Try to identify the names of the documents to reference them in the response.
        - If the names of the institution or person are not provided in the content, use the file names without the extension.

    10. **Answer:**
        - The <RULES> and <SUB_RULE> are guides to represent the answer.
        - Must include the rules and weights for evaluation in the markdown_code response.
        - Indicate elements that you consider relevant for the evaluation of the documents.
        - The types must always be expressed in English, only the content of the documents can be in another language.
        - Return a score that corresponds to the similarity between the documents based on the rules and weights provided.
        - In the markdown_code field, generate a document in markdown with the content of the answer, taking into account the <RULES> and <SUB_RULE>.
        - The response must be in the language with code: {language}.
        - Use tables for comparison and add the names of the documents in the header, taking into account the <RULES> and <SUB_RULE>.
        - Your answer should be structured exclusively in JSON format without additional additions or explanations:

        <RESPONSE>
        <IMPORTANT>All the content of the response should be in {language} code.<IMPORTANT>
        <IMPORTANT>Only the JSON format.<IMPORTANT>
        <IMPORTANT>You don't user markdown to return a JSON.<IMPORTANT>
        <IMPORTANT>This response will be used with a JSON parse like json.loads().<IMPORTANT>
        </RESPONSE>
    {{
        "documents_names": [{{"doc1":"name_doc1"}}, {{"doc2":"name_doc2"}}],
        "similarities": [{{"type": "", "value": "", "match": true}}],
        "differences": [{{"type": "...", "doc1": "...", "doc2": "..."}}],
        "gaps": ["Clearly expressed gap..."],
        "difficulty_level": "not explicitly mentioned",
        "prerequisites_validation": [{{"prerequisite": "...", "status": "Met/Not Met"}}],
        "matching_key_phrases": ["phrase1", "phrase2", "phrase3"],
        "non_matching_key_phrases": [
            {{"phrase": "unique phrase 1", "document": "A"}},
            {{"phrase": "unique phrase 2", "document": "B"}}
        ],
        "matching_entities": ["entity1", "entity2"],
        "non_matching_entities": [
            {{"entity": "unique entity 1", "document": "A"}},
            {{"entity": "unique entity 2", "document": "B"}}
        ],
        "score": 0.0,
        "metadata": {{"doc1_language": "es", "doc2_language": "es"}},
        "error": "",
        "markdown_code": ""
    }}
    '''

def build_instruction_prompt_for_converse_resume(language: str, rules_data: str) -> str:
    return f'''
        Your task is to act as a rule-based comparison engine to analyze two provided documents: a CV and a job description.
    Follow these instructions only, without suggesting additional solutions or using inferences not permitted by these rules:

    1. **Topics and Keywords (Skills):**
       - Extract important topics or keywords from each document that represent the candidate's skills and the job requirements.
       - Clearly indicate which topics (skills) are present in both and which appear only in one of the documents.
       - Try to identify all topics and/or keywords in each document.
       - Consider the rules for evaluation.
       - All types in the similarities and differences must match exactly.

    2. **Experience Level:**
       - Indicate whether an experience level is explicitly mentioned (e.g., "junior", "senior", "expert").
       - If not explicitly mentioned, clearly indicate it ("not explicitly mentioned") and refrain from making detailed inferences not based on explicit text.

    3. **Results and Professional Objectives:**
       - Extract and compare professional objectives explicitly mentioned in both documents.
       - Clearly indicate which objectives are present in one document but not in the other.
       - Try to identify all objectives or competencies in each document.
       - Consider the rules for evaluation.

    4. **Methodologies or Areas of Expertise:**
       - If methodologies or areas of expertise are explicitly mentioned (e.g., "Agile", "DevOps", "Digital Marketing"), compare them clearly.

    5. **Mandatory Requirements and Desired Knowledge:**
       - Explicitly validate whether the requirements mentioned in the job description appear as covered in the CV ("Met"/"Not Met").
       - If no explicit requirements are mentioned, clearly indicate "Not mentioned".

    6. **Key phrases (Skills):**
        - These are the keywords of each document, representing skills and knowledge.
        - Identify the similarities and differences between the documents based on these keywords.
        - All "key_phrases" from document A (CV) and document B (job position) must be listed.
        - Consider the rules for evaluation.
        - Key phrases can be more than one per document and can overlap or be exclusive.
    
    7. **Entities (Companies, technologies, certifications):**
        - These are the entities extracted in each document (companies where they worked, technologies they master, certifications).
        - Identify the similarities and differences between the documents based on these entities.
        - All "entities" from document A (CV) and document B (job position) must be listed.
        
    8. **Language:**
        - The response must be in the language with code: {language}.

    9. **Document name:**
        - Try to identify the names of the documents to refer to them in the response.
        - If the names of the institution or person are not provided in the content, use the file names without the extension.

    10. **Answer:**
        - The <RULES> and <SUB_RULE> are guides to represent the answer.
        - Must include the rules and weights for evaluation in the markdown_code response.
        - Indicate elements that you consider relevant for the evaluation of the documents.
        - The types must always be expressed in English, only the content of the documents can be in another language.
        - Return a score that corresponds to the similarity between the documents based on the rules and weights provided.
        - In the markdown_code field, generate a document in markdown with the content of the answer, taking into account the <RULES> and <SUB_RULE>.
        - The response must be in the language with code: {language}.
        - Use tables for comparison and add the names of the documents in the header, taking into account the <RULES> and <SUB_RULE>.
        - Your answer should be structured exclusively in JSON format without additional additions or explanations:
        
        <RESPONSE>
        <IMPORTANT>All the content of the response should be in {language} code.<IMPORTANT>
        <IMPORTANT>Only the JSON format.<IMPORTANT>
        <IMPORTANT>You don't user markdown to return a JSON.<IMPORTANT>
        <IMPORTANT>This response will be used with a JSON parse like json.loads().<IMPORTANT>
        </RESPONSE>
        {{
            "documents_names": [{{"doc1":"name_doc1"}}, {{"doc2":"name_doc2"}}],
            "skills_present": ["skill1", "skill2"],
            "skills_absent": ["skill3", "skill4"],
            "general_matches": ["match1", "match2"],
            "knowledge_gaps": ["gap1", "gap2"],
            "metadata": {{"doc_cv_language": "es", "doc_oferta_language": "es"}},
            "score": 0.0,
            "markdown_code": ""
        }}
    '''

def build_comparation_prompt_for_converse(
        document_a_file_name: str,
        document_b_file_name: str,
        language: str,
        rules_data: str,
        ) -> str:
    '''
    Builds a prompt for comparing two documents. The prompt includes the text of each document and their respective key phrases and entities.
    '''
    return f'''    
    1. **Nombre del archivo:**
        - Documento A: """{document_a_file_name}"""
        - Documento B: """{document_b_file_name}"""

    2. **Content language:**
        - The response content must be in the language with code: {language}.

    3. **Rules to respect in the comparison:**
        <IMPORTANT>{rules_data}</IMPORTANT>
    '''