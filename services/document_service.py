# © [2025] EDT&Partners. Licensed under CC BY 4.0.

"""
Service for educational document processing.

This service centralizes the logic for:
- Upload and process files with AWS Textract
- Extract structured information from documents
- Generate indices, pedagogical frameworks and instructional models using IA (Strands/AWS Bedrock)
- Provide reusable asynchronous methods for controllers
"""
from typing import List
from fastapi import UploadFile
from services.aws_service import AWSService
from services.html_service import HTMLService
from services.strands_service import StrandsService
from services.ai_service import AIService
import tempfile
import os
import uuid
import time
import asyncio
from concurrent.futures import ThreadPoolExecutor
from icecream import ic
import json

class DocumentService:
    def __init__(self):
        self.aws_service = AWSService()
        self.strands_service = StrandsService()
        self.ai_service = AIService()

    async def extract_all_from_files(self, archivos: List[UploadFile]):
        """
        Processes a list of files, extracts information with Textract and generates:
        - Content index using IA
        - Pedagogical framework
        - Instructional model
        
        Parameters:
            archivos (List[UploadFile]): Files to process
        
        Returns:
            dict: Dictionary with 'index', 'pedagogical_framework' and 'instructional_model'
        """
        s3_keys = []
        # Save and upload all files
        for archivo in archivos:
            with tempfile.NamedTemporaryFile(delete=False) as tmp:
                tmp.write(await archivo.read())
                tmp_path = tmp.name
            s3_key = self.aws_service.upload_file_to_s3(tmp_path, f"{uuid.uuid4()}.{archivo.filename.split('.')[-1]}")
            s3_keys.append(s3_key)
            os.remove(tmp_path)
        # Process each file with Textract and combine the information
        texto_extraido = ""
        info_extraida_completa = []
        for s3_key in s3_keys:
            ic(s3_key)
            job_id = self.aws_service.start_textract_analysis(s3_key)
            status = 'IN_PROGRESS'
            response = None
            while status == 'IN_PROGRESS':
                time.sleep(2)
                response = self.aws_service.get_textract_result(job_id)
                status = response.get('JobStatus')
            info_extraida = self.aws_service.extract_all_from_textract(response)
            info_extraida_completa.append(info_extraida)
            # Convert the extracted information into plain text for the index
            for doc in info_extraida.get('documents', []):
                for page in doc.get('aws_texttract_document', []):
                    for content in page.get('contents', []):
                        if 'text' in content:
                            texto_extraido += content['text'] + "\n"
                        elif 'table' in content:
                            for row in content['table']:
                                texto_extraido += " | ".join(row) + "\n"
        # Generate the 3 tasks in parallel to optimize performance
        print("🚀 Starting parallel generation of index, pedagogical framework and instructional model...")
        
        # Create tasks to execute in parallel
        index_task = self.ai_service.generate_content_index(texto_extraido)
        
        prompt_pedagogical = f"Genera un marco pedagógico a partir de la siguiente información: {info_extraida_completa}"
        pedagogical_task = self._run_sync_in_executor(
            self.strands_service.generate_pedagogical_framework, 
            prompt_pedagogical
        )
        
        prompt_instructional = f"Genera un marco instruccional a partir de la siguiente información: {info_extraida_completa}"
        instructional_task = self._run_sync_in_executor(
            self.strands_service.generate_instructional_model, 
            prompt_instructional
        )
        
        # Execute all tasks in parallel
        index, pedagogical_framework, instructional_model = await asyncio.gather(
            index_task,
            pedagogical_task,
            instructional_task,
            return_exceptions=True
        )
        
        # Handle individual errors
        if isinstance(index, Exception):
            print(f"❌ Error generating index: {str(index)}")
            index = {"error": f"Error generating index: {str(index)}"}
        
        if isinstance(pedagogical_framework, Exception):
            print(f"❌ Error generating pedagogical framework: {str(pedagogical_framework)}")
            pedagogical_framework = {"error": f"Error generating pedagogical framework: {str(pedagogical_framework)}"}
        
        if isinstance(instructional_model, Exception):
            print(f"❌ Error generating instructional model: {str(instructional_model)}")
            instructional_model = {"error": f"Error generating instructional model: {str(instructional_model)}"}
        
        print("✅ Parallel generation completed")
        return {
            'index': index,
            'pedagogical_framework': pedagogical_framework,
            'instructional_model': instructional_model
        }

    async def create_instructional_model(self, prompt: str, archivos: List[UploadFile]):
        """
        Generates an instructional model from one or more files and a prompt.
        
        Parameters:
            prompt (str): Prompt for the IA
            archivos (List[UploadFile]): Files to process
        
        Returns:
            dict: Dictionary with the key 'model' and the generated result
        """
        s3_keys = []
        for archivo in archivos:
            with tempfile.NamedTemporaryFile(delete=False) as tmp:
                tmp.write(await archivo.read())
                tmp_path = tmp.name
            s3_key = self.aws_service.upload_file_to_s3(tmp_path, f"{uuid.uuid4()}.{archivo.filename.split('.')[-1]}")
            s3_keys.append(s3_key)
            os.remove(tmp_path)
        resultados = []
        for s3_key in s3_keys:
            job_id = self.aws_service.start_textract_analysis(s3_key)
            status = 'IN_PROGRESS'
            response = None
            while status == 'IN_PROGRESS':
                time.sleep(2)
                response = self.aws_service.get_textract_result(job_id)
                status = response.get('JobStatus')
            info_extraida = self.aws_service.extract_all_from_textract(response)
            prompt_model = f"Genera un marco instruccional a partir de la siguiente información: {info_extraida}"
            model = self.strands_service.generate_instructional_model(prompt_model)
            resultados.append(model)
        resultados = [item for sublist in resultados for item in sublist]
        return {'model': resultados}

    async def create_pedagogical_framework(self, prompt: str, archivos: List[UploadFile]):
        """
        Generates a pedagogical framework from one or more files and a prompt.
        
        Parameters:
            prompt (str): Prompt for the IA
            archivos (List[UploadFile]): Files to process
        
        Returns:
            dict: Dictionary with the key 'model' and the generated result
        """
        s3_keys = []
        for archivo in archivos:
            with tempfile.NamedTemporaryFile(delete=False) as tmp:
                tmp.write(await archivo.read())
                tmp_path = tmp.name
            s3_key = self.aws_service.upload_file_to_s3(tmp_path, f"{uuid.uuid4()}.{archivo.filename.split('.')[-1]}")
            s3_keys.append(s3_key)
            os.remove(tmp_path)
        resultados = []
        for s3_key in s3_keys:
            job_id = self.aws_service.start_textract_analysis(s3_key)
            status = 'IN_PROGRESS'
            response = None
            while status == 'IN_PROGRESS':
                time.sleep(2)
                response = self.aws_service.get_textract_result(job_id)
                status = response.get('JobStatus')
            info_extraida = self.aws_service.extract_all_from_textract(response)
            prompt_model = f"Genera un marco pedagógico a partir de la siguiente información: {info_extraida}"
            model = self.strands_service.generate_pedagogical_framework(prompt_model)
            resultados.append(model)
        resultados = [item for sublist in resultados for item in sublist]
        return {'model': resultados}

    async def extract_index_from_pdf(self, archivos: List[UploadFile]):
        """
        Extracts the index of one or more PDF files using Textract and the IA.
        
        Parameters:
            archivos (List[UploadFile]): PDF files to process
        
        Returns:
            dict: Dictionary with the key 'index' and the generated index
        """
        texto_extraido = """Based on the following data, you must be able to generate a content index for an educational document. 
        You must identify if the document is a curriculum design, a study plan, a book, an auxiliary document, etc.
        You must identify the training that will be imparted according to the document.
        The index will be based on a pedagogical content.
        Based on the training that will be imparted, you must identify the contents that must be addressed.
        If you do not identify the topics that must be addressed, you must generate a general index of the contents that must be addressed.
        Indicate through the index how to achieve the learning objectives and theoretical and practical contents.
        Add data from the training, subject, level, content type, evaluation type, etc. before the learning objectives."""
        for archivo in archivos:
            with tempfile.NamedTemporaryFile(delete=False) as tmp:
                tmp.write(await archivo.read())
                tmp_path = tmp.name
            s3_key = self.aws_service.upload_file_to_s3(tmp_path, f"{uuid.uuid4()}.{archivo.filename.split('.')[-1]}")
            os.remove(tmp_path)
            job_id = self.aws_service.start_textract_analysis(s3_key)
            status = 'IN_PROGRESS'
            response = None
            while status == 'IN_PROGRESS':
                time.sleep(2)
                response = self.aws_service.get_textract_result(job_id)
                status = response.get('JobStatus')
            info_extraida = self.aws_service.extract_all_from_textract(response)
            for doc in info_extraida.get('documents', []):
                for page in doc.get('aws_texttract_document', []):
                    for content in page.get('contents', []):
                        if 'text' in content:
                            texto_extraido += content['text'] + "\n"
                        elif 'table' in content:
                            for row in content['table']:
                                texto_extraido += " | ".join(row) + "\n"
        index = await self.ai_service.generate_content_index(texto_extraido)
        return {'index': index}

    async def extract_index_from_saved_files(self, saved_files: List[dict]):
        """
        Extracts index from saved file contents (for async processing)
        
        Parameters:
            saved_files (List[dict]): List of dictionaries with file info
                Each dict contains: {'filename': str, 'content': bytes, 'content_type': str}
        
        Returns:
            dict: Dictionary with the key 'index' and the generated index
        """
        texto_extraido = """Based on the following data, you must be able to generate a content index for an educational document. 
        You must identify if the document is a curriculum design, a study plan, a book, an auxiliary document, etc.
        You must identify the training that will be imparted according to the document.
        The index will be based on a pedagogical content.
        Based on the training that will be imparted, you must identify the contents that must be addressed.
        If you do not identify the topics that must be addressed, you must generate a general index of the contents that must be addressed.
        Indicate through the index how to achieve the learning objectives and theoretical and practical contents.
        Add data from the training, subject, level, content type, evaluation type, etc. before the learning objectives."""
        
        for saved_file in saved_files:
            with tempfile.NamedTemporaryFile(delete=False) as tmp:
                tmp.write(saved_file['content'])
                tmp_path = tmp.name
            s3_key = self.aws_service.upload_file_to_s3(tmp_path, f"{uuid.uuid4()}.{saved_file['filename'].split('.')[-1]}")
            os.remove(tmp_path)
            job_id = self.aws_service.start_textract_analysis(s3_key)
            status = 'IN_PROGRESS'
            response = None
            while status == 'IN_PROGRESS':
                time.sleep(2)
                response = self.aws_service.get_textract_result(job_id)
                status = response.get('JobStatus')
            info_extraida = self.aws_service.extract_all_from_textract(response)
            for doc in info_extraida.get('documents', []):
                for page in doc.get('aws_texttract_document', []):
                    for content in page.get('contents', []):
                        if 'text' in content:
                            texto_extraido += content['text'] + "\n"
                        elif 'table' in content:
                            for row in content['table']:
                                texto_extraido += " | ".join(row) + "\n"
        index = await self.ai_service.generate_content_index(texto_extraido)
        return {'index': index}

    async def extract_all_from_saved_files(self, saved_files: List[dict]):
        """
        Extracts all information from saved file contents (for async processing)
        
        Parameters:
            saved_files (List[dict]): List of dictionaries with file info
                Each dict contains: {'filename': str, 'content': bytes, 'content_type': str}
        
        Returns:
            dict: Dictionary with 'index', 'pedagogical_framework' and 'instructional_model'
        """
        texto_extraido = """Based on the following data, you must be able to generate a content index for an educational document. 
        You must identify if the document is a curriculum design, a study plan, a book, an auxiliary document, etc.
        You must identify the training that will be imparted according to the document.
        The index will be based on a pedagogical content.
        Based on the training that will be imparted, you must identify the contents that must be addressed.
        If you do not identify the topics that must be addressed, you must generate a general index of the contents that must be addressed.
        Indicate through the index how to achieve the learning objectives and theoretical and practical contents.
        Add data from the training, subject, level, content type, evaluation type, etc. before the learning objectives."""
        
        for saved_file in saved_files:
            with tempfile.NamedTemporaryFile(delete=False) as tmp:
                tmp.write(saved_file['content'])
                tmp_path = tmp.name
            s3_key = self.aws_service.upload_file_to_s3(tmp_path, f"{uuid.uuid4()}.{saved_file['filename'].split('.')[-1]}")
            os.remove(tmp_path)
            job_id = self.aws_service.start_textract_analysis(s3_key)
            status = 'IN_PROGRESS'
            response = None
            while status == 'IN_PROGRESS':
                time.sleep(2)
                response = self.aws_service.get_textract_result(job_id)
                status = response.get('JobStatus')
            info_extraida = self.aws_service.extract_all_from_textract(response)
            for doc in info_extraida.get('documents', []):
                for page in doc.get('aws_texttract_document', []):
                    for content in page.get('contents', []):
                        if 'text' in content:
                            texto_extraido += content['text'] + "\n"
                        elif 'table' in content:
                            for row in content['table']:
                                texto_extraido += " | ".join(row) + "\n"
        
        # Generate all three outputs
        index = await self.ai_service.generate_content_index(texto_extraido)
        pedagogical_framework = await self.ai_service.generate_pedagogical_framework(texto_extraido)
        instructional_model = await self.ai_service.generate_instructional_model(texto_extraido)
        
        return {
            'index': index,
            'pedagogical_framework': pedagogical_framework,
            'instructional_model': instructional_model
        }

    async def generate_structured_content(self, prompt: str, context: List[dict], profile: str, files: List[UploadFile]):
        """
        Generates structured HTML content from PDF files and context.
        
        Parameters:
            prompt (str): User prompt
            context (List[dict]): List of objects with {title: str, context: str}
            profile (str): Type of content to generate
            files (List[UploadFile]): PDF files to process (optional)
        
        Returns:
            str: Structured HTML generated in a section tag
        """
        # 1. Generate the structure of each PDF file (if provided)
        pdf_structures = []
        if files:
            for archivo in files:
                with tempfile.NamedTemporaryFile(delete=False) as tmp:
                    tmp.write(await archivo.read())
                    tmp_path = tmp.name
                s3_key = self.aws_service.upload_file_to_s3(tmp_path, f"{uuid.uuid4()}.{archivo.filename.split('.')[-1]}")
                os.remove(tmp_path)
                
                # Process with Textract
                job_id = self.aws_service.start_textract_analysis(s3_key)
                status = 'IN_PROGRESS'
                response = None
                while status == 'IN_PROGRESS':
                    time.sleep(2)
                    response = self.aws_service.get_textract_result(job_id)
                    status = response.get('JobStatus')
                
                # Extract the structure of the PDF
                info_extraida = self.aws_service.extract_all_from_textract(response)
                pdf_structures.append({
                    'filename': archivo.filename,
                    'structure': info_extraida
                })
        
        # 2. Generate instructions for the Strands Agent
        agent_instructions = f"""
        You are an expert in generating structured HTML content for {profile}.
        
        SPECIFIC INSTRUCTIONS:
        1. You must return ONLY valid HTML
        2. The HTML must be grouped in a <body></body> tag
        3. Use appropriate semantic tags (h1, h2, h3, p, ul, ol, etc.)
        4. The content must be well structured and readable
        5. DO NOT include HTML comments or additional text
        6. The HTML must be valid and complete
        
        REQUIRED STRUCTURE:
        <body>
            <!-- Your HTML content here -->
        </body>
        """
        
        # 3. Generate the prompt for the Strands Agent
        context_text = ""
        if not context:
            context = []

        try:
            context = json.loads(context)
        except Exception as e:
            ic(e)
            context = context

        for item in context:
            context_text += f"TITLE: {item['title']}\nCONTEXT: {item['context']}\n\n"
        
        pdf_content = ""
        if pdf_structures:
            for pdf in pdf_structures:
                pdf_content += f"FILE: {pdf['filename']}\n"
                # Use the auxiliary method to extract text
                file_content = self._extract_text_from_file_structure(pdf)
                pdf_content += file_content + "\n\n"
        else:
            pdf_content = "No files were provided to process.\n"
        
        final_prompt = f"""
        USER REQUEST: {prompt}
        
        CONTENT TYPE: {profile}
        
        PROVIDED CONTEXT:
        {context_text}
        
        PDF FILE CONTENT:
        {pdf_content}
        
        Generate structured HTML content based on the user request, 
        the provided context and the content of the PDF files.
        """
        
        # 4. Generate HTML using Strands Agent
        try:
            html_service = HTMLService()
            html_content = await self.strands_service.generate_text(
                prompt=final_prompt,
                system_prompt=agent_instructions
            )

            # Remove the section tag if it exists <body> and </body>
            html_content = html_content.replace('<body>', '').replace('</body>', '')
            
            html_content = html_service.clean_html(html_content)
            html_content = html_service.wrap_element_with_void_divs(html_content)
            html_content = html_service.add_identification_to_elements(html_content)
            return html_content
            
        except Exception as e:
            print(f"❌ Error generating structured content: {str(e)}")
            # Fallback: generate basic HTML with the error
            return f'<section><p>Error generando contenido: {str(e)}</p></section>'
    
    async def _run_sync_in_executor(self, func, *args, **kwargs):
        """
        Executes a synchronous function in an executor to make it asynchronous
        
        Args:
            func: Synchronous function to execute
            *args: Positional arguments for the function
            **kwargs: Named arguments for the function
            
        Returns:
            Result of the function executed asynchronously
        """
        loop = asyncio.get_event_loop()
        with ThreadPoolExecutor() as executor:
            return await loop.run_in_executor(executor, func, *args, **kwargs) 

    async def extract_pdf_metadata_and_generate_html(self, file: UploadFile, preserve_styles: bool = True, generate_html: bool = True):
        """
        Extracts detailed metadata from a PDF and generates HTML respecting styles.
        
        Parameters:
            file (UploadFile): PDF file to process
            preserve_styles (bool): If the original styles should be preserved
            generate_html (bool): If HTML should be generated with the styles
        
        Returns:
            dict: Dictionary with metadata and generated HTML
        """
        import tempfile
        import fitz
        import json
        import re
        from utility.common import _process_pdf_with_formatting
        
        # Save file temporarily
        with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as tmp:
            tmp.write(await file.read())
            tmp_path = tmp.name
        
        try:
            # Open PDF with PyMuPDF
            doc = fitz.open(tmp_path)
            
            # Verify that the document was opened correctly
            if doc is None or len(doc) == 0:
                raise ValueError("The PDF could not be opened or is empty")
            
            # Extract metadata from the document safely
            doc_metadata = doc.metadata
            if isinstance(doc_metadata, bytes):
                doc_metadata = {}
            elif not isinstance(doc_metadata, dict):
                doc_metadata = {}
            
            metadata = {
                "document_info": {
                    "title": doc_metadata.get("title", "") if isinstance(doc_metadata, dict) else "",
                    "author": doc_metadata.get("author", "") if isinstance(doc_metadata, dict) else "",
                    "subject": doc_metadata.get("subject", "") if isinstance(doc_metadata, dict) else "",
                    "creator": doc_metadata.get("creator", "") if isinstance(doc_metadata, dict) else "",
                    "producer": doc_metadata.get("producer", "") if isinstance(doc_metadata, dict) else "",
                    "creation_date": doc_metadata.get("creationDate", "") if isinstance(doc_metadata, dict) else "",
                    "modification_date": doc_metadata.get("modDate", "") if isinstance(doc_metadata, dict) else "",
                    "page_count": len(doc),
                    "file_size": os.path.getsize(tmp_path)
                },
                "pages": [],
                "fonts": set(),
                "colors": set(),
                "styles": {
                    "paragraph_styles": [],
                    "text_styles": [],
                    "layout_styles": []
                },
                "images": [],
                "tables": [],
                "links": []
            }
            
            # Process each page
            for page_num in range(len(doc)):
                try:
                    page = doc[page_num]
                    page_dict = page.get_text("dict")
                    
                    # Verify that page_dict is a valid dictionary
                    if not isinstance(page_dict, dict):
                        page_dict = {"blocks": []}
                    
                    page_metadata = {
                        "page_number": page_num + 1,
                        "width": page.rect.width,
                        "height": page.rect.height,
                        "rotation": page.rotation,
                        "blocks": [],
                        "fonts_used": set(),
                        "colors_used": set(),
                        "text_content": "",
                        "html_content": ""
                    }
                    
                    # Process text blocks
                    for block in page_dict.get("blocks", []):
                        if "lines" in block:  # Text block
                            block_data = {
                                "type": "text",
                                "bbox": block.get("bbox", []),
                                "lines": []
                            }
                            
                            for line in block["lines"]:
                                line_data = {
                                    "bbox": line.get("bbox", []),
                                    "spans": []
                                }
                                
                                for span in line["spans"]:
                                    # Extract font and color information
                                    font_name = span.get("font", "")
                                    font_size = span.get("size", 0)
                                    color = span.get("color", 0)
                                    flags = span.get("flags", 0)
                                    
                                    # Convert color to RGB
                                    color_rgb = self._convert_color_to_rgb(color)
                                    
                                    # Determine text style
                                    text_style = self._determine_text_style(flags)
                                    
                                    span_data = {
                                        "text": span.get("text", ""),
                                        "font": font_name,
                                        "font_size": font_size,
                                        "color": color_rgb,
                                        "style": text_style,
                                        "bbox": span.get("bbox", [])
                                    }
                                    
                                    line_data["spans"].append(span_data)
                                    page_metadata["fonts_used"].add(font_name)
                                    page_metadata["colors_used"].add(color_rgb)
                                    metadata["fonts"].add(font_name)
                                    metadata["colors"].add(color_rgb)
                                    
                                    # Accumulate text
                                    page_metadata["text_content"] += span.get("text", "")
                                
                                block_data["lines"].append(line_data)
                            
                            page_metadata["blocks"].append(block_data)
                        
                        elif "image" in block:  # Image block
                            # Handle different types of image data
                            image_info = block["image"]
                            
                            if isinstance(image_info, dict):
                                # It is a dictionary with metadata
                                image_data = {
                                    "type": "image",
                                    "bbox": block.get("bbox", []),
                                    "width": image_info.get("width", 0),
                                    "height": image_info.get("height", 0),
                                    "colorspace": image_info.get("colorspace", 0),
                                    "bpc": image_info.get("bpc", 0),
                                    "data_type": "metadata"
                                }
                            elif isinstance(image_info, bytes):
                                # They are the bytes of the image - convert to base64
                                try:
                                    import base64
                                    image_base64 = base64.b64encode(image_info).decode('utf-8')
                                    
                                    # Try to detect the MIME type based on the first bytes
                                    mime_type = "image/jpeg"  # Default
                                    if image_info.startswith(b'\xff\xd8\xff'):
                                        mime_type = "image/jpeg"
                                    elif image_info.startswith(b'\x89PNG\r\n\x1a\n'):
                                        mime_type = "image/png"
                                    elif image_info.startswith(b'GIF87a') or image_info.startswith(b'GIF89a'):
                                        mime_type = "image/gif"
                                    elif image_info.startswith(b'RIFF') and image_info[8:12] == b'WEBP':
                                        mime_type = "image/webp"
                                    elif image_info.startswith(b'BM'):
                                        mime_type = "image/bmp"
                                    
                                    image_data = {
                                        "type": "image",
                                        "bbox": block.get("bbox", []),
                                        "width": 0,  # No disponible en bytes
                                        "height": 0,  # No disponible en bytes
                                        "colorspace": 0,  # No disponible en bytes
                                        "bpc": 0,  # No disponible en bytes
                                        "data_type": "base64",
                                        "mime_type": mime_type,
                                        "data_size": len(image_info),
                                        "base64_data": image_base64,
                                        "data_preview": image_info[:100].hex() if len(image_info) > 100 else image_info.hex()
                                    }
                                except Exception as e:
                                    # Fallback if the conversion fails
                                    image_data = {
                                        "type": "image",
                                        "bbox": block.get("bbox", []),
                                        "width": 0,
                                        "height": 0,
                                        "colorspace": 0,
                                        "bpc": 0,
                                        "data_type": "bytes",
                                        "data_size": len(image_info),
                                        "data_preview": image_info[:100].hex() if len(image_info) > 100 else image_info.hex(),
                                        "conversion_error": str(e)
                                    }
                            else:
                                # Unknown type
                                image_data = {
                                    "type": "image",
                                    "bbox": block.get("bbox", []),
                                    "width": 0,
                                    "height": 0,
                                    "colorspace": 0,
                                    "bpc": 0,
                                    "data_type": "unknown",
                                    "raw_data_type": str(type(image_info))
                                }
                            
                            page_metadata["blocks"].append(image_data)
                            metadata["images"].append(image_data)
                    
                    # Process links
                    links = page.get_links()
                    for link in links:
                        link_data = {
                            "type": link.get("kind", ""),
                            "uri": link.get("uri", ""),
                            "bbox": link.get("rect", []),
                            "page": page_num + 1
                        }
                        page_metadata["blocks"].append(link_data)
                        metadata["links"].append(link_data)
                    
                    # Convert sets to lists for JSON serialization
                    page_metadata["fonts_used"] = list(page_metadata["fonts_used"])
                    page_metadata["colors_used"] = list(page_metadata["colors_used"])
                    
                    metadata["pages"].append(page_metadata)
                    
                except Exception as e:
                    print(f"Error processing page {page_num + 1}: {str(e)}")
                    # Add empty page in case of error
                    metadata["pages"].append({
                        "page_number": page_num + 1,
                        "width": 0,
                        "height": 0,
                        "rotation": 0,
                        "blocks": [],
                        "fonts_used": [],
                        "colors_used": [],
                        "text_content": f"Error processing page: {str(e)}",
                        "html_content": ""
                    })
            
            # Convert sets to lists
            metadata["fonts"] = list(metadata["fonts"])
            metadata["colors"] = list(metadata["colors"])
            
            # Generate HTML if requested
            html_content = ""
            if generate_html:
                html_content = self._generate_html_from_metadata(metadata, preserve_styles)
            
            return {
                "metadata": metadata,
                "html_content": html_content if generate_html else None,
                "preserve_styles": preserve_styles
            }
            
        finally:
            # Clean temporary file
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
            doc.close()

    async def extract_pdf_metadata_by_pages(self, file: UploadFile):
        """
        Extracts metadata from a PDF grouped by pages.
        
        Args:
            file (UploadFile): PDF file to process
            
        Returns:
            dict: Dictionary with list of pages and their metadata
        """
        import tempfile
        import os
        import fitz
        import uuid
        
        # Create temporary file
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp_file:
            tmp_path = tmp_file.name
            content = await file.read()
            tmp_file.write(content)
        
        try:
            # Open the PDF document
            doc = fitz.open(tmp_path)
            
            # Extract metadata from the document safely
            doc_metadata = doc.metadata
            if isinstance(doc_metadata, bytes):
                doc_metadata = {}
            elif not isinstance(doc_metadata, dict):
                doc_metadata = {}
            
            document_info = {
                "title": doc_metadata.get("title", "") if isinstance(doc_metadata, dict) else "",
                "author": doc_metadata.get("author", "") if isinstance(doc_metadata, dict) else "",
                "subject": doc_metadata.get("subject", "") if isinstance(doc_metadata, dict) else "",
                "creator": doc_metadata.get("creator", "") if isinstance(doc_metadata, dict) else "",
                "producer": doc_metadata.get("producer", "") if isinstance(doc_metadata, dict) else "",
                "creation_date": doc_metadata.get("creationDate", "") if isinstance(doc_metadata, dict) else "",
                "modification_date": doc_metadata.get("modDate", "") if isinstance(doc_metadata, dict) else "",
                "page_count": len(doc),
                "file_size": os.path.getsize(tmp_path)
            }
            
            pages = []
            
            # Process each page
            for page_num in range(len(doc)):
                try:
                    page = doc[page_num]
                    page_dict = page.get_text("dict")
                    
                    # Verify that page_dict is a valid dictionary
                    if not isinstance(page_dict, dict):
                        page_dict = {"blocks": []}
                    
                    # Page metadata
                    page_metadata = {
                        "page_number": page_num + 1,
                        "width": page.rect.width,
                        "height": page.rect.height,
                        "rotation": page.rotation,
                        "blocks": [],
                        "fonts_used": [],
                        "colors_used": [],
                        "images": [],
                        "links": [],
                        "styles": [],
                        "text_content": "",
                        "document_info": document_info
                    }
                    
                    # Process blocks of the page
                    blocks = page_dict.get("blocks", [])
                    if not isinstance(blocks, list):
                        blocks = []
                    
                    for block in blocks:
                        if not isinstance(block, dict):
                            continue
                            
                        if "lines" in block:  # Text block
                            # Process lines and spans
                            for line in block.get("lines", []):
                                if not isinstance(line, dict):
                                    continue
                                    
                                for span in line.get("spans", []):
                                    if not isinstance(span, dict):
                                        continue
                                        
                                    # Extract span information
                                    text = span.get("text", "")
                                    font = span.get("font", "")
                                    size = span.get("size", 0)
                                    color = span.get("color", 0)
                                    flags = span.get("flags", 0)
                                    
                                    # Add text to the page content
                                    page_metadata["text_content"] += text
                                    
                                    # Add font if it does not exist
                                    if font and font not in page_metadata["fonts_used"]:
                                        page_metadata["fonts_used"].append(font)
                                    
                                    # Add color if it does not exist
                                    if color not in page_metadata["colors_used"]:
                                        page_metadata["colors_used"].append(color)
                                    
                                    # Determine text style
                                    style = self._determine_text_style(flags)
                                    if style not in page_metadata["styles"]:
                                        page_metadata["styles"].append(style)
                                    
                                    # Create text block
                                    text_block = {
                                        "type": "text",
                                        "text": text,
                                        "font": font,
                                        "size": size,
                                        "color": color,
                                        "style": style,
                                        "bbox": span.get("bbox", [])
                                    }
                                    page_metadata["blocks"].append(text_block)
                                    
                        elif "image" in block:  # Image block
                            # Handle different types of image data
                            image_info = block["image"]
                            image_uuid = str(uuid.uuid4())
                            
                            if isinstance(image_info, dict):
                                # It is a dictionary with metadata
                                image_data = {
                                    "uuid": image_uuid,
                                    "type": "image",
                                    "bbox": block.get("bbox", []),
                                    "width": image_info.get("width", 0),
                                    "height": image_info.get("height", 0),
                                    "colorspace": image_info.get("colorspace", 0),
                                    "bpc": image_info.get("bpc", 0),
                                    "data_type": "metadata"
                                }
                            elif isinstance(image_info, bytes):
                                # They are the bytes of the image - convert to base64
                                try:
                                    import base64
                                    image_base64 = base64.b64encode(image_info).decode('utf-8')
                                    
                                    # Try to detect the MIME type based on the first bytes
                                    mime_type = "image/jpeg"  # Default
                                    if image_info.startswith(b'\xff\xd8\xff'):
                                        mime_type = "image/jpeg"
                                    elif image_info.startswith(b'\x89PNG\r\n\x1a\n'):
                                        mime_type = "image/png"
                                    elif image_info.startswith(b'GIF87a') or image_info.startswith(b'GIF89a'):
                                        mime_type = "image/gif"
                                    elif image_info.startswith(b'RIFF') and image_info[8:12] == b'WEBP':
                                        mime_type = "image/webp"
                                    elif image_info.startswith(b'BM'):
                                        mime_type = "image/bmp"
                                    
                                    image_data = {
                                        "uuid": image_uuid,
                                        "type": "image",
                                        "bbox": block.get("bbox", []),
                                        "width": 0,  # Not available in bytes
                                        "height": 0,  # Not available in bytes
                                        "colorspace": 0,  # Not available in bytes
                                        "bpc": 0,  # Not available in bytes
                                        "data_type": "base64",
                                        "mime_type": mime_type,
                                        "data_size": len(image_info),
                                        "base64_data": image_base64,
                                        "data_preview": image_info[:100].hex() if len(image_info) > 100 else image_info.hex()
                                    }
                                except Exception as e:
                                    # Fallback if the conversion fails
                                    image_data = {
                                        "uuid": image_uuid,
                                        "type": "image",
                                        "bbox": block.get("bbox", []),
                                        "width": 0,
                                        "height": 0,
                                        "colorspace": 0,
                                        "bpc": 0,
                                        "data_type": "bytes",
                                        "data_size": len(image_info),
                                        "data_preview": image_info[:100].hex() if len(image_info) > 100 else image_info.hex(),
                                        "conversion_error": str(e)
                                    }
                            else:
                                # Unknown type
                                image_data = {
                                    "uuid": image_uuid,
                                    "type": "image",
                                    "bbox": block.get("bbox", []),
                                    "width": 0,
                                    "height": 0,
                                    "colorspace": 0,
                                    "bpc": 0,
                                    "data_type": "unknown",
                                    "raw_data_type": str(type(image_info))
                                }
                            
                            page_metadata["blocks"].append(image_data)
                            page_metadata["images"].append(image_data)
                            
                        elif "link" in block:  # Link block
                            link_data = {
                                "type": "link",
                                "uri": block.get("uri", ""),
                                "bbox": block.get("bbox", []),
                                "text": block.get("text", "")
                            }
                            page_metadata["blocks"].append(link_data)
                            page_metadata["links"].append(link_data)
                    
                    # Convert colors to RGB
                    page_metadata["colors"] = [self._convert_color_to_rgb(color) for color in page_metadata["colors_used"]]
                    
                    pages.append(page_metadata)
                    
                except Exception as e:
                    print(f"Error processing page {page_num + 1}: {str(e)}")
                    # Add empty page in case of error
                    pages.append({
                        "page_number": page_num + 1,
                        "width": 0,
                        "height": 0,
                        "rotation": 0,
                        "blocks": [],
                        "fonts_used": [],
                        "colors_used": [],
                        "images": [],
                        "links": [],
                        "styles": [],
                        "text_content": f"Error processing page: {str(e)}",
                        "document_info": document_info
                    })
            
            doc.close()
            
            return {
                "pages": pages,
                "total_pages": len(pages),
                "document_info": document_info
            }
            
        except Exception as e:
            raise Exception(f"Error procesando PDF: {str(e)}")
        finally:
            # Clean temporary file
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)

    async def process_accessibility_rules_file(self, accessibility_file: UploadFile) -> dict:
        """
        Processes an accessibility rules file using the same process as generate_structured_content.
        
        Args:
            accessibility_file (UploadFile): File with accessibility rules
            
        Returns:
            dict: Dictionary with the processed file structure
        """
        import tempfile
        import uuid
        import time
        
        try:
            # 1. Save file temporarily
            with tempfile.NamedTemporaryFile(delete=False) as tmp:
                tmp.write(await accessibility_file.read())
                tmp_path = tmp.name
            
            # 2. Upload file to S3
            s3_key = self.aws_service.upload_file_to_s3(
                tmp_path, 
                f"{uuid.uuid4()}.{accessibility_file.filename.split('.')[-1]}"
            )
            
            # 3. Process with Textract
            job_id = self.aws_service.start_textract_analysis(s3_key)
            status = 'IN_PROGRESS'
            response = None
            
            while status == 'IN_PROGRESS':
                time.sleep(2)
                response = self.aws_service.get_textract_result(job_id)
                status = response.get('JobStatus')
            
            # 4. Extract file structure
            info_extraida = self.aws_service.extract_all_from_textract(response)
            
            # 5. Create structure similar to pdf_structures
            file_structure = {
                'filename': accessibility_file.filename,
                'structure': info_extraida,
                'type': 'accessibility_rules'
            }
            
            # 6. Clean temporary file
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
            
            return file_structure
            
        except Exception as e:
            print(f"❌ Error procesando archivo de accesibilidad: {str(e)}")
            # Fallback: read the file as plain text
            try:
                content = await accessibility_file.read()
                text_content = content.decode('utf-8')
                
                return {
                    'filename': accessibility_file.filename,
                    'structure': {
                        'raw_text': text_content,
                        'documents': [{
                            'aws_texttract_document': [{
                                'contents': [{'text': text_content}]
                            }]
                        }]
                    },
                    'type': 'accessibility_rules',
                    'fallback': True
                }
            except Exception as fallback_error:
                print(f"❌ Error en fallback: {str(fallback_error)}")
                return {
                    'filename': accessibility_file.filename,
                    'structure': {
                        'raw_text': 'Error procesando archivo de accesibilidad',
                        'documents': []
                    },
                    'type': 'accessibility_rules',
                    'error': str(e)
                }

    def _extract_text_from_file_structure(self, file_structure: dict) -> str:
        """
        Extracts the text content of a processed file structure.
        
        Args:
            file_structure (dict): Processed file structure
            
        Returns:
            str: Extracted text content
        """
        try:
            structure = file_structure.get('structure', {})
            
            # If there is raw text (fallback), use it directly
            if 'raw_text' in structure:
                return structure['raw_text']
            
            # Extract text from the document structure (like in generate_structured_content)
            text_content = ""
            
            for doc in structure.get('documents', []):
                for page in doc.get('aws_texttract_document', []):
                    for content in page.get('contents', []):
                        if 'text' in content:
                            text_content += content['text'] + "\n"
                        elif 'table' in content:
                            for row in content['table']:
                                text_content += " | ".join(row) + "\n"
            
            return text_content.strip()
            
        except Exception as e:
            print(f"❌ Error extracting text from structure: {str(e)}")
            return f"Error extracting content: {str(e)}"

    def _convert_color_to_rgb(self, color_value):
        """Converts color value from PDF to RGB"""
        if color_value == 0:
            return "#000000"  # Black by default
        
        # Convert color value to RGB (simplified)
        # In PDF, the color can be in different formats
        try:
            # Assume that it is an RGB value in decimal format
            r = int((color_value >> 16) & 255)
            g = int((color_value >> 8) & 255)
            b = int(color_value & 255)
            return f"#{r:02x}{g:02x}{b:02x}"
        except:
            return "#000000"

    def _determine_text_style(self, flags):
        """Determines the text style based on PDF flags"""
        styles = []
        
        if flags & 2**0:  # Superscript
            styles.append("superscript")
        if flags & 2**1:  # Italic
            styles.append("italic")
        if flags & 2**2:  # Serifed
            styles.append("serif")
        if flags & 2**3:  # Monospaced
            styles.append("monospace")
        if flags & 2**4:  # Bold
            styles.append("bold")
        
        return styles

    def _generate_html_from_metadata(self, metadata, preserve_styles):
        """Generates HTML respecting the extracted styles from the PDF"""
        html_parts = []
        
        # CSS for styles
        css_styles = []
        if preserve_styles:
            # Add styles for unique fonts
            for i, font in enumerate(metadata["fonts"]):
                css_styles.append(f"""
                .font-{i} {{
                    font-family: "{font}", Arial, sans-serif;
                }}
                """)
            
            # Add styles for unique colors
            for i, color in enumerate(metadata["colors"]):
                css_styles.append(f"""
                .color-{i} {{
                    color: {color};
                }}
                """)
        
        html_parts.append(f"""
        <!DOCTYPE html>
        <html lang="en">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>{metadata['document_info']['title'] or 'Documento PDF'}</title>
            <style>
                body {{
                    font-family: Arial, sans-serif;
                    line-height: 1.6;
                    margin: 0;
                    padding: 20px;
                    background-color: #ffffff;
                }}
                .page {{
                    margin-bottom: 30px;
                    border: 1px solid #ddd;
                    padding: 20px;
                    background-color: #fff;
                }}
                .page-header {{
                    font-size: 14px;
                    color: #666;
                    margin-bottom: 10px;
                    border-bottom: 1px solid #eee;
                    padding-bottom: 5px;
                }}
                .text-block {{
                    margin-bottom: 10px;
                }}
                .text-line {{
                    margin-bottom: 5px;
                }}
                .text-span {{
                    display: inline;
                }}
                .image-block {{
                    text-align: center;
                    margin: 20px 0;
                }}
                .image-block img {{
                    max-width: 100%;
                    height: auto;
                    border: 1px solid #ddd;
                }}
                .link-block {{
                    color: #0066cc;
                    text-decoration: underline;
                }}
                {''.join(css_styles)}
            </style>
        </head>
        <body>
        """)
        
        # Generate content of each page
        for page in metadata["pages"]:
            html_parts.append(f"""
            <div class="page">
                <div class="page-header">
                    Page {page['page_number']} - Dimensions: {page['width']:.1f} x {page['height']:.1f}
                </div>
            """)
            
            for block in page["blocks"]:
                if block["type"] == "text":
                    html_parts.append('<div class="text-block">')
                    
                    for line in block["lines"]:
                        html_parts.append('<div class="text-line">')
                        
                        for span in line["spans"]:
                            # Apply styles if preserved
                            style_attrs = []
                            if preserve_styles:
                                # Search for font index
                                try:
                                    font_index = metadata["fonts"].index(span["font"])
                                    style_attrs.append(f'class="font-{font_index}')
                                except ValueError:
                                    style_attrs.append('class="font-default')
                                
                                # Search for color index
                                try:
                                    color_index = metadata["colors"].index(span["color"])
                                    style_attrs.append(f' color-{color_index}"')
                                except ValueError:
                                    style_attrs.append('"')
                                
                                # Apply additional styles
                                if "bold" in span["style"]:
                                    style_attrs.append(' style="font-weight: bold;')
                                if "italic" in span["style"]:
                                    style_attrs.append(' font-style: italic;')
                                if span["font_size"] > 0:
                                    style_attrs.append(f' font-size: {span["font_size"]}px;')
                                style_attrs.append('"')
                            else:
                                style_attrs = ['class="text-span"']
                            
                            html_parts.append(f'<span{"".join(style_attrs)}>{span["text"]}</span>')
                        
                        html_parts.append('</div>')
                    
                    html_parts.append('</div>')
                
                elif block["type"] == "image":
                    # Generate image information according to the data type
                    if block.get("data_type") == "metadata":
                        image_info = f"[Imagen - {block['width']}x{block['height']}px]"
                        image_details = f"Espacio de color: {block['colorspace']}, Bits por canal: {block['bpc']}"
                        html_parts.append(f"""
                        <div class="image-block">
                            <div>{image_info}</div>
                            <div style="font-size: 12px; color: #666;">
                                {image_details}
                            </div>
                        </div>
                        """)
                    elif block.get("data_type") == "base64":
                        # Show the real image using base64
                        mime_type = block.get("mime_type", "image/jpeg")
                        base64_data = block.get("base64_data", "")
                        data_size = block.get("data_size", 0)
                        
                        html_parts.append(f"""
                        <div class="image-block">
                            <img src="data:{mime_type};base64,{base64_data}" 
                                 alt="Image from PDF" 
                                 style="max-width: 100%; height: auto; border: 1px solid #ddd;"
                                 onerror="this.style.display='none'; this.nextElementSibling.style.display='block';">
                            <div style="display: none; font-size: 12px; color: #666;">
                                [Image not available - Size: {data_size} bytes]
                            </div>
                            <div style="font-size: 12px; color: #666; margin-top: 5px;">
                                Type: {mime_type}, Size: {data_size} bytes
                            </div>
                        </div>
                        """)
                    elif block.get("data_type") == "bytes":
                        image_info = f"[Image - Binary data]"
                        image_details = f"Size: {block.get('data_size', 0)} bytes"
                        if block.get("data_preview"):
                            image_details += f", Preview: {block['data_preview'][:50]}..."
                        if block.get("conversion_error"):
                            image_details += f", Error: {block['conversion_error']}"
                        
                        html_parts.append(f"""
                        <div class="image-block">
                            <div>{image_info}</div>
                            <div style="font-size: 12px; color: #666;">
                                {image_details}
                            </div>
                        </div>
                        """)
                    else:
                        image_info = f"[Image - Unknown type]"
                        image_details = f"Data type: {block.get('raw_data_type', 'N/A')}"
                        
                        html_parts.append(f"""
                        <div class="image-block">
                            <div>{image_info}</div>
                            <div style="font-size: 12px; color: #666;">
                                {image_details}
                            </div>
                        </div>
                        """)
                
                elif block["type"] == "link":
                    html_parts.append(f"""
                    <div class="link-block">
                        <a href="{block['uri']}" target="_blank">[Enlace: {block['uri']}]</a>
                    </div>
                    """)
            
            html_parts.append('</div>')
        
        # Document information
        html_parts.append(f"""
        <div style="margin-top: 40px; padding: 20px; background-color: #f5f5f5; border-radius: 5px;">
            <h3>Document Information</h3>
            <p><strong>Title:</strong> {metadata['document_info']['title'] or 'Not specified'}</p>
            <p><strong>Author:</strong> {metadata['document_info']['author'] or 'Not specified'}</p>
            <p><strong>Pages:</strong> {metadata['document_info']['page_count']}</p>
            <p><strong>Fonts used:</strong> {len(metadata['fonts'])}</p>
            <p><strong>Colors used:</strong> {len(metadata['colors'])}</p>
            <p><strong>Images:</strong> {len(metadata['images'])}</p>
            <p><strong>Links:</strong> {len(metadata['links'])}</p>
        </div>
        """)
        
        html_parts.append("""
        </body>
        </html>
        """)
        
        return ''.join(html_parts) 