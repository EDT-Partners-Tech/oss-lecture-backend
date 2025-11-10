# © [2025] EDT&Partners. Licensed under CC BY 4.0.

import json
from database.models import Rubric

def format_rubric_for_prompt(rubric: Rubric) -> str:
    """
    Format rubric indicators into a human-readable string for the prompt.
    """
    formatted_rubric = "### Rubric Criteria:\n"
    for indicator in rubric.indicators:
        formatted_rubric += f"- **{indicator.name}** (Weight: {indicator.weight}):\n"
        criteria = json.loads(indicator.criteria)
        for level, description in criteria.items():
            formatted_rubric += f"  - {level}: {description}\n"
    return formatted_rubric.strip()


def build_evaluation_prompt(source_text: str, rubric: Rubric, language: str = "English", custom_instructions: str = None) -> str:
    if not isinstance(rubric, Rubric):
        raise ValueError("Expected a valid Rubric instance.")

    # Format the rubric details for the prompt
    rubric_text = format_rubric_for_prompt(rubric)
    instructions = custom_instructions or """
    You are a teacher evaluating a student's exam based on the provided rubric criteria.
    Focus on:
    - Providing constructive feedback
    - Offering specific suggestions for improvement
    - Ensuring the evaluation is fair and consistent
    - Using the rubric criteria to justify the scores
    - Providing an overall assessment of the student's performance
    
    Important: Provide structured feedback value and improvement suggestions in JSON format in {language}.

    JSON Format:
    {
      "feedback": "General feedback on the responses.",
      "criteria_evaluation": [
        {
          "name": "Criterion Name",
          "score": "Numeric score evaluating the criterion",
          "suggestions": "Specific and detailed suggestions for improvement"
        }
      ],
      "overall_comments": "Final thoughts and suggestions."
    }
    """

    prompt = f"""
    ### Instructions:
    {instructions}

    ### Extracted Text with Formatting:
    {source_text}

    {rubric_text}
    """
    return prompt.strip()

def build_rubric_creation_prompt(source_text: str, language: str = "English") -> str:
    return f"""Analyze the following text and create a comprehensive rubric for evaluation. 
    The rubric should include relevant performance indicators with specific criteria for different score levels (0, 25, 50, 75, 100).
    Each indicator should have a weight (summing to 1.0) and detailed criteria descriptions.

    Important Note: The rubric should be in {language} and follow the JSON format provided below.
    
    Text to analyze:
    {source_text}

    Create a rubric in valid JSON format with this exact structure:
    {{
        "name": "Generated Rubric Name",
        "description": "Brief description of what this rubric evaluates",
        "indicators": [
            {{
                "name": "Indicator Name",
                "weight": 0.X,
                "criteria": {{
                    "0": "Description for 0% performance",
                    "25": "Description for 25% performance",
                    "50": "Description for 50% performance",
                    "75": "Description for 75% performance",
                    "100": "Description for 100% performance"
                }}
            }}
        ]
    }}

    Ensure:
    1. The sum of all indicator weights equals 1.0
    2. Each indicator has criteria for all five score levels (0, 25, 50, 75, 100)
    3. Criteria descriptions are specific and measurable
    4. The rubric name and description are relevant to the content
    5. Generate 3-5 relevant indicators based on the text content

    Return only the JSON object with no additional text or explanation.
    """
