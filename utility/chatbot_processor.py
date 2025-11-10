# © [2025] EDT&Partners. Licensed under CC BY 4.0.

import base64
import re
import markdown
import os
import json
import uuid
from function.llms.bedrock_invoke import retrieve_and_generate
from routers.courses import get_material_by_id
from logging_config import setup_logging
from utility.agent_registry import AgentRegistry
from utility.analytics import AnalyticsProcessor

region_name = os.getenv('AWS_REGION_NAME')
from typing import Dict, Any, List, Optional, Tuple, Union
from fastapi import HTTPException
from sqlalchemy.orm import Session
from database.crud import (
    get_agents,
    get_chatbot_by_id,
    get_chatbot_material_by_id,
    get_course_by_knowledge_base_id,
    get_last_30_conversations,
    get_user_by_cognito_id,
    get_chatbot_materials_by_chatbot_id_with_is_main_true,
    save_conversation,
    update_chatbot_status,
    get_course
)
from logging_config import setup_logging
from utility.aws import generate_presigned_url, invoke_bedrock_agent 
from database.models import ChatbotMaterial, Conversation
from constants import S3_FOLDER_IMAGES
from utility.ssm_parameter_store import SSMParameterStore
from utility.aws_clients import get_caller_identity
from function.llms.bedrock_invoke import get_model_by_id, get_default_model_ids, get_model_region, is_inference_model

logger = setup_logging()

class ChatbotProcessor:
    def __init__(self, db: Session, prompt: str = None, stream: bool = False, is_external: bool = False, analytics_processor: AnalyticsProcessor = None ):
        self.db = db
        self.chatbot = None
        self.course = None
        self.user = None
        self.prompt = prompt
        self.stream = stream
        self.agent_id = None
        self.alias_id = None
        self.agent = {
            "without_knowledge_base": {
                "agent_id": "",
                "alias_id": ""
            },
            "with_knowledge_base": {
                "agent_id": "",
                "alias_id": ""
            }
        }
        self.session_id = None
        self.knowledge_base_id = None
        self.is_external = is_external
        self.analytics_processor = analytics_processor
        self.save_conversation = True

    async def set_agent(self):
        # agents = await get_agents(self.db)
        print("Create the SSM client")
        ssm_client = SSMParameterStore()
        print("Create the agent registry")
        try:
            agent_registry = AgentRegistry()
            print("Get all agents")
            all_agents = agent_registry.get_all_agents()
            print(f"ChatbotProcessor: all_agents: {all_agents}")
        except Exception as e:
            logger.error(f"Error getting the agents from the agent registry: {e}")
        try:
            print("Get the agents from SSM")
            # /lecture/global/BEDROCK_AGENT_EXTERNAL
            # /lecture/global/BEDROCK_AGENT_WITH_KNOWLEDGEBASES
            # /lecture/global/BEDROCK_AGENT_WITHOUT_KNOWLEDGEBASES
            agent_external = ssm_client.get_parameter("/lecture/global/BEDROCK_AGENT_EXTERNAL")
            agent_with_knowledgebases = ssm_client.get_parameter("/lecture/global/BEDROCK_AGENT_WITH_KNOWLEDGEBASES")
            agent_without_knowledgebases = ssm_client.get_parameter("/lecture/global/BEDROCK_AGENT_WITHOUT_KNOWLEDGEBASES")
            print(f"agent_external: {agent_external}")
            print(f"agent_with_knowledgebases: {agent_with_knowledgebases}")
            print(f"agent_without_knowledgebases: {agent_without_knowledgebases}")
            print(f"all_agents: {all_agents}")
        except Exception as e:
            logger.error(f"Error getting the agents from SSM: {e}")


        if agent_external and agent_with_knowledgebases and agent_without_knowledgebases:
            print("Get the alias id of the agents using the SSM parameters")
            agent_external_alias_id = agent_registry.get_alias_id_by_agent_id(agent_external)
            agent_with_knowledgebases_alias_id = agent_registry.get_alias_id_by_agent_id(agent_with_knowledgebases)
            agent_without_knowledgebases_alias_id = agent_registry.get_alias_id_by_agent_id(agent_without_knowledgebases)
            print(f"ChatbotProcessor: agent_external_alias_id: {agent_external_alias_id}")
            print(f"ChatbotProcessor: agent_with_knowledgebases_alias_id: {agent_with_knowledgebases_alias_id}")
            print(f"ChatbotProcessor: agent_without_knowledgebases_alias_id: {agent_without_knowledgebases_alias_id}")
            self.agent_id = agent_external
            self.alias_id = agent_external_alias_id
            self.agent["without_knowledge_base"] = type('Agent', (), {
                'agent_id': agent_without_knowledgebases,
                'alias_id': agent_without_knowledgebases_alias_id
            })
            self.agent["with_knowledge_base"] = type('Agent', (), {
                'agent_id': agent_with_knowledgebases,
                'alias_id': agent_with_knowledgebases_alias_id
            })
        elif all_agents and "agent-external" in all_agents and "agent-with-knowledgebases" in all_agents and "agent-without-knowledgebases" in all_agents:
            print("Get the alias id of the agents using the all_agents")
            self.agent["without_knowledge_base"] = type('Agent', (), {
                'agent_id': all_agents["agent-without-knowledgebases"]["agent_id"],
                'alias_id': all_agents["agent-without-knowledgebases"]["alias_id"]
            })
            self.agent["with_knowledge_base"] = type('Agent', (), {
                'agent_id': all_agents["agent-with-knowledgebases"]["agent_id"],
                'alias_id': all_agents["agent-with-knowledgebases"]["alias_id"]
            })
            self.agent_id = all_agents["agent-external"]["agent_id"]
            self.alias_id = all_agents["agent-external"]["alias_id"]
        else:
            raise HTTPException(
                status_code=404,
                detail="No agent found"
            )
        # else:
        #     for agent in agents:
        #         if agent.code == "internal_chatbot_without_kb":
        #             self.agent["without_knowledge_base"] = agent
        #         elif agent.code == "internal_chatbot_with_kb":
        #             self.agent["with_knowledge_base"] = agent
        #         elif agent.code == "external_chatbot":
        #             self.agent_id = agent.agent_id
        #             self.alias_id = agent.alias_id

    async def set_chatbot(self, chatbot_id: str):
        self.chatbot = await get_chatbot_by_id(self.db, chatbot_id)

    def set_save_conversation(self, save_conversation: bool):
        self.save_conversation = save_conversation

    async def set_course(self, course_id: str, session_id: str):
        self.course = get_course(self.db, course_id)
        self.session_id = session_id
        self.knowledge_base_id = self.course.knowledge_base_id

    def get_user_id(self):
        if self.chatbot:
            return str(self.chatbot.user_id)
        elif self.course:
            return str(self.course.teacher_id)
        else:
            return None

    def _get_user(self):
        user = get_user_by_cognito_id(self.db, self.cognito_id)
        if not user:
            raise HTTPException(
                status_code=404,
                detail=f"User with cognito_id {self.cognito_id} not found"
            )
        return user

    async def set_session_id(self, session_id: str):
        self.session_id = session_id

    async def check_if_external_chatbot(self) -> bool:
        """Check if the chatbot is external"""
        if self.chatbot.resource_data: 
            try:
                resource_data = json.loads(self.chatbot.resource_data)
                kb_id = resource_data.get("resource_id")
                course = get_course_by_knowledge_base_id(self.db, kb_id)
                is_settings_in_course = course.settings is not None
                self.is_external = is_settings_in_course
                if is_settings_in_course:
                    self.course = course
                    self.knowledge_base_id = course.knowledge_base_id
                    self.session_id = self.chatbot.session_id
                return is_settings_in_course
            except Exception as e:
                logger.error(f"Error checking if the chatbot is external: {e}")
                return False
        return False

    async def _get_chatbot_materials(self) -> List[ChatbotMaterial]:
        """Get the main materials of the chatbot"""
        materials = await get_chatbot_materials_by_chatbot_id_with_is_main_true(self.db, self.chatbot.id)
        if not materials:
            raise HTTPException(
                status_code=404,
                detail=f"No main materials found for the chatbot {self.chatbot.id}"
            )
        return materials

    def _build_user_prompt(self) -> str:
        """Build the prompt for the agent"""
        return f"<user_prompt>{self.prompt}</user_prompt>\n<system_context>{self.chatbot.system_prompt}</system_context>"

    async def _get_resource_data(self, resource_data_json: dict) -> Dict[str, Any]:
        """Get the resource of the conversation"""
        materials = []

        resource_type = resource_data_json.get("resource_type")

        if resource_type:
            material_id = resource_data_json.get("resource_id")
            if resource_type == "course_material":
                material = await get_material_by_id(self.db, material_id)
                if material:
                    materials.append(material)
            elif resource_type == "chatbot_material":
                material = await get_chatbot_material_by_id(self.db, material_id)
                if material:
                    materials.append(material)
        
        return materials

    def _prepare_s3_files(self, materials: List[ChatbotMaterial]) -> List[Dict[str, Any]]:
        """Prepare the list of S3 files for the agent"""
        files = []
        for material in materials:
            if material.s3_uri:
                files.append({
                    "name": f"material_{material.id}",
                    "source": {
                        "s3Location": {
                            "uri": material.s3_uri
                        },
                        "sourceType": "S3"
                    },
                    "useCase": "CHAT"
                })
        return files

    async def get_image_from_s3_and_convert_to_presigned_url(self, file_path: str) -> str:
        """Get an image from S3 and convert it to a presigned URL."""
        try:
            presigned_url = generate_presigned_url('content',f"{file_path}", 604800)
            return presigned_url
        except Exception as e:
            print(f"Error getting image from S3: {e}")
            return ""

    async def process_markdown_images(self, markdown_text: str) -> str:
        """Process the markdown to replace images with base64."""
        # Pattern to find images in markdown
        pattern = r'!\[[^\]]*\]\(([^)]*)\)'
        image_matches = re.finditer(pattern, markdown_text)
        
        processed_text = markdown_text
        
        for match in image_matches:
            image_path = match.group(1)
            # Extract UUID from the file name (with or without extension)
            uuid_match = re.search(r'([a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12})(?:\.png)?', image_path)
            # Extract the bucket from the image path
            if uuid_match:
                uuid = uuid_match.group(1)
                presigned_url = await self.get_image_from_s3_and_convert_to_presigned_url(f"{S3_FOLDER_IMAGES}/{uuid}.png")
                if presigned_url:
                    # Replace the UUID (with or without .png) with the base64
                    processed_text = processed_text.replace(f"data:image/png;base64,{uuid}.png", presigned_url)
                    processed_text = processed_text.replace(f"data:image/png;base64,{uuid}", presigned_url)
                    
                    bucket_match = re.search(r's3://([^/]+)/', image_path)
                    if bucket_match:
                        processed_text = processed_text.replace(f"s3://{bucket_match.group(1)}/{S3_FOLDER_IMAGES}/{uuid}.png", presigned_url)
                    
                    bucket_match = re.search(r'https://s3.amazonaws.com/([^/]+)/', image_path)
                    if bucket_match:
                        processed_text = processed_text.replace(f"https://s3.amazonaws.com/{bucket_match.group(1)}/{S3_FOLDER_IMAGES}/{uuid}.png", presigned_url)
        
        return processed_text

    # Create a method where a markdown is received and a HTML structure is returned.
    async def convert_markdown_to_html(self, markdown_text: str) -> str:
        """Convert a markdown text to HTML."""
        return markdown.markdown(markdown_text)
    
    async def _update_chatbot_status(self, status: str) -> None:
        """Update the status of the chatbot."""
        await update_chatbot_status(self.db, self.chatbot.id, status)

    async def process_conversation(self) -> Dict[str, Any]:
        """
        Process a chatbot conversation following the flow:
        1. Get the chatbot
        2. Get the main materials of the chatbot
        3. Build the prompt
        4. Save the conversation of the role 'user'
        5. Invoke the Bedrock agent with the S3 files
        6. Process the response
        """
        try:

            if not self.chatbot:
                raise HTTPException(
                    status_code=404,
                    detail=f"Chatbot with id {self.chatbot.id} not found"
                )
            
            if self.chatbot.status == "PROCESSING":
                print("Chatbot is still processing")
            
            # await self._update_chatbot_status("PROCESSING")

            # Process based on resource type
            data = None
            if self.chatbot.resource_data:
                data = await self._process_with_resource_data()
            else:
                data = await self._process_without_resource_data()
            
            # await self._update_chatbot_status("COMPLETED")

            return data

        except Exception as e:
            # await self._update_chatbot_status("FAILED")
            raise HTTPException(
                status_code=500,
                detail=f"Error in the chatbot processing: {str(e)}"
            )

    async def _process_with_resource_data(self) -> Dict[str, Any]:
        """Process conversation with resource data"""
        resource_data_json = json.loads(self.chatbot.resource_data)
        resource_type = resource_data_json.get("resource_type")

        if resource_type == "course_knowledge_base" or resource_type == "knowledge_base_manager":
            return await self._process_course_knowledge_base(resource_data_json)
        elif resource_type in ["chatbot_material"]:
            materials = await self._get_resource_data(resource_data_json)
            print(f"materials: {materials}")
        else:
            materials = await self._get_chatbot_materials()
            
        return await self._process_with_materials(materials)

    async def _process_course_knowledge_base(self, resource_data_json) -> Dict[str, Any]:
        """Process conversation with course knowledge base"""
        # Save user conversation
        conversation = Conversation(
            chatbot_id=self.chatbot.id,
            role="user",
            content=json.dumps(self.prompt) if isinstance(self.prompt, dict) else self.prompt
        )
        await save_conversation(self.db, conversation)

        # Get the knowledge base id
        knowledge_base_id = resource_data_json.get("resource_id")
        
        # Build prompt with knowledge base
        kb_prompt = f"""
            <user_prompt>
                {self.prompt}
            </user_prompt>
            <system_context>
                {self.chatbot.system_prompt}
            </system_context>
            <language_to_use>
                Use $user_prompt$ language to answer
            </language_to_use>
        """
        
        # Process with knowledge base
        completition = await self.process_conversation_with_knowledge_base(kb_prompt, knowledge_base_id=knowledge_base_id)
        
        # Save assistant conversation
        conversation = Conversation(
            chatbot_id=self.chatbot.id,
            role="assistant",
            content=completition.get("response")
        )
        await save_conversation(self.db, conversation)
        
        # Process markdown images
        completition = await self.process_markdown_images(completition.get("response"))
        
        return {
            "response": completition,
            "files": []
        }

    async def _process_without_resource_data(self) -> Dict[str, Any]:
        """Process conversation without resource data"""
        materials = await self._get_chatbot_materials()
        return await self._process_with_materials(materials)
    
    def _build_conversation_history(self, conversations: List[Conversation]) -> Dict[str, Any]:
        """Build the conversation history"""
        conversation_filtered_pattern = self._prepare_last_30_conversations_pattern(conversations)
        return {
            "conversationHistory": {
                "messages": conversation_filtered_pattern
            }
        }
    
    def _prepare_last_30_conversations_pattern(self, conversations: List[Conversation]) -> List[Dict[str, Any]]:
        """
        Prepare the last 30 conversations to be used.
        Select only the "user", "assistant", "user", "assistant" pattern.
        """
        conversation_filtered_pattern = []
        previous_role = None
        for conversation in conversations:
            if conversation.role == "user" and (previous_role == "assistant" or previous_role == None):
                conversation_filtered_pattern.append({
                    "role": "user",
                    "content": [{"text": conversation.content}]
                })
            elif conversation.role == "assistant" and previous_role == "user":
                conversation_filtered_pattern.append({
                    "role": "assistant",
                    "content": [{"text": conversation.content}]
                })
            previous_role = conversation.role

        # remove the las item if previous_role is "user"
        if previous_role == "user":
            conversation_filtered_pattern.pop()

        return conversation_filtered_pattern

    async def _process_with_materials(self, materials) -> Dict[str, Any]:
        """Process conversation with materials"""
        # Build the prompt
        agent_user_prompt = self._build_user_prompt()
        
        # Prepare S3 files
        s3_files = self._prepare_s3_files(materials)

        # Get the last 30 conversations
        conversations = await get_last_30_conversations(self.db, self.chatbot.id)

        # Prepare the last 30 conversations
        conversation_filtered_pattern = self._build_conversation_history(conversations)
        
        # Save user conversation
        conversation = Conversation(
            chatbot_id=self.chatbot.id,
            role="user",
            content=json.dumps(self.prompt) if isinstance(self.prompt, dict) else self.prompt
        )
        await save_conversation(self.db, conversation)
        
        # Invoke Bedrock agent
        response = invoke_bedrock_agent(
            agent_id=self.agent["without_knowledge_base"].agent_id,
            agent_alias_id=self.agent["without_knowledge_base"].alias_id,
            input_text=agent_user_prompt,
            session_id=self.chatbot.session_id,
            files=s3_files,
            memory_id=self.chatbot.memory_id,
            conversation_history=conversation_filtered_pattern,
            stream=self.stream
        )
        
        # Process response
        completion, files_base64 = await self._process_agent_response(response)
        
        # Save assistant conversation
        conversation = Conversation(
            chatbot_id=self.chatbot.id,
            role="assistant",
            content=completion
        )
        await save_conversation(self.db, conversation)
        
        # Process markdown images
        completion = await self.process_markdown_images(completion)
        
        return {
            "response": completion,
            "files": files_base64
        }

    async def _process_agent_response(self, response) -> Tuple[str, List[Dict[str, Any]]]:
        """Process the agent response and return completion and files"""
        completion = ""
        files_base64 = []
        events = []
        # Process the stream of events
        for event in response.get("completion", []):
            if "chunk" in event:
                chunk = event["chunk"]
                if "bytes" in chunk:
                    text = chunk["bytes"].decode("utf-8")
                    completion += text
            
            # Process attachments if they exist
            if "files" in event:
                file_info = event["files"]
                for file_item in file_info.get("files", []):
                    file_bytes = file_item.get("bytes")
                    file_name = file_item.get("name")
                    file_type = file_item.get("type")
                    files_base64.append({
                        "name": file_name,
                        "type": file_type,
                        "base64": base64.b64encode(file_bytes).decode("utf-8")
                    })
            elif "returnControl" in event:
                events.append(event["returnControl"])
                    
        for event in events:
            new_completion = await self._process_return_control(
                event, self.knowledge_base_id, self.prompt
            )
            completion += new_completion
        
        # Build the response
        completion = completion if completion else "No se pudo obtener una respuesta del agente"
        
        return completion, files_base64

    async def _process_chunk_event(self, chunk: Dict[str, Any]) -> str:
        """Process a chunk event and returns the decoded text."""
        if "bytes" in chunk:
            return chunk["bytes"].decode("utf-8")
        return ""

    async def _extract_knowledge_base_params(self, parameters: List[Dict[str, Any]]) -> Tuple[str, str]:
        """Extract the knowledge base parameters from the list of parameters."""
        prompt_text = None
        tags = None
        
        for param in parameters:
            if param.get("name") in ["query", "prompt"]:
                prompt_text = param.get("value")
            if param.get("name") in ["tags", "filters"]:
                tags = param.get("value")
        return prompt_text, tags

    async def _create_formatted_response(self, invocation_id: str, action_group: str, 
                                        function_name: str, result_text: str) -> Dict[str, Any]:
        """Create a formatted response for the agent."""
        data = {
            "invocationId": invocation_id,
            "returnControlInvocationResults": [{
                "functionResult": {
                    "actionGroup": action_group,
                    "function": function_name,
                    "responseBody": {
                        "TEXT": {
                            "body": result_text
                        }
                    }
                }
            }]
        }
        return data
    
    def _check_if_general_tag_exists(self, mandatory_filters: Dict[str, str]) -> bool:
        """Check if the general key exists in the mandatory filters."""
        for filter_item in mandatory_filters:
            values = filter_item.get("values", [])
            if "general" in values:
                return True
        return False

    async def _validate_tags(self, tags: Dict[str, str]) -> Tuple[bool, str]:
        """Validate that the tags match the structure of mandatory filters."""
        if not self.course or not self.course.settings:
            return True, ""
        
        mandatory_filters = self.course.settings.get("knowledge_base_filter_structure_mandatory", [])
        
        for tag_key, tag_value in tags.items():
            # Search the key in the mandatory filters
            filter_found = False
            for filter_item in mandatory_filters:
                if filter_item.get("key") == tag_key:
                    filter_found = True
                    # Verify if it is a list or a string
                    if isinstance(tag_value, list):
                        # Verify if the values of the list are in the allowed values
                        for tag_value_item in tag_value:
                            if tag_value_item not in filter_item.get("values", []):
                                return tags, False, f"No se encuentra el valor '{tag_value_item}' para la key '{tag_key}', los valores disponibles son {filter_item.get('values')}, por favor intente nuevamente."
                    else:
                        # Verify if the value is in the allowed values
                        if tag_value not in filter_item.get("values", []):
                            return tags, False, f"No se encuentra el valor '{tag_value}' para la key '{tag_key}', los valores disponibles son {filter_item.get('values')}, por favor intente nuevamente."
                    break
            
            if not filter_found:
                return tags, False, f"No se encuentra la key '{tag_key}' en los filtros obligatorios."
        
        if self._check_if_general_tag_exists(mandatory_filters):
            tags = {
                **tags,
                "_general": "general"
            }

        return tags, True, ""

    async def _process_tags(self, tags: Union[str, List[str]]) -> Dict[str, List[str]]:
        """Process the tags and convert them into a dictionary of key-value.
        
        Args:
            tags: Can be a string or a list of strings with the format "key=value"
            
        Returns:
            Dict[str, List[str]]: Dictionary with the keys and lists of processed values
        """
        result_dict = {}
        
        if isinstance(tags, str):
            # If it is a string, process it as before
            tags_str = tags.replace("[", "").replace("]", "").replace('"', '')
            tag_pairs = [tag.strip() for tag in tags_str.split(",")]
            
            for pair in tag_pairs:
                if "=" in pair:
                    key, value = pair.split("=")
                    key = key.strip()
                    value = value.strip().replace(" ", "-")
                    if key in result_dict:
                        result_dict[key].append(value)
                    else:
                        result_dict[key] = [value]
                    
        elif isinstance(tags, list):
            # If it is already a list, process it directly
            for tag in tags:
                if isinstance(tag, str) and "=" in tag:
                    key, value = tag.split("=")
                    key = key.strip()
                    value = value.strip().replace(" ", "-")
                    if key in result_dict:
                        result_dict[key].append(value)
                    else:
                        result_dict[key] = [value]
        
        return result_dict

    async def _process_knowledge_base_retrieval(self, prompt_text: str, knowledge_base_id: str, tags: Optional[Dict[str, str]]) -> Dict[str, Any]:
        """Process the retrieval of information from the knowledge base.
        
        Args:
            prompt_text: The text of the prompt
            knowledge_base_id: ID of the knowledge base
            tags: Tags to filter the search
            is_external: Indicates if it is an external call
            
        Returns:
            Dict[str, Any]: Result of the retrieval
        """
        model_name = "anthropic.claude-3-7-sonnet-20250219-v1:0"
        
        try:
            error_message = ""
            if tags:
                # Validate the tags
                tags, is_valid, error_message = await self._validate_tags(tags)
                if not is_valid:
                    return {
                        "text": error_message
                    }
            
            return retrieve_and_generate(
                prompt=prompt_text,
                kb_id=knowledge_base_id,
                model_id=model_name,
                not_block_error=False,
                files=[],
                temperature=0.8,
                custom_query=tags if self.is_external else None
            )
        except Exception as e:
            return {
                "text": f"No se pudo obtener una respuesta del agente: {str(e)}"
            }

    async def _process_knowledge_base_invocation(self, function_input: Dict[str, Any], 
                                               invocation_id: str, knowledge_base_id: str, prompt: str) -> Tuple[Dict[str, Any], Optional[str]]:
        """Process a knowledge base invocation and returns the completed text and the updated session_id."""
        parameters = function_input.get("parameters", [])
        prompt_text, tags = await self._extract_knowledge_base_params(parameters)
        prompt_text = (
            # "Human: Please answer the following question about the content in the knowledge base:\n\n"
            f"{prompt}\n\n"
            f"<AWS_BEDROCK_AGENT_QUESTION> {prompt_text} </AWS_BEDROCK_AGENT_QUESTION>\n\n"
            f"<AWS_BEDROCK_AGENT_TAGS> {tags} </AWS_BEDROCK_AGENT_TAGS>\n\n"
        )
        print(f"prompt_text: {prompt_text}")
        
        if not (knowledge_base_id  and prompt_text):
            return "", []
        
        if self.is_external and tags:
            tags = await self._process_tags(tags)
        
        retrieve_result = await self._process_knowledge_base_retrieval(prompt_text, knowledge_base_id, tags)
        
        result_text = f"""<KNOWLEDGE_BASE_RESPONSE_TEXT>{retrieve_result.get("text", "")}</KNOWLEDGE_BASE_RESPONSE_TEXT>"""
        if "contexts" in retrieve_result:
            result_text += f"\n<USER_PROMPT>{prompt}</USER_PROMPT>\n"
            index = 0
            for context in retrieve_result.get("contexts", []):
                if "text" in context:
                    result_text += f"""<CITATION_{index}>{context.get("text")}</CITATION_{index}>"""
                    index += 1

        formatted_response = await self._create_formatted_response(
            invocation_id, function_input.get("actionGroup"), function_input.get("function"), result_text
        )

        # Invoke Bedrock agent
        response = invoke_bedrock_agent(
            agent_id=self.agent["with_knowledge_base"].agent_id if not self.is_external else self.agent_id,
            agent_alias_id=self.agent["with_knowledge_base"].alias_id if not self.is_external else self.alias_id,
            input_text=json.dumps(formatted_response),
            session_id=str(self.chatbot.session_id) if not self.is_external else str(self.session_id),
            files=[],
            memory_id=str(self.chatbot.memory_id) if not self.is_external else None,
            invocationId=invocation_id,
            returnControlInvocationResults=formatted_response.get("returnControlInvocationResults", [])
        )

        completion, files_base64 = await self._process_agent_response(response)

        if self.analytics_processor:
            self.analytics_processor.process_and_add_analytics(model="default", request_prompt=self.prompt, response=completion)

        return completion, files_base64
    
    async def _process_chatbot_context(self, function_input: Dict[str, Any], invocation_id: str) -> Tuple[str, List[Dict[str, Any]]]:
        """Process the chatbot context."""
        result_text = json.dumps({
            "chatbot_id": str(self.course.id),
            "knowledge_base_id": self.course.knowledge_base_id,
            "settings": self.course.settings
        })

        # Create the formatted response for the agent
        formatted_response = await self._create_formatted_response(
            invocation_id, function_input.get("actionGroup"), function_input.get("function"), result_text
        )

        # Invocar al agente con la respuesta formateada usando los IDs del agente original
        response = invoke_bedrock_agent(
            agent_id=function_input.get("agentId"),
            agent_alias_id=self.alias_id,
            input_text=json.dumps(formatted_response),
            session_id=str(self.session_id),
            files=[],
            invocationId=invocation_id,
            returnControlInvocationResults=formatted_response.get("returnControlInvocationResults", [])
        )

        # Process the agent response
        completion, files_base64 = await self._process_agent_response(response)

        if self.analytics_processor:
            self.analytics_processor.process_and_add_analytics(model="default", request_prompt=self.prompt, response=completion)

        return completion, files_base64

    async def _process_function_invocation(self, function_input: Dict[str, Any], 
                                          invocation_id: str, knowledge_base_id: Optional[str], prompt: str) -> Tuple[Dict[str, Any], Optional[str]]:
        """Process a function invocation and returns the completed text and the updated session_id."""
        action_group = function_input.get("actionGroup")
        function_name = function_input.get("function")
        
        if (action_group == "action_group_knowledgebase_call" or action_group == "ag1") and function_name == "knowledgebase":
            return await self._process_knowledge_base_invocation(function_input, invocation_id, knowledge_base_id, prompt)
        if (action_group == "action_group_chatbot_context" or action_group == "ag1") and function_name == "Chatbot_context":
            completion, _ = await self._process_chatbot_context(function_input, invocation_id)
            return completion, None
        if (action_group == "action_group_chatbot_context" or action_group == "ag1") and function_name == "knowledge_base_question":
            return await self._process_knowledge_base_invocation(function_input, invocation_id, knowledge_base_id, prompt)
        return "", []
    
    async def _process_return_control(self, return_control: Dict[str, Any], knowledge_base_id: Optional[str], prompt: str) -> str:
        """
        Process a return control event and returns the completed text and the updated session_id.
        """
        invocation_id = return_control.get("invocationId")
        invocation_inputs = return_control.get("invocationInputs", [])
        
        completion = ""
        for invocation_input in invocation_inputs:
            if "functionInvocationInput" in invocation_input:
                function_input = invocation_input["functionInvocationInput"]
                new_completion, _ = await self._process_function_invocation(
                    function_input, invocation_id, knowledge_base_id, prompt
                )
                completion += new_completion
        
        return completion

    async def process_conversation_with_knowledge_base(self, prompt: str, knowledge_base_id: str, block_return_control: bool = False) -> Dict[str, Any]:
        """
        Process a chatbot conversation following the flow:
        1. Generate the conversation structure using the knowledge base ID
        2. Invoke the Bedrock agent with the conversation structure
        3. Process the agent's response
        4. If a returnControl event is received, process the retrieve_and_generate request
        5. Return the results to the agent to complete the query
        """
        try:

            response = invoke_bedrock_agent(
                agent_id=self.agent["with_knowledge_base"].agent_id if not self.is_external else self.agent_id,
                agent_alias_id=self.agent["with_knowledge_base"].alias_id if not self.is_external else self.alias_id,
                input_text=prompt,
                session_id=self.chatbot.session_id,
                files=[],
                memory_id=self.chatbot.memory_id
            )

            # Process the agent's response
            completion = ""
            # Process the stream of events
            events = []
            for event in response.get("completion", []):
                if "chunk" in event:
                    completion += await self._process_chunk_event(event["chunk"])
                elif "returnControl" in event and not block_return_control:
                        events.append(event["returnControl"])
                    
            for event in events:
                new_completion = await self._process_return_control(
                    event, knowledge_base_id, prompt
                )
                completion += new_completion
            
            return {
                "response": completion,
            }

        except Exception as e:
            raise HTTPException(
                status_code=500,
                detail=f"Error in the chatbot processing: {str(e)}"
            )
    
    def _get_system_prompt(self) -> str:
        """Get the system prompt for the chatbot."""
        try:
            settings = self.course.settings
            if settings:
                return settings.get("system_prompt", "")
        except Exception as e:
            logger.error(f"Error getting the system prompt: {e}")
            return ""

    async def process_external_conversation(self, block_return_control: bool = False) -> Dict[str, Any]:
        """
        Process a chatbot conversation following the flow:
        1. Generate the conversation structure using the knowledge base ID
        2. Invoke the Bedrock agent with the conversation structure
        3. Process the agent's response
        4. If a returnControl event is received, process the retrieve_and_generate request
        5. Return the results to the agent to complete the query
        """
        try:
            if not self.session_id:
                self.session_id = str(uuid.uuid4())

            if self.save_conversation:
                # Get the last 30 conversations
                conversations = await get_last_30_conversations(self.db, self.chatbot.id)

                # Prepare the last 30 conversations
                conversation_filtered_pattern = self._build_conversation_history(conversations)
                
                # Save user conversation
                conversation = Conversation(
                    chatbot_id=self.chatbot.id,
                    role="user",
                    content=json.dumps(self.prompt) if isinstance(self.prompt, dict) else self.prompt
                )
                await save_conversation(self.db, conversation)

                if len(conversations) == 0:
                    self.prompt = f"<USER_PROMPT>{self.prompt}</USER_PROMPT>\n<ID>{str(self.chatbot.id)}</ID>"
                
                if len(self._get_system_prompt()) > 0:
                    self.prompt = f"<SYSTEM_PROMPT>{self._get_system_prompt()}</SYSTEM_PROMPT>\n\n{self.prompt}"

            # Invoke Bedrock agent
            response = invoke_bedrock_agent(
                agent_id=self.agent_id,
                agent_alias_id=self.alias_id,
                input_text=self.prompt,
                session_id=self.session_id,
                files=[],
                conversation_history=conversation_filtered_pattern if self.save_conversation else None  
            )


            # Process the agent's response
            completion = ""
            # Process the stream of events
            events = []
            for event in response.get("completion", []):
                if "chunk" in event:
                    completion += await self._process_chunk_event(event["chunk"])
                elif "returnControl" in event and not block_return_control:
                        events.append(event["returnControl"])
                    
            for event in events:
                new_completion = await self._process_return_control(
                    event, self.knowledge_base_id, self.prompt
                )
                completion += new_completion
            
            if self.analytics_processor:
                self.analytics_processor.process_and_add_analytics(model="anthropic.claude-3-7-sonnet-20250219-v1:0", request_prompt=self.prompt, response=completion)

            if self.save_conversation:
                # Save assistant conversation
                conversation = Conversation(
                    chatbot_id=self.chatbot.id,
                    role="assistant",
                    content=completion
                )
                await save_conversation(self.db, conversation)
                
                # Process markdown images
                completion = await self.process_markdown_images(completion)

            return {
                "response": completion,
            }

        except Exception as e:
            raise HTTPException(
                status_code=500,
                detail=f"Error in the chatbot processing: {str(e)}"
            )
