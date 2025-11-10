# © [2025] EDT&Partners. Licensed under CC BY 4.0.

"""
Service for handling AI using Strands
"""
import json
import uuid
from botocore.exceptions import ClientError
import asyncio
import base64
import os
from dotenv import load_dotenv
load_dotenv()
from database.schemas import Routine
from services.strands_service import StrandsService
from interfaces.ai_interface import AIServiceInterface
from utility.aws_clients import bedrock_client

class AIService(AIServiceInterface):
    """Service for handling AI using Strands"""
    
    def __init__(self, model_id: str = None, model_region: str = None):
        """Initializes the AI service"""
        self.model_id = model_id
        self.model_region = model_region
        self.strands_service = StrandsService(model_id, model_region)
        self._validate_aws_credentials()
    
    def _validate_aws_credentials(self):
        """Validates that the AWS credentials are configured"""
        try:
            bedrock = bedrock_client
            # Try to make a simple call to validate credentials
            bedrock.list_foundation_models()
        except ClientError as e:
            raise Exception(f"Error in AWS credentials: {str(e)}")
        except Exception as e:
            raise Exception(f"Error validating AWS: {str(e)}")
    
    async def generate_content(
        self, 
        prompt: str
    ) -> str:
        """
        Generates content using AI
        
        Args:
            prompt (str): Prompt to generate content
            max_tokens (Optional[int]): Maximum number of tokens
            temperature (Optional[float]): Temperature for the generation
            
        Returns:
            str: Generated content
        """
        try:
            # Default system prompt for text generation
            system_prompt = "You are a helpful assistant that generates high-quality text content. Respond clearly, concisely, and well-structured."
            
            # Generate content using the Strands service
            result = await self.strands_service.generate_text(
                prompt=prompt,
                system_prompt=system_prompt
            )
            
            return result
            
        except Exception as e:
            raise Exception(f"Error generando contenido: {str(e)}")
    
    async def get_status(self) -> str:
        """
        Gets the status of the AI service
        
        Returns:
            str: Status of the service
        """
        try:
            # Verify that the Strands service is working
            status = await self.strands_service.get_status()
            return f"IA Service: {status}"
        except Exception as e:
            return f"Error: {str(e)}"
    
    async def generate_html_content(self, prompt: str, system_prompt: str, context: str) -> str:
        """
        Generates HTML content using AI
        
        Args:
            prompt (str): Prompt to generate HTML content
            system_prompt (str): System prompt to define the behavior
            context (str): Context to generate HTML content
            
        Returns:
            str: Generated HTML content
        """
        try:
            # Generate HTML content using the Strands service
            result = await self.strands_service.generate_html_content(
                prompt=prompt,
                system_prompt=system_prompt,
                context=context
            )
            return result
        except Exception as e:
            raise Exception(f"Error generating HTML content: {str(e)}")
    
    async def generate_routines_content(self, prompt_data, system_prompt: str, content_type: str) -> str:
        """
        Generates HTML content for multiple routines in parallel with optimizations
        
        Args:
            prompt_data: Object with contexts and routines
            system_prompt (str): System prompt to define the behavior
            content_type (str): Type of content to generate
        Returns:
            str: Concatenated HTML content of all routines
        """
        try:
            system_prompt = ""
            # Build the base prompt with all contexts
            context_prompt = "Contextos:\n"
            for context in prompt_data.contexts:
                context_prompt += f"- {context.title}: {context.content}\n"
            context_prompt += "\n"
            context_prompt += """
                IMPORTANT FORMATTING RULES:
                1. ALWAYS return valid and complete HTML tags.
                2. ALWAYS use the largest possible width for the content (width: 100%).
                3. Do not add the <html> or <body> tags at the beginning or end.
                4. Do not add additional text at the beginning or end.
                5. Do not add comments at the beginning or end.
                """ if content_type == "ai_html" else ""
            context_prompt += "\n"
            context_prompt += "Index of contents:\n"
            
            # Variables for numbering
            subtitle_counter = 0
            subitem_counter = 0
            
            for routine in prompt_data.routines:
                if routine.type == "title":
                    context_prompt += f"- title: {routine.content}\n"
                elif routine.type == "subtitle":
                    subtitle_counter += 1
                    subitem_counter = 0  # Reset counter of subitems
                    context_prompt += f"- {subtitle_counter}. {routine.content}\n"
                elif routine.type == "subitem":
                    subitem_counter += 1
                    # Use lowercase letters for subitems (a, b, c, etc.)
                    subitem_letter = chr(96 + subitem_counter)  # 97 = 'a', 98 = 'b', etc.
                    context_prompt += f"- {subtitle_counter}.{subitem_letter} {routine.content}\n"
            
            context_prompt += "\n"
            
            # Add a "index" type at the beginning of "prompt_data.routines" to generate the index of contents structure
            prompt_data.routines.insert(1, Routine(
                id=None,
                type="index",
                content="Index of contents"
            ))

            subtitle_counter = 0

            # Create tasks to process each routine in parallel
            tasks = []
            task_descriptions = []

            for i, routine in enumerate(prompt_data.routines):
                # Determine if the current subtitle has subitems
                has_subitems = False
                if routine.type == "subtitle":
                    # Search for subitems after this subtitle until the next subtitle or title
                    for j in range(i + 1, len(prompt_data.routines)):
                        next_routine = prompt_data.routines[j]
                        if next_routine.type in ["title", "subtitle"]:
                            break
                        if next_routine.type == "subitem":
                            has_subitems = True
                            break
                
                # Update counters according to the type
                if routine.type == "subtitle":
                    subtitle_counter += 1
                    subitem_counter = 0  # Reset counter of subitems
                elif routine.type == "subitem":
                    subitem_counter += 1
                
                # Build the specific prompt according to the type and context
                if content_type == "ai_md":
                    if routine.type == "index":
                        task_description = "Generate the index of contents with hierarchy of number and letter. Only add the title Index and then the list of contents.\n"
                    elif routine.type == "title":
                        task_description = f"""Generate the title '{routine.content}' in markdown format\n"""
                    elif routine.type == "subtitle" and has_subitems:
                        task_description = f"Generate the subtitle {subtitle_counter}. {routine.content} in markdown format\n"
                    elif routine.type == "subtitle" and not has_subitems:
                        task_description = f"Generate only the content related to {subtitle_counter}. {routine.content} in markdown format\n"
                    elif routine.type == "subitem":
                        subitem_letter = chr(96 + subitem_counter)  # 97 = 'a', 98 = 'b', etc.
                        task_description = f"Generate only the content related to {subtitle_counter}.{subitem_letter} {routine.content} in markdown format\n"
                    else:
                        task_description = f"Generate only the content related to {routine.content} in markdown format\n"
                else:
                    if routine.type == "index":
                        task_description = "Generate the index of contents with hierarchy of number and letter. Only add the title Index and then the list of contents.\n"
                    elif routine.type == "title":
                        task_description = f"""Generate the tag for the title '{routine.content}'\n"""
                    elif routine.type == "subtitle" and has_subitems:
                        task_description = f"Generate the tag for the subtitle {subtitle_counter}. {routine.content}\n"
                    elif routine.type == "subtitle" and not has_subitems:
                        task_description = f"Generate only the content related to {subtitle_counter}. {routine.content}\n"
                    elif routine.type == "subitem":
                        subitem_letter = chr(96 + subitem_counter)  # 97 = 'a', 98 = 'b', etc.
                        task_description = f"Generate only the content related to {subtitle_counter}.{subitem_letter} {routine.content}\n"
                    else:
                        task_description = f"Generate only the content related to {routine.content}\n"
                
                # Combine contexts with the specific routine
                full_prompt = context_prompt + f"Task to perform:\n{task_description}"
                
                # Create asynchronous task with retries for this routine
                if content_type == "ai_html":
                    task = self._generate_html_with_retry(
                        prompt=full_prompt,
                        system_prompt=system_prompt,
                        context="",
                        max_retries=int(os.getenv("MAX_RETRIES", "3"))
                    )
                elif content_type == "ai_md":
                    task = self._generate_md_with_retry(
                        prompt=full_prompt,
                        system_prompt=system_prompt,
                        context="",
                        max_retries=int(os.getenv("MAX_RETRIES", "3"))
                    )
                tasks.append(task)
                task_descriptions.append(task_description)
            
            # Execute all tasks in parallel with concurrency limit
            max_concurrent = int(os.getenv("MAX_CONCURRENT_TASKS", "3"))  # Use dynamic configuration
            results = await self._execute_tasks_with_semaphore(tasks, max_concurrent)
            
            # Concatenar en "agent_message" y "content"
            agent_messages = [result[0] for result in results]
            contents = [result[1] for result in results]

            # Join the agent_messages and contents
            agent_message = "\n".join(agent_messages)
            content = "\n".join(contents)

            # Remove "\n    " from agent_message and content
            agent_message = agent_message.replace("\n    ", "")
            content = content.replace("\n    ", "")
            
            return full_prompt,agent_message, content
            
        except Exception as e:
            raise Exception(f"Error generating routines content: {str(e)}")

    async def _generate_html_with_retry(self, prompt: str, system_prompt: str, context: str, max_retries: int = 3) -> str:
        """
        Generates HTML with automatic retries in case of error
        
        Args:
            prompt (str): Prompt para generar contenido
            system_prompt (str): System prompt
            context (str): Additional context
            max_retries (int): Maximum number of retries
            
        Returns:
            str: Generated HTML content
        """
        for attempt in range(max_retries):
            try:
                # Use the local Strands service instead of HTTP call
                result = await self.strands_service.generate_html_content(
                    prompt=prompt,
                    system_prompt=system_prompt,
                    context=context
                )

                # Extract the MD content with CONTENT tag
                result = self.extract_xml_content(result)
                return result["agent_message"], result["content"]
            except Exception as e:
                if attempt == max_retries - 1:  # Last attempt
                    print(f"❌ Error después de {max_retries} intentos: {str(e)}")
                    raise e
                else:
                    print(f"⚠️ Attempt {attempt + 1} failed, retrying... Error: {str(e)}")
                    await asyncio.sleep(os.getenv("RETRY_DELAY_BASE", "1.0") * (attempt + 1))  # Exponential backoff configurable
    
    async def _generate_md_with_retry(self, prompt: str, system_prompt: str, context: str, max_retries: int = 3) -> str:
        """
        Generates MD with automatic retries in case of error
        
        Args:
            prompt (str): Prompt para generar contenido
            system_prompt (str): System prompt
            context (str): Additional context
            max_retries (int): Maximum number of retries
            
        Returns:
            str: Generated MD content
        """
        for attempt in range(max_retries):
            try:
                # Use the local Strands service instead of HTTP call
                result = await self.strands_service.generate_markdown_content(
                    prompt=prompt,
                    system_prompt=system_prompt,
                    context=context
                )

                # Extract the MD content with CONTENT tag
                result = self.extract_xml_content(result)
                return result["agent_message"], result["content"]
            except Exception as e:
                if attempt == max_retries - 1:  # Last attempt
                    print(f"❌ Error después de {max_retries} intentos: {str(e)}")
                    raise e
                else:
                    print(f"⚠️ Attempt {attempt + 1} failed, retrying... Error: {str(e)}")
                    await asyncio.sleep(os.getenv("RETRY_DELAY_BASE", "1.0") * (attempt + 1))  # Exponential backoff configurable

    async def _execute_tasks_with_semaphore(self, tasks: list, max_concurrent: int) -> list:
        """
        Executes tasks with concurrency limit using semaphore
        
        Args:
            tasks (list): List of asynchronous tasks
            max_concurrent (int): Maximum number of concurrent tasks
            
        Returns:
            list: Results of the tasks
        """
        semaphore = asyncio.Semaphore(max_concurrent)
        total_tasks = len(tasks)
        completed_tasks = 0
        
        async def execute_with_semaphore(task, task_index):
            nonlocal completed_tasks
            async with semaphore:
                try:
                    agent_message, content = await task
                    completed_tasks += 1
                    print(f"✅ Tarea {task_index + 1}/{total_tasks} completada ({completed_tasks}/{total_tasks})")
                    return agent_message, content
                except Exception as e:
                    completed_tasks += 1
                    print(f"❌ Tarea {task_index + 1}/{total_tasks} falló ({completed_tasks}/{total_tasks}): {str(e)}")
                    raise e
        
        # Create tasks with semaphore and monitoring
        semaphore_tasks = [execute_with_semaphore(task, i) for i, task in enumerate(tasks)]
        
        print(f"🚀 Iniciando ejecución de {total_tasks} tareas con límite de {max_concurrent} concurrentes")
        
        # Execute all tasks
        results = await asyncio.gather(*semaphore_tasks, return_exceptions=True)
        
        # Handle individual errors
        processed_results = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                print(f"❌ Error en tarea {i}: {str(result)}")
                # Return HTML of error to maintain order
                processed_results.append(f"<div class='error'>Error generando contenido: {str(result)}</div>")
            else:
                processed_results.append(result)
        
        # Check if processed_results is a list of tuples
        print(f"🎉 Process completed: {len(processed_results)/2}/{total_tasks} successful tasks")
        
        return processed_results
    
    def _should_use_iframe(self, html_content: str) -> bool:
        """
        Determines if the HTML content should go in an iframe
        
        Args:
            html_content (str): HTML content to evaluate
            
        Returns:
            bool: True if it should use iframe, False if it goes directly in TipTap
        """
        # Criteria to use iframe
        complex_elements = [
            '<table',           # Tables
            '<canvas',          # Graphics
            '<form',            # Forms
            '<script',          # JavaScript
            'Chart.js',         # Specific graphics
            'oninput',          # Interactive events
            '<input',           # Inputs
            '<button',          # Buttons
            '<select',          # Selects
            '<textarea',        # Text areas
            'onclick',          # Click events
            'onchange',         # Change events
            'addEventListener', # Event listeners
            'getElementById',   # DOM manipulation
            'style="',          # Complex inline styles
            'background-color', # Background colors
            'border-radius',    # Rounded borders
            'box-shadow',       # Shadows
            'transform',        # Transformations
            'animation'         # Animations
        ]
        
        # If it contains any complex element, use iframe
        for element in complex_elements:
            if element in html_content:
                return True
        
        # If the content is too long (>500 characters), use iframe
        if len(html_content) > 500:
            return True
            
        return False
    
    def _create_iframe_content(self, html_content: str) -> str:
        """
        Creates the HTML for an iframe with the specified content
        
        Args:
            html_content (str): HTML content to put in the iframe
            
        Returns:
            str: HTML of the iframe with the content
        """
        # Encode the HTML content in base64
        encoded_content = base64.b64encode(html_content.encode('utf-8')).decode('utf-8')
        
        # Create the iframe that points to the endpoint
        iframe_html = f'''
        <div class="iframe-container" style="margin: 20px 0; border: 1px solid #e0e0e0; border-radius: 8px; overflow: hidden; background: white;">
            <iframe 
                src="/ai/serve-iframe-content?content={encoded_content}"
                style="width: 100%; height: 500px; border: none; display: block;"
                sandbox="allow-scripts allow-same-origin allow-forms allow-popups allow-modals"
                title="Contenido interactivo"
                allowfullscreen="true"
            ></iframe>
        </div>
        '''
        
        return iframe_html
    
    async def generate_routines_content_hybrid(self, prompt_data, system_prompt: str) -> dict:
        """
        Generates HTML content for multiple routines using hybrid approach with optimizations
        
        Args:
            prompt_data: Object with contexts and routines
            system_prompt (str): System prompt to define the behavior
            
        Returns:
            dict: Dictionary with simple and complex content separated
        """
        try:
            # Build the base prompt with all contexts
            context_prompt = "Contextos:\n"
            for context in prompt_data.contexts:
                context_prompt += f"- {context.title}: {context.content}\n"
            context_prompt += "\n"
            context_prompt += """
                IMPORTANT FORMATTING RULES:
                1. ALWAYS return valid and complete HTML tags.
                2. DO NOT add the <html> or <body> tags at the beginning or end.
                3. DO NOT add additional text at the beginning or end.
                4. DO NOT add comments at the beginning or end.
                """
            context_prompt += "\n"
            context_prompt += "Index of contents:\n"
            
            # Variables for numbering
            subtitle_counter = 0
            subitem_counter = 0
            
            for routine in prompt_data.routines:
                if routine.type == "title":
                    context_prompt += f"- title: {routine.content}\n"
                elif routine.type == "subtitle":
                    subtitle_counter += 1
                    subitem_counter = 0  # Reset counter of subitems
                    context_prompt += f"- {subtitle_counter}. {routine.content}\n"
                elif routine.type == "subitem":
                    subitem_counter += 1
                    # Use lowercase letters for subitems (a, b, c, etc.)
                    subitem_letter = chr(96 + subitem_counter)  # 97 = 'a', 98 = 'b', etc.
                    context_prompt += f"- {subtitle_counter}.{subitem_letter} {routine.content}\n"
            
            context_prompt += "\n"
            
            # Add a "index" type at the beginning of "prompt_data.routines" to generate the index of contents structure
            prompt_data.routines.insert(1, Routine(
                id=None,
                type="index",
                content="Index of contents"
            ))

            subtitle_counter = 0
            subitem_counter = 0
            
            # Create tasks to process each routine in parallel
            tasks = []
            task_descriptions = []

            for i, routine in enumerate(prompt_data.routines):
                # Determine if the current subtitle has subitems
                has_subitems = False
                if routine.type == "subtitle":
                    # Search for subitems after this subtitle until the next subtitle or title
                    for j in range(i + 1, len(prompt_data.routines)):
                        next_routine = prompt_data.routines[j]
                        if next_routine.type in ["title", "subtitle"]:
                            break
                        if next_routine.type == "subitem":
                            has_subitems = True
                            break
                
                # Update counters according to the type
                if routine.type == "subtitle":
                    subtitle_counter += 1
                    subitem_counter = 0  # Reset counter of subitems
                elif routine.type == "subitem":
                    subitem_counter += 1
                
                # Build the specific prompt according to the type and context
                if routine.type == "index":
                    task_description = "Generate the index of contents with hierarchy of number and letter. Only add the title Index and then the list of contents.\n"
                elif routine.type == "title":
                    task_description = f"""Generate the tag for the title '{routine.content}'\n"""
                elif routine.type == "subtitle" and has_subitems:
                    task_description = f"Generate the tag for the subtitle {subtitle_counter}. {routine.content}\n"
                elif routine.type == "subtitle" and not has_subitems:
                    task_description = f"Generate the content related to {subtitle_counter}. {routine.content}\n"
                elif routine.type == "subitem":
                    subitem_letter = chr(96 + subitem_counter)  # 97 = 'a', 98 = 'b', etc.
                    task_description = f"Generate the content related to {subtitle_counter}.{subitem_letter} {routine.content}\n"
                else:
                    task_description = f"Generate the content related to {routine.content}\n"
                
                # Combine contexts with the specific routine
                full_prompt = context_prompt + f"Task to perform:\n{task_description}"
                
                print(full_prompt)
                
                # Create asynchronous task with retries for this routine
                task = self._generate_html_with_retry(
                    prompt=full_prompt,
                    system_prompt=system_prompt,
                    context="",
                    max_retries=int(os.getenv("MAX_RETRIES", "3"))
                )
                tasks.append(task)
                task_descriptions.append(task_description)
            
            # Execute all tasks in parallel with concurrency limit
            max_concurrent = int(os.getenv("MAX_CONCURRENT_TASKS", "3"))  # Use dynamic configuration
            results = await self._execute_tasks_with_semaphore(tasks, max_concurrent)
            
            # Separate simple and complex content
            simple_content = []
            complex_content = []
            
            for i, html_content in enumerate(results):
                if isinstance(html_content, str) and self._should_use_iframe(html_content):
                    # Complex content → iframe
                    iframe_html = self._create_iframe_content(html_content)
                    complex_content.append({
                        "index": i,
                        "type": "iframe",
                        "content": iframe_html,
                        "original_content": html_content
                    })
                elif isinstance(html_content, str):
                    # Simple content → TipTap directly
                    simple_content.append({
                        "index": i,
                        "type": "simple",
                        "content": html_content
                    })
                else:
                    # Error in generation
                    simple_content.append({
                        "index": i,
                        "type": "error",
                        "content": f"<div class='error'>Error generando contenido: {str(html_content)}</div>"
                    })
            
            return {
                "simple_content": simple_content,
                "complex_content": complex_content,
                "total_items": len(results)
            }
            
        except Exception as e:
            raise Exception(f"Error generating hybrid routines content: {str(e)}")
    
    async def generate_text_with_agent(self, prompt: str) -> str:
        """
        Generates text using the Strands Agent
        
        Args:
            prompt (str): Prompt to generate content
            
        Returns:
            str: Content generated by the agent
        """
        try:
            print(prompt)
            result = await self.strands_service.generate_text_with_agent(prompt=prompt)
            return result
        except Exception as e:
            raise Exception(f"Error generando texto con agent: {str(e)}")

    def _generate_md_system_prompt(self, user_profile: str) -> str:
        """
        Generates a system prompt for markdown content generation
        
        Args:
            user_profile (str): User profile information
            
        Returns:
            str: System prompt for markdown generation
        """
        system_prompt = f"""Eres un asistente educativo especializado en generar contenido en markdown para un chat educativo.

PERFIL DEL USUARIO: {user_profile}

INSTRUCCIONES IMPORTANTES:
1. Debes responder SIEMPRE en el siguiente formato XML específico:
<RESPONSE>
    <AGENT_MESSAGE>
<--- Aquí irá el mensaje que verá en el chat --->
    </AGENT_MESSAGE>
    <CONTENT>
<--- Aquí irá el contenido generado en markdown --->
    </CONTENT>
</RESPONSE>

2. El contenido en <CONTENT> debe estar en formato markdown válido
3. El mensaje en <AGENT_MESSAGE> debe ser una respuesta natural y útil para el usuario
4. Adapta tu respuesta al perfil del usuario proporcionado
5. Genera contenido educativo de alta calidad
6. Usa el markdown para estructurar el contenido de manera clara y organizada

FORMATO DE RESPUESTA REQUERIDO:
- <AGENT_MESSAGE>: Mensaje directo al usuario (texto plano)
- <CONTENT>: Contenido educativo en markdown (títulos, listas, tablas, etc.)

Ejemplo de respuesta esperada:
<RESPONSE>
    <AGENT_MESSAGE>
He generado un resumen completo del tema que solicitaste. El contenido incluye los conceptos principales organizados de manera clara y fácil de entender.
    </AGENT_MESSAGE>
    <CONTENT>
# Resumen del Tema

## Conceptos Principales

### 1. Introducción
- Punto clave 1
- Punto clave 2

### 2. Desarrollo
1. **Concepto A**: Descripción detallada
2. **Concepto B**: Explicación con ejemplos

## Conclusión
Resumen de los puntos más importantes.
    </CONTENT>
</RESPONSE>
"""
        
        return system_prompt

    def extract_xml_content(self, xml_response: str) -> dict:
        """
        Extracts agent_message and content from XML response
        
        Args:
            xml_response (str): XML response from AI
            
        Returns:
            dict: Dictionary with agent_message and content
        """
        try:
            import re

            # Remove all <reasoning> tags and their content
            xml_response = re.sub(r'<reasoning>(.*?)</reasoning>', '', xml_response, flags=re.DOTALL)
            print(xml_response)
            
            # Extract AGENT_MESSAGE content
            agent_message_pattern = r'<AGENT_MESSAGE>(.*?)</AGENT_MESSAGE>'
            agent_message_match = re.search(agent_message_pattern, xml_response, re.DOTALL)
            agent_message = agent_message_match.group(1).strip() if agent_message_match else ""
            
            # Extract CONTENT
            content_pattern = r'<CONTENT>(.*?)</CONTENT>'
            content_match = re.search(content_pattern, xml_response, re.DOTALL)
            content = content_match.group(1).strip() if content_match else ""

            # Extract TITLE
            title_pattern = r'<TITLE>(.*?)</TITLE>'
            title_match = re.search(title_pattern, xml_response, re.DOTALL)
            title = title_match.group(1).strip() if title_match else ""
            
            return {
                "agent_message": agent_message,
                "content": content,
                "title": title
            }
            
        except Exception as e:
            # If extraction fails, return the original response as content
            return {
                "agent_message": "Respuesta generada exitosamente",
                "content": xml_response,
                "title": ""
            }

    async def generate_markdown_content(self, db, prompt: str, user_profile: str, system_prompt: str = None, content: str = "", message_history: list = None, model_id: str = None, context: list = [], deepThinkingEnabled: bool = False) -> dict:
        """
        Generates markdown content using AI with structured response format
        
        Args:
            prompt (str): User prompt
            user_profile (str): User profile information
            system_prompt (str): Optional custom system prompt
            content (str): Document content being manipulated
            message_history (list): List of message history
        Returns:
            dict: Dictionary with agent_message and content extracted from XML
        """
        try:
            # Generate system prompt if not provided
            if not system_prompt:
                system_prompt = self._generate_md_system_prompt(user_profile)
            
            # Build the full prompt with context
            full_prompt = prompt
            if content and content.strip():
                full_prompt = f"CONTENIDO DEL DOCUMENTO:\n{content}\n\nPETICIÓN DEL USUARIO:\n{prompt}"

            parts = []
            for f in context:
                title = getattr(f, "title", "") or ""
                doc_id = getattr(f, "id", None) or getattr(f, "uuid", None) or title
                parts.append({"title": title, "id": str(doc_id), "note": "[document attached — use file_read(id)]"})

            if parts:
                message_history.append({
                    "role": "user",
                    "content": [
                        {"text": "Se adjuntan documentos. Use la tool 'file_read' con los ids para obtener su contenido cuando lo necesite."},
                        {"text": json.dumps(parts)}
                    ]
                })

            strands_service = StrandsService(self.model_id, self.model_region, db, deepThinkingEnabled)
            # Generate content using the Strands service
            xml_result = await strands_service.generate_text(
                prompt=full_prompt,
                system_prompt=system_prompt,
                messages=message_history,
            )
            
            # Extract agent_message and content from XML
            extracted_content = self.extract_xml_content(xml_result)
            
            return extracted_content, xml_result
            
        except Exception as e:
            raise Exception(f"Error generando contenido markdown: {str(e)}")
    
    async def generate_title_from_prompt(self, prompt: str = "Create an example title name") -> str:
        """
        Generates a title from a prompt
        
        Args:
            prompt (str): Prompt to generate the title

        Returns:
            str: Title generated from the prompt
        """
        try:
            system_prompt = """
            You are an expert in creating titles. 
            Your task is to generate a title for a conversation.
            The title must be short and concise.

            Your response must be only in the following format:
            <TITLE>
            <--- Aquí irá el título generado --->
            </TITLE>
            """
            # Generate a title for the conversation
            title = await self.strands_service.generate_text(
                prompt=prompt,
                system_prompt=system_prompt
            )
            title = self.extract_xml_content(title)
            return title['title']
        except Exception as e:
            raise Exception(f"Error generating title from prompt: {str(e)}")

    def clean_and_get_property(self, data, property_name: str, fallback_properties: list = None) -> list:
        """
        Cleans and extracts a specific property from the JSON
        
        Args:
            data: Can be a JSON string, dict or list
            property_name: Name of the property to extract (e.g: "index", "routines", "html_content")
            fallback_properties: List of alternative properties if the main one is not found
            
        Returns:
            list: Cleaned array of the requested property
        """
        try:
            # If it is a string, try to parse it as JSON
            if isinstance(data, str):
                # Clean the string of possible extra characters
                cleaned_data = data.strip()
                
                # Search for the first { and the last }
                start = cleaned_data.find('{')
                end = cleaned_data.rfind('}')
                
                if start != -1 and end != -1:
                    cleaned_data = cleaned_data[start:end + 1]
                
                # Try to parse as JSON
                try:
                    data = json.loads(cleaned_data)
                except json.JSONDecodeError:
                    # If it fails, try to extract only the array using regex
                    import re
                    array_pattern = r'\[\s*\{[^\]]*\}\s*\]'
                    match = re.search(array_pattern, cleaned_data, re.DOTALL)
                    if match:
                        try:
                            data = json.loads(match.group())
                            return data
                        except json.JSONDecodeError:
                            pass
            
            # If it is already a dict, extract the requested property
            if isinstance(data, dict):
                # Search for the main property
                if property_name in data:
                    if isinstance(data[property_name], list):
                        return data[property_name]
                    elif isinstance(data[property_name], str):
                        return [data[property_name]]
                
                # Search for alternative properties
                if fallback_properties:
                    for fallback_prop in fallback_properties:
                        if fallback_prop in data and isinstance(data[fallback_prop], list):
                            return data[fallback_prop]
                
                # If it does not have the property but is a list of valid objects
                if all(isinstance(item, dict) and "type" in item and "content" in item for item in data.values()):
                    return list(data.values())
            
            # If it is already a list, return it directly
            if isinstance(data, list):
                return data
            
            # If it cannot be processed, return empty list
            return []
            
        except Exception as e:
            print(f"⚠️ Error cleaning property '{property_name}': {str(e)}")
            return []
    
    def _clean_and_get_index(self, index) -> list:
        """
        Cleans and extracts the array of the index from the JSON (legacy method for compatibility)
        
        Args:
            index: Can be a JSON string, dict or list
            
        Returns:
            list: Cleaned array of the index
        """
        return self._clean_and_get_property(index, "index", ["routines"])

    async def generate_content_index(self, prompt: str) -> list:
        """
        Generates an index of content in JSON format
        
        Args:
            prompt (str): Prompt to generate the index of content
            
        Returns:
            list: Array of Routine objects with the index structure
        """
        try:
            
            # Build the specific system prompt to generate indices
            system_prompt = """
            You are an expert in creating educational content indices without adding additional text or comments before or after the JSON. 
            Your task is to generate a JSON structure that represents an index of content with the following hierarchy:

1. TITLE (type: "title"): The main title of the course or module
2. SUBTITLE (type: "subtitle"): Didactic units or main topics
3. SUBITEM (type: "subitem"): Specific contents within each unit

IMPORTANT RULES:
- ALWAYS return a valid JSON with an array of objects
- Each object must have: {"type": "title|subtitle|subitem", "content": "content name"}
- The first element MUST be a title (type: "title")
- Subtitles must be related to the main title
- Subitems must be related to their corresponding subtitle
- Use descriptive and clear names
- DO NOT include numbering in the content, only the name
- Your response must be a valid JSON because it will be parsed by 'json.loads'

Example of expected structure:
```
{
"index": [
  {"type": "title", "content": "Introduction to Programming"},
  {"type": "subtitle", "content": "Basic Concepts"},
  {"type": "subitem", "content": "What is programming?"},
  {"type": "subitem", "content": "Types of languages"},
  {"type": "subtitle", "content": "First Steps"},
  {"type": "subitem", "content": "Environment installation"},
  {"type": "subitem", "content": "First program"}
]
}
```

Respond ONLY with the valid JSON, without additional text."""

            # Generate the index using the Strands service
            index = await self.strands_service.generate_text(
                prompt=prompt,
                system_prompt=system_prompt
            )

            print(index)

            # Try to transform the result into a valid JSON
            try:
                index = json.loads(index)
            except:
                pass
            
            index = self.clean_and_get_property(index, "index", ["routines"])
            
            # Parse the JSON
            try:
                # routines = json.loads(result)
                
                # Validate that it is a list
                if not isinstance(index, list):
                    raise ValueError("The response is not a valid list")
                
                # Validate that it has at least one title
                if not index or not any(r.get("type") == "title" for r in index):
                    raise ValueError("There must be at least one title in the index")
                
                # Validate the structure of each element
                for routine in index:
                    routine["id"] = str(uuid.uuid4())
                    if not isinstance(routine, dict):
                        raise ValueError("Each element must be an object")
                    if "type" not in routine or "content" not in routine:
                        raise ValueError("Each element must have 'type' and 'content'")
                    if routine["type"] not in ["title", "subtitle", "subitem"]:
                        raise ValueError("The type must be 'title', 'subtitle' or 'subitem'")
                
                return index
                
            except json.JSONDecodeError as e:
                raise Exception(f"Error parsing JSON: {str(e)}")
            except ValueError as e:
                raise Exception(f"Error validating structure: {str(e)}")
            
        except Exception as e:
            raise Exception(f"Error generating content index: {str(e)}") 