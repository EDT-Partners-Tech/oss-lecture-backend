# © [2025] EDT&Partners. Licensed under CC BY 4.0.

def build_summary_prompt(text: str) -> str:
    response_format = """{
    "summary": "A summary of the content",
    "title": "Proposed title"
    }"""

    escaped_format = response_format.replace('{', '{{').replace('}', '}}')

    return f"""Human: You are tasked with generating a summary and a concise title for the following content. Analyze the text provided between <content> </content> tags and create a detailed summary and an accurate title that captures the essence of the content.

        - The summary should be detailed and cover the main points and key information from the content.
        - The title should be concise and reflect the primary focus of the content.

        Please provide the summary and title in the following format exactly:
        {escaped_format}

        <content>
        {text}
        </content>

        Return the response in a proper JSON format.
        Assistant:"""
