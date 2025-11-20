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
