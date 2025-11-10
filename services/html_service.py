# © [2025] EDT&Partners. Licensed under CC BY 4.0.

"""
Service for HTML handling and manipulation
"""
import re
import uuid
from typing import Optional
from bs4 import BeautifulSoup

from interfaces.html_interface import HTMLServiceInterface

class HTMLService(HTMLServiceInterface):
    """Service for HTML manipulation using BeautifulSoup"""
    
    def __init__(self):
        """Initializes the HTML service"""
        pass
    
    def generate_initial_structure(self) -> str:
        """
        Generates an initial HTML structure
        
        Args:
            None
        Returns:
            str: HTML with initial structure
        """
        html_template = """
<style>
    body {
      font-family: Arial, sans-serif;
      margin: 2em;
      background: #f9f9f9;
      color: #222;
    }
    h1, h2 {
      color: #2a6ebb;
    }
    .modo {
      background: #e3f0ff;
      border-left: 4px solid #2a6ebb;
      padding: 1em;
      margin-bottom: 1em;
    }
    ul {
      margin-top: 0.5em;
    }
  </style>
""" f"""
        
    <div data-identification="void-{str(uuid.uuid4())} aria-hidden="true">&nbsp;</div>
    <h1>Start Guide - Content Generator</h1>
  <p>
    To start using the content generator, simply press the <strong>"Generate Content"</strong> button located in the main interface. This button will allow you to start the content creation process in a simple and guided way.
  </p>

  <h2>Content Generation Modes</h2>
  <p>
    By pressing the "Generate Content" button, the <strong>Content Generation Wizard</strong> will open, where you can choose between two generation modes:
  </p>

  <div class="modo">
    <h3>Manual Mode</h3>
    <ul>
      <li>In this mode, you have total control over the parameters and details of the content to be generated.</li>
      <li>You can customize each aspect according to your specific needs.</li>
      <li>Ideal for advanced users or when a very specific result is required.</li>
    </ul>
  </div>

  <div class="modo">
    <h3>Assisted Mode</h3>
    <ul>
      <li>The system will guide you step by step through a simplified process.</li>
      <li>You only need to provide the basic information and the assistant will take care of the rest.</li>
      <li>Recommended for new users or for generating content quickly and efficiently.</li>
    </ul>
  </div>

  <h2>How does the Content Generation Wizard work?</h2>
  <p>
    The <strong>Content Generation Wizard</strong> is an interactive modal that helps you select the generation mode and complete the necessary data to create your content. Follow the instructions on the screen and, once the process is complete, your content will be ready to be used.
  </p>

  <p>
    If you have any questions or need additional help, consult the complete documentation or contact the technical support.
  </p>
    <div data-identification="void-{str(uuid.uuid4())} aria-hidden="true">&nbsp;</div>"""
        return html_template
    
    def add_head_tags(self, html_content: str, tags: str) -> str:
        """
        Adds tags to the head of the HTML
        
        Args:
            html_content (str): Existing HTML content
            tags (str): Tags HTML to add to the head
            
        Returns:
            str: HTML with the tags added to the head
        """
        try:
            soup = BeautifulSoup(html_content, 'html.parser')
            head = soup.find('head')
            
            if head is None:
                # If there is no head, create one
                head = soup.new_tag('head')
                soup.html.insert(0, head)
            
            # Create a temporary soup to parse the tags
            tags_soup = BeautifulSoup(tags, 'html.parser')
            
            # Add each tag to the head
            for tag in tags_soup.find_all():
                head.append(tag)
            
            return str(soup)
            
        except Exception as e:
            raise RuntimeError(f"Error agregando tags al head: {str(e)}") from e
    
    def add_script(self, html_content: str, script: str, position: str = "body_end") -> str:
        """
        Adds a script to the HTML
        
        Args:
            html_content (str): Existing HTML content
            script (str): Script to add
            position (str): Position where to add the script ('head', 'body_start', 'body_end')
            
        Returns:
            str: HTML with the script added
        """
        try:
            soup = BeautifulSoup(html_content, 'html.parser')
            
            # Create the script tag
            script_tag = soup.new_tag('script')
            script_tag.string = script
            
            if position == "head":
                # Add to the head
                head = soup.find('head')
                if head is None:
                    head = soup.new_tag('head')
                    soup.html.insert(0, head)
                head.append(script_tag)
                
            elif position == "body_start":
                # Add to the beginning of the body
                body = soup.find('body')
                if body is None:
                    body = soup.new_tag('body')
                    soup.html.append(body)
                body.insert(0, script_tag)
                
            elif position == "body_end":
                # Add to the end of the body (by default)
                body = soup.find('body')
                if body is None:
                    body = soup.new_tag('body')
                    soup.html.append(body)
                body.append(script_tag)
                
            else:
                raise ValueError(f"Invalid position: {position}. Use 'head', 'body_start' or 'body_end'")
            
            return str(soup)
            
        except Exception as e:
            raise RuntimeError(f"Error adding script: {str(e)}") from e
    
    def replace_element_by_id(self, html_content: str, element_id: str, new_html: str) -> str:
        """
        Replaces an element by data-identification with new HTML structure
        
        Args:
            html_content (str): Existing HTML content
            element_id (str): Value of data-identification of the element to replace
            new_html (str): New HTML structure
            
        Returns:
            str: HTML with the element replaced
        """
        try:
            soup = BeautifulSoup(html_content, 'html.parser')
            
            # Search for the element by data-identification
            element = soup.find(attrs={"data-identification": element_id})
            
            if element is None:
                raise ValueError(f"Element with data-identification '{element_id}' not found")
            
            # Create soup for the new HTML structure
            new_soup = BeautifulSoup(new_html, 'html.parser')
            
            # Replace the content of the element
            element.clear()
            for child in new_soup.children:
                if child.name:  # Only HTML elements, no loose text
                    element.append(child)
                else:
                    element.append(str(child))
            
            return str(soup)
            
        except Exception as e:
            raise RuntimeError(f"Error replacing element by data-identification: {str(e)}") from e
    
    def validate_html(self, html_content: str) -> bool:
        """
        Validates that the HTML is valid
        
        Args:
            html_content (str): HTML content to validate
            
        Returns:
            bool: True if the HTML is valid
        """
        try:
            BeautifulSoup(html_content, 'html.parser')
            return True
        except (ValueError, TypeError):
            return False
    
    def get_element_by_id(self, html_content: str, element_id: str) -> Optional[str]:
        """
        Gets the content of an element by data-identification
        
        Args:
            html_content (str): HTML content
            element_id (str): Value of data-identification of the element
            
        Returns:
            Optional[str]: Content of the element or None if it does not exist
        """
        try:
            soup = BeautifulSoup(html_content, 'html.parser')
            element = soup.find(attrs={"data-identification": element_id})
            
            if element:
                return str(element)
            return None
            
        except (ValueError, TypeError):
            return None
    
    def add_identification_to_elements(self, html_content: str) -> str:
        """
        Traverses all HTML elements and assigns a UUID in data-identification
        
        Args:
            html_content (str): HTML content to process
            
        Returns:
            str: HTML with data-identification added to all elements
        """
        try:
            soup = BeautifulSoup(html_content, 'html.parser')
            
            # Traverse all HTML elements
            for element in soup.find_all():
                # Generate a unique UUID for each element
                element_uuid = str(uuid.uuid4())
                
                # Assign the UUID to the data-identification attribute
                element['data-identification'] = element_uuid
            
            return str(soup)
            
        except Exception as e:
            raise RuntimeError(f"Error adding identification to elements: {str(e)}") from e
    
    def wrap_element_with_void_divs(self, html_element: str) -> str:
        """
        Wraps an HTML element with void divs with data-identification void-UUID
        
        Args:
            html_element (str): HTML element to wrap
            
        Returns:
            str: HTML with the original element and two void divs before and after
        """
        try:
            # Generate unique UUIDs for the void divs
            void_uuid_before = str(uuid.uuid4())
            void_uuid_after = str(uuid.uuid4())
            
            # Create the void divs
            void_div_before = f'<div data-identification="void-{void_uuid_before}" aria-hidden="true">&nbsp;</div>'
            void_div_after = f'<div data-identification="void-{void_uuid_after}" aria-hidden="true">&nbsp;</div>'
            
            # Combine: void div + original element + void div
            result = f"{void_div_before}\n{html_element}\n{void_div_after}"
            
            return result
            
        except Exception as e:
            raise RuntimeError(f"Error wrapping element with void divs: {str(e)}") from e
    
    def clean_html(self, html_content: str) -> str:
        """
        Cleans the HTML by removing all text that is not inside HTML tags
        
        Args:
            html_content (str): HTML content to clean
            
        Returns:
            str: HTML clean with only valid HTML elements
        """
        try:
            # If the content is empty, return empty
            if not html_content or html_content.strip() == "":
                return ""
            
            # Search for the first HTML element (<)
            first_tag_start = html_content.find('<')
            if first_tag_start == -1:
                # No HTML tags, return empty
                return ""
            
            # Search for the last HTML element (>)
            last_tag_end = html_content.rfind('>')
            if last_tag_end == -1:
                # No closed HTML tags, return empty
                return ""
            
            # Extract only the part that contains valid HTML
            clean_html = html_content[first_tag_start:last_tag_end + 1]
            
            # Validate that the extracted HTML is valid
            try:
                soup = BeautifulSoup(clean_html, 'html.parser')
                # If there are valid HTML elements, return the clean HTML
                if soup.find_all():
                    return clean_html
                else:
                    # No valid HTML elements
                    return ""
            except Exception:
                # If it cannot be parsed, try a more aggressive cleaning
                return self._aggressive_html_clean(html_content)
                
        except Exception as e:
            raise RuntimeError(f"Error cleaning HTML: {str(e)}") from e
    
    def _aggressive_html_clean(self, html_content: str) -> str:
        """
        Aggressive HTML cleaning when the main method fails
        
        Args:
            html_content (str): HTML content to clean
            
        Returns:
            str: Clean HTML or empty string if it cannot be cleaned
        """
        try:
            # Search for all HTML tags using regex
            html_pattern = r'<[^>]+>'
            tags = re.findall(html_pattern, html_content)
            
            if not tags:
                return ""
            
            # Reconstruct HTML only with the found tags
            # This is an approximation, but it can work in simple cases
            clean_parts = []
            for tag in tags:
                clean_parts.append(tag)
            
            # Try to parse the result
            reconstructed_html = ''.join(clean_parts)
            try:
                soup = BeautifulSoup(reconstructed_html, 'html.parser')
                if soup.find_all():
                    return reconstructed_html
                else:
                    return ""
            except (ValueError, TypeError):
                return ""
                
        except (ValueError, TypeError):
            return ""
    
    def clean_void_duplicates(self, html_content: str) -> str:
        """
        Cleans duplicate void elements at the same level, leaving only one before and after each non-void element
        
        Args:
            html_content (str): HTML content to process
            
        Returns:
            str: HTML with duplicate void elements removed
        """
        try:
            soup = BeautifulSoup(html_content, 'html.parser')

            def process_container(container):
                if not container.children:
                    return
                children = list(container.children)
                new_children = []
                i = 0
                n = len(children)
                while i < n:
                    child = children[i]
                    # If it is a non-void element
                    if hasattr(child, 'name') and child.name and child.get('data-identification') and not child.get('data-identification').startswith('void-'):
                        # Group voids before
                        voids_before = []
                        j = i - 1
                        while j >= 0:
                            prev = children[j]
                            if hasattr(prev, 'name') and prev.name == 'div' and prev.get('data-identification', '').startswith('void-'):
                                voids_before.append(prev)
                                j -= 1
                            else:
                                break
                        if voids_before:
                            new_children.append(voids_before[-1])  # Only the last void before
                        else:
                            # If there is no void before, create one
                            new_children.append(soup.new_tag('div', **{'data-identification': f'void-{uuid.uuid4()}'}))
                        new_children.append(child)
                        # Group voids after
                        voids_after = []
                        j = i + 1
                        while j < n:
                            next_ = children[j]
                            if hasattr(next_, 'name') and next_.name == 'div' and next_.get('data-identification', '').startswith('void-'):
                                voids_after.append(next_)
                                j += 1
                            else:
                                break
                        if voids_after:
                            new_children.append(voids_after[0])  # Only the first void after
                        else:
                            # If there is no void after, create one
                            new_children.append(soup.new_tag('div', **{'data-identification': f'void-{uuid.uuid4()}'}))
                        i = j  # Skip the voids after
                    else:
                        # If it is not a non-void element, only add if it is not void
                        if not (hasattr(child, 'name') and child.name == 'div' and child.get('data-identification', '').startswith('void-')):
                            new_children.append(child)
                        i += 1
                container.clear()
                for c in new_children:
                    container.append(c)
                # Process recursively the children
                for c in container.children:
                    if hasattr(c, 'name') and c.name:
                        process_container(c)

            # Process the entire document
            for tag in soup.find_all(recursive=False):
                process_container(tag)
            process_container(soup)
            return str(soup)
        except Exception as e:
            raise RuntimeError(f"Error cleaning duplicate void elements: {str(e)}") from e 