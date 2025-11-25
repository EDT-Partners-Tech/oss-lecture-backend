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

import json
import os
import uuid
import base64
import fitz
from fastapi import UploadFile
from utility.aws import upload_file_to_s3
from utility.pdf_utils import extract_images_from_pdf, extract_text_from_image_with_textract
from database.schemas import ChatbotCreate
from database.crud import create_chatbot_material
from sqlalchemy.orm import Session
from constants import S3_FOLDER_IMAGES, S3_FOLDER_KNOWLEDGE_BASE, CONTENT_TYPE_JSON
import asyncio

class PDFDocumentProcessor:
    def __init__(self, db: Session, file: UploadFile, chatbot_data: ChatbotCreate, block_chatbot_material: bool = False, material_uuid: str = None):
        self.file = file
        self.db = db
        self.chatbot_data = chatbot_data
        self.chatbot_name = f"{chatbot_data.name} - {chatbot_data.id}"
        self.create_chatbot_material = create_chatbot_material
        self.block_chatbot_material = block_chatbot_material
        self.temp_file = f"{uuid.uuid4()}.pdf"
        self.data = {
            "chatbot_name": chatbot_data.name,
            "markdown_content": []
        }
        self.data_metadata = {
            "chatbot_name": chatbot_data.name,
            "markdown_content": "This is the metadata of the chatbot"
        }
        self.image_uuid_context = []
        self.image_uuid_context_metadata = []
        self.material_uuid = material_uuid

    async def save_temp_file(self):
        """Save the PDF file in a temporary file"""
        try:
            content = await self.file.read()
            if not content:
                raise ValueError("The PDF file is empty")
                
            # Verify that the file starts with the PDF signature
            if not content.startswith(b'%PDF-'):
                raise ValueError("The file does not seem to be a valid PDF (does not start with %PDF-)")
                
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, lambda: self._save_temp_file_sync(content))
                
        except Exception as e:
            if os.path.exists(self.temp_file):
                os.remove(self.temp_file)
            raise ValueError(f"Error saving the PDF file: {str(e)}")
            
    def _save_temp_file_sync(self, content):
        """Helper method to save file synchronously"""
        with open(self.temp_file, "wb") as f:
            f.write(content)
            
        # Verify that the file has been saved correctly
        if not os.path.exists(self.temp_file) or os.path.getsize(self.temp_file) == 0:
            raise ValueError("Error saving the temporary PDF file")
        
    def open_pdf_document(self):
        """Open the PDF document using fitz"""
        try:
            return fitz.open(self.temp_file)
        except Exception as e:
            error_message = str(e)
            if "cannot open broken document" in error_message:
                raise ValueError(f"The PDF file is corrupted or not a valid PDF: {error_message}")
            else:
                raise ValueError(f"Error opening the PDF document: {error_message}")
        
    async def extract_images_from_pdf(self):
        """Extract all the images from the PDF"""
        with open(self.temp_file, "rb") as f:
            file_copy = UploadFile(filename=self.file.filename, file=f)
            return await extract_images_from_pdf(file_copy)
            
    def create_xref_to_index_mapping(self, images_info):
        """Create a mapping of xref to image index"""
        return {img['xref']: idx for idx, img in enumerate(images_info)}
        
    def get_image_locations(self, page, images):
        """Get the image locations in a page"""
        image_locations = []
        for img in images:
            try:
                xref = img[0]
                rects = page.get_image_rects(xref)
                if rects:
                    bbox = rects[0]
                    image_locations.append({
                        'xref': xref,
                        'y_position': bbox.y0
                    })
            except Exception as e:
                print(f"Warning: Error getting image location: {str(e)}")
                continue
        return sorted(image_locations, key=lambda x: x['y_position'])
        
    def create_image_context(self, image_uuid, page_index, img_info):
        """Create the context of an image"""
        return {
            'uuid': image_uuid,
            'page_number': page_index + 1,
            'elements': [],
            'document_info': {
                'filename': self.file.filename,
                'page_number': page_index + 1,
                'dimensions': {
                    'width': img_info['width'],
                    'height': img_info['height']
                }
            }
        }
        
    def create_image_metadata(self, image_uuid, page_index, img_info):
        """Create the metadata of an image"""
        return {
            'metadataAttributes': {
                'uuid': image_uuid,
                'page_number': page_index + 1,
                'elements': [{
                    'id': 'Element identification',
                    'text': 'This is part of the image text',
                    'confidence': "Percentage of confidence",
                    'position': {
                        'x_min': "Minimum x position",
                        'y_min': "Minimum y position",
                        'x_max': "Maximum x position",
                        'y_max': "Maximum y position"
                    }
                }],
                'document_info': {
                    'filename': self.file.filename,
                    'page_number': page_index + 1,
                    'dimensions': {
                        'width': img_info['width'],
                        'height': img_info['height']
                    }
                }
            }
        }
        
    def process_ocr_results(self, ocr_results, img_info, context_data):
        """Process the OCR results and add them to the context"""
        for idx_ocr, item in enumerate(ocr_results):
            text = item.get('Text', '')
            confidence = item.get('Confidence', 0.0)
            geometry = item.get('Geometry', {})
            bounding_box = geometry.get('BoundingBox', {})
            
            width = img_info['width']
            height = img_info['height']
            
            x_min = int(bounding_box.get('Left', 0) * width)
            y_min = int(bounding_box.get('Top', 0) * height)
            x_max = int((bounding_box.get('Left', 0) + bounding_box.get('Width', 0)) * width)
            y_max = int((bounding_box.get('Top', 0) + bounding_box.get('Height', 0)) * height)
            
            context_data['elements'].append({
                'id': item.get('Id', f'element_{idx_ocr}'),
                'text': text,
                'confidence': confidence,
                'position': {
                    'x_min': x_min,
                    'y_min': y_min,
                    'x_max': x_max,
                    'y_max': y_max
                }
            })
            
    async def upload_image_to_s3(self, image_uuid, img_info):
        """Upload an image to S3"""
        image_filename = f"{image_uuid}.png"
        file_temporary_path = f"{uuid.uuid4()}.png"
        with open(file_temporary_path, "wb") as f:
            f.write(base64.b64decode(img_info['base64']))
        s3_uri = await upload_file_to_s3('content', file_temporary_path, f"{S3_FOLDER_IMAGES}/{image_filename}")
        os.remove(file_temporary_path)
        return s3_uri
        
    async def upload_context_to_s3(self, image_uuid, context_data):
        """Upload the context of an image to S3"""
        context_data_json = json.dumps(context_data)
        file_temporary_path = f"{uuid.uuid4()}.json"
        with open(file_temporary_path, "wb") as f:
            f.write(context_data_json.encode('utf-8'))
        s3_uri = await upload_file_to_s3('content', file_temporary_path, f"{S3_FOLDER_KNOWLEDGE_BASE}/{self.chatbot_name}/{image_uuid}.json")
        os.remove(file_temporary_path)
        return {
            "s3_uri": s3_uri,
            "filename": f"{image_uuid}.json"
        }
        
    async def upload_metadata_to_s3(self, image_uuid, metadata):
        """Upload the metadata of an image to S3"""
        metadata_json = json.dumps(metadata)
        file_temporary_path = f"{uuid.uuid4()}.metadata.json"
        with open(file_temporary_path, "wb") as f:
            f.write(metadata_json.encode('utf-8'))
        s3_uri = await upload_file_to_s3('content', file_temporary_path, f"{S3_FOLDER_KNOWLEDGE_BASE}/{self.chatbot_name}/{image_uuid}.metadata.json")
        os.remove(file_temporary_path)
        return {
            "s3_uri": s3_uri,
            "filename": f"{image_uuid}.metadata.json"
        }
        
    def add_image_to_markdown(self, idx, image_filename, image_uuid, page_index, img_info, context_data):
        """Add the information of an image to the markdown"""
        self.data["markdown_content"].append(f"![Imagen {idx + 1}]({image_filename})\n")
        self.data["markdown_content"].append(f"\n### Image context {idx + 1} start\n")
        self.data["markdown_content"].append(f"![Imagen {idx + 1}]({image_filename})\n")
        self.data["markdown_content"].append(f"- **UUID**: {image_uuid}\n")
        self.data["markdown_content"].append(f"- **Page**: {page_index + 1}\n")
        self.data["markdown_content"].append(f"- **Dimensions**: {img_info['width']}x{img_info['height']} pixels\n")
        self.data["markdown_content"].append("- **Detected Elements:**\n")
        for elem in context_data['elements']:
            self.data["markdown_content"].append(f"-- {elem['text']}\n")
        self.data["markdown_content"].append(f"\n--- Image context {idx + 1} end ---\n")
        
    async def save_data_to_s3(self):
        """Save the data and metadata in S3"""
        # Save the JSON in s3
        json_filename = f"{os.path.splitext(self.file.filename)[0]}.json"
        file_temporary_path = f"{uuid.uuid4()}.json"
        with open(file_temporary_path, "w") as f:
            f.write(json.dumps(self.data))
        s3_uri = await upload_file_to_s3('content', file_temporary_path, f"{S3_FOLDER_KNOWLEDGE_BASE}/{self.chatbot_name}/{json_filename}")
        
        # Create the material
        await self.create_chatbot_material(self.db, {
            "chatbot_id": self.chatbot_data.id,
            "title": json_filename,
            "type": CONTENT_TYPE_JSON,
            "s3_uri": s3_uri,
            "status": "SUCCESS",
            "is_main": True
        })
        os.remove(file_temporary_path)
        
        # This method is deprecated (No remove this yet)
        # metadata_filename = f"{os.path.splitext(self.file.filename)[0]}.metadata.json"
        # file_temporary_path = f"{uuid.uuid4()}.metadata.json"
        # with open(file_temporary_path, "w") as f:
        #     f.write(json.dumps(self.data_metadata))
        # s3_uri_metadata = await upload_file_to_s3('content', file_temporary_path, f"{S3_FOLDER_KNOWLEDGE_BASE}/{self.chatbot_name}/{metadata_filename}")
        
        # # Create the material
        # await self.create_chatbot_material(self.db, {
        #     "chatbot_id": self.chatbot_data.id,
        #     "title": metadata_filename,
        #     "type": "application/json",
        #     "s3_uri": s3_uri_metadata,
        #     "status": "SUCCESS",
        #     "is_main": True
        # })
        # os.remove(file_temporary_path)
        
    async def process_page(self, page, page_index, images_info, xref_to_index, doc):
        """Process a page of the PDF"""
        text_page = page.get_text("text")
        images = page.get_images()
        
        image_locations = self.get_image_locations(page, images)
        lines = text_page.split('\n')
        image_index = 0
        
        for line in lines:
            if line.strip():
                self.data["markdown_content"].append(line)
            
            # Insert images that are in this position
            while image_index < len(image_locations):
                img_loc = image_locations[image_index]
                try:
                    idx = xref_to_index.get(img_loc['xref'])
                    if idx is not None:
                        await self.process_image(idx, page_index, images_info)
                except Exception as e:
                    print(f"Warning: Error processing image: {str(e)}")
                image_index += 1
        
        # Add a separator between pages
        if page_index < len(doc) - 1:
            self.data["markdown_content"].append("\n---\n")
            
    async def process_image(self, idx, page_index, images_info):
        """Process an image of the PDF"""
        img_info = images_info[idx]
        image_uuid = str(uuid.uuid4())
        
        # Process the image with EasyOCR
        img_bytes = base64.b64decode(img_info['base64'])
        
        # Perform OCR on the processed image
        ocr_results = extract_text_from_image_with_textract(img_bytes)
        
        # Only process if there are detected elements
        if ocr_results:
            # Create the context and metadata
            context_data = self.create_image_context(image_uuid, page_index, img_info)
            metadata = self.create_image_metadata(image_uuid, page_index, img_info)
            
            # Process OCR results
            self.process_ocr_results(ocr_results, img_info, context_data)
            
            # Upload files to S3
            image_filename = await self.upload_image_to_s3(image_uuid, img_info)
            s3_uri_context = await self.upload_context_to_s3(image_uuid, context_data)
            s3_uri_metadata = await self.upload_metadata_to_s3(image_uuid, metadata)

            if not self.block_chatbot_material:
                # Create the material
                await self.create_chatbot_material(self.db, {
                    "chatbot_id": self.chatbot_data.id,
                    "title": s3_uri_context["filename"],
                    "type": "application/json",
                    "s3_uri": s3_uri_context["s3_uri"],
                    "status": "SUCCESS",
                    "is_main": False
                })

                # Create the metadata for the material
                await self.create_chatbot_material(self.db, {
                    "chatbot_id": self.chatbot_data.id,
                    "title": s3_uri_metadata["filename"],
                    "type": "application/json",
                    "s3_uri": s3_uri_metadata["s3_uri"],
                    "status": "SUCCESS",
                    "is_main": False
                })

            # Add to the context and metadata lists
            self.image_uuid_context.append(context_data)
            self.image_uuid_context_metadata.append(metadata)
            
            # Add to markdown
            self.add_image_to_markdown(idx, image_filename, image_uuid, page_index, img_info, context_data)
        else:
            print(f"Warning: No elements detected in image {image_uuid}, skipping processing")
            
    async def process_document(self):
        """Process the complete PDF document"""
        try:
            self.image_uuid_context = []
            self.image_uuid_context_metadata = []
            await self.save_temp_file()
            try:
                doc = self.open_pdf_document()
            except ValueError as ve:
                # Clean the temporary file before propagating the error
                if os.path.exists(self.temp_file):
                    os.remove(self.temp_file)
                raise ve
            
            # Extract all images first
            images_info = await self.extract_images_from_pdf()
            xref_to_index = self.create_xref_to_index_mapping(images_info)
            
            # Process each page
            for page_index in range(len(doc)):
                page = doc[page_index]
                await self.process_page(page, page_index, images_info, xref_to_index, doc)
                
            # Save data to S3
            await self.save_data_to_s3()
                
        except Exception as e:
            print(f"Error processing the PDF: {str(e)}")
            raise
        finally:
            # Clean the temporary file
            if os.path.exists(self.temp_file):
                os.remove(self.temp_file)
                
        return {
            "chatbot_name": self.chatbot_data.name,
            "markdown_content": self.data["markdown_content"]
        }

    async def process_and_upload_to_s3(self, s3_path: str, metadata: dict = None, properties_order: list = None):
        """
        Procesa el PDF y lo sube a S3 sin realizar operaciones en la base de datos.
        
        Args:
            s3_path (str): Ruta en S3 donde se guardará el archivo procesado
            metadata (dict): Metadatos adicionales para el archivo procesado, se guardará con el nombre [file_temporary_path].metadata.json.
            Estos metadatos se guardarán en la misma carpeta para que AWS Bedrock pueda acceder a ellos.
        
        Returns:
            dict: Información sobre el archivo procesado y su ubicación en S3
        """
        try:
            # Guardar archivo temporal
            await self.save_temp_file()
            
            # Abrir documento PDF
            doc = self.open_pdf_document()
            
            # Extract images
            images_info = await self.extract_images_from_pdf()
            xref_to_index = self.create_xref_to_index_mapping(images_info)
            
            # Process each page
            for page_index in range(len(doc)):
                page = doc[page_index]
                await self.process_page(page, page_index, images_info, xref_to_index, doc)
            
            # Convert markdown content to JSON
            processed_data = {
                "chatbot_name": self.chatbot_data.name,
                "markdown_content": self.data["markdown_content"]
            }
            
            file_temporary_path = f"{self.material_uuid}.md"
            file_temporary_path_metadata = f"{file_temporary_path}.metadata.json"
            if metadata:
                metadata_content = json.dumps({
                    "metadataAttributes": metadata
                })
                with open(file_temporary_path_metadata, "w") as f:
                    f.write(metadata_content)
            with open(file_temporary_path, "w", encoding='utf-8') as f:
                f.write(json.dumps(self.data["markdown_content"], ensure_ascii=False))
            
            # Upload both files to S3
            s3_uri = await upload_file_to_s3('content', file_temporary_path, f"{s3_path}/{file_temporary_path}")
            s3_uri_metadata = await upload_file_to_s3('content', file_temporary_path_metadata, f"{s3_path}/{file_temporary_path_metadata}")
            
            # Clean temporary file
            os.remove(file_temporary_path)
            os.remove(file_temporary_path_metadata)
            
            return {
                "status": "success",
                "s3_uri": s3_uri,
                "s3_uri_metadata": s3_uri_metadata,
                "s3_path": s3_path,
                "processed_data": processed_data
            }
            
        except Exception as e:
            return {
                "status": "error",
                "error": str(e)
            }
        finally:
            # Clean temporary PDF file
            if os.path.exists(self.temp_file):
                os.remove(self.temp_file) 