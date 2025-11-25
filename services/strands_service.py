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

"""
Service for integration with AWS Bedrock using boto3
"""
import base64
import os
import logging
import json
import re
from typing import Optional
from strands import Agent, tool
from strands.models import BedrockModel
try:
    from strands_tools import current_time
except ImportError:
    current_time = None
from dotenv import load_dotenv
from interfaces.strands_interface import StrandsServiceInterface
from services.content_storage_service import ContentStorageService
from services.html_service import HTMLService
from utility.aws_clients import bedrock_runtime_client

logger = logging.getLogger(__name__)

load_dotenv()




class StrandsService(StrandsServiceInterface):
    """Class for handling AI using AWS Bedrock directly"""
    
    def __init__(self, model_id: str = None, model_region: str = None, db = None, deepThinkingEnabled: bool = False):
        """Initializes the Bedrock service"""
        # Nota: no prefijar el ID del modelo con región (p. ej. "us.") para evitar resoluciones de región incorrectas
        self.region_name = model_region or os.getenv("AWS_REGION_NAME", "eu-central-1")
        self.deepThinkingEnabled = deepThinkingEnabled
        if(deepThinkingEnabled):
            self.model_id = model_id or os.getenv("BEDROCK_DEEP_MODEL_ID", "eu.anthropic.claude-3-7-sonnet-20250219-v1:0")
            self.max_tokens = int(os.getenv("STRANDS_DEEP_MAX_TOKENS", "16000"))
            self.temperature = float(os.getenv("STRANDS_DEEP_TEMPERATURE", "0.15"))
        else:
            self.model_id = model_id or os.getenv("BEDROCK_MODEL_ID", "eu.anthropic.claude-3-7-sonnet-20250219-v1:0")
            self.max_tokens = int(os.getenv("STRANDS_MAX_TOKENS", "8000"))
            self.temperature = float(os.getenv("STRANDS_TEMPERATURE", "0.7"))

        print(f"🧠 Using model {self.model_id} in region {self.region_name} with max_tokens={self.max_tokens} and temperature={self.temperature}")
        # Configure Bedrock Runtime client
        self.bedrock_runtime = bedrock_runtime_client
        self.html_service = HTMLService()
        # Create a BedrockModel
        self.bedrock_model = BedrockModel(
            model_id=self.model_id,
            region_name=self.region_name,
            max_tokens=self.max_tokens,
            temperature=self.temperature
        )
        self.db = db

        
    async def generate_text_with_agent(self, prompt: str) -> str:
        """
        Generates text using the Strands Agent
        """
        try:
            logger.info(f"🤖 Agent prompt: {prompt}")
            tools = [current_time] if current_time else []
            agent = Agent(
                name="AI Content Generator",
                model=self.bedrock_model,
                tools=tools
            )
            
            response = agent(prompt)
            
            # The Agent returns an AgentResult, we need to extract the text
            if hasattr(response, 'content'):
                # If it has attribute content, use it
                result = response.content
            elif hasattr(response, 'text'):
                # If it has attribute text, use it
                result = response.text
            elif hasattr(response, '__str__'):
                # If not, convert to string
                result = str(response)
            else:
                # Fallback to string
                result = str(response)
            
            logger.info(f"✅ Agent response type: {type(response)}")
            logger.info(f"📝 Agent response length: {len(result)}")
            
            return result
        except Exception as e:
            logger.error(f"❌ Error in Agent: {str(e)}")
            raise RuntimeError(f"Error generating text with Agent: {str(e)}") from e

    async def generate_text(
        self, 
        prompt: str, 
        system_prompt: Optional[str] = None,
        messages: Optional[list] = None,
    ) -> str:
        """
        Generates text using the Strands Agent
        class Message(TypedDict):
    ""A message in a conversation with the agent.

    Attributes:
        content: The message content.
        role: The role of the message sender.
    ""

    content: List[ContentBlock]
    role: Role
    class ContentBlock(TypedDict, total=False):
    "A block of content for a message that you pass to, or receive from, a model.

    Attributes:
        cachePoint: A cache point configuration to optimize conversation history.
        document: A document to include in the message.
        guardContent: Contains the content to assess with the guardrail.
        image: Image to include in the message.
        reasoningContent: Contains content regarding the reasoning that is carried out by the model.
        text: Text to include in the message.
        toolResult: The result for a tool request that a model makes.
        toolUse: Information about a tool use request from a model.
        video: Video to include in the message.
    "

    cachePoint: CachePoint
    document: DocumentContent
    guardContent: GuardContent
    image: ImageContent
    reasoningContent: ReasoningContentBlock
    text: str
    toolResult: ToolResult
    toolUse: ToolUse
    video: VideoContent
        """
        try:
            if messages:
                normalized = []
                for msg in messages:
                    # extraer role y content ya sea de dict o de objeto
                    if isinstance(msg, dict):
                        role = msg.get("role", "user")
                        content = msg.get("content", [])
                    else:
                        role = getattr(msg, "role", "user")
                        content = getattr(msg, "content", "")

                    content_blocks = []
                    if isinstance(content, list):
                        for block in content:
                            if isinstance(block, dict):
                                content_blocks.append(block)
                            else:
                                content_blocks.append({"text": str(block)})
                    else:
                        content_blocks.append({"text": str(content)})

                    normalized.append({"role": role, "content": content_blocks})
                messages = normalized
            else:
                messages = []

            agent = Agent(
                name="AI Content Generator",
                system_prompt=system_prompt,
                model=self.bedrock_model,
                tools=[current_time, self.file_read_tool],
                messages=messages
            )

            if(self.deepThinkingEnabled):
                try:
                    if hasattr(agent, "model") and hasattr(agent.model, "update_config"):
                        config = {
                            "reasoning": {"type": "enabled", "interleaved_thinking": True, "max_reflections": 3, "budget_tokens": 4000, "max_thoughts": 5, "max_tool_calls": 8},
                            "max_tool_calls": 8
                        }
                        agent.model.update_config(**config["reasoning"])
                        print("✅ Deep Thinking configuration applied:", config)
                except Exception:
                    # fallback: seguir con defaults
                    pass


            # Use the Strands Agent
            try:
                response = agent(prompt)
            except Exception as e:
                msg = str(e).lower()
                logging.exception("Agent call failed; checking if caused by token limit")
                if "exceeds the model limit" in msg or "maximum tokens you requested" in msg or "max tokens" in msg:
                    # reintentar de forma segura bajando requested_output a la mitad y/o quitando reasoning_budget
                    logging.warning("Detected token-limit error from model. Retrying with reduced token budget.")
                    # estrategia: bajar output y reasoning y reintentar una vez
                    if self.max_tokens > 256:
                        self.max_tokens = max(256, self.max_tokens // 2)

                        self.bedrock_model = BedrockModel(
                            model_id=self.model_id,
                            region_name=self.region_name,
                            max_tokens=self.max_tokens,
                            temperature=self.temperature
                        )

                    agent = Agent(
                        name="AI Content Generator",
                        system_prompt=system_prompt,
                        model=self.bedrock_model,
                        tools=[current_time, self.file_read_tool],
                        messages=messages
                    )

                    if(self.deepThinkingEnabled):
                        try:
                            if hasattr(agent, "model") and hasattr(agent.model, "update_config"):
                                config = {
                                    "reasoning": {"type": "enabled", "interleaved_thinking": True, "max_reflections": 3, "budget_tokens": 2000, "max_thoughts": 2, "max_tool_calls": 4},
                                    "max_tool_calls": 4
                                }
                                agent.model.update_config(**config["reasoning"])
                                print("✅ Deep Thinking configuration applied:", config)
                        except Exception:
                            # fallback: seguir con defaults
                            pass
                    try:
                        response = agent(prompt)
                    except Exception:
                        logging.exception("Retry after token adjustment failed")
                        raise
                else:
                    raise


            # The Agent returns an AgentResult, we need to extract the text
            if hasattr(response, 'content'):
                result = response.content
            elif hasattr(response, 'text'):
                result = response.text
            elif hasattr(response, '__str__'):
                result = str(response)
            else:
                result = str(response)
            
            logger.info(f"📝 Agent generate_text response length: {len(result)}")
            
            return result
        except Exception as e:
            # logger.error(f"❌ Error in Agent generate_text: {str(e)}")
            raise
    
    async def get_status(self) -> str:
        """
        Gets the status of the Bedrock service
        """
        try:
            agent = Agent(
                name="Status Checker",
                model=self.bedrock_model,
                tools=[current_time]
            )
            response = agent("Are you available? Only respond with a text that says 'Available' or 'Not available'")
            return response
        except Exception as e:
            logger.error(f"❌ Error checking status: {str(e)}")
            return f"Error checking status: {str(e)}"
    
    async def generate_markdown_content(self, prompt: str, system_prompt: str, context: str) -> str:
        """
        Generates markdown content using the Strands Agent
        """
        try:
            # Add the context to the prompt if provided
            if context and context.strip() != "":
                prompt = f"Contexto: {context}\n\n{prompt}"

            # Improve the system prompt with advanced capabilities if no specific one is provided
            if not system_prompt or system_prompt.strip() == "":
                system_prompt = self._get_enhanced_md_system_prompt()
    
            logger.info(f"🤖 Agent MD prompt: {prompt[:100]}...")
            logger.info(f"🔧 Agent MD system_prompt: {system_prompt[:100]}...")
            
            # Create Agent with specific system prompt for MD
            agent = Agent(
                name="MD Content Generator",
                system_prompt=system_prompt,
                model=self.bedrock_model,
                tools=[current_time]
            )
            
            # Use the Strands Agent
            response = agent(prompt)
            
            # The Agent returns an AgentResult, we need to extract the text
            if hasattr(response, 'content'):
                generated_md = response.content
            elif hasattr(response, 'text'):
                generated_md = response.text
            elif hasattr(response, '__str__'):
                generated_md = str(response)
            else:
                generated_md = str(response)
            
            logger.info(f"Generated MD: {generated_md}")

            return generated_md
        except Exception as e:
            logger.error(f"❌ Error in Agent MD: {str(e)}")
            raise RuntimeError(f"Error generating MD: {e}") from e

    async def generate_html_content(self, prompt: str, system_prompt: str, context: str) -> str:
        """
        Generates HTML content using the Strands Agent
        """
        try:
            # Add the context to the prompt if provided
            if context and context.strip() != "":
                prompt = f"Contexto: {context}\n\n{prompt}"

            # Improve the system prompt with advanced capabilities if no specific one is provided
            if not system_prompt or system_prompt.strip() == "":
                system_prompt = self._get_enhanced_html_system_prompt()
            
            logger.info(f"🤖 Agent HTML prompt: {prompt[:100]}...")
            logger.info(f"🔧 Agent HTML system_prompt: {system_prompt[:100]}...")
            
            # Create Agent with specific system prompt for HTML
            agent = Agent(
                name="HTML Content Generator",
                system_prompt=system_prompt,
                model=self.bedrock_model,
                tools=[current_time]
            )
            
            # Use the Strands Agent
            response = agent(prompt)
            
            # The Agent returns an AgentResult, we need to extract the text
            if hasattr(response, 'content'):
                generated_html = response.content
            elif hasattr(response, 'text'):
                generated_html = response.text
            elif hasattr(response, '__str__'):
                generated_html = str(response)
            else:
                generated_html = str(response)
            
            logger.info(f"Generated HTML: {generated_html}")

            return generated_html

        except Exception as e:
            logger.error(f"❌ Error in Agent HTML: {str(e)}")
            raise RuntimeError(f"Error generating HTML: {e}") from e

    async def generate_html_from_page_metadata(
        self, 
        page_metadata: dict, 
        custom_prompt: str = None,
        language: str = "es",
        accessibility_rules: str = None
    ) -> str:
        """
        Generates HTML for a specific page based on its metadata
        
        Args:
            page_metadata (dict): Metadata of the page of the PDF
            custom_prompt (str, optional): Custom prompt for the generation
            language (str): Language of the content (default: "es")
            accessibility_rules (str, optional): Accessibility rules to apply
            
        Returns:
            str: Generated HTML for the page
        """
        try:
            # Create the specific prompt for the page
            prompt = self._create_page_metadata_prompt(
                page_metadata, 
                custom_prompt="",
                language=language,
                accessibility_rules=accessibility_rules
            )
            
            # System prompt for HTML generation with styles
            system_prompt = self._get_page_metadata_system_prompt(
                language=language,
                accessibility_rules=accessibility_rules
            )
            
            # Generate HTML using the existing method
            html_content = await self.generate_html_content(prompt, system_prompt, "")
            
            # Wrap in a section tag
            # section_html = f'<section class="pdf-page" data-page-number="{page_metadata.get("page_number", 1)}" lang="{language}">\n{html_content}\n</section>'
            
            # system_prompt = ""
            # prompt = """
            # # 🎯 Objective
            # - Generate **semantic HTML** complying with **WCAG 2.1 AA**.
            # - The content must be navigable with keyboard, understandable with screen reader and with good contrast.

            # ---

            # ## 📐 Structure and semantics
            # - Use `html lang="…"`. 
            # - Title (`<title>`) descriptive and unique per page.
            # - Use landmarks: `header`, `nav`, `main`, `aside`, `footer`. **One `main` per page.**
            # - Consistent header hierarchy (H1 unique → H2 → H3…).
            # - Use lists (`ul`, `ol`, `dl`) when appropriate.
            # - Do not use `div`/`span` as buttons or links.

            # ---

            # ## ⌨️ Keyboard and focus
            # - All interactive content must be accessible with Tab / Shift+Tab, activable with Enter or Space.
            # - **Visible focus**:
            # ```css
            # a:focus, button:focus {
            #     outline: 3px solid #2563eb;
            #     outline-offset: 2px;
            # }
            # ```
            # - Do not remove focus with `outline: none`.
            # - Modals/menus must catch the focus and return it to the trigger when closing.

            # ---

            # ## 🎨 Color and contrast
            # - Normal text: contrast ≥ **4.5:1**.
            # - Large text (≥24px or ≥18.66px bold): contrast ≥ **3:1**.
            # - Interface controls and focus/hover: contrast ≥ **3:1**.
            # - Do not use color as the only means of information.

            # ---

            # ## 🔗 Links and buttons
            # - Use `<a href>` for navigation and `<button>` for actions.
            # - Clear link text (not "click here").
            # - Differentiated `:hover` and `:focus` states.

            # ---

            # ## 🖼️ Images and multimedia
            # - All images with significant `alt`. If decorative: `alt=""` and `aria-hidden="true"`.
            # - SVG icons: `aria-hidden="true"` if decorative, or `<title>`/`aria-label` if informative.
            # - Videos with subtitles. Audios with transcriptions. No autoplay with sound.

            # ---

            # ## 🧾 Forms
            # - Each field with `<label>` visible or `aria-label`.
            # - Errors must be announced (`aria-describedby`) and not only depend on color.
            # - Group options with `fieldset` + `legend`.
            # - Logical tab order (avoid positive `tabindex`).

            # ---

            # ## 📊 Tables
            # - Use `<th scope="col|row">` and `<caption>` if adds value.
            # - For complex tables use `headers`/`id` or ARIA.

            # ---

            # ## 📱 Responsive design and zoom
            # - Responsive design that works at 320px or 200% zoom without horizontal scroll.
            # - Touch areas of at least 44x44px.

            # ---

            # ## 🗣️ ARIA (minimum necessary)
            # - Prefer native HTML over ARIA roles.
            # - If necessary: `aria-expanded`, `aria-controls`, `aria-live`.
            # - Announce dynamic changes with `aria-live="polite"` or `assertive`.

            # ---

            # ## 🚫 Anti‑patterns
            # - Remove visible focus.
            # - Block zoom.
            # - Use only color for states.
            # - Placeholder as the only label.
            # - `div` as buttons.
            # - `tabindex > 0`.
            # - Modals without controlled focus.

            # ---

            # Content to analyze and repair (return only the HTML fixed):
            # """ + html_content
            # html_content = await self.generate_html_content(prompt, system_prompt, "")
            return html_content
            
        except Exception as e:
            logger.error(f"❌ Error generating HTML for page {page_metadata.get('page_number', 'unknown')}: {str(e)}")
            # Return error HTML
            return f'<main class="pdf-page error" data-page-number="{page_metadata.get("page_number", 1)}">\n<div class="error-message">Error procesando página: {str(e)}</div>\n</main>'

    def _create_page_metadata_prompt(
        self, 
        page_metadata: dict, 
        custom_prompt: str = None,
        language: str = "es",
        accessibility_rules: str = None
    ) -> str:
        """
        Creates a specific prompt based on the page metadata
        """
        page_num = page_metadata.get("page_number", 1)
        text_content = page_metadata.get("text_content", "")
        fonts_used = page_metadata.get("fonts_used", [])
        colors = page_metadata.get("colors", [])
        styles = page_metadata.get("styles", [])
        images = page_metadata.get("images", [])
        links = page_metadata.get("links", [])

        # Flat styles [[],["bold"]] -> ["bold"]
        styles = [style for sublist in styles for style in sublist]

        # Prompt base
        base_prompt = f"""
Generates HTML for the page {page_num} of the PDF with the following characteristics:

TEXT CONTENT:
{text_content}

STYLES TO RESPECT:
- Fonts used: {', '.join(fonts_used) if fonts_used else 'Default font'}
- Colors used: {', '.join(colors) if colors else 'Default color'}
- Text styles: {', '.join(styles) if styles else 'No special styles'}

SPECIAL ELEMENTS:
- Found images: {len(images)} image(s)
- Found links: {len(links)} link(s)

CONTENT LANGUAGE:
- Language: {language}

SPECIFIC INSTRUCTIONS:
1. Maintain the semantic structure of the content
2. Apply the specified font and color styles
3. Include images as <img> elements with base64 data if available
4. Convert links to appropriate <a> elements
5. Use HTML semantic elements like <h1>-<h6>, <p>, <div>, etc.
6. Maintain the original content hierarchy and organization
7. Ensure the HTML is valid and accessible
8. Generate the content in the specified language: {language}
"""
        
        # Add custom prompt if provided
        if custom_prompt:
            base_prompt += f"\nPROMPT PERSONALIZADO:\n{custom_prompt}\n"
        
        # Add accessibility rules if provided
        if accessibility_rules:
            base_prompt += f"\nACCESSIBILITY RULES TO APPLY:\n{accessibility_rules}\n"
        
        base_prompt += "\nGenerate HTML that faithfully represents the content and style of this page of the PDF."
        
        return base_prompt

    def _get_page_metadata_system_prompt(
        self, 
        language: str = "es",
        accessibility_rules: str = None
    ) -> str:
        """
        Generates a specific system prompt for HTML generation based on page metadata
        """
        base_system_prompt = f"""
You are a specialized HTML generator that converts PDF content to semantic and accessible HTML.

Your function is to generate HTML that:
1. RESPECT the original styles (fonts, colors, sizes)
2. MAINTAIN the semantic structure of the content
3. INCLUDE images with base64 data when available
4. CONVERT links to appropriate <a> elements
5. USE appropriate HTML semantic elements
6. GENERATE content in the specified language: {language}
7. APPLY the specified accessibility rules
8. ADD the "data-" attributes according to the specified accessibility rules
9. The generated HTML must be between <XHTML_CONTENT> and </XHTML_CONTENT>
10. Do not add the <head> nor the <body> at the beginning nor at the end

CRITICAL RULES:
- Your response must be valid HTML within a XML tag called <XHTML_CONTENT>
- Apply CSS inline styles to respect fonts and colors
- Use semantic elements like <h1>-<h6>, <p>, <div>, <section>, etc.
- Include images as <img src="data:image/...;base64,...">
- Convert links to <a href="...">text</a>
- Maintain the visual hierarchy of the original content
- Ensure the content is in {language}
- The generated HTML must be between <XHTML_CONTENT> and </XHTML_CONTENT>
- Do not add the <head> nor the <body> at the beginning nor at the end
- HTML 100% compatible with Level AA accessibility
"""
        
        # Agregar reglas de accesibilidad si se proporcionan
        if accessibility_rules:
            base_system_prompt += f"""

SPECIFIC ACCESSIBILITY RULES:
{accessibility_rules}

Ensure to apply these accessibility rules in the generated HTML.
"""
        
        base_system_prompt += """

EXAMPLE OF STRUCTURE:

<XHTML_CONTENT>
  <!-- Your HTML content here -->
</XHTML_CONTENT>

Generate HTML that is faithful to the original content of the PDF and respects all the specified styles.
"""
        
        return base_system_prompt
    
    def _get_enhanced_html_system_prompt(self) -> str:
        """
        Generates an enhanced system prompt with advanced HTML capabilities
        """
        return """
        You are an HTML content generator within a XML tag called <RESPONSE>. 
        Your ONLY function is to return valid and semantic HTML within the <RESPONSE>, NOTHING ELSE.


ALLOWED HTML ELEMENTS:
- Structure: <div>, <section>, <article>, <header>, <footer>, <main>, <aside>
- Titles: <h1>-<h6>
- Text: <p>, <span>, <strong>, <em>, <mark>, <small>
- Lists: <ul>, <ol>, <li>, <dl>, <dt>, <dd>
- Tables: <table>, <thead>, <tbody>, <tfoot>, <tr>, <th>, <td>, <caption>
- Forms: <form>, <input>, <textarea>, <select>, <option>, <button>, <label>
- Multimedia: <img>, <audio>, <video>, <iframe>, <canvas>
- Scripts: <script>, <style>
- Links: <a>
- Quotes: <blockquote>, <cite>
- Code: <code>, <pre>, <kbd>, <samp>
- Others: <hr>, <br>, <details>, <summary>

ADVANCED CAPABILITIES:
1. YOU CAN INCLUDE INTERACTIVE ELEMENTS:
   - Tables with inputs, buttons and forms
   - Graphics using Chart.js: <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
   - JavaScript for dynamic functionality
   - CSS inline for advanced styles
   - Multimedia elements (audio, video, iframes)

2. FOR INTERACTIVE GRAPHICS:
   - Use Chart.js from CDN
   - Include JavaScript for dynamic updates
   - Use <canvas> for rendering

3. FOR INTERACTIVE TABLES:
   - Include inputs, buttons and controls
   - Use JavaScript for functionality
   - Maintain semantic structure

4. FOR FORMS:
   - Use elements <form>, <input>, <button>
   - Include validation with JavaScript
   - Maintain accessibility

STYLES:
- Use inline style attributes when necessary
- DO NOT use CSS classes from frameworks like Tailwind
- Maintain colors, spacing and basic design with CSS inline
- Example: <div style='background-color: #f3f4f6; padding: 16px; border-radius: 8px;'>

ABSOLUTE RULES:
❌ DO NOT add explanatory text before the HTML
❌ DO NOT add explanatory text after the HTML
❌ DO NOT add comments like "Here is the HTML:"
❌ DO NOT add <html>, <head>, <body> at the beginning nor at the end
❌ DO NOT use code blocks with ```html or ```
✅ ALWAYS start directly with <div>, <h1>, <p>, etc.
✅ ALWAYS end with the last closed HTML element
✅ ALWAYS return valid and semantic HTML

EXAMPLE OF EXPECTED STRUCTURE:
```
Your response must be valid MD within the <RESPONSE> tag.
<RESPONSE>
    <AGENT_MESSAGE>
    <--- Mensaje que verá el usuario en el chat --->
    </AGENT_MESSAGE>
    <CONTENT>
    <--- Contenido generado en formato HTML --->
    </CONTENT>
</RESPONSE>
```
"""

    def _get_enhanced_md_system_prompt(self) -> str:
        """
        Generates an enhanced system prompt with advanced MD capabilities
        """
        return """
        You are an MD content generator within a XML tag called <RESPONSE>. 
        Your ONLY function is to return valid and semantic MD within the <RESPONSE>, NOTHING ELSE.

        Your response must be valid MD within the <RESPONSE> tag.
        <RESPONSE>
            <AGENT_MESSAGE>
            <--- Message that the user will see in the chat --->
            </AGENT_MESSAGE>
            <CONTENT>
<--- Generated content in markdown format, do not use spaces at the beginning of the line --->
            </CONTENT>
        </RESPONSE>
        """

    def _extract_xhtml_content(self, html_content: str) -> str:
        """
        Extract the XHTML_CONTENT from the generated HTML
        """
        return html_content.split("<XHTML_CONTENT>")[1].split("</XHTML_CONTENT>")[0]
    
    def _parse_json_string(self, data: str) -> dict:
        """
        Parse a JSON string, handling various formats and edge cases.
        
        Args:
            data: JSON string to parse
            
        Returns:
            dict: Parsed JSON data or empty dict if parsing fails
        """
        
        try:
            # Clean the string of possible extra characters
            cleaned_data = data.strip()
            
            # Find the first { and the last }
            start = cleaned_data.find('{')
            end = cleaned_data.rfind('}')
            
            if start != -1 and end != -1:
                cleaned_data = cleaned_data[start:end + 1]

            # Check if start with "{\n"}" and remove "\n"   
            if cleaned_data.startswith("{\n"):
                cleaned_data = cleaned_data.replace("{\n", "{", 1)
            
            # Check if end with "\n}" and replace the last "\n}" with "}". Remove only the last "\n}" because maybe there are more "\n}"
            if cleaned_data.endswith("\n}"):
                cleaned_data = cleaned_data.replace("\n}", "}", -1)
            
            # Try to parse as JSON
            return json.loads(cleaned_data)
            
        except json.JSONDecodeError as e:
            logger.warning(f"⚠️ First JSON parsing attempt failed: {str(e)}")
            
            # Try to fix common JSON issues
            try:
                fixed_data = self._fix_json_string(cleaned_data)
                return json.loads(fixed_data)
            except json.JSONDecodeError as e2:
                logger.warning(f"⚠️ Fixed JSON parsing also failed: {str(e2)}")
                
                # Try to extract JSON using regex patterns
                try:
                    return self._extract_json_with_regex(cleaned_data)
                except Exception as e3:
                    logger.error(f"❌ All JSON parsing attempts failed: {str(e3)}")
                    return {}
    
    def _fix_json_string(self, data: str) -> str:
        """
        Fix common JSON string issues like single quotes in HTML content.
        
        Args:
            data: JSON string to fix
            
        Returns:
            str: Fixed JSON string
        """
        # Replace single quotes with double quotes in HTML attributes
        # This is a more sophisticated approach to handle HTML content
        import re
        
        # Pattern to match HTML attributes with single quotes
        # This will find patterns like: lang='es', href='#estructura', etc.
        html_attr_pattern = r"(\w+)=['\"]([^'\"]*)['\"]"
        
        def replace_quotes(match):
            attr_name = match.group(1)
            attr_value = match.group(2)
            # Keep the original quotes but ensure they're consistent
            return f'{attr_name}="{attr_value}"'
        
        # Apply the fix
        fixed_data = re.sub(html_attr_pattern, replace_quotes, data)
        
        # Also handle escaped quotes in the HTML content
        # Replace escaped single quotes with regular single quotes
        fixed_data = fixed_data.replace("\\'", "'")
        
        return fixed_data
    
    def _extract_json_with_regex(self, data: str) -> dict:
        """
        Extract JSON using regex patterns when standard parsing fails.
        
        Args:
            data: String containing JSON
            
        Returns:
            dict: Extracted JSON data
        """
        # Try to extract JSON object pattern
        json_object_pattern = r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}'
        match = re.search(json_object_pattern, data, re.DOTALL)
        
        if match:
            try:
                return json.loads(match.group())
            except json.JSONDecodeError:
                pass
        
        # Try to extract array pattern
        array_pattern = r'\[\s*\{[^\]]*\}\s*\]'
        match = re.search(array_pattern, data, re.DOTALL)
        if match:
            try:
                return json.loads(match.group())
            except json.JSONDecodeError:
                pass
        
        # If all else fails, try to construct a simple dict from the data
        return self._construct_dict_from_string(data)
    
    def _construct_dict_from_string(self, data: str) -> dict:
        """
        Construct a dictionary from string when JSON parsing completely fails.
        
        Args:
            data: String to parse
            
        Returns:
            dict: Constructed dictionary
        """
        # Look for common patterns like "key": "value"
        key_value_pattern = r'"([^"]+)"\s*:\s*"([^"]*)"'
        matches = re.findall(key_value_pattern, data)
        
        if matches:
            result = {}
            for key, value in matches:
                result[key] = value
            return result
        
        # If no key-value pairs found, return empty dict
        return {}

    def _extract_property_from_dict(self, data: dict, property_name: str, fallback_properties: list = None) -> list:
        """
        Extract a specific property from a dictionary.
        
        Args:
            data: Dictionary to search in
            property_name: Name of the property to extract
            fallback_properties: List of alternative properties if the main one is not found
            
        Returns:
            list: Extracted property as a list
        """
        # Search the main property
        if property_name in data:
            property_value = data[property_name]
            if isinstance(property_value, list):
                return property_value
            elif isinstance(property_value, str):
                return [property_value]
        
        # Search alternative properties
        if fallback_properties:
            for fallback_prop in fallback_properties:
                if fallback_prop in data and isinstance(data[fallback_prop], list):
                    return data[fallback_prop]
        
        # If it does not have the property but is a list of valid objects
        if self._is_valid_object_list(data):
            return list(data.values())
        
        return []

    def _is_valid_object_list(self, data: dict) -> bool:
        """
        Check if the dictionary contains valid objects with 'type' and 'content' keys.
        
        Args:
            data: Dictionary to validate
            
        Returns:
            bool: True if all values are valid objects
        """
        return all(
            isinstance(item, dict) and "type" in item and "content" in item 
            for item in data.values()
        )

    def _normalize_to_list(self, data) -> list:
        """
        Normalize data to a list format.
        
        Args:
            data: Data to normalize
            
        Returns:
            list: Normalized list
        """
        if isinstance(data, list):
            return data
        elif isinstance(data, dict):
            return [data]
        elif isinstance(data, str):
            return [data]
        else:
            return []

    def clean_and_get_property(self, data, property_name: str, fallback_properties: list = None) -> list:
        """
        Clean and extract a specific property from the JSON
        
        Args:
            data: Can be a JSON string, a dict or a list
            property_name: Name of the property to extract (e.g: "index", "routines", "html_content")
            fallback_properties: List of alternative properties if the main one is not found
            
        Returns:
            list: Clean array of the requested property
        """
        try:
            # Handle string input by parsing it as JSON
            if isinstance(data, str):
                data = self._parse_json_string(data)
                # If parsing failed and returned empty dict, try to normalize as list
                if not data:
                    return self._normalize_to_list(data)
            
            # Handle dictionary input
            if isinstance(data, dict):
                result = self._extract_property_from_dict(data, property_name, fallback_properties)
                if result:
                    return result
            
            # Handle list input or fallback to normalization
            return self._normalize_to_list(data)
            
        except Exception as e:
            logger.error(f"⚠️ Error cleaning property '{property_name}': {str(e)}")
            return []
    
    def generate_instructional_model(self, prompt):
        """
        Generates an instructional model from the information extracted from Textract.
        """
        # Build the specific system prompt to generate indices
        system_prompt = """
                    You are an expert in creating educational content indices without adding additional text or comments before or after the JSON. 
                    Your task is to generate a JSON structure that represents an index of content with the following hierarchy:

        1. TITLE ("title"): The main title of the instructional model
        2. CONTENT ("content"): Specific contents within the instructional model

        IMPORTANT RULES:
        - ALWAYS return a valid JSON with an array of objects
        - Each object must have: {"title": "content title", "content": "content related to the title"}
        - The first element MUST be a title (title)
        - The contents must be related to the main title
        - Use descriptive and clear names
        - Your response must be a valid JSON because it will be parsed by 'json.loads'

        EXAMPLE OF EXPECTED STRUCTURE:
        ```
        {
        "model": [
            {"title": "Responsible institution", "content": "General Directorate of Planning, Centers and Professional Training of the Government of Aragon"},
            {"title": "Dependency", "content": "Department of Education, Science and Universities."},
            {"title": "Scope", "content": "Professional Training, module A173: Advanced Office Applications Applied to the Productive Sector."},
            {"title": "Purpose", "content": "Promote the creation of professional documents and templates using office tools efficiently."},
            {"title": "Focus", "content": "Development of technical skills applied to the productive sector, following an official curriculum."},
            {"title": "Methodology", "content": "Based on learning outcomes and evaluation criteria aligned with curricular content."},
            {"title": "Expected result", "content": "Acquisition of practical skills adapted to the real demands of the working environment."}
            ]
        }
        ```

        Respond ONLY with the valid JSON, without additional text."""
        # Create Agent with specific system prompt for HTML
        agent = Agent(
            name="Instructional Model Generator",
            system_prompt=system_prompt,
            model=self.bedrock_model,
            tools=[current_time]
        )
        
        # Use the Strands Agent
        response = agent(prompt)
        
        # The Agent returns an AgentResult, we need to extract the text
        if hasattr(response, 'content'):
            generated_html = response.content
        elif hasattr(response, 'text'):
            generated_html = response.text
        elif hasattr(response, '__str__'):
            generated_html = str(response)
        else:
            generated_html = str(response)
        
        logger.debug(f"Generated instructional model: {generated_html}")
        generated_html = self.clean_and_get_property(generated_html, "model")

        logger.info(f"Instructional model: {generated_html}")

        return generated_html
    
    def generate_pedagogical_framework(self, prompt):
        """
        Generates a pedagogical framework from the information extracted from Textract.
        """
        # Build the specific system prompt to generate indices
        system_prompt = """
                    You are an expert in creating educational content indices without adding additional text or comments before or after the JSON. 
                    Your task is to generate a JSON structure that represents an index of content with the following hierarchy:

        1. TITLE ("title"): The main title of the pedagogical framework
        2. CONTENT ("content"): Specific contents within the pedagogical framework

        IMPORTANT RULES:
        - ALWAYS return a valid JSON with an array of objects
        - Each object must have: {"title": "content title", "content": "content related to the title"}
        - The first element MUST be a title (title)
        - The contents must be related to the main title
        - Use descriptive and clear names
        - Your response must be a valid JSON because it will be parsed by 'json.loads'

        EXAMPLE OF EXPECTED STRUCTURE:
        ```
        {
        "model": [
            {"title": "Responsible institution", "content": "General Directorate of Planning, Centers and Professional Training of the Government of Aragon"},
            {"title": "Dependency", "content": "Department of Education, Science and Universities."},
            {"title": "Scope", "content": "Professional Training, module A173: Advanced Office Applications Applied to the Productive Sector."},
            {"title": "Purpose", "content": "Promote the creation of professional documents and templates using office tools efficiently."},
            {"title": "Focus", "content": "Development of technical skills applied to the productive sector, following an official curriculum."},
            {"title": "Methodology", "content": "Based on learning outcomes and evaluation criteria aligned with curricular content."},
            {"title": "Expected result", "content": "Acquisition of practical skills adapted to the real demands of the working environment."}
            ]
        }
        ```

        Respond ONLY with the valid JSON, without additional text."""
        # Create Agent with specific system prompt for HTML
        agent = Agent(
            name="Pedagogical Framework Generator",
            system_prompt=system_prompt,
            model=self.bedrock_model,
            tools=[current_time]
        )
        
        # Use the Strands Agent
        response = agent(prompt)
        
        # The Agent returns an AgentResult, we need to extract the text
        if hasattr(response, 'content'):
            generated_html = response.content
        elif hasattr(response, 'text'):
            generated_html = response.text
        elif hasattr(response, '__str__'):
            generated_html = str(response)
        else:
            generated_html = str(response)
        
        logger.debug(f"Generated pedagogical framework: {generated_html}")
        generated_html = self.clean_and_get_property(generated_html, "model")

        logger.info(f"Pedagogical framework: {generated_html}")

        return generated_html
    
    def test_json_parsing(self):
        """
        Test method to verify JSON parsing works with problematic JSON strings.
        This method can be used for debugging purposes.
        """
        test_json = '''{\n"html_content": "<div lang=\'es\'>\n  <header>\n    <h1>Accesibilidad Web: Principos Fundamentales</h1>\n    <nav>\n      <ul>\n        <li><a href=\'#estructura\'>Estructura</a></li>\n        <li><a href=\'#teclado\'>Teclado</a></li>\n        <li><a href=\'#color\'>Color</a></li>\n        <li><a href=\'#formulario\'>Formulario</a></li>\n      </ul>\n    </nav>\n  </header>\n\n  <main>\n    <section id=\'estructura\'>\n      <h2>Estructura y Semántica</h2>\n      <p>Una estructura HTML semántica es fundamental para la accesibilidad.</p>\n      <ul>\n        <li>Usa landmarks como <code>header</code>, <code>nav</code>, <code>main</code></li>\n        <li>Jerarquía de encabezados coherente</li>\n        <li>Listas cuando corresponda</li>\n      </ul>\n    </section>\n\n    <section id=\'teclado\'>\n      <h2>Navegación por Teclado</h2>\n      <p>Asegúrate de que todo sea accesible mediante teclado:</p>\n      <button style=\'padding: 10px; background-color: #2563eb; color: white; border: none; border-radius: 5px;\'>\n        Botón Enfocable\n      </button>\n    </section>\n\n    <section id=\'color\'>\n      <h2>Color y Contraste</h2>\n      <p>El contraste adecuado es crucial para la legibilidad:</p>\n      <ul>\n        <li>Texto normal: contraste ≥ 4.5:1</li>\n        <li>Texto grande: contraste ≥ 3:1</li>\n      </ul>\n      <div style=\'background-color: #2563eb; color: white; padding: 10px; border-radius: 5px;\'>\n        Ejemplo de buen contraste\n      </div>\n    </section>\n\n    <section id=\'formulario\'>\n      <h2>Formulario Accesible</h2>\n      <form>\n        <div style=\'margin-bottom: 15px;\'>\n          <label for=\'nombre\'>Nombre:</label>\n          <input type=\'text\' id=\'nombre\' name=\'nombre\' required aria-required=\'true\'>\n        </div>\n        <div style=\'margin-bottom: 15px;\'>\n          <label for=\'email\'>Email:</label>\n          <input type=\'email\' id=\'email\' name=\'email\' required aria-required=\'true\'>\n        </div>\n        <div>\n          <button type=\'submit\' style=\'padding: 10px; background-color: #2563eb; color: white; border: none; border-radius: 5px;\'>\n            Enviar\n          </button>\n        </div>\n      </form>\n    </section>\n  </main>\n\n  <footer>\n    <p>© 2023 Accesibilidad Web. Todos los derechos reservados.</p>\n  </footer>\n\n  <script>\n    // Ejemplo de manejo de foco para el botón\n    const button = document.querySelector(\'button\');\n    button.addEventListener(\'focus\', () => {\n      button.style.outline = \'3px solid #2563eb\';\n    });\n    button.addEventListener(\'blur\', () => {\n      button.style.outline = \'none\';\n    });\n\n    // Validación de formulario\n    const form = document.querySelector(\'form\');\n    form.addEventListener(\'submit\', (e) => {\n      e.preventDefault();\n      // Aquí iría la lógica de validación\n      alert(\'Formulario enviado con éxito\');\n    });\n  </script>\n</div>\n\n<script>\n// Checklist de autoevaluación\nconsole.log(\'Checklist de autoevaluación:\');\nconsole.log(\'✅ Idioma y título correctos\');\nconsole.log(\'✅ Landmarks y main único\');\nconsole.log(\'✅ Jerarquía de encabezados coherente\');\nconsole.log(\'✅ Navegación 100% teclado; foco visible\');\nconsole.log(\'✅ Contraste mínimo 4.5:1 texto normal / 3:1 texto grande\');\nconsole.log(\'✅ Enlaces y botones con propósito claro\');\nconsole.log(\'✅ Formularios con label y errores accesibles\');\nconsole.log(\'✅ Reflow a 320px/200% zoom sin pérdida (asumiendo CSS responsive)\');\nconsole.log(\'❓ Imágenes con alt correcto (no hay imágenes en este ejemplo)\');\nconsole.log(\'❓ Tablas con th y caption si procede (no hay tablas en este ejemplo)\');\nconsole.log(\'❓ Respeto de prefers-reduced-motion (no implementado en este ejemplo básico)\');\n</script>"\n}\n'''
        
        try:
            result = self._parse_json_string(test_json)
            logger.info(f"✅ JSON parsing successful: {len(result)} keys found")
            if 'html_content' in result:
                logger.info(f"✅ html_content found with length: {len(result['html_content'])}")
            return result
        except Exception as e:
            logger.error(f"❌ JSON parsing failed: {str(e)}")
            return {}

    @tool
    async def file_read_tool(self, **kwargs) -> dict:
        """
        Lee un archivo adjunto a partir de su id.
        params: dict que contendrá al menos {"id": "<document-id>"}
        Retorna un dict con el contenido textual (o error).
        """
        try:
            print("file_read called with:", kwargs)
            raw_kwargs = kwargs.get("kwargs")
            if not raw_kwargs:
                return {"error": "missing kwargs"}

            # convertir string JSON a dict
            params = json.loads(raw_kwargs)
            doc_id = params.get("id")
            if not doc_id:
                return {"error": "missing id"}


            storage_service = ContentStorageService()
            record = await storage_service.get_content_by_id(db = self.db, content_id = doc_id)
            if not record:
                return {"error": "file not found"}

            raw = getattr(record, "generation_parameters", None)
            try:
                if isinstance(raw, str):
                    params = json.loads(raw)
                else:
                    params = raw or {}
            except Exception:
                params = {}

            b64 = params.get("content")
            if not b64:
                return {"error": "no content"}

            # decodificar y extraer texto — puedes reutilizar tu lógica fitz/docx/utf8
            b64_clean = "".join(str(b64).split())
            decoded_bytes = base64.b64decode(b64_clean)
            title = getattr(record, "title", "")
            ext = title.lower().rsplit(".", 1)[-1] if "." in title else ""
            text = ""
            if ext == "pdf":
                import fitz
                with fitz.open(stream=decoded_bytes, filetype="pdf") as doc:
                    text = "\n".join(p.get_text("text") or "" for p in doc).strip()
            elif ext == "docx":
                import docx, io
                docx_file = io.BytesIO(decoded_bytes)
                doc = docx.Document(docx_file)
                text = "\n".join(p.text for p in doc.paragraphs).strip()
            else:
                try:
                    text = decoded_bytes.decode("utf-8")
                except Exception:
                    text = decoded_bytes.decode("latin1", errors="ignore")

            # recortar si es demasiado largo, o devolver por chunks
            MAX_CHARS = 20000
            if len(text) > MAX_CHARS:
                text = text[:MAX_CHARS] + "\n\n[--TRUNCATED--]"

            return {"text": text, "title": title, "id": doc_id}
        except Exception as e:
            return {"error": str(e)}