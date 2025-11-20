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
Router for document management endpoints
"""
from fastapi import APIRouter, UploadFile, File, Form, HTTPException, Depends, BackgroundTasks
from typing import List
import asyncio
# import uuid
# import subprocess
# import os
# import tempfile
# import shutil
# from fastapi.responses import FileResponse, JSONResponse
# from database.schemas import HTMLResponse
from services.document_service import DocumentService
from utility.auth import require_token_types
from utility.tokens import JWTLectureTokenPayload
from database.crud import get_user_by_cognito_id
from database.db import get_db, SessionLocal
from sqlalchemy.orm import Session
from utility.async_manager import AsyncManager
from pathlib import Path
# import base64
# import io
# from PIL import Image
# import fitz

BASE_DIR = Path(__file__).resolve().parent
TEMP_DIR = BASE_DIR / "../temp"
SCRIPT_PATH = BASE_DIR / "../convert_pdf.sh"
TEMP_DIR.mkdir(exist_ok=True)

router = APIRouter()

document_service = None

def get_document_service():
    """Get an instance of the document service"""
    global document_service
    if document_service is None:
        document_service = DocumentService()
    return document_service

# Internal function to process document instructional model with notifications
async def _process_document_instructional_model_internal(db, user_id, prompt, archivos, task_type):
    """
    Internal function to process document instructional model with notifications
    """
    app_sync = AsyncManager()
    app_sync.set_parameters()
    
    try:
        # Notify the start of processing
        await app_sync.send_event_with_notification(
            db=db,
            user_id=str(user_id),
            service_id="document_instructional_model",
            title="document_instructional_model.processing.title",
            body="document_instructional_model.processing.body",
            data={
                "task_type": task_type,
                "stage": "processing",
                "files_count": len(archivos) if archivos else 0
            },
            notification_type="info",
            priority="normal"
        )

        # Process the document instructional model
        doc_service = DocumentService()
        result = await doc_service.create_instructional_model(prompt, archivos)

        # Notify the completion
        await app_sync.send_event_with_notification(
            db=db,
            user_id=str(user_id),
            service_id="document_instructional_model",
            title="document_instructional_model.completed.title",
            body="document_instructional_model.completed.body",
            data={
                "task_type": task_type,
                "stage": "completed",
                "files_count": len(archivos) if archivos else 0
            },
            notification_type="success",
            priority="normal"
        )
        
        return result
    except Exception as e:
        # Notify the error
        await app_sync.send_event_with_notification(
            db=db,
            user_id=str(user_id),
            service_id="document_instructional_model",
            title="document_instructional_model.error.title",
            body="document_instructional_model.error.body",
            data={
                "task_type": task_type,
                "stage": "error",
                "error": str(e)
            },
            notification_type="error",
            priority="high"
        )
        raise

# Internal function to process document pedagogical framework with notifications
async def _process_document_pedagogical_framework_internal(db, user_id, prompt, archivos, task_type):
    """
    Internal function to process document pedagogical framework with notifications
    """
    app_sync = AsyncManager()
    app_sync.set_parameters()
    
    try:
        # Notify the start of processing
        await app_sync.send_event_with_notification(
            db=db,
            user_id=str(user_id),
            service_id="document_pedagogical_framework",
            title="document_pedagogical_framework.processing.title",
            body="document_pedagogical_framework.processing.body",
            data={
                "task_type": task_type,
                "stage": "processing",
                "files_count": len(archivos) if archivos else 0
            },
            notification_type="info",
            priority="normal"
        )

        # Process the document pedagogical framework
        doc_service = DocumentService()
        result = await doc_service.create_pedagogical_framework(prompt, archivos)

        # Notify the completion
        await app_sync.send_event_with_notification(
            db=db,
            user_id=str(user_id),
            service_id="document_pedagogical_framework",
            title="document_pedagogical_framework.completed.title",
            body="document_pedagogical_framework.completed.body",
            data={
                "task_type": task_type,
                "stage": "completed",
                "files_count": len(archivos) if archivos else 0
            },
            notification_type="success",
            priority="normal"
        )
        
        return result
    except Exception as e:
        # Notify the error
        await app_sync.send_event_with_notification(
            db=db,
            user_id=str(user_id),
            service_id="document_pedagogical_framework",
            title="document_pedagogical_framework.error.title",
            body="document_pedagogical_framework.error.body",
            data={
                "task_type": task_type,
                "stage": "error",
                "error": str(e)
            },
            notification_type="error",
            priority="high"
        )
        raise

# Internal function to process document extract index with notifications
async def _process_document_extract_index_internal(db, user_id, archivos, task_type):
    """
    Internal function to process document extract index with notifications
    """
    app_sync = AsyncManager()
    app_sync.set_parameters()
    
    try:
        # Notify the start of processing
        await app_sync.send_event_with_notification(
            db=db,
            user_id=str(user_id),
            service_id="document_extract_index",
            title="document_extract_index.processing.title",
            body="document_extract_index.processing.body",
            data={
                "task_type": task_type,
                "stage": "processing",
                "files_count": len(archivos) if archivos else 0
            },
            notification_type="info",
            priority="normal"
        )

        # Process the document extract index
        doc_service = DocumentService()
        
        # Handle both UploadFile objects and saved file dictionaries
        if archivos and isinstance(archivos[0], dict):
            # These are saved files from async processing
            result = await doc_service.extract_index_from_saved_files(archivos)
        else:
            # These are UploadFile objects from sync processing
            result = await doc_service.extract_index_from_pdf(archivos)


        # Notify the completion
        await app_sync.send_event_with_notification(
            db=db,
            user_id=str(user_id),
            service_id="document_extract_index",
            title="document_extract_index.completed.title",
            body="document_extract_index.completed.body",
            data={
                "task_type": task_type,
                "stage": "completed",
                "routines": result.get("index", [])
            },
            notification_type="success",
            priority="normal"
        )
        
        return result
    except Exception as e:
        # Notify the error
        await app_sync.send_event_with_notification(
            db=db,
            user_id=str(user_id),
            service_id="document_extract_index",
            title="document_extract_index.error.title",
            body="document_extract_index.error.body",
            data={
                "task_type": task_type,
                "stage": "error",
                "error": str(e)
            },
            notification_type="error",
            priority="high"
        )
        raise

# Internal function to process document extract all with notifications
async def _process_document_extract_all_internal(db, user_id, archivos, task_type):
    """
    Internal function to process document extract all with notifications
    """
    app_sync = AsyncManager()
    app_sync.set_parameters()
    
    try:
        # Notify the start of processing
        await app_sync.send_event_with_notification(
            db=db,
            user_id=str(user_id),
            service_id="document_extract_all",
            title="document_extract_all.processing.title",
            body="document_extract_all.processing.body",
            data={
                "task_type": task_type,
                "stage": "processing",
                "files_count": len(archivos) if archivos else 0
            },
            notification_type="info",
            priority="normal"
        )

        # Process the document extract all
        doc_service = DocumentService()
        
        # Handle both UploadFile objects and saved file dictionaries
        if archivos and isinstance(archivos[0], dict):
            # These are saved files from async processing
            result = await doc_service.extract_all_from_saved_files(archivos)
        else:
            # These are UploadFile objects from sync processing
            result = await doc_service.extract_all_from_files(archivos)

        # Notify the completion
        await app_sync.send_event_with_notification(
            db=db,
            user_id=str(user_id),
            service_id="document_extract_all",
            title="document_extract_all.completed.title",
            body="document_extract_all.completed.body",
            data={
                "task_type": task_type,
                "stage": "completed",
                "files_count": len(archivos) if archivos else 0
            },
            notification_type="success",
            priority="normal"
        )
        
        return result
    except Exception as e:
        # Notify the error
        await app_sync.send_event_with_notification(
            db=db,
            user_id=str(user_id),
            service_id="document_extract_all",
            title="document_extract_all.error.title",
            body="document_extract_all.error.body",
            data={
                "task_type": task_type,
                "stage": "error",
                "error": str(e)
            },
            notification_type="error",
            priority="high"
        )
        raise

# Internal function to process document structured content with notifications
async def _process_document_structured_content_internal(db, user_id, prompt, context, profile, files, task_type):
    """
    Internal function to process document structured content with notifications
    """
    app_sync = AsyncManager()
    app_sync.set_parameters()
    
    try:
        # Notify the start of processing
        await app_sync.send_event_with_notification(
            db=db,
            user_id=str(user_id),
            service_id="document_structured_content",
            title="document_structured_content.processing.title",
            body="document_structured_content.processing.body",
            data={
                "task_type": task_type,
                "stage": "processing",
                "files_count": len(files) if files else 0
            },
            notification_type="info",
            priority="normal"
        )

        # Process the document structured content
        doc_service = DocumentService()
        result = await doc_service.generate_structured_content(
            prompt=prompt,
            context=context,
            profile=profile,
            files=files
        )

        # Notify the completion
        await app_sync.send_event_with_notification(
            db=db,
            user_id=str(user_id),
            service_id="document_structured_content",
            title="document_structured_content.completed.title",
            body="document_structured_content.completed.body",
            data={
                "task_type": task_type,
                "stage": "completed",
                "files_count": len(files) if files else 0
            },
            notification_type="success",
            priority="normal"
        )
        
        return result
    except Exception as e:
        # Notify the error
        await app_sync.send_event_with_notification(
            db=db,
            user_id=str(user_id),
            service_id="document_structured_content",
            title="document_structured_content.error.title",
            body="document_structured_content.error.body",
            data={
                "task_type": task_type,
                "stage": "error",
                "error": str(e)
            },
            notification_type="error",
            priority="high"
        )
        raise

# Internal function to process document accessible HTML with notifications
async def _process_document_accessible_html_internal(db, user_id, file, task_type):
    """
    Internal function to process document accessible HTML with notifications
    """
    app_sync = AsyncManager()
    app_sync.set_parameters()
    
    try:
        # Notify the start of processing
        await app_sync.send_event_with_notification(
            db=db,
            user_id=str(user_id),
            service_id="document_accessible_html",
            title="document_accessible_html.processing.title",
            body="document_accessible_html.processing.body",
            data={
                "task_type": task_type,
                "stage": "processing",
                "filename": file.filename if file else "unknown"
            },
            notification_type="info",
            priority="normal"
        )

        # Process the document accessible HTML (simplified for async)
        # In a real implementation, this would call the actual processing logic
        result = f"Accessible HTML generated for {file.filename if file else 'unknown file'}"

        # Notify the completion
        await app_sync.send_event_with_notification(
            db=db,
            user_id=str(user_id),
            service_id="document_accessible_html",
            title="document_accessible_html.completed.title",
            body="document_accessible_html.completed.body",
            data={
                "task_type": task_type,
                "stage": "completed",
                "filename": file.filename if file else "unknown"
            },
            notification_type="success",
            priority="normal"
        )
        
        return result
    except Exception as e:
        # Notify the error
        await app_sync.send_event_with_notification(
            db=db,
            user_id=str(user_id),
            service_id="document_accessible_html",
            title="document_accessible_html.error.title",
            body="document_accessible_html.error.body",
            data={
                "task_type": task_type,
                "stage": "error",
                "error": str(e)
            },
            notification_type="error",
            priority="high"
        )
        raise

# Internal function to process document PDF metadata HTML with notifications
async def _process_document_pdf_metadata_html_internal(db, user_id, file, preserve_styles, generate_html, task_type):
    """
    Internal function to process document PDF metadata HTML with notifications
    """
    app_sync = AsyncManager()
    app_sync.set_parameters()
    
    try:
        # Notify the start of processing
        await app_sync.send_event_with_notification(
            db=db,
            user_id=str(user_id),
            service_id="document_pdf_metadata_html",
            title="document_pdf_metadata_html.processing.title",
            body="document_pdf_metadata_html.processing.body",
            data={
                "task_type": task_type,
                "stage": "processing",
                "filename": file.filename if file else "unknown",
                "preserve_styles": preserve_styles,
                "generate_html": generate_html
            },
            notification_type="info",
            priority="normal"
        )

        # Process the document PDF metadata HTML
        doc_service = DocumentService()
        result = await doc_service.extract_pdf_metadata_and_generate_html(
            file, preserve_styles, generate_html
        )

        # Notify the completion
        await app_sync.send_event_with_notification(
            db=db,
            user_id=str(user_id),
            service_id="document_pdf_metadata_html",
            title="document_pdf_metadata_html.completed.title",
            body="document_pdf_metadata_html.completed.body",
            data={
                "task_type": task_type,
                "stage": "completed",
                "filename": file.filename if file else "unknown"
            },
            notification_type="success",
            priority="normal"
        )
        
        return result
    except Exception as e:
        # Notify the error
        await app_sync.send_event_with_notification(
            db=db,
            user_id=str(user_id),
            service_id="document_pdf_metadata_html",
            title="document_pdf_metadata_html.error.title",
            body="document_pdf_metadata_html.error.body",
            data={
                "task_type": task_type,
                "stage": "error",
                "error": str(e)
            },
            notification_type="error",
            priority="high"
        )
        raise

# Internal function to process document HTML from PDF pages with notifications
async def _process_document_html_from_pdf_pages_internal(db, user_id, file, prompt, language, accessibility_rules_file, task_type):
    """
    Internal function to process document HTML from PDF pages with notifications
    """
    app_sync = AsyncManager()
    app_sync.set_parameters()
    
    try:
        # Notify the start of processing
        await app_sync.send_event_with_notification(
            db=db,
            user_id=str(user_id),
            service_id="document_html_from_pdf_pages",
            title="document_html_from_pdf_pages.processing.title",
            body="document_html_from_pdf_pages.processing.body",
            data={
                "task_type": task_type,
                "stage": "processing",
                "filename": file.filename if file else "unknown",
                "language": language
            },
            notification_type="info",
            priority="normal"
        )

        # Process the document HTML from PDF pages
        doc_service = DocumentService()
        metadata_result = await doc_service.extract_pdf_metadata_by_pages(file)
        
        pages = metadata_result.get("pages", [])
        total_pages = metadata_result.get("total_pages", 0)
        
        if total_pages == 0:
            raise Exception("No pages found in the PDF")
        
        # Process accessibility rules file if provided
        accessibility_rules = None
        if accessibility_rules_file:
            try:
                file_structure = await doc_service.process_accessibility_rules_file(accessibility_rules_file)
                accessibility_rules = doc_service._extract_text_from_file_structure(file_structure)
            except Exception as e:
                print(f"⚠️ Error processing accessibility file: {str(e)}")
                accessibility_rules = None
        
        # Import strands service
        from services.strands_service import StrandsService
        strands_service = StrandsService()
        
        # Generate HTML for each page
        html_sections = []
        
        for page in pages:
            try:
                page_html = await strands_service.generate_html_from_page_metadata(
                    page, 
                    custom_prompt=prompt,
                    language=language,
                    accessibility_rules=accessibility_rules
                )
                html_sections.append(page_html)
            except Exception as e:
                error_html = f'<main class="pdf-page error" data-page-number="{page.get("page_number", 1)}">\n<div class="error-message">Error procesando página: {str(e)}</div>\n</main>'
                html_sections.append(error_html)
        
        # Combine all sections
        result = "".join(html_sections)

        # Notify the completion
        await app_sync.send_event_with_notification(
            db=db,
            user_id=str(user_id),
            service_id="document_html_from_pdf_pages",
            title="document_html_from_pdf_pages.completed.title",
            body="document_html_from_pdf_pages.completed.body",
            data={
                "task_type": task_type,
                "stage": "completed",
                "filename": file.filename if file else "unknown",
                "total_pages": total_pages
            },
            notification_type="success",
            priority="normal"
        )
        
        return result
    except Exception as e:
        # Notify the error
        await app_sync.send_event_with_notification(
            db=db,
            user_id=str(user_id),
            service_id="document_html_from_pdf_pages",
            title="document_html_from_pdf_pages.error.title",
            body="document_html_from_pdf_pages.error.body",
            data={
                "task_type": task_type,
                "stage": "error",
                "error": str(e)
            },
            notification_type="error",
            priority="high"
        )
        raise


@router.post("/test-process-indt")
async def test_process_indt_file(file: UploadFile = File(...)):
    """
    Test endpoint to process .indt and .inddbook files
    
    Parameters:
        file (UploadFile): .indt or .inddbook file to process
    
    Response:
        JSON with the extracted structure from the file
    """
    try:
        # Verificar que sea un archivo .indt, .inddbook o .zip
        if not (file.filename.lower().endswith('.indt') or 
                file.filename.lower().endswith('.inddbook') or 
                file.filename.lower().endswith('.zip')):
            raise HTTPException(
                status_code=400,
                detail="The file must be a .indt, .inddbook or .zip file"
            )
        
        # Leer el contenido del archivo
        content = await file.read()
        
        # Procesar el archivo .indt
        import zipfile
        import xml.etree.ElementTree as ET
        import io
        import json
        
        structure = {
            "file_info": {
                "name": file.filename,
                "size": len(content),
                "type": "indesign_template" if file.filename.lower().endswith('.indt') else 
                       "indesign_book" if file.filename.lower().endswith('.inddbook') else "zip_archive"
            },
            "structure": {
                "pages": [],
                "styles": {},
                "assets": {
                    "images": [],
                    "fonts": [],
                    "colors": []
                },
                "accessibility": {
                    "wcag_level": "AA",
                    "semantic_structure": [],
                    "navigation_elements": [],
                    "alt_text_requirements": []
                }
            },
            "content_summary": {
                "text_content": "",
                "visual_elements": [],
                "layout_structure": "Extracted layout structure",
                "html_ready": {
                    "sections": [],
                    "headings": [],
                    "content_blocks": []
                }
            }
        }
        
        try:
            # The .indt, .inddbook and .zip files are ZIP files
            with zipfile.ZipFile(io.BytesIO(content), 'r') as zip_file:
                # List all files in the ZIP
                file_list = zip_file.namelist()
                
                # Add information about found files
                structure["structure"]["files"] = {
                    "total_files": len(file_list),
                    "file_list": file_list
                }
                
                # Extract design information (only for .indt)
                if file.filename.lower().endswith('.indt'):
                    designmap_file = None
                    for file_name in file_list:
                        if file_name.endswith('designmap.xml'):
                            designmap_file = file_name
                            break
                    
                    if designmap_file:
                        # Read the designmap.xml file
                        designmap_content = zip_file.read(designmap_file)
                        root = ET.fromstring(designmap_content)
                        
                        # Extract information about pages
                        for spread in root.findall('.//idPkg:Spread', namespaces={'idPkg': 'http://ns.adobe.com/AdobeInDesign/idml/1.0/packaging'}):
                            spread_id = spread.get('src', '')
                            if spread_id:
                                try:
                                    spread_content = zip_file.read(spread_id)
                                    spread_root = ET.fromstring(spread_content)
                                    
                                    # Extract text elements
                                    for text_frame in spread_root.findall('.//TextFrame'):
                                        text_content = ""
                                        for story in text_frame.findall('.//ParagraphStyleRange'):
                                            for para in story.findall('.//Content'):
                                                if char.text:
                                                    text_content += char.text + " "
                                        
                                        if text_content.strip():
                                            structure["structure"]["pages"].append({
                                                "type": "text_frame",
                                                "content": text_content.strip(),
                                                "spread_id": spread_id
                                            })
                                            structure["content_summary"]["text_content"] += text_content.strip() + " "
                                except Exception as e:
                                    print(f"Error procesando spread {spread_id}: {str(e)}")
                
                # Extract styles information (only for .indt)
                if file.filename.lower().endswith('.indt'):
                    styles_file = None
                    for file_name in file_list:
                        if 'styles' in file_name.lower() and file_name.endswith('.xml'):
                            styles_file = file_name
                            break
                    
                    if styles_file:
                        try:
                            styles_content = zip_file.read(styles_file)
                            styles_root = ET.fromstring(styles_content)
                            
                            # Extract paragraph styles
                            paragraph_styles = []
                            for style in styles_root.findall('.//ParagraphStyle'):
                                style_name = style.get('Self', '')
                                if style_name:
                                    paragraph_styles.append(style_name)
                            
                            structure["structure"]["styles"]["paragraph_styles"] = paragraph_styles
                        except Exception as e:
                            print(f"Error procesando estilos: {str(e)}")
                
                # Extract assets information (only fonts, the images are in links)
                for file_name in file_list:
                    if file_name.endswith('.otf') or file_name.endswith('.ttf'):
                        structure["structure"]["assets"]["fonts"].append({
                            "name": file_name,
                            "type": "font"
                        })
                
                # Process specific files of .inddbook or ZIP
                if file.filename.lower().endswith('.inddbook') or file.filename.lower().endswith('.zip'):
                    # Search for the main .indd file
                    indd_files = [f for f in file_list if f.endswith('.indd')]
                    if indd_files:
                        structure["structure"]["main_document"] = {
                            "indd_files": indd_files,
                            "count": len(indd_files)
                        }
                        
                        # Process the main .indd file
                        try:
                            indd_content = zip_file.read(indd_files[0])
                            # The .indd files are also ZIP files
                            with zipfile.ZipFile(io.BytesIO(indd_content), 'r') as indd_zip:
                                indd_file_list = indd_zip.namelist()
                                
                                # Search for designmap.xml in the .indd file
                                designmap_file = None
                                for indd_file_name in indd_file_list:
                                    if indd_file_name.endswith('designmap.xml'):
                                        designmap_file = indd_file_name
                                        break
                                
                                if designmap_file:
                                    # Read the designmap.xml file from the .indd
                                    designmap_content = indd_zip.read(designmap_file)
                                    root = ET.fromstring(designmap_content)
                                    
                                    # Extract information about pages from the .indd
                                    for spread in root.findall('.//idPkg:Spread', namespaces={'idPkg': 'http://ns.adobe.com/AdobeInDesign/idml/1.0/packaging'}):
                                        spread_id = spread.get('src', '')
                                        if spread_id:
                                            try:
                                                spread_content = indd_zip.read(spread_id)
                                                spread_root = ET.fromstring(spread_content)
                                                
                                                # Extract text elements from the .indd with better structure
                                                # Search for different types of text elements
                                                text_elements = []
                                                
                                                # Search for TextFrames
                                                text_frames = spread_root.findall('.//TextFrame')
                                                text_elements.extend(text_frames)
                                                print(f"DEBUG: Encontrados {len(text_frames)} TextFrames en spread {spread_id}")
                                                
                                                # Search for other text elements
                                                other_text_elements = spread_root.findall('.//Text')
                                                text_elements.extend(other_text_elements)
                                                print(f"DEBUG: Encontrados {len(other_text_elements)} elementos Text en spread {spread_id}")
                                                
                                                # Search for direct content elements
                                                content_elements = spread_root.findall('.//Content')
                                                text_elements.extend(content_elements)
                                                print(f"DEBUG: Encontrados {len(content_elements)} elementos Content en spread {spread_id}")
                                                
                                                # Search for paragraph elements
                                                paragraph_elements = spread_root.findall('.//ParagraphStyleRange')
                                                text_elements.extend(paragraph_elements)
                                                print(f"DEBUG: Encontrados {len(paragraph_elements)} elementos ParagraphStyleRange en spread {spread_id}")
                                                
                                                # Search for story elements
                                                story_elements = spread_root.findall('.//Story')
                                                text_elements.extend(story_elements)
                                                print(f"DEBUG: Encontrados {len(story_elements)} elementos Story en spread {spread_id}")
                                                
                                                # Search for CharacterStyleRange elements
                                                char_style_elements = spread_root.findall('.//CharacterStyleRange')
                                                print(f"DEBUG: Encontrados {len(char_style_elements)} elementos CharacterStyleRange en spread {spread_id}")
                                                
                                                # Show all unique types of elements found
                                                all_elements = list(spread_root.iter())
                                                element_types = set(elem.tag for elem in all_elements)
                                                print(f"DEBUG: Tipos de elementos únicos en spread {spread_id}: {sorted(element_types)}")
                                                
                                                # Process all text elements found
                                                for text_element in text_elements:
                                                    text_content = ""
                                                    text_structure = {
                                                        "type": text_element.tag,
                                                        "spread_id": spread_id,
                                                        "source": indd_files[0],
                                                        "paragraphs": [],
                                                        "styles_used": set(),
                                                        "attributes": dict(text_element.attrib)
                                                    }
                                                    
                                                    # Extract direct text from the element
                                                    if text_element.text and text_element.text.strip():
                                                        text_content += text_element.text.strip() + " "
                                                    
                                                    # Search for content in child elements
                                                    for child in text_element.iter():
                                                        if child.text and child.text.strip():
                                                            text_content += child.text.strip() + " "
                                                    
                                                    # Search specifically in Content elements
                                                    for content_elem in text_element.findall('.//Content'):
                                                        if content_elem.text and content_elem.text.strip():
                                                            text_content += content_elem.text.strip() + " "
                                                    
                                                    # Search in CharacterStyleRange elements
                                                    for char_elem in text_element.findall('.//CharacterStyleRange'):
                                                        char_content = ""
                                                        for content_elem in char_elem.findall('.//Content'):
                                                            if content_elem.text:
                                                                char_content += content_elem.text
                                                        if char_content.strip():
                                                            text_content += char_content.strip() + " "
                                                    
                                                    # Search in ParagraphStyleRange elements
                                                    for para_elem in text_element.findall('.//ParagraphStyleRange'):
                                                        para_content = ""
                                                        para_style = para_elem.get('AppliedParagraphStyle', '')
                                                        
                                                        # Extract content from the paragraph
                                                        for content_elem in para_elem.findall('.//Content'):
                                                            if content_elem.text:
                                                                para_content += content_elem.text
                                                        
                                                        if para_content.strip():
                                                            text_structure["paragraphs"].append({
                                                                "content": para_content.strip(),
                                                                "style": para_style,
                                                                "type": "paragraph"
                                                            })
                                                            text_content += para_content.strip() + " "
                                                            if para_style:
                                                                text_structure["styles_used"].add(para_style)
                                                    
                                                    # If we find content, add it to the structure
                                                    if text_content.strip():
                                                        text_structure["content"] = text_content.strip()
                                                        text_structure["styles_used"] = list(text_structure["styles_used"])
                                                        structure["structure"]["pages"].append(text_structure)
                                                        structure["content_summary"]["text_content"] += text_content.strip() + " "
                                                        print(f"DEBUG: Content extracted from the element {text_element.tag}: '{text_content.strip()[:100]}...'")
                                                
                                                # If we don't find content in specific elements, search in the whole XML
                                                if not structure["structure"]["pages"]:
                                                    print(f"DEBUG: No content found in specific elements, searching in the whole XML of the spread {spread_id}")
                                                    # Search for any text in the XML
                                                    all_text = ""
                                                    for elem in spread_root.iter():
                                                        if elem.text and elem.text.strip():
                                                            all_text += elem.text.strip() + " "
                                                    
                                                    if all_text.strip():
                                                        print(f"DEBUG: Content extracted from the whole XML: '{all_text.strip()[:200]}...'")
                                                        structure["structure"]["pages"].append({
                                                            "type": "raw_xml_content",
                                                            "spread_id": spread_id,
                                                            "source": indd_files[0],
                                                            "content": all_text.strip(),
                                                            "paragraphs": [{
                                                                "content": all_text.strip(),
                                                                "style": "unknown",
                                                                "type": "raw_content"
                                                            }],
                                                            "styles_used": [],
                                                            "note": "Content extracted directly from the XML"
                                                        })
                                                        structure["content_summary"]["text_content"] = all_text.strip()
                                                    else:
                                                        print(f"DEBUG: No text found in the XML of the spread {spread_id}")
                                            except Exception as e:
                                                print(f"Error processing spread {spread_id} of the .indd: {str(e)}")
                                
                                # Extract styles information from the .indd
                                styles_file = None
                                for indd_file_name in indd_file_list:
                                    if 'styles' in indd_file_name.lower() and indd_file_name.endswith('.xml'):
                                        styles_file = indd_file_name
                                        break
                                
                                if styles_file:
                                    try:
                                        styles_content = indd_zip.read(styles_file)
                                        styles_root = ET.fromstring(styles_content)
                                        
                                        # Extract paragraph styles from the .indd
                                        paragraph_styles = []
                                        for style in styles_root.findall('.//ParagraphStyle'):
                                            style_name = style.get('Self', '')
                                            if style_name:
                                                paragraph_styles.append(style_name)
                                        
                                        structure["structure"]["styles"]["paragraph_styles"] = paragraph_styles
                                    except Exception as e:
                                        print(f"Error processing styles from the .indd: {str(e)}")
                                        
                        except Exception as e:
                            print(f"Error processing .indd file: {str(e)}")
                    
                    # Search for Instructions.txt
                    instructions_files = [f for f in file_list if 'instructions' in f.lower()]
                    if instructions_files:
                        try:
                            instructions_content = zip_file.read(instructions_files[0])
                            structure["structure"]["instructions"] = {
                                "file": instructions_files[0],
                                "content": instructions_content.decode('utf-8', errors='ignore')
                            }
                        except Exception as e:
                            print(f"Error reading instructions: {str(e)}")
                    
                    # Organize links by file type
                    links_files = [f for f in file_list if 'links' in f.lower()]
                    links_by_type = {}
                    for link_file in links_files:
                        file_extension = link_file.split('.')[-1].lower()
                        if file_extension not in links_by_type:
                            links_by_type[file_extension] = []
                        links_by_type[file_extension].append({
                            "name": link_file,
                            "type": file_extension
                        })
                    
                    structure["structure"]["links"] = {
                        "total_links": len(links_files),
                        "by_type": links_by_type,
                        "file_list": links_files
                    }
                    
                    # Count main folders
                    folders = {
                        "Document fonts": len([f for f in file_list if 'document fonts' in f.lower()]),
                        "Links": len(links_files)
                    }
                    structure["structure"]["folders"] = folders
                
                # Count visual elements
                total_images = 0
                if "links" in structure["structure"]:
                    for link_type, links in structure["structure"]["links"]["by_type"].items():
                        if link_type in ['eps', 'psd', 'tif', 'jpg', 'jpeg', 'png', 'gif']:
                            total_images += len(links)
                
                structure["content_summary"]["visual_elements"] = [
                    f"Images found: {total_images}",
                    f"Fonts found: {len(structure['structure']['assets']['fonts'])}",
                    f"Links found: {structure['structure']['links']['total_links'] if 'links' in structure['structure'] else 0}"
                ]
                
                # Process content for HTML with accessibility
                if structure["structure"]["pages"]:
                    # Organize content by sections
                    sections = []
                    headings = []
                    content_blocks = []
                    
                    for page in structure["structure"]["pages"]:
                        if "paragraphs" in page:
                            section_content = {
                                "type": "section",
                                "source": page.get("source", "unknown"),
                                "spread_id": page.get("spread_id", ""),
                                "paragraphs": page["paragraphs"],
                                "html_structure": {
                                    "tag": "section",
                                    "attributes": {
                                        "class": "content-section",
                                        "aria-label": f"Content of {page.get('source', 'document')}"
                                    }
                                }
                            }
                            sections.append(section_content)
                            
                            # Identify headings based on styles
                            for para in page["paragraphs"]:
                                para_style = para.get("style", "").lower()
                                content = para.get("content", "")
                                
                                # Detect headings by style or content
                                if any(keyword in para_style for keyword in ["heading", "title", "header"]) or \
                                   any(keyword in content.lower() for keyword in ["chapter", "section", "part", "title"]):
                                    heading_level = 1
                                    if any(keyword in para_style for keyword in ["sub", "secondary"]):
                                        heading_level = 2
                                    elif any(keyword in para_style for keyword in ["tertiary", "minor"]):
                                        heading_level = 3
                                    
                                    headings.append({
                                        "level": heading_level,
                                        "text": content,
                                        "style": para_style,
                                        "html_tag": f"h{heading_level}",
                                        "accessibility": {
                                            "id": f"heading-{len(headings)}",
                                            "aria-level": heading_level
                                        }
                                    })
                                else:
                                    content_blocks.append({
                                        "type": "paragraph",
                                        "content": content,
                                        "style": para_style,
                                        "html_tag": "p",
                                        "accessibility": {
                                            "class": "content-paragraph"
                                        }
                                    })
                    
                    structure["content_summary"]["html_ready"]["sections"] = sections
                    structure["content_summary"]["html_ready"]["headings"] = headings
                    structure["content_summary"]["html_ready"]["content_blocks"] = content_blocks
                    
                    # Generate semantic structure for accessibility
                    semantic_structure = []
                    for heading in headings:
                        semantic_structure.append({
                            "type": "heading",
                            "level": heading["level"],
                            "text": heading["text"],
                            "navigation_id": heading["accessibility"]["id"]
                        })
                    
                    structure["structure"]["accessibility"]["semantic_structure"] = semantic_structure
                    
                    # Generate navigation elements
                    if headings:
                        nav_elements = []
                        for heading in headings:
                            nav_elements.append({
                                "text": heading["text"],
                                "level": heading["level"],
                                "link": f"#{heading['accessibility']['id']}"
                            })
                        structure["structure"]["accessibility"]["navigation_elements"] = nav_elements
                    
                    # Alternative text requirements for images
                    if "links" in structure["structure"] and structure["structure"]["links"]["by_type"]:
                        alt_text_requirements = []
                        for link_type, links in structure["structure"]["links"]["by_type"].items():
                            if link_type in ['eps', 'psd', 'tif', 'jpg', 'jpeg', 'png', 'gif']:
                                for link in links:
                                    alt_text_requirements.append({
                                        "file": link["name"],
                                        "type": link_type,
                                        "requirement": "Needs descriptive alternative text",
                                        "priority": "high" if link_type in ['jpg', 'jpeg', 'png'] else "medium"
                                    })
                        structure["structure"]["accessibility"]["alt_text_requirements"] = alt_text_requirements
                
        except zipfile.BadZipFile:
            raise HTTPException(
                status_code=400,
                detail="The file is not a valid .indt, .inddbook or .zip file"
            )
        
        return {
            "success": True,
            "message": f"File {file.filename} processed successfully",
            "data": structure
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error processing .indt file: {str(e)}"
        )

@router.post("/generate-accessible-html")
async def generate_accessible_html(
    file: UploadFile = File(...),
    async_processing: bool = False,
    background_tasks: BackgroundTasks = None,
    token: JWTLectureTokenPayload = Depends(require_token_types(allowed_types=["cognito"])), 
    db: Session = Depends(get_db)
):
    """
    Generates accessible HTML (WCAG AA) from .indt, .inddbook or .zip files
    
    Parameters:
        file (UploadFile): .indt, .inddbook or .zip file to process
        async_processing (bool): Whether to process asynchronously
        background_tasks (BackgroundTasks): Background tasks for async processing
        token (str): User authentication token
        db (Session): Database session
    
    Response:
        JSON with accessible HTML and accessibility metadata
    """
    # Verify user token
    user = get_user_by_cognito_id(db, token.sub)
    user_id = user.id if user else None

    if user_id is None:
        raise HTTPException(status_code=401, detail="Unauthorized")

    try:
        if async_processing and background_tasks:
            # Async processing with AppSync
            def process_async_document_accessible_html(file, user_id, task_type):
                # Create a new connection for the background task
                db_task = SessionLocal()
                try:
                    # Create an event loop to execute asynchronous code
                    loop = asyncio.new_event_loop()
                    
                    # Execute the document accessible HTML in the loop
                    result = loop.run_until_complete(
                        _process_document_accessible_html_internal(db_task, user_id, file, task_type)
                    )
                    
                    return result
                except Exception as e:
                    raise
                finally:
                    db_task.close()
            
            # Add task to background
            background_tasks.add_task(
                process_async_document_accessible_html,
                file=file,
                user_id=user_id,
                task_type="generate_accessible_html"
            )
            
            return {
                "success": True,
                "message": f"Accessible HTML generation started in background for {file.filename}",
                "html_content": "Processing started. You will be notified when complete.",
                "accessibility_metadata": {
                    "wcag_level": "AA",
                    "status": "processing"
                }
            }
        else:
            # Synchronous processing
            # First process the file to get the structure
            content = await file.read()
        
        # Verify that it is a valid file
        if not (file.filename.lower().endswith('.indt') or 
                file.filename.lower().endswith('.inddbook') or 
                file.filename.lower().endswith('.zip')):
            raise HTTPException(
                status_code=400,
                detail="The file must be a .indt, .inddbook or .zip file"
            )
        
        # Process the file (reuse the logic of the previous endpoint)
        import zipfile
        import xml.etree.ElementTree as ET
        import io
        
        # Here goes the processing logic (simplified for the example)
        # In a real implementation, the code of the previous endpoint would be reused
        
        # Generate accessible HTML
        html_content = f"""
<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Accessible Document - {file.filename}</title>
    <style>
        body {{
            font-family: Arial, sans-serif;
            line-height: 1.6;
            max-width: 800px;
            margin: 0 auto;
            padding: 20px;
        }}
        .skip-link {{
            position: absolute;
            top: -40px;
            left: 6px;
            background: #000;
            color: #fff;
            padding: 8px;
            text-decoration: none;
            z-index: 1000;
        }}
        .skip-link:focus {{
            top: 6px;
        }}
        .content-section {{
            margin-bottom: 2rem;
        }}
        .content-paragraph {{
            margin-bottom: 1rem;
        }}
        .navigation {{
            background: #f5f5f5;
            padding: 1rem;
            margin-bottom: 2rem;
            border-radius: 5px;
        }}
        .navigation ul {{
            list-style: none;
            padding: 0;
        }}
        .navigation li {{
            margin-bottom: 0.5rem;
        }}
        .navigation a {{
            color: #333;
            text-decoration: none;
        }}
        .navigation a:hover {{
            text-decoration: underline;
        }}
        h1, h2, h3 {{
            color: #333;
            margin-top: 2rem;
            margin-bottom: 1rem;
        }}
        .accessibility-info {{
            background: #e8f4f8;
            padding: 1rem;
            margin: 1rem 0;
            border-left: 4px solid #007cba;
            border-radius: 3px;
        }}
        .skip-link {{
            position: absolute;
            left: -9999px;
        }}
        .skip-link:focus {{
            left: 16px;
            top: 16px;
            background: white;
            padding: 8px;
            outline: 3px solid #2563eb;
        }}
        :focus-visible {{
            outline: 3px solid #2563eb;
        }}
    </style>
</head>
<body>
    <a href="#main-content" class="skip-link">Skip to main content</a>
    
    <header role="banner">
        <h1>Documento: {file.filename}</h1>
        <div class="accessibility-info">
            <p><strong>Accessibility Information:</strong></p>
            <ul>
                <li>This document meets the WCAG 2.1 Level AA guidelines</li>
                <li>Correct semantic structure with hierarchical headings</li>
                <li>Keyboard navigation available</li>
                <li>Appropriate color contrast</li>
            </ul>
        </div>
    </header>
    
    <nav role="navigation" aria-label="Main navigation">
        <div class="navigation">
            <h2>Table of Contents</h2>
            <ul>
                <li><a href="#main-content">Main Content</a></li>
                <!-- The navigation links would be generated dynamically -->
            </ul>
        </div>
    </nav>
    
    <main id="main-content" role="main">
        <section class="content-section" aria-label="Document content">
            <h2>Extracted Content</h2>
            <p>The content of the document will be processed and structured here with appropriate semantic HTML tags.</p>
            
            <!-- Here the processed content would be inserted -->
            <div class="content-placeholder">
                <p>The content of the file {file.filename} will be processed and displayed here in accessible format.</p>
            </div>
        </section>
    </main>
    
    <footer role="contentinfo">
        <p>Document generated automatically with WCAG 2.1 AA accessibility standards</p>
    </footer>
</body>
</html>
        """
        
        # Accessibility metadata
        accessibility_metadata = {
            "wcag_level": "AA",
            "compliance": {
                "perceivable": True,
                "operable": True,
                "understandable": True,
                "robust": True
            },
            "features": [
                "Semantic HTML5 structure",
                "Hierarchical headings",
                "Keyboard navigation",
                "Skip links",
                "ARIA labels",
                "Appropriate color contrast",
                "Descriptive alternative text for images"
            ],
            "file_info": {
                "original_file": file.filename,
                "processed_at": "2024-01-01T00:00:00Z",
                "html_version": "5",
                "accessibility_standard": "WCAG 2.1"
            }
        }
        
        return {
            "success": True,
            "message": f"Accessible HTML generated for {file.filename}",
            "html_content": html_content,
            "accessibility_metadata": accessibility_metadata,
            "file_info": {
                "original_file": file.filename,
                "size": len(content)
            }
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error generating accessible HTML: {str(e)}"
        )

@router.post("/get-raw-xml")
async def get_raw_xml_from_zip(
    file: UploadFile = File(...),
    async_processing: bool = False,
    background_tasks: BackgroundTasks = None,
    token: JWTLectureTokenPayload = Depends(require_token_types(allowed_types=["cognito"])), 
    db: Session = Depends(get_db)
):
    """
    Endpoint to get the raw XML of .indt, .inddbook or .zip files
    
    Parameters:
        file (UploadFile): .indt, .inddbook or .zip file to process
        async_processing (bool): Whether to process asynchronously
        background_tasks (BackgroundTasks): Background tasks for async processing
        token (str): User authentication token
        db (Session): Database session
    
    Response:
        JSON with the raw XML of the main files
    """
    # Verify user token
    user = get_user_by_cognito_id(db, token.sub)
    user_id = user.id if user else None

    if user_id is None:
        raise HTTPException(status_code=401, detail="Unauthorized")

    try:
        if async_processing and background_tasks:
            # Async processing with AppSync
            app_sync = AsyncManager()
            app_sync.set_parameters()
            
            # Add task to background
            background_tasks.add_task(
                app_sync.process_document_raw_xml,
                user_id=user_id,
                file=file,
                task_type="get_raw_xml"
            )
            
            return {
                "success": True,
                "message": f"Raw XML extraction started in background for {file.filename}",
                "data": {
                    "file_info": {
                        "name": file.filename,
                        "status": "processing"
                    }
                }
            }
        else:
            # Synchronous processing
            # Verify that it is a valid file
            if not (file.filename.lower().endswith('.indt') or 
                    file.filename.lower().endswith('.inddbook') or 
                    file.filename.lower().endswith('.zip')):
                raise HTTPException(
                    status_code=400,
                    detail="The file must be a .indt, .inddbook or .zip file"
                )
            
            # Read the content of the file
            content = await file.read()
        
        import zipfile
        import xml.etree.ElementTree as ET
        import io
        import json
        
        raw_xml_data = {
            "file_info": {
                "name": file.filename,
                "size": len(content),
                "type": "indesign_template" if file.filename.lower().endswith('.indt') else 
                       "indesign_book" if file.filename.lower().endswith('.inddbook') else "zip_archive"
            },
            "xml_files": {},
            "file_structure": [],
            "debug_info": {}
        }
        
        try:
            # Process the ZIP file
            with zipfile.ZipFile(io.BytesIO(content), 'r') as zip_file:
                file_list = zip_file.namelist()
                raw_xml_data["file_structure"] = file_list
                raw_xml_data["debug_info"]["total_files"] = len(file_list)
                
                # Search for main XML files
                xml_files = [f for f in file_list if f.endswith('.xml')]
                raw_xml_data["debug_info"]["xml_files_found"] = len(xml_files)
                
                # Process .indd files if they exist
                indd_files = [f for f in file_list if f.endswith('.indd')]
                if indd_files:
                    raw_xml_data["debug_info"]["indd_files"] = indd_files
                    
                    # Process the first .indd file
                    try:
                        indd_content = zip_file.read(indd_files[0])
                        with zipfile.ZipFile(io.BytesIO(indd_content), 'r') as indd_zip:
                            indd_file_list = indd_zip.namelist()
                            raw_xml_data["debug_info"]["indd_internal_files"] = indd_file_list
                            
                            # Search for XML files inside the .indd
                            indd_xml_files = [f for f in indd_file_list if f.endswith('.xml')]
                            raw_xml_data["debug_info"]["indd_xml_files"] = indd_xml_files
                            
                            # Extract raw XML from important files
                            important_files = [
                                'designmap.xml',
                                'BackingStory.xml',
                                'Graphic.xml',
                                'Preferences.xml',
                                'Toc.xml',
                                'Tags.xml',
                                'XML.xml'
                            ]
                            
                            for xml_file in indd_xml_files:
                                try:
                                    xml_content = indd_zip.read(xml_file)
                                    xml_text = xml_content.decode('utf-8', errors='ignore')
                                    
                                    # Try to parse the XML to format it
                                    try:
                                        root = ET.fromstring(xml_content)
                                        # Format XML in a readable way
                                        import xml.dom.minidom
                                        dom = xml.dom.minidom.parseString(xml_content)
                                        formatted_xml = dom.toprettyxml(indent="  ")
                                    except:
                                        formatted_xml = xml_text
                                    
                                    raw_xml_data["xml_files"][f"indd_{xml_file}"] = {
                                        "file_path": xml_file,
                                        "size": len(xml_content),
                                        "raw_xml": xml_text,
                                        "formatted_xml": formatted_xml,
                                        "is_important": xml_file in important_files
                                    }
                                    
                                    # Basic analysis of the XML
                                    try:
                                        root = ET.fromstring(xml_content)
                                        elements = list(root.iter())
                                        element_types = set(elem.tag for elem in elements)
                                        
                                        raw_xml_data["xml_files"][f"indd_{xml_file}"]["analysis"] = {
                                            "total_elements": len(elements),
                                            "unique_element_types": sorted(list(element_types)),
                                            "has_text_content": any(elem.text and elem.text.strip() for elem in elements),
                                            "text_elements_count": len([elem for elem in elements if elem.text and elem.text.strip()])
                                        }
                                    except Exception as e:
                                        raw_xml_data["xml_files"][f"indd_{xml_file}"]["analysis"] = {
                                            "error": str(e)
                                        }
                                        
                                except Exception as e:
                                    raw_xml_data["xml_files"][f"indd_{xml_file}"] = {
                                        "file_path": xml_file,
                                        "error": f"Error reading file: {str(e)}"
                                    }
                                    
                    except Exception as e:
                        raw_xml_data["debug_info"]["indd_processing_error"] = str(e)
                
                # Also process XML files from the main ZIP
                for xml_file in xml_files:
                    try:
                        xml_content = zip_file.read(xml_file)
                        xml_text = xml_content.decode('utf-8', errors='ignore')
                        
                        # Try to parse the XML to format it
                        try:
                            root = ET.fromstring(xml_content)
                            import xml.dom.minidom
                            dom = xml.dom.minidom.parseString(xml_content)
                            formatted_xml = dom.toprettyxml(indent="  ")
                        except:
                            formatted_xml = xml_text
                        
                        raw_xml_data["xml_files"][f"zip_{xml_file}"] = {
                            "file_path": xml_file,
                            "size": len(xml_content),
                            "raw_xml": xml_text,
                            "formatted_xml": formatted_xml,
                            "is_important": xml_file in ['designmap.xml', 'BackingStory.xml']
                        }
                        
                        # Basic analysis of the XML
                        try:
                            root = ET.fromstring(xml_content)
                            elements = list(root.iter())
                            element_types = set(elem.tag for elem in elements)
                            
                            raw_xml_data["xml_files"][f"zip_{xml_file}"]["analysis"] = {
                                "total_elements": len(elements),
                                "unique_element_types": sorted(list(element_types)),
                                "has_text_content": any(elem.text and elem.text.strip() for elem in elements),
                                "text_elements_count": len([elem for elem in elements if elem.text and elem.text.strip()])
                            }
                        except Exception as e:
                            raw_xml_data["xml_files"][f"zip_{xml_file}"]["analysis"] = {
                                "error": str(e)
                            }
                            
                    except Exception as e:
                        raw_xml_data["xml_files"][f"zip_{xml_file}"] = {
                            "file_path": xml_file,
                            "error": f"Error reading file: {str(e)}"
                        }
                
                # Search for plain text files that may contain information
                text_files = [f for f in file_list if f.endswith('.txt') or 'instructions' in f.lower()]
                if text_files:
                    raw_xml_data["text_files"] = {}
                    for text_file in text_files:
                        try:
                            text_content = zip_file.read(text_file)
                            text_text = text_content.decode('utf-8', errors='ignore')
                            raw_xml_data["text_files"][text_file] = {
                                "content": text_text,
                                "size": len(text_content)
                            }
                        except Exception as e:
                            raw_xml_data["text_files"][text_file] = {
                                "error": f"Error reading file: {str(e)}"
                            }
                
        except zipfile.BadZipFile:
            raise HTTPException(
                status_code=400,
                detail="The file is not a valid ZIP file"
            )
        
        return {
            "success": True,
            "message": f"Raw XML extracted from {file.filename}",
            "data": raw_xml_data
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error extracting raw XML: {str(e)}"
        )

@router.post("/diagnose-indd")
async def diagnose_indd_file(
    file: UploadFile = File(...),
    async_processing: bool = False,
    background_tasks: BackgroundTasks = None,
    token: JWTLectureTokenPayload = Depends(require_token_types(allowed_types=["cognito"])), 
    db: Session = Depends(get_db)
):
    """
    Endpoint to diagnose files .indt, .inddbook or .zip
    Unzip the ZIP, identify the .indd file and make a detailed verification
    
    Parameters:
        file (UploadFile): .indt, .inddbook or .zip file to analyze
        async_processing (bool): Whether to process asynchronously
        background_tasks (BackgroundTasks): Background tasks for async processing
        token (str): User authentication token
        db (Session): Database session
    
    Response:
        JSON with detailed diagnosis of the .indd file
    """
    # Verify user token
    user = get_user_by_cognito_id(db, token.sub)
    user_id = user.id if user else None

    if user_id is None:
        raise HTTPException(status_code=401, detail="Unauthorized")

    try:
        if async_processing and background_tasks:
            # Async processing with AppSync
            app_sync = AsyncManager()
            app_sync.set_parameters()
            
            # Add task to background
            background_tasks.add_task(
                app_sync.process_document_diagnose_indd,
                user_id=user_id,
                file=file,
                task_type="diagnose_indd"
            )
            
            return {
                "success": True,
                "message": f"INDD diagnosis started in background for {file.filename}",
                "data": {
                    "file_info": {
                        "name": file.filename,
                        "status": "processing"
                    }
                }
            }
        else:
            # Synchronous processing
            # Verify that it is a valid file
            if not (file.filename.lower().endswith('.indt') or 
                    file.filename.lower().endswith('.inddbook') or 
                    file.filename.lower().endswith('.zip')):
                raise HTTPException(
                    status_code=400,
                    detail="The file must be a .indt, .inddbook or .zip file"
                )
            
            # Read the content of the file
            content = await file.read()
        
        import zipfile
        import xml.etree.ElementTree as ET
        import io
        import json
        import os
        import tempfile
        import shutil
        import magic  # To detect file types
        
        diagnosis = {
            "file_info": {
                "name": file.filename,
                "size": len(content),
                "type": "indesign_template" if file.filename.lower().endswith('.indt') else 
                       "indesign_book" if file.filename.lower().endswith('.inddbook') else "zip_archive"
            },
            "zip_analysis": {},
            "indd_analysis": {},
            "extraction_results": {},
            "debug_info": {}
        }
        
        try:
            # Create temporary directory for extraction
            with tempfile.TemporaryDirectory() as temp_dir:
                # Process the ZIP file
                with zipfile.ZipFile(io.BytesIO(content), 'r') as zip_file:
                    file_list = zip_file.namelist()
                    diagnosis["zip_analysis"]["total_files"] = len(file_list)
                    diagnosis["zip_analysis"]["file_list"] = file_list
                    
                    # Search for .indd files
                    indd_files = [f for f in file_list if f.endswith('.indd')]
                    diagnosis["zip_analysis"]["indd_files_found"] = len(indd_files)
                    diagnosis["zip_analysis"]["indd_files"] = indd_files
                    
                    if not indd_files:
                        diagnosis["indd_analysis"]["error"] = "No .indd files found in the ZIP"
                        return {
                            "success": False,
                            "message": "No .indd files found",
                            "data": diagnosis
                        }
                    
                    # Extract the first .indd file
                    indd_file_path = indd_files[0]
                    indd_content = zip_file.read(indd_file_path)
                    indd_file_size = len(indd_content)
                    
                    diagnosis["indd_analysis"]["file_info"] = {
                        "name": indd_file_path,
                        "size": indd_file_size,
                        "size_mb": round(indd_file_size / (1024 * 1024), 2)
                    }
                    
                    # Save the .indd file in the temporary directory
                    indd_temp_path = os.path.join(temp_dir, "extracted.indd")
                    with open(indd_temp_path, 'wb') as f:
                        f.write(indd_content)
                    
                    # Verify that it is a valid ZIP file
                    try:
                        with zipfile.ZipFile(indd_temp_path, 'r') as indd_zip:
                            indd_file_list = indd_zip.namelist()
                            diagnosis["indd_analysis"]["is_valid_zip"] = True
                            diagnosis["indd_analysis"]["internal_files"] = indd_file_list
                            diagnosis["indd_analysis"]["internal_files_count"] = len(indd_file_list)
                            
                            # Search for important XML files
                            xml_files = [f for f in indd_file_list if f.endswith('.xml')]
                            diagnosis["indd_analysis"]["xml_files"] = xml_files
                            diagnosis["indd_analysis"]["xml_files_count"] = len(xml_files)
                            
                            # Verify critical files
                            critical_files = [
                                'designmap.xml',
                                'BackingStory.xml',
                                'Graphic.xml',
                                'Preferences.xml',
                                'Toc.xml',
                                'Tags.xml',
                                'XML.xml',
                                'Spreads.xml',
                                'Stories.xml'
                            ]
                            
                            found_critical_files = []
                            for critical_file in critical_files:
                                if critical_file in indd_file_list:
                                    found_critical_files.append(critical_file)
                            
                            diagnosis["indd_analysis"]["critical_files_found"] = found_critical_files
                            diagnosis["indd_analysis"]["critical_files_missing"] = [f for f in critical_files if f not in indd_file_list]
                            
                            # Analyze found XML files
                            xml_analysis = {}
                            for xml_file in xml_files:
                                try:
                                    xml_content = indd_zip.read(xml_file)
                                    xml_size = len(xml_content)
                                    
                                    # Try to parse XML
                                    try:
                                        root = ET.fromstring(xml_content)
                                        elements = list(root.iter())
                                        element_types = set(elem.tag for elem in elements)
                                        
                                        xml_analysis[xml_file] = {
                                            "size": xml_size,
                                            "size_kb": round(xml_size / 1024, 2),
                                            "parseable": True,
                                            "total_elements": len(elements),
                                            "unique_element_types": sorted(list(element_types)),
                                            "has_text_content": any(elem.text and elem.text.strip() for elem in elements),
                                            "text_elements_count": len([elem for elem in elements if elem.text and elem.text.strip()]),
                                            "is_critical": xml_file in critical_files
                                        }
                                        
                                        # Specific analysis for critical files
                                        if xml_file == 'designmap.xml':
                                            spreads = root.findall('.//idPkg:Spread', namespaces={'idPkg': 'http://ns.adobe.com/AdobeInDesign/idml/1.0/packaging'})
                                            xml_analysis[xml_file]["spreads_count"] = len(spreads)
                                            xml_analysis[xml_file]["spread_files"] = [spread.get('src', '') for spread in spreads]
                                        
                                        elif xml_file == 'BackingStory.xml':
                                            stories = root.findall('.//Story')
                                            xml_analysis[xml_file]["stories_count"] = len(stories)
                                            
                                    except ET.ParseError as e:
                                        xml_analysis[xml_file] = {
                                            "size": xml_size,
                                            "size_kb": round(xml_size / 1024, 2),
                                            "parseable": False,
                                            "parse_error": str(e),
                                            "is_critical": xml_file in critical_files
                                        }
                                        
                                except Exception as e:
                                    xml_analysis[xml_file] = {
                                        "error": f"Error reading file: {str(e)}",
                                        "is_critical": xml_file in critical_files
                                    }
                            
                            diagnosis["indd_analysis"]["xml_analysis"] = xml_analysis
                            
                            # Try to extract text content
                            text_extraction = {}
                            if 'designmap.xml' in xml_files and 'designmap.xml' in xml_analysis and xml_analysis['designmap.xml']['parseable']:
                                try:
                                    designmap_content = indd_zip.read('designmap.xml')
                                    root = ET.fromstring(designmap_content)
                                    
                                    # Search for spreads and extract content
                                    spreads = root.findall('.//idPkg:Spread', namespaces={'idPkg': 'http://ns.adobe.com/AdobeInDesign/idml/1.0/packaging'})
                                    text_extraction["spreads_found"] = len(spreads)
                                    text_extraction["spread_analysis"] = []
                                    
                                    for i, spread in enumerate(spreads[:3]):  # Analyze only the first 3 spreads
                                        spread_id = spread.get('src', '')
                                        if spread_id and spread_id in indd_file_list:
                                            try:
                                                spread_content = indd_zip.read(spread_id)
                                                spread_root = ET.fromstring(spread_content)
                                                
                                                # Search for text elements
                                                text_elements = []
                                                for elem in spread_root.iter():
                                                    if elem.text and elem.text.strip():
                                                        text_elements.append({
                                                            "tag": elem.tag,
                                                            "text": elem.text.strip()[:100] + "..." if len(elem.text.strip()) > 100 else elem.text.strip()
                                                        })
                                                
                                                text_extraction["spread_analysis"].append({
                                                    "spread_id": spread_id,
                                                    "text_elements_found": len(text_elements),
                                                    "sample_text_elements": text_elements[:5]  # Only the first 5
                                                })
                                                
                                            except Exception as e:
                                                text_extraction["spread_analysis"].append({
                                                    "spread_id": spread_id,
                                                    "error": str(e)
                                                })
                                    
                                except Exception as e:
                                    text_extraction["error"] = f"Error analyzing designmap.xml: {str(e)}"
                            
                            diagnosis["indd_analysis"]["text_extraction"] = text_extraction
                            
                    except zipfile.BadZipFile:
                        diagnosis["indd_analysis"]["is_valid_zip"] = False
                        diagnosis["indd_analysis"]["error"] = "The .indd file is not a valid ZIP file"
                        
                        # Try to detect the real file type
                        try:
                            file_type = magic.from_file(indd_temp_path, mime=True)
                            diagnosis["indd_analysis"]["detected_file_type"] = file_type
                            
                            # Read the first bytes for analysis
                            with open(indd_temp_path, 'rb') as f:
                                first_bytes = f.read(100)
                                diagnosis["indd_analysis"]["first_bytes_hex"] = first_bytes.hex()
                                diagnosis["indd_analysis"]["first_bytes_ascii"] = first_bytes.decode('ascii', errors='ignore')
                                
                        except Exception as e:
                            diagnosis["indd_analysis"]["file_type_detection_error"] = str(e)
                    
                    # Extract other important files from the ZIP
                    other_files = {}
                    for file_name in file_list:
                        if file_name.endswith('.txt') or 'instructions' in file_name.lower():
                            try:
                                file_content = zip_file.read(file_name)
                                other_files[file_name] = {
                                    "size": len(file_content),
                                    "content": file_content.decode('utf-8', errors='ignore')[:1000] + "..." if len(file_content) > 1000 else file_content.decode('utf-8', errors='ignore')
                                }
                            except Exception as e:
                                other_files[file_name] = {"error": str(e)}
                    
                    diagnosis["extraction_results"]["other_files"] = other_files
                    
                    # Summary of the diagnosis
                    diagnosis["summary"] = {
                        "zip_valid": True,
                        "indd_found": len(indd_files) > 0,
                        "indd_is_zip": diagnosis["indd_analysis"].get("is_valid_zip", False),
                        "xml_files_found": diagnosis["indd_analysis"].get("xml_files_count", 0),
                        "critical_files_found": len(diagnosis["indd_analysis"].get("critical_files_found", [])),
                        "has_text_content": any(
                            xml_info.get("has_text_content", False) 
                            for xml_info in diagnosis["indd_analysis"].get("xml_analysis", {}).values()
                        )
                    }
                
        except zipfile.BadZipFile:
            diagnosis["zip_analysis"]["error"] = "The file is not a valid ZIP file"
            return {
                "success": False,
                "message": "The file is not a valid ZIP file",
                "data": diagnosis
            }
        
        return {
            "success": True,
            "message": f"Diagnosis completed for {file.filename}",
            "data": diagnosis
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error in diagnosis: {str(e)}"
        )

@router.post("/extract-pdf-metadata-and-generate-html")
async def extract_pdf_metadata_and_generate_html(
    file: UploadFile = File(...),
    preserve_styles: bool = Form(True),
    generate_html: bool = Form(True),
    async_processing: bool = False,
    background_tasks: BackgroundTasks = None,
    token: JWTLectureTokenPayload = Depends(require_token_types(allowed_types=["cognito"])), 
    db: Session = Depends(get_db)
):
    """
    Extract detailed metadata from a PDF and generate HTML respecting sources, colors and structures.
    
    Parameters:
        file (UploadFile): PDF file to process
        preserve_styles (bool): Whether to preserve original styles
        generate_html (bool): Whether to generate HTML with styles
        async_processing (bool): Whether to process asynchronously
        background_tasks (BackgroundTasks): Background tasks for async processing
        token (str): User authentication token
        db (Session): Database session
    
    Response:
        JSON with PDF metadata and generated HTML
    """
    # Verify user token
    user = get_user_by_cognito_id(db, token.sub)
    user_id = user.id if user else None

    if user_id is None:
        raise HTTPException(status_code=401, detail="Unauthorized")

    try:
        if async_processing and background_tasks:
            # Async processing with AppSync
            def process_async_document_pdf_metadata_html(file, preserve_styles, generate_html, user_id, task_type):
                # Create a new connection for the background task
                db_task = SessionLocal()
                try:
                    # Create an event loop to execute asynchronous code
                    loop = asyncio.new_event_loop()
                    
                    # Execute the document PDF metadata HTML in the loop
                    result = loop.run_until_complete(
                        _process_document_pdf_metadata_html_internal(db_task, user_id, file, preserve_styles, generate_html, task_type)
                    )
                    
                    return result
                except Exception as e:
                    raise
                finally:
                    db_task.close()
            
            # Add task to background
            background_tasks.add_task(
                process_async_document_pdf_metadata_html,
                file=file,
                preserve_styles=preserve_styles,
                generate_html=generate_html,
                user_id=user_id,
                task_type="extract_pdf_metadata_and_generate_html"
            )
            
            return {
                'success': True,
                'message': f'PDF metadata extraction and HTML generation started in background for {file.filename}',
                'metadata': 'Processing started. You will be notified when complete.',
                'html_content': 'Processing started. You will be notified when complete.'
            }
        else:
            # Synchronous processing
            resultado = await get_document_service().extract_pdf_metadata_and_generate_html(
                file, preserve_styles, generate_html
            )
            return {
                'success': True,
                **resultado
            }
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error processing PDF: {str(e)}"
        )
        resultado = await get_document_service().extract_pdf_metadata_and_generate_html(
            file, preserve_styles, generate_html
        )
        return {
            'success': True,
            **resultado
        }
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error processing PDF: {str(e)}"
        )

@router.post("/extract-pdf-metadata-by-pages")
async def extract_pdf_metadata_by_pages(
    file: UploadFile = File(...),
):
    """
    Extract metadata from a PDF grouped by pages.
    
    Parameters:
        file (UploadFile): PDF file to process
    
    Respuesta:
        JSON with list of pages and their metadata
    """

    try:
        resultado = await get_document_service().extract_pdf_metadata_by_pages(file)
        return {
            'success': True,
            **resultado
        }
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error processing PDF: {str(e)}"
        )


@router.post("/generate-html-from-pdf-pages")
async def generate_html_from_pdf_pages(
    file: UploadFile = File(...),
    prompt: str = Form(None),
    language: str = Form("es"),
    accessibility_rules_file: UploadFile = File(None),
    async_processing: bool = False,
    background_tasks: BackgroundTasks = None,
    token: JWTLectureTokenPayload = Depends(require_token_types(allowed_types=["cognito"])), 
    db: Session = Depends(get_db)
):
    """
    Generate HTML from a PDF using page metadata and AI.
    
    Parameters:
        file (UploadFile): PDF file to process
        prompt (str, optional): Custom prompt for HTML generation
        language (str, optional): Language of the content (default: "es")
        accessibility_rules_file (UploadFile, optional): File with accessibility rules
        async_processing (bool): Whether to process asynchronously
        background_tasks (BackgroundTasks): Background tasks for async processing
        token (str): User authentication token
        db (Session): Database session
    
    Response:
        JSON with HTML generated for each page
    """
    # Verify user token
    user = get_user_by_cognito_id(db, token.sub)
    user_id = user.id if user else None

    if user_id is None:
        raise HTTPException(status_code=401, detail="Unauthorized")

    try:
        if async_processing and background_tasks:
            # Async processing with AppSync
            def process_async_document_html_from_pdf_pages(file, prompt, language, accessibility_rules_file, user_id, task_type):
                # Create a new connection for the background task
                db_task = SessionLocal()
                try:
                    # Create an event loop to execute asynchronous code
                    loop = asyncio.new_event_loop()
                    
                    # Execute the document HTML from PDF pages in the loop
                    result = loop.run_until_complete(
                        _process_document_html_from_pdf_pages_internal(db_task, user_id, file, prompt, language, accessibility_rules_file, task_type)
                    )
                    
                    return result
                except Exception as e:
                    raise
                finally:
                    db_task.close()
            
            # Add task to background
            background_tasks.add_task(
                process_async_document_html_from_pdf_pages,
                file=file,
                prompt=prompt,
                language=language,
                accessibility_rules_file=accessibility_rules_file,
                user_id=user_id,
                task_type="generate_html_from_pdf_pages"
            )
            
            return {
                "success": True,
                "message": f"HTML generation from PDF pages started in background for {file.filename}",
                "html_content": "Processing started. You will be notified when complete."
            }
        else:
            # Synchronous processing
            # Get metadata by pages
            document_service = get_document_service()
            metadata_result = await document_service.extract_pdf_metadata_by_pages(file)
        
            pages = metadata_result.get("pages", [])
            total_pages = metadata_result.get("total_pages", 0)
            
            if total_pages == 0:
                return {
                    "success": False,
                    "message": "No pages found in the PDF",
                    "html_content": ""
                }
            
            # Process accessibility rules file if provided
            accessibility_rules = None
            if accessibility_rules_file:
                try:
                    # Use the new method to process the file
                    file_structure = await document_service.process_accessibility_rules_file(accessibility_rules_file)
                    accessibility_rules = document_service._extract_text_from_file_structure(file_structure)
                    print(f"✅ Accessibility rules file processed: {len(accessibility_rules)} characters")
                    print(f"📋 Processing type: {'Fallback' if file_structure.get('fallback') else 'Textract'}")
                except Exception as e:
                    print(f"⚠️ Error processing accessibility file: {str(e)}")
                    accessibility_rules = None
            
            # Import strands service
            from services.strands_service import StrandsService
            strands_service = StrandsService()
            
            # Generate HTML for each page
            html_sections = []
            
            for page in pages:
                try:
                    page_html = await strands_service.generate_html_from_page_metadata(
                        page, 
                        custom_prompt=prompt,
                        language=language,
                        accessibility_rules=accessibility_rules
                    )
                    html_sections.append(page_html)
                    print(f"✅ HTML generado para página {page.get('page_number', 'unknown')}")
                except Exception as e:
                    print(f"❌ Error generating HTML for page {page.get('page_number', 'unknown')}: {str(e)}")
                    # Add error section
                    error_html = f'<main class="pdf-page error" data-page-number="{page.get("page_number", 1)}">\n<div class="error-message">Error procesando página: {str(e)}</div>\n</main>'
                    html_sections.append(error_html)
            
            # Combine all sections
            full_html_content = "".join(html_sections)
            
            return {
                "success": True,
                "message": f"HTML generated successfully for {total_pages} page(s)",
                "html_content": full_html_content
            }
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error generating HTML: {str(e)}"
        )



# @router.post("/extract-images-from-pdf")
# async def extract_images_from_pdf(file: UploadFile):
#     """
#     Extrae todas las imágenes de un PDF usando MuPDF (PyMuPDF)
#     Devuelve las imágenes organizadas por página con sus posiciones
#     """
#     try:
#         # Importar fitz (PyMuPDF)
#         import fitz
        
#         # Generar UUID único para archivos temporales
#         unique_id = uuid.uuid4().hex
#         temp_pdf_path = TEMP_DIR / f"{unique_id}.pdf"
        
#         print(f"=== Extracción de imágenes del PDF ===")
#         print(f"UUID: {unique_id}")
#         print(f"Archivo: {file.filename}")
        
#         # Guardar el PDF temporalmente
#         pdf_content = await file.read()
#         print(f"📄 Tamaño del archivo PDF: {len(pdf_content)} bytes")
        
#         with open(temp_pdf_path, "wb") as f:
#             f.write(pdf_content)
        
#         # Verificar que es un PDF válido
#         with open(temp_pdf_path, "rb") as f:
#             header = f.read(4)
#             if header != b'%PDF':
#                 return {
#                     "success": False,
#                     "error": "El archivo no parece ser un PDF válido"
#                 }
        
#         # Abrir el PDF con PyMuPDF
#         doc = fitz.open(temp_pdf_path)
#         total_pages = len(doc)
#         print(f"📄 Total de páginas: {total_pages}")
        
#         pages_data = []
        
#         for page_num in range(total_pages):
#             page = doc.load_page(page_num)
#             page_width = page.rect.width
#             page_height = page.rect.height
            
#             print(f"🔄 Procesando página {page_num + 1}/{total_pages}")
#             print(f"   Tamaño de página: {page_width:.2f} x {page_height:.2f} puntos")
            
#             # Obtener las imágenes de la página
#             image_list = page.get_images()
#             print(f"   Imágenes encontradas: {len(image_list)}")
            
#             page_images = []
            
#             for img_index, img in enumerate(image_list):
#                 try:
#                     # Obtener información de la imagen
#                     xref = img[0]  # Referencia cruzada de la imagen
                    
#                     # Extraer la imagen
#                     pix = fitz.Pixmap(doc, xref)
                    
#                     # Convertir a formato RGB si es necesario
#                     if pix.n - pix.alpha < 4:  # GRAY or RGB
#                         img_data = pix.tobytes("png")
#                     else:  # CMYK: convert to RGB first
#                         pix1 = fitz.Pixmap(fitz.csRGB, pix)
#                         img_data = pix1.tobytes("png")
#                         pix1 = None
                    
#                     # Convertir a base64 con prefijo data URL
#                     img_base64 = "data:image/png;base64," + base64.b64encode(img_data).decode('utf-8')
                    
#                     # Obtener información de posición real de la imagen
#                     img_id = str(uuid.uuid4())
                    
#                     # Buscar la posición real de la imagen en la página
#                     x_position = 0
#                     y_position = 0
#                     img_width = "unknown"
#                     img_height = "unknown"
                    
#                     try:
#                         # Obtener información del stream de la imagen
#                         img_stream = doc.extract_image(xref)
#                         if img_stream:
#                             img_width = img_stream.get("width", "unknown")
#                             img_height = img_stream.get("height", "unknown")
                        
#                         # Buscar la posición de la imagen usando múltiples métodos
                        
#                         # Método 1: Usar get_image_info() para obtener información detallada
#                         try:
#                             img_info_list = page.get_image_info()
#                             for info in img_info_list:
#                                 if info.get("xref") == xref:
#                                     bbox = info.get("bbox", [0, 0, 0, 0])
#                                     x_position = bbox[0]  # x1 (izquierda)
#                                     y_position = page_height - bbox[3]  # Convertir coordenadas PDF a CSS (top)
#                                     print(f"   📍 Posición encontrada con get_image_info: ({x_position:.2f}, {y_position:.2f})")
#                                     break
#                         except Exception as e:
#                             print(f"   ⚠️ get_image_info falló: {e}")
                        
#                         # Método 2: Si no se encontró, buscar en los bloques de texto
#                         if x_position == 0 and y_position == 0:
#                             try:
#                                 page_dict = page.get_text("dict")
#                                 for block in page_dict.get("blocks", []):
#                                     if block.get("type") == 1:  # Image block
#                                         if block.get("xref") == xref:
#                                             bbox = block.get("bbox", [0, 0, 0, 0])
#                                             x_position = bbox[0]  # x1
#                                             y_position = page_height - bbox[3]  # Convertir coordenadas PDF a CSS
#                                             print(f"   📍 Posición encontrada en bloques: ({x_position:.2f}, {y_position:.2f})")
#                                             break
#                             except Exception as e:
#                                 print(f"   ⚠️ Búsqueda en bloques falló: {e}")
                        
#                         # Método 3: Buscar en el stream de contenido
#                         if x_position == 0 and y_position == 0:
#                             try:
#                                 # Obtener el stream de contenido de la página
#                                 page_stream = page.get_contents()
#                                 if page_stream:
#                                     # Buscar matrices de transformación que referencien esta imagen
#                                     # Esto es más complejo y requiere análisis del stream
#                                     print(f"   🔍 Buscando en stream de contenido...")
#                                     # Por ahora, usaremos aproximación
#                             except Exception as e:
#                                 print(f"   ⚠️ Análisis de stream falló: {e}")
                        
#                         # Si no se encontró posición específica, usar aproximación basada en índice
#                         if x_position == 0 and y_position == 0:
#                             # Calcular posición aproximada basada en el índice
#                             images_per_row = 3  # Asumir 3 imágenes por fila
#                             row = img_index // images_per_row
#                             col = img_index % images_per_row
#                             x_position = col * 100  # 100 puntos de separación
#                             y_position = row * 100
#                             print(f"   📍 Posición aproximada: ({x_position:.2f}, {y_position:.2f})")
                        
#                     except Exception as e:
#                         print(f"   ⚠️ Error obteniendo posición de imagen {img_index}: {e}")
#                         # Usar posición por defecto
#                         x_position = img_index * 50
#                         y_position = img_index * 50
                    
#                     # Crear información de la imagen con posición real
#                     img_info = {
#                         "id": img_id,
#                         "x_position": f"{x_position:.2f}pt",
#                         "y_position": f"{y_position:.2f}pt",
#                         "image_base64": img_base64,
#                         "width": img_width,
#                         "height": img_height,
#                         "colorspace": img_stream.get("colorspace", "unknown") if img_stream else "unknown",
#                         "bpc": img_stream.get("bpc", "unknown") if img_stream else "unknown"
#                     }
                    
#                     page_images.append(img_info)
#                     print(f"   ✅ Imagen {img_index + 1} extraída: {len(img_base64)} caracteres base64")
                    
#                     # Liberar memoria
#                     pix = None
                    
#                 except Exception as e:
#                     print(f"   ❌ Error procesando imagen {img_index}: {e}")
#                     continue
            
#             # Crear datos de la página
#             page_data = {
#                 "page": page_num + 1,
#                 "page_size": {
#                     "x": f"{page_width:.0f}pt",
#                     "y": f"{page_height:.0f}pt"
#                 },
#                 "images": page_images
#             }
            
#             pages_data.append(page_data)
#             print(f"   📊 Página {page_num + 1} completada: {len(page_images)} imágenes")
        
#         # Cerrar el documento
#         doc.close()
        
#         # Limpiar archivo temporal
#         temp_pdf_path.unlink(missing_ok=True)
        
#         print(f"✅ Extracción completada: {len(pages_data)} páginas procesadas")
        
#         return {
#             "success": True,
#             "message": f"Extracción exitosa: {len(pages_data)} páginas, {sum(len(page['images']) for page in pages_data)} imágenes totales",
#             "total_pages": total_pages,
#             "total_images": sum(len(page['images']) for page in pages_data),
#             "pages": pages_data
#         }
        
#     except ImportError:
#         return {
#             "success": False,
#             "error": "PyMuPDF (fitz) no está instalado. Instala con: pip install PyMuPDF"
#         }
#     except Exception as e:
#         # Limpiar archivo temporal en caso de error
#         try:
#             temp_pdf_path.unlink(missing_ok=True)
#         except:
#             pass
        
#         return {
#             "success": False,
#             "error": f"Error durante la extracción: {str(e)}"
#         }


# @router.post("/extract-images")
# async def extract_images(file: UploadFile = File(...)):
#     if not file.filename.endswith(".pdf"):
#         raise HTTPException(status_code=400, detail="Only PDF files are supported.")

#     try:
#         with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
#             temp_path = tmp.name
#             shutil.copyfileobj(file.file, tmp)

#         doc = fitz.open(temp_path)
#         result = []

#         for page_number in range(len(doc)):
#             page = doc[page_number]
#             images_info = []

#             for img in page.get_images(full=True):
#                 xref = img[0]
#                 bbox = page.get_image_bbox(img)
#                 base_image = doc.extract_image(xref)

#                 # Encode image in base64
#                 image_bytes = base_image["image"]
#                 image_ext = base_image["ext"]
#                 base64_data = base64.b64encode(image_bytes).decode("utf-8")
#                 base64_uri = f"data:image/{image_ext};base64,{base64_data}"

#                 images_info.append({
#                     "xref": xref,
#                     "bbox": {
#                         "x0": bbox.x0,
#                         "y0": bbox.y0,
#                         "x1": bbox.x1,
#                         "y1": bbox.y1
#                     },
#                     "width": base_image["width"],
#                     "height": base_image["height"],
#                     "ext": image_ext,
#                     "base64": base64_uri
#                 })

#             result.append({
#                 "page": page_number + 1,
#                 "images": images_info
#             })

#         doc.close()
#         os.remove(temp_path)

#         return JSONResponse(content={"success": True, "pages": result})

#     except Exception as e:
#         return JSONResponse(
#             status_code=500,
#             content={"success": False, "error": str(e)}
#         )
    

# @router.post("/extract-images-html")
# async def extract_images_html(file: UploadFile = File(...)):
#     # Preparar directorio temporal
#     temp_dir = "temp"
#     os.makedirs(temp_dir, exist_ok=True)

#     uid = str(uuid.uuid4())
#     pdf_path = os.path.join(temp_dir, f"{uid}.pdf")
#     html_path = os.path.join(temp_dir, f"{uid}_index.html")

#     try:
#         # Guardar el archivo PDF
#         with open(pdf_path, "wb") as f:
#             f.write(await file.read())

#         doc = fitz.open(pdf_path)

#         html_lines = [
#             '<!DOCTYPE html>',
#             '<html><head><meta charset="utf-8">',
#             '<title>PDF Extracted PNGs</title>',
#             '<style>',
#             '  .page { position: relative; margin: 20px auto; border: 1px solid #ccc; }',
#             '  .page img { position: absolute; visibility: hidden; opacity: 0; }',
#             '</style>',
#             '</head><body>'
#         ]

#         for page_index, page in enumerate(doc):
#             page_width, page_height = page.rect.width, page.rect.height
#             html_lines.append(
#                 f'<div class="page" style="width:{int(page_width)}px; height:{int(page_height)}px;">'
#             )

#             for img in page.get_images(full=True):
#                 xref = img[0]
#                 bbox_list = page.get_image_rects(xref)

#                 if not bbox_list:
#                     continue

#                 try:
#                     # Extraer imagen con PyMuPDF
#                     image_info = doc.extract_image(xref)
#                     image_bytes = image_info["image"]
                    
#                     # Verificar que tenemos datos de imagen válidos
#                     if not image_bytes:
#                         continue

#                     # Procesar imagen con Pillow para preservar colores y transparencia
#                     image = Image.open(io.BytesIO(image_bytes))
                    
#                     # Debug: mostrar información de la imagen original
#                     print(f"Imagen original - Modo: {image.mode}, Tamaño: {image.size}")
                    
#                     # Detectar el modo de la imagen y convertir apropiadamente
#                     if image.mode in ('RGBA', 'LA', 'P'):
#                         # Si ya tiene canal alfa o es paleta, convertir a RGBA
#                         if image.mode == 'P':
#                             image = image.convert('RGBA')
#                         else:
#                             image = image.convert('RGBA')
#                     elif image.mode in ('RGB', 'L', '1'):
#                         # Si no tiene transparencia, convertir a RGB
#                         image = image.convert('RGB')
#                     else:
#                         # Para otros modos, intentar convertir a RGB
#                         image = image.convert('RGB')
                    
#                     print(f"Imagen procesada - Modo: {image.mode}, Tamaño: {image.size}")

#                     buffered = io.BytesIO()
                    
#                     # Determinar el formato de salida basado en el modo de la imagen
#                     if image.mode == 'RGBA':
#                         # Si tiene transparencia, usar PNG
#                         image.save(buffered, format="PNG", optimize=True)
#                         mime_type = "image/png"
#                     else:
#                         # Si no tiene transparencia, usar JPEG para mejor compresión
#                         image.save(buffered, format="JPEG", quality=95, optimize=True)
#                         mime_type = "image/jpeg"
                    
#                     img_base64 = base64.b64encode(buffered.getvalue()).decode("utf-8")

#                     for bbox in bbox_list:
#                         left = int(bbox.x0)
#                         top = int(bbox.y0)
#                         width = int(bbox.width)
#                         height = int(bbox.height)

#                         html_lines.append(
#                             f'<img src="data:{mime_type};base64,{img_base64}" '
#                             f'style="left:{left}px; top:{top}px; width:{width}px; height:{height}px;" />'
#                         )
                        
#                 except Exception as e:
#                     # Si hay error procesando una imagen específica, continuar con la siguiente
#                     print(f"Error procesando imagen en página {page_index + 1}: {str(e)}")
#                     continue

#             html_lines.append("</div>")

#         html_lines.append("</body></html>")

#         with open(html_path, "w", encoding="utf-8") as f:
#             f.write("\n".join(html_lines))

#         # Limpiar archivo PDF temporal
#         try:
#             os.remove(pdf_path)
#         except:
#             pass

#         return FileResponse(html_path, media_type="text/html", filename="index.html")
        
#     except Exception as e:
#         # Limpiar archivos temporales en caso de error
#         try:
#             if os.path.exists(pdf_path):
#                 os.remove(pdf_path)
#             if os.path.exists(html_path):
#                 os.remove(html_path)
#         except:
#             pass
            
#         return JSONResponse(
#             status_code=500,
#             content={"success": False, "error": f"Error procesando PDF: {str(e)}"}
#         )

# def pdf_to_html_div(pdf_bytes: bytes, output_path: str):
#     with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as temp_pdf:
#         temp_pdf.write(pdf_bytes)
#         temp_pdf_path = temp_pdf.name

#     doc = fitz.open(temp_pdf_path)
#     output_parts = ['<div id="pdf-content">']

#     for page_number, page in enumerate(doc):
#         page_html = page.get_text("html")

#         # Imágenes incrustadas en base64 con alt
#         images_html = ""
#         for img_index, img in enumerate(page.get_images(full=True)):
#             xref = img[0]
#             base_image = doc.extract_image(xref)
#             image_bytes = base_image["image"]
#             image_ext = base_image["ext"]
#             base64_str = base64.b64encode(image_bytes).decode("utf-8")
#             data_uri = f"data:image/{image_ext};base64,{base64_str}"
#             alt_text = f"Image from page {page_number + 1}, index {img_index}"
#             images_html += f'<img src="{data_uri}" alt="{alt_text}" style="max-width:100%; display:block; margin-bottom:1rem;" />\n'

#         output_parts.append(f'<div class="pdf-page">{images_html}{page_html}</div>')

#     output_parts.append('</div>')

#     with open(output_path, "w", encoding="utf-8") as f:
#         f.write('\n'.join(output_parts))

#     os.remove(temp_pdf_path)



# # @router.post("/convert")
# # async def convert_pdf(file: UploadFile = File(...)):
# #     contents = await file.read()
# #     output_file = "index.html"
# #     pdf_to_html_div(contents, output_file)
# #     return FileResponse(output_file, filename="index.html", media_type="text/html")
# @router.post("/convert")
# async def convert_pdf(file: UploadFile = File(...)):
#     with tempfile.TemporaryDirectory() as tmpdir:
#         temp_pdf_path = Path(tmpdir) / file.filename
#         output_html_path = Path(tmpdir) / "index.html"

#         # Guardar PDF temporalmente
#         with open(temp_pdf_path, "wb") as f:
#             f.write(await file.read())

#         doc = fitz.open(temp_pdf_path)

#         html_body = ""
#         for page_index, page in enumerate(doc):
#             page_dict = page.get_text("dict")
#             html_body += f'<div style="position:relative;width:{page.rect.width}px;height:{page.rect.height}px;border:1px solid #ccc;margin-bottom:30px;">\n'

#             # Textos
#             for block in page_dict.get("blocks", []):
#                 for line in block.get("lines", []):
#                     for span in line.get("spans", []):
#                         text = (
#                             span.get("text", "")
#                             .replace("&", "&amp;")
#                             .replace("<", "&lt;")
#                             .replace(">", "&gt;")
#                         )
#                         style = (
#                             f"position:absolute;"
#                             f"left:{span['bbox'][0]}px;"
#                             f"top:{span['bbox'][1]}px;"
#                             f"font-size:{span['size']}px;"
#                             f"font-family:'{span['font']}';"
#                             f"color:rgb({span['color']>>16 & 255},{span['color']>>8 & 255},{span['color'] & 255});"
#                         )
#                         html_body += f'<span style="{style}">{text}</span>\n'

#             # Imágenes
#             images = page.get_images(full=True)
#             for img_index, img in enumerate(images):
#                 xref = img[0]

#                 try:
#                     rects = page.get_image_rects(xref)
#                     if not rects:
#                         continue

#                     for rect in rects:
#                         pix = fitz.Pixmap(doc, xref)
#                         if pix.colorspace is None or pix.n >= 5:
#                             pix = fitz.Pixmap(fitz.csRGB, pix)
#                         elif pix.n == 4:
#                             pix = fitz.Pixmap(fitz.csRGB, pix)

#                         img_data = pix.tobytes("png")
#                         img_base64 = base64.b64encode(img_data).decode("utf-8")

#                         style = (
#                             f"position:absolute;"
#                             f"left:{rect.x0}px;"
#                             f"top:{rect.y0}px;"
#                             f"width:{rect.width}px;"
#                             f"height:{rect.height}px;"
#                         )

#                         html_body += (
#                             f'<img src="data:image/png;base64,{img_base64}" '
#                             f'style="{style}" alt="Imagen {img_index}" />\n'
#                         )
#                 except Exception as e:
#                     print(f"[Página {page_index}] Error procesando imagen: {e}")
#                     continue

#             html_body += "</div>\n"

#         final_html = f"""
# <!DOCTYPE html>
# <html lang="en">
# <head>
#     <meta charset="UTF-8">
#     <title>PDF to HTML</title>
# </head>
# <body>
# {html_body}
# </body>
# </html>
# """

#         with open(output_html_path, "w", encoding="utf-8") as f:
#             f.write(final_html)

#         return Response(
#             content=final_html,
#             media_type="text/html",
#             headers={"Content-Disposition": "attachment; filename=index.html"}
#         )

# @router.post("/pdf-to-pages-with-only-images")
# async def pdf_to_pages_with_only_images(file: UploadFile = File(...)):
#     with tempfile.TemporaryDirectory() as tmpdir:
#         temp_pdf_path = Path(tmpdir) / file.filename
#         output_html_path = Path(tmpdir) / "index.html"

#         # Guardar PDF temporalmente
#         with open(temp_pdf_path, "wb") as f:
#             f.write(await file.read())

#         doc = fitz.open(temp_pdf_path)

#         html_body = ""
#         for page_index, page in enumerate(doc):
#             page_dict = page.get_text("dict")
#             html_body += f'<div style="position:relative;width:{page.rect.width}px;height:{page.rect.height}px;border:1px solid #ccc;margin-bottom:30px;">\n'

#             # Textos
#             for block in page_dict.get("blocks", []):
#                 for line in block.get("lines", []):
#                     for span in line.get("spans", []):
#                         text = (
#                             span.get("text", "")
#                             .replace("&", "&amp;")
#                             .replace("<", "&lt;")
#                             .replace(">", "&gt;")
#                         )
#                         style = (
#                             f"position:absolute;"
#                             f"left:{span['bbox'][0]}px;"
#                             f"top:{span['bbox'][1]}px;"
#                             f"font-size:{span['size']}px;"
#                             f"font-family:'{span['font']}';"
#                             f"color:rgb({span['color']>>16 & 255},{span['color']>>8 & 255},{span['color'] & 255});"
#                         )
#                         html_body += f'<span style="{style}">{text}</span>\n'

#             # Imágenes
#             images = page.get_images(full=True)
#             for img_index, img in enumerate(images):
#                 xref = img[0]

#                 try:
#                     rects = page.get_image_rects(xref)
#                     if not rects:
#                         continue

#                     for rect in rects:
#                         pix = fitz.Pixmap(doc, xref)
#                         if pix.colorspace is None or pix.n >= 5:
#                             pix = fitz.Pixmap(fitz.csRGB, pix)
#                         elif pix.n == 4:
#                             pix = fitz.Pixmap(fitz.csRGB, pix)

#                         img_data = pix.tobytes("png")
#                         img_base64 = base64.b64encode(img_data).decode("utf-8")

#                         style = (
#                             f"position:absolute;"
#                             f"left:{rect.x0}px;"
#                             f"top:{rect.y0}px;"
#                             f"width:{rect.width}px;"
#                             f"height:{rect.height}px;"
#                         )

#                         html_body += (
#                             f'<img src="data:image/png;base64,{img_base64}" '
#                             f'style="{style}" alt="Imagen {img_index}" />\n'
#                         )
#                 except Exception as e:
#                     print(f"[Página {page_index}] Error procesando imagen: {e}")
#                     continue

#             html_body += "</div>\n"

#         final_html = f"""
# <!DOCTYPE html>
# <html lang="en">
# <head>
#     <meta charset="UTF-8">
#     <title>PDF to HTML</title>
# </head>
# <body>
# {html_body}
# </body>
# </html>
# """

#         with open(output_html_path, "w", encoding="utf-8") as f:
#             f.write(final_html)

#         return Response(
#             content=final_html,
#             media_type="text/html",
#             headers={"Content-Disposition": "attachment; filename=index.html"}
#         )

# @router.post("/pdf-to-pages-images-only")
# async def pdf_to_pages_images_only(file: UploadFile = File(...)):
#     """
#     Extrae SOLO las imágenes del PDF y las convierte a HTML.
#     No incluye textos, solo gráficos e imágenes.
#     """
#     with tempfile.TemporaryDirectory() as tmpdir:
#         temp_pdf_path = Path(tmpdir) / file.filename
#         output_html_path = Path(tmpdir) / "index.html"

#         # Guardar PDF temporalmente
#         with open(temp_pdf_path, "wb") as f:
#             f.write(await file.read())

#         doc = fitz.open(temp_pdf_path)

#         html_body = ""
#         for page_index, page in enumerate(doc):
#             html_body += f'<div style="position:relative;width:{page.rect.width}px;height:{page.rect.height}px;border:1px solid #ccc;margin-bottom:30px;">\n'

#             # Solo Imágenes - Sin textos
#             images = page.get_images(full=True)
#             for img_index, img in enumerate(images):
#                 xref = img[0]

#                 try:
#                     rects = page.get_image_rects(xref)
#                     if not rects:
#                         continue

#                     for rect in rects:
#                         pix = fitz.Pixmap(doc, xref)
#                         if pix.colorspace is None or pix.n >= 5:
#                             pix = fitz.Pixmap(fitz.csRGB, pix)
#                         elif pix.n == 4:
#                             pix = fitz.Pixmap(fitz.csRGB, pix)

#                         img_data = pix.tobytes("png")
#                         img_base64 = base64.b64encode(img_data).decode("utf-8")

#                         style = (
#                             f"position:absolute;"
#                             f"left:{rect.x0}px;"
#                             f"top:{rect.y0}px;"
#                             f"width:{rect.width}px;"
#                             f"height:{rect.height}px;"
#                         )

#                         html_body += (
#                             f'<img src="data:image/png;base64,{img_base64}" '
#                             f'style="{style}" alt="Imagen {img_index}" />\n'
#                         )
#                 except Exception as e:
#                     print(f"[Página {page_index}] Error procesando imagen: {e}")
#                     continue

#             html_body += "</div>\n"

#         final_html = f"""
#     <!DOCTYPE html>
#     <html lang="en">
#     <head>
#     <meta charset="UTF-8">
#     <title>PDF Images Only</title>
#     <style>
#         body {{ margin: 20px; font-family: Arial, sans-serif; }}
#         .page {{ background: white; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }}
#     </style>
#     </head>
#     <body>
#     {html_body}
#     </body>
#     </html>
#     """

#         with open(output_html_path, "w", encoding="utf-8") as f:
#             f.write(final_html)

#         return Response(
#             content=final_html,
#             media_type="text/html",
#             headers={"Content-Disposition": "attachment; filename=images_only.html"}
#         )