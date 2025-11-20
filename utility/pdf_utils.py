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

import os
import base64
import fitz
from fastapi import UploadFile, File
from utility.aws import textract_client

# Extract images from pdf
async def extract_images_from_pdf(file: UploadFile = File(...)) -> list:
    print("Extracting images from pdf")
    nombre_documento = file.filename
    temp_file = "temp2.pdf"
    lista_imagenes = []
    
    try:
        # Save the file in a temporary file
        with open(temp_file, "wb") as f:
            f.write(file.file.read())
            
        doc = fitz.open(temp_file)

        # Iterate through each page of the document
        for page_index in range(len(doc)):
            page = doc[page_index]
            
            # Get all the images of the page
            images = page.get_images()
            
            # Process each image found
            for img_index, img in enumerate(images):
                try:
                    # img is a tuple with (xref, smask, width, height, bpc, colorspace, ...)
                    xref = img[0]
                    
                    # Extract the image
                    image_info = doc.extract_image(xref)
                    if not image_info or "image" not in image_info:
                        print(f"Warning: No se pudo extraer la imagen con xref {xref}")
                        continue
                        
                    image_bytes = image_info["image"]
                    # Convert the image to base64
                    image_b64 = base64.b64encode(image_bytes).decode('utf-8')
                    
                    # Get the image metadata
                    width = img[2]
                    height = img[3]
                    bpc = img[4]
                    colorspace = img[5]
                    ext = image_info.get("ext", "png")
                    
                    # Get the image location in the page
                    rects = page.get_image_rects(xref)
                    bbox = rects[0] if rects else None
                    
                    # Get the text that surrounds the image
                    context_text = ""
                    if bbox:
                        # Expand the search area to include more context
                        search_area = fitz.Rect(
                            bbox.x0 - 50,
                            bbox.y0 - 20,
                            bbox.x1 + 50,
                            bbox.y1 + 20 
                        )
                        context_text = page.get_text("text", clip=search_area)
                    
                    # Get the image name
                    image_name = f"image_{img_index}.{ext}"

                    # Add the information to the list
                    lista_imagenes.append({
                        "document_name": nombre_documento,
                        "page_number": page_index + 1,
                        "image_index": img_index,
                        "xref": xref,
                        "bbox": bbox,
                        "width": width,
                        "height": height,
                        "bpc": bpc,
                        "colorspace": colorspace,
                        "extension": ext,
                        "base64": image_b64,
                        "context_text": context_text,
                        "image_name": image_name
                    })
                    
                except ValueError as e:
                    print(f"Warning: Error extracting image with xref {xref}: {str(e)}")
                    continue
                except Exception as e:
                    print(f"Warning: Unexpected error processing image with xref {xref}: {str(e)}")
                    continue
                    
    except Exception as e:
        print(f"Error processing the PDF: {str(e)}")
        raise
    finally:
        # Clean the temporary file
        if os.path.exists(temp_file):
            os.remove(temp_file)
    
    return lista_imagenes


# Extract text from image with AWS Textract
def extract_text_from_image_with_textract(img_bytes: bytes) -> list:
    response = textract_client.detect_document_text(
        Document={'Bytes': img_bytes}
    )

    # Return directly the blocks of type LINE from the Textract response
    blocks_with_text = []
    for item in response['Blocks']:
        if item['BlockType'] == 'LINE':
            blocks_with_text.append(item)
    return blocks_with_text 