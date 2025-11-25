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

from typing import List
from function.llms.bedrock_invoke import invoke_bedrock_nova_async
from icecream import ic
import random
import asyncio
import json
import re
from sqlalchemy.orm import Session
from uuid import UUID
from database.crud import get_conversation_topics_for_chatbots, update_conversation_topic_global_topic

TOPIC_EXTRACTION_PROMPT = """
You are a helpful assistant that extracts conversation topics from chat messages.

Analyze the following conversation messages and extract the main topics discussed. 

Instructions:
- Identify the key topics, themes, or subjects discussed in the conversation
- Focus on substantive topics, not just greetings or small talk
- Return the topics as a comma-separated list of strings
- Each topic should be 1-4 words maximum
- Use consistent terminology (e.g., "Machine Learning" not "ML" or "machine learning")
- Limit to maximum 5 topics per conversation
- If no meaningful topics are found, return "General Discussion"

Conversation Messages:
{messages}

Topics (comma-separated):"""

SUPERTOPICS_PROMPT = """You are going to work with the following list of topics:
{topics}

Your task is to generate related supertopics. A supertopic is a short phrase that summarizes the topics of its group.
Supertopics can't match the main topics, but they can be related to them.

Return the suggested supertopics as a comma-separated list of strings.

Ensure that all the provided topics are processed.

Topics (comma-separated):"""

CLASSIFIER_PROMPT = """You are a classifier that categorizes a given list of topics into one of the following categories:
{categories}

You must output the category that best fits the list of topics, in JSON format, following the next structure:
```json
{{
    "category": "category_name"
}}
```

Just output the JSON response, without any additional text or explanation. The category_name must be verbatim one of the categories provided.

The list of topics to classify is: {topics}
"""

class SupertopicsLLMTool:
    def __init__(self, model_name: str = 'amazon.nova-micro-v1:0', max_supertopics: int = 20):
        self.model_name = model_name
        self.max_retries = 3
        self.max_supertopics = max_supertopics

    async def get_supertopics(self, topic_names: List[str]) -> List[str]:
        prompt = SUPERTOPICS_PROMPT.format(
            topics=','.join(topic_names)
        )
        retries = 1
        last_error = None
        while retries <= self.max_retries:
            try:
                response = await invoke_bedrock_nova_async(prompt, model_id=self.model_name)
                output = response.strip()

                supertopics = [topic.strip() for topic in output.split(',')]
                supertopics = random.sample(supertopics, min(self.max_supertopics, len(supertopics)))
                return supertopics
            except Exception as e:
                last_error = e
                ic(f"Error processing supertopics response: {e}")
                sleep_time = 2 ** retries
                await asyncio.sleep(sleep_time)
                retries += 1
        raise Exception(f"Max retries exceeded! Error: {last_error}")


class UnknownCategoryException(Exception):
    pass

class TopicClassifierLLMTool:
    def __init__(self, model_name: str = "amazon.nova-lite-v1:0"):
        self.model_name = model_name
        self.max_retries = 3

    async def classify(self, supertopics: List[str], topics: str) -> str:
        prompt = CLASSIFIER_PROMPT.format(
            categories=','.join(supertopics),
            topics=topics
        )
        retries = 1
        last_error = None
        while retries <= self.max_retries:
            try:
                response = await invoke_bedrock_nova_async(prompt, model_id=self.model_name)
                output = response.strip()

                json_query = re.search(r'```(?:json\s*\n)?(.*?)```', output, re.DOTALL)
                if json_query:
                    json_str = json_query.group(1)
                    category = json.loads(json_str)['category']
                    if category in supertopics:
                        return category
                    else:
                        raise UnknownCategoryException(f"Invalid category: {category}")
                else:
                    raise Exception(f"Invalid JSON response: {output}")
            except Exception as e:
                last_error = e
                sleep_time = 2 ** retries
                await asyncio.sleep(sleep_time)
                retries += 1
        if isinstance(last_error, UnknownCategoryException):
            ic(f"Unknown category: {last_error}, returning default value.")
            return "General Discussion"
        raise Exception(f"Max retries exceeded! Error: {last_error}")


async def extract_topics_from_messages(messages: List[str], max_retries: int = 2) -> List[str]:
    """Extract topics from conversation messages using LLM."""
    
    if not messages:
        return ["General Discussion"]
    
    # Combine messages into a single text
    combined_messages = "\n".join([f"- {msg}" for msg in messages])
    
    # Truncate if too long (to avoid token limits)
    if len(combined_messages) > 4000:
        ic(f"Combined messages are too long, truncating to 4000 characters")
        # Shuffle original messages, and take the first 4000 characters
        random.shuffle(messages)
        combined_messages = "\n".join([f"- {msg}" for msg in messages])[:4000] + "..."
    
    prompt = TOPIC_EXTRACTION_PROMPT.format(messages=combined_messages)
    
    for attempt in range(max_retries):
        try:
            response = await invoke_bedrock_nova_async(prompt, model_id="amazon.nova-micro-v1:0")
            
            if response:
                topics_text = response.strip()
                topics = [topic.strip() for topic in topics_text.split(',')]
                topics = [topic for topic in topics if topic and len(topic) > 0][:5]
    
                if not topics:
                    return ["General Discussion"]
                
                return topics
            else:
                ic(f"Empty response from LLM on attempt {attempt + 1}")
                
        except Exception as e:
            ic(f"Error extracting topics on attempt {attempt + 1}: {str(e)}")
            if attempt == max_retries - 1:
                ic("Max retries reached, returning default topic")
                return ["General Discussion"]
            
            # Wait before retry
            await asyncio.sleep(1)
    
    return ["General Discussion"]


async def compute_global_topics(db: Session, chatbot_ids: List[UUID], max_supertopics: int = 20):
    """Compute global topics for a list of chatbots."""
    ic("Computing global topics...")
    try:
        conversation_topics = await get_conversation_topics_for_chatbots(db, chatbot_ids)
        ic(f"Found {len(conversation_topics)} conversation topics")
        if not conversation_topics:
            ic("No conversation topics found")
            return
        # Get all topics from conversation topics
        all_topics = []
        for conversation_topic in conversation_topics:
            topics = conversation_topic.topics
            all_topics.extend(topics)
        ic(f"Found {len(all_topics)} total topics")
        
        supertopics_tool = SupertopicsLLMTool(max_supertopics=max_supertopics)
        supertopics = await supertopics_tool.get_supertopics(all_topics)
        ic(f"Computed supertopics: {supertopics}")
        
        # Classify topics into supertopics
        classifier_tool = TopicClassifierLLMTool()
        for conversation_topic in conversation_topics:
            category = await classifier_tool.classify(supertopics, conversation_topic.topics)
            ic(f"Topics {conversation_topic.topics} classified as {category} for chatbot {conversation_topic.chatbot_id}")
            await update_conversation_topic_global_topic(db, conversation_topic, category)

    except Exception as e:
        ic(f"Error computing global topics: {str(e)}")
        raise