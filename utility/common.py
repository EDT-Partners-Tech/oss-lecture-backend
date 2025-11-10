# © [2025] EDT&Partners. Licensed under CC BY 4.0.

import json
import secrets
import string
from uuid import UUID
import fitz
import re
import aiofiles
import tempfile
import os
import filetype
import asyncio
import aiohttp
import ebooklib
import pandas as pd
from pathlib import Path
from typing import Dict, Optional, Final, List
from urllib.parse import urlparse
from docx import Document
from icecream import ic
from ebooklib import epub
from bs4 import BeautifulSoup
from fastapi import HTTPException, UploadFile
from io import BytesIO
from docx import Document
from requests import Session
from database.crud import get_material
from utility.aws import extract_text_from_image, get_s3_object, upload_to_s3
from .exceptions import DocxExtractionError, FileValidationError, FileExtractionError, PdfExtractionError, TxtExtractionError
from constants import DOCX_EXTENSION, PDF_EXTENSION, TXT_EXTENSION
from logging_config import setup_logging

# Constants
MAX_FILE_SIZE: Final[int] = 10 * 1024 * 1024  # 10MB
ALLOWED_EXTENSIONS: Final[set] = {PDF_EXTENSION, DOCX_EXTENSION, TXT_EXTENSION}
ALLOWED_MIME_TYPES: Final[dict] = {
    PDF_EXTENSION: 'application/pdf',
    TXT_EXTENSION: 'text/plain',
    DOCX_EXTENSION: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
    '.mp3': 'audio/mpeg',
    '.wav': 'audio/wav',
    '.ogg': 'audio/ogg',
    '.mp4': 'video/mp4',
    '.mpeg': 'video/mpeg',
    '.webm': 'video/webm',
    '.xlsx': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    '.xls': 'application/vnd.ms-excel',
    '.doc': 'application/msword',
}
REQUEST_RATE_LIMIT: Final[int] = 30  # requests
REQUEST_RATE_PERIOD: Final[int] = 60  # seconds
REQUEST_TIMEOUT: Final[int] = 10  # seconds
MAX_CHUNK_SIZE: Final[int] = 10000  # bytes

# Configure logging
logger = setup_logging()

def validate_file_type(file_data: bytes, suffix: str) -> bool:
    """Validate file type using file signatures."""
    try:
        kind = filetype.guess(file_data)
        if not kind:
            logger.warning("Could not determine file type")
            return False
            
        file_mime = kind.mime
        expected_mime = ALLOWED_MIME_TYPES.get(suffix.lower())
        
        # Special case for audio/video files
        if suffix.lower() in ['.mp3', '.wav', '.ogg']:
            return file_mime.startswith('audio/')
        elif suffix.lower() in ['.mp4', '.mpeg', '.webm']:
            return file_mime.startswith('video/')
        
        if not expected_mime or file_mime != expected_mime:
            logger.warning(f"Invalid file type: expected {expected_mime}, got {file_mime}")
            return False
        return True
    except Exception as e:
        logger.error(f"File type validation error: {str(e)}")
        return False

async def extract_text_from_data(file: UploadFile, block_mimetype_verification: bool = False, block_size_verification: bool = False) -> Optional[str]:
    """
    Extract text from an uploaded file with security checks.
    """
    try:
        safe_filename = Path(os.path.basename(file.filename)).name
        suffix = Path(safe_filename).suffix.lower()
        
        if suffix not in ALLOWED_EXTENSIONS:
            logger.warning(f"Unsupported file format: {suffix}")
            raise HTTPException(status_code=400, detail=f"Unsupported file format: {suffix}")

        # Check file size
        if file.size > MAX_FILE_SIZE and not block_size_verification:
            logger.warning(f"File too large: {file.size / (1024 * 1024):.2f} MB. Max size is {MAX_FILE_SIZE / (1024 * 1024):.2f} MB.")
            raise HTTPException(status_code=400, detail=f"File too large: {file.size / (1024 * 1024):.2f} MB. Max size is {MAX_FILE_SIZE / (1024 * 1024):.2f} MB.")

        file_data = await file.read()

        # Validate file type
        if not validate_file_type(file_data, suffix) and not block_mimetype_verification:
            logger.warning(f"Invalid file type: {suffix}")
            raise HTTPException(status_code=400, detail="Invalid file type")

        with tempfile.NamedTemporaryFile(delete=True, suffix=suffix) as tmp:
            tmp.write(file_data)
            tmp.flush()
            return await extract_text_from_file(tmp.name)

    except Exception as e:
        logger.error(f"Error processing file {safe_filename}: {str(e)}")
        raise e

async def save_uploaded_file(file_data: bytes, file_name: str) -> str:
    """
    Safely save an uploaded file to a temporary location.
    
    Args:
        file_data (bytes): The file content
        file_name (str): Original filename
        
    Returns:
        str: Path to the temporary file
    """
    # Sanitize filename
    safe_filename = os.path.basename(file_name)
    suffix = Path(safe_filename).suffix.lower()
    
    # Add size check
    if len(file_data) > MAX_FILE_SIZE:
        raise ValueError("File too large")
        
    # Validate file type
    if not validate_file_type(file_data, suffix):
        raise ValueError("File type does not match extension")
    
    with tempfile.NamedTemporaryFile(delete=True, suffix=suffix) as tmp_file:
        async with aiofiles.open(tmp_file.name, 'wb') as f:
            await f.write(file_data)
        return tmp_file.name

async def extract_text_from_file(file_path: str) -> Optional[str]:
    """
    Extract text from various file formats (PDF, DOCX, TXT) asynchronously.
    """
    try:
        file_path = Path(file_path)
        if not file_path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        if file_path.suffix.lower() == PDF_EXTENSION:
            return await extract_text_from_pdf(str(file_path))
        elif file_path.suffix.lower() == DOCX_EXTENSION:
            return await extract_text_from_docx(str(file_path))
        elif file_path.suffix.lower() == TXT_EXTENSION:
            return await extract_text_from_txt(str(file_path))
        else:
            raise ValueError(f"Unsupported file format: {file_path.suffix}")
            
    except Exception as e:
        logger.error(f"Error extracting text from {file_path}: {str(e)}")
        raise FileExtractionError(f"Failed to extract text from file: {str(e)}")

async def extract_text_from_pdf(pdf_path: str) -> str:
    """
    Extract text content from a PDF file asynchronously.
    """
    try:
        # Run PDF processing in a thread pool to avoid blocking
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, _sync_extract_pdf, pdf_path)
    except Exception as e:
        raise PdfExtractionError(e)

def _sync_extract_pdf(pdf_path: str) -> str:
    """Synchronous PDF extraction to run in thread pool"""
    doc = fitz.open(pdf_path)
    text = ""
    for page_num in range(len(doc)):
        page = doc.load_page(page_num)
        text += page.get_text()
    doc.close()
    return text

async def extract_text_from_docx(docx_path: str) -> str:
    """
    Extract text content from a DOCX file asynchronously.
    """
    try:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, _sync_extract_docx, docx_path)
    except Exception as e:
        raise DocxExtractionError(e)

def _sync_extract_docx(docx_path: str) -> str:
    """Synchronous DOCX extraction to run in thread pool"""
    doc = Document(docx_path)
    text = []
    for paragraph in doc.paragraphs:
        text.append(paragraph.text)
    return '\n'.join(text)

async def extract_text_from_txt(txt_path: str) -> str:
    """
    Extract text content from a TXT file asynchronously.
    """
    try:
        async with aiofiles.open(txt_path, 'r', encoding='utf-8') as file:
            return await file.read()
    except Exception as e:
        raise TxtExtractionError(e)
    
async def extract_text_from_epub(epub_path: str) -> str:
    loop = asyncio.get_event_loop()
    book = await loop.run_in_executor(None, epub.read_epub, epub_path)

    text_content = []

    for item in book.get_items_of_type(ebooklib.ITEM_DOCUMENT):
        content = await loop.run_in_executor(None, item.get_content)
        soup = BeautifulSoup(content, 'html.parser')
        extracted_text = soup.get_text()

        cleaned_text = re.sub(r'\n+', '\n', extracted_text).strip()

        text_content.append(cleaned_text)

    return "\n\n".join(text_content)

async def process_epub_file(file_path: str, course_id: UUID, safe_filename: str) -> str:
    """Handles EPUB file processing: extracting text and uploading to S3."""
    ic("Processing EPUB file")
    
    try:
        extracted_text = await extract_text_from_epub(file_path)
        
        # Save extracted text as a temporary file
        processed_filename = f"processed_{safe_filename}.txt"
        with tempfile.NamedTemporaryFile(delete=False, suffix=".txt") as processed_tmp_file:
            processed_tmp_file.write(extracted_text.encode("utf-8"))
            processed_temp_path = processed_tmp_file.name
        
        ic("Processed text saved", processed_temp_path)

        # Upload processed text file to S3
        transcription_s3_uri = upload_to_s3('content', processed_temp_path, f"materials/{course_id}/{processed_filename}")
        ic("Processed file uploaded to S3", transcription_s3_uri)

        os.unlink(processed_temp_path)  # Cleanup processed file
        return transcription_s3_uri

    except Exception as e:
        ic("Error extracting text from EPUB", e)
        raise HTTPException(status_code=400, detail=f"Failed to process EPUB: {str(e)}")



async def extract_text_from_url(url: str) -> str:
    """
    Extract text from URL asynchronously with rate limiting and security checks.
    """
    try:
        parsed = urlparse(url)
        if not all([parsed.scheme, parsed.netloc]):
            raise ValueError("Invalid URL")

        # Use aiohttp instead of requests for async HTTP requests
        async with aiohttp.ClientSession() as session:
            async with session.get(
                url,
                timeout=REQUEST_TIMEOUT,
                headers={'User-Agent': 'Mozilla/5.0'},
                ssl=True
            ) as response:
                content = await response.read()
                
                if len(content) > MAX_FILE_SIZE:
                    raise ValueError("Response too large")

                # Run BeautifulSoup parsing in thread pool
                loop = asyncio.get_event_loop()
                return await loop.run_in_executor(None, _parse_html_content, content)

    except Exception as e:
        logger.error(f"URL processing error: {str(e)}")
        raise

def _parse_html_content(content: bytes) -> str:
    """Synchronous HTML parsing to run in thread pool"""
    soup = BeautifulSoup(content, 'html.parser')
    paragraphs = soup.find_all('p')
    return ' '.join(para.get_text() for para in paragraphs)

def get_selected_text(text, start, end):
    """ Get selected text from a given range """
    if start is not None and end is not None:
        return text[start - 1:end - 1]
    return None

async def process_uploaded_files(files: list[UploadFile], with_formatting: bool = False, use_xml_format: bool = False) -> Optional[str]:
    """Process uploaded files and return combined text."""
    if not files:
        return None
    
    try:
        combined_text = ""
        for file in files:
            text = await process_and_extract_text(file, with_formatting)
            if use_xml_format:
                combined_text += f'''
                <RESOURCE>
                    <RESOURCE_TITLE>{file.filename}</RESOURCE_TITLE>
                    <RESOURCE_CONTENT>{text}</RESOURCE_CONTENT>
                </RESOURCE>
                '''
            else:
                combined_text += text + "\n\n"
        return combined_text.strip()
    except FileValidationError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except FileExtractionError as e:
        raise HTTPException(status_code=500, detail=str(e))


def generate_temporary_password(length: int = 12) -> str:
    """
    Generate a secure temporary password with entropy validation.
    """
    if not 8 <= length <= 128:
        raise ValueError("Password length must be between 8 and 128")
    
    password = [
        secrets.choice(string.ascii_lowercase),
        secrets.choice(string.ascii_uppercase),
        secrets.choice(string.digits),
        secrets.choice(string.punctuation)
    ]
    
    remaining_length = length - 4
    alphabet = string.ascii_letters + string.digits + string.punctuation
    password += [secrets.choice(alphabet) for _ in range(remaining_length)]

    # Use secrets.token_bytes() to generate random indices for shuffling
    for i in range(len(password)-1, 0, -1):
        # Generate a secure random index
        j = int.from_bytes(secrets.token_bytes(4), 'big') % (i + 1)
        password[i], password[j] = password[j], password[i]
    
    return ''.join(password)

def clean_document_for_prompt(text):
    """
    Clean up exam guide text by removing line numbers, fixing formatting,
    and standardizing bullet points.
    
    Args:
        text (str): Raw input text
    
    Returns:
        str: Cleaned text with consistent formatting
    """
    lines = [line.strip() for line in text.split('\n') if line.strip()]
    cleaned_lines = []
    current_section = ""
    
    for line in lines:
        if line.isdigit():
            continue
        line = clean_line(line)
        current_section, cleaned_line = handle_section_headers(line, current_section)
        cleaned_lines.append(cleaned_line)
    
    cleaned_text = join_and_clean_lines(cleaned_lines)
    return cleaned_text.strip()

def clean_line(line: str) -> str:
    """
    Clean a single line of text by removing numbers and standardizing bullet points.
    
    Args:
        line (str): Input line to clean
        
    Returns:
        str: Cleaned line with standardized formatting
    """
    if line[0].isdigit() and '. ' in line[:3]:
        line = line[line.index('.')+1:].strip()
    line = line.replace('•', '-').replace('∗', '-').replace('–', '-')
    while '- -' in line:
        line = line.replace('- -', '-')
    return line.strip('- ')

def handle_section_headers(line: str, current_section: str) -> tuple[str, str]:
    """
    Process and format section headers in the text.
    
    Args:
        line (str): Current line to process
        current_section (str): Name of the current section
        
    Returns:
        tuple[str, str]: Updated current section and processed line
    """
    if line.isupper() or line.endswith(':'):
        current_section = line.title()
        if not line.endswith(':'):
            current_section += ':'
        return current_section, '\n' + current_section
    else:
        if line.startswith('-'):
            line = '  ' + line
        return current_section, line

def join_and_clean_lines(cleaned_lines: list) -> str:
    """
    Join multiple lines and clean up excessive newlines.
    
    Args:
        cleaned_lines (list): List of text lines to join
        
    Returns:
        str: Joined and cleaned text with normalized spacing
    """
    cleaned_text = '\n'.join(cleaned_lines)
    while '\n\n\n' in cleaned_text:
        cleaned_text = cleaned_text.replace('\n\n\n', '\n\n')
    return cleaned_text

def replace_selected_text(original_text: str, start_index: int, end_index: int, replacement_text: str) -> str:
    """
    Replace a portion of text with new text based on start and end indices.
    
    Args:
        original_text (str): The original text to modify
        start_index (int): Starting index of the text to replace
        end_index (int): Ending index of the text to replace
        replacement_text (str): New text to insert
        
    Returns:
        str: Modified text with the replacement
    """
    return original_text[:start_index] + replacement_text + original_text[end_index:]

def clean_raw_data(raw_data: str) -> list:
    """
    Clean and parse raw data with input validation.
    """
    if not raw_data or len(raw_data) > MAX_FILE_SIZE:
        raise ValueError("Invalid input data size")
        
    # Step 1: Remove excessive whitespace and newlines
    cleaned_data = raw_data.strip()

    # Step 2: Extract JSON-like structures by splitting the text and identifying JSON objects
    json_objects = re.findall(r"\{[^\}]*\}", cleaned_data, re.DOTALL)

    # Step 3: Parse each JSON object to ensure validity
    parsed_objects = []
    for obj in json_objects:
        try:
            parsed_objects.append(json.loads(obj))
        except json.JSONDecodeError as e:
            raise ValueError(f"Error parsing JSON object: {obj}. Error: {e}")

    return parsed_objects

def parse_failure_reasons(failure_reasons: str) -> list:
    """
    Parse and format error messages from failure reasons.
    
    Args:
        failure_reasons (str): JSON string or list containing error messages
        
    Returns:
        list: List of dictionaries containing formatted error messages with
              associated files
    """
    errors = []

    if isinstance(failure_reasons, list):
        reasons = failure_reasons
    else:
        reasons = json.loads(failure_reasons)

    for reason in reasons:
        error_blocks = re.split(r'Encountered error:\s*', reason)
        
        for block in error_blocks:
            if not block.strip(): 
                continue
            
            error_message = block.split("[Files:")[0].strip()
            error_message = re.sub(r"Ignored \d+ ", "Ignored ", error_message)
            error_message = re.sub(r"\bfiles\b", "file", error_message, flags=re.IGNORECASE)
            error_message = re.sub(r"\btheir\b", "its", error_message, flags=re.IGNORECASE)

            file_uris_match = re.search(r"\[Files:\s*([^\]]+)\]", block)
            if file_uris_match:
                file_uris = file_uris_match.group(1).split(", ")
                for file_uri in file_uris:
                    errors.append({"file": file_uri.strip(), "error": error_message})
        ic(errors)
    return errors

def process_pdf_span(span, page_num):
    """Helper function to process individual text spans from PDF"""
    text = span["text"].strip()
    if not text:
        return None
    font_size = span.get("size", "N/A")
    is_bold = "bold" in span.get("font", "").lower()
    return f"Page {page_num}: '{text}' [Font size: {font_size}, Bold: {is_bold}]"

def _process_page_blocks(blocks: list, page_num: int) -> list:
    """Process blocks from a PDF page and extract formatted content"""
    page_content = []
    for block in blocks:
        if "lines" in block:
            for line in block["lines"]:
                for span in line["spans"]:
                    content_line = process_pdf_span(span, page_num)
                    if content_line:
                        page_content.append(content_line)
    return page_content

def _clean_formatted_text(text: str) -> str:
    """
    Clean formatted text by removing page numbers, formatting info, and special characters.
    
    Args:
        text (str): Text with formatting information
        
    Returns:
        str: Clean text without formatting
    """
    # Remove page number and formatting patterns
    text = re.sub(r"Page \d+: '", "", text)
    text = re.sub(r"' \[Font size: [\d.]+, Bold: (?:True|False)\]", "", text)
    
    # Remove special characters but keep spaces and basic punctuation
    text = re.sub(r'[©®™\[\]{}()<>]', '', text)
    
    # Remove multiple spaces and trim
    text = re.sub(r'\s+', ' ', text)
    return text.strip()

def _process_pdf_with_formatting(file_path: str, with_formatting: bool) -> list:
    """
    Process PDF document with optional formatting details synchronously
    
    Args:
        file_path (str): Path to the PDF file
        with_formatting (bool): If True, includes formatting details like font size and bold
        
    Returns:
        list: List of extracted text lines, with or without formatting information
    """
    extracted_content = []
    doc = fitz.open(file_path)
    try:
        if with_formatting:
            for page_num, page in enumerate(doc, start=1):
                blocks = page.get_text("dict")["blocks"]
                extracted_content.extend(_process_page_blocks(blocks, page_num))
        else:
            for page in doc:
                extracted_content.append(page.get_text().strip())
        return extracted_content
    finally:
        doc.close()

def _extract_text_from_excel(file_path: str) -> str:
    """Extract text from Excel files (.xlsx, .xls)"""
    try:
        # Try pandas first for better handling of both .xls and .xlsx
        df = pd.read_excel(file_path, sheet_name=None)
        text_parts = []
        
        for sheet_name, sheet_df in df.items():
            text_parts.append(f"Sheet: {sheet_name}")
            # Convert headers to string
            headers = [str(col) for col in sheet_df.columns]
            text_parts.append("Headers: " + ", ".join(headers))
            
            # Convert all cell values to string and join
            for _, row in sheet_df.iterrows():
                row_text = " | ".join(str(cell) for cell in row)
                text_parts.append(row_text)
                
        return "\n".join(text_parts)
    except Exception as e:
        logger.error(f"Error extracting text from Excel: {str(e)}")
        raise FileExtractionError(f"Failed to extract text from Excel file: {str(e)}")

def _extract_text_from_doc(file_path: str) -> str:
    """Extract text from legacy .doc files"""
    try:
        # Use antiword for .doc files if available
        if os.system("which antiword > /dev/null") == 0:
            result = os.popen(f'antiword "{file_path}"').read()
            return result
        else:
            raise FileExtractionError("antiword not installed. Cannot process .doc files")
    except Exception as e:
        logger.error(f"Error extracting text from DOC: {str(e)}")
        raise FileExtractionError(f"Failed to extract text from DOC file: {str(e)}")

async def process_and_extract_text(file: UploadFile, with_formatting: bool) -> str:
    """Process uploaded file and extract text content with proper error handling."""
    try:
        print("Processing uploaded file...")
        content_type = file.content_type
        
        # Read file content once
        content = await file.read()
        if not content:
            raise FileValidationError("Empty file received")

        suffix = Path(file.filename).suffix.lower()
        
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp_file:
            tmp_file.write(content)
            tmp_file.flush()
            
            try:
                if content_type == 'application/pdf':
                    # Process PDF directly from the temporary file
                    loop = asyncio.get_event_loop()
                    extracted_content = await loop.run_in_executor(
                        None,
                        _process_pdf_with_formatting,
                        tmp_file.name,
                        with_formatting
                    )
                    source_text = "\n".join(extracted_content)
                elif content_type.startswith('image/'):
                    image_bytes = BytesIO(content)
                    source_text = extract_text_from_image(image_bytes)
                elif content_type in ['application/vnd.ms-excel', 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet']:
                    loop = asyncio.get_event_loop()
                    source_text = await loop.run_in_executor(None, _extract_text_from_excel, tmp_file.name)
                elif content_type == 'application/msword':
                    loop = asyncio.get_event_loop()
                    source_text = await loop.run_in_executor(None, _extract_text_from_doc, tmp_file.name)
                elif content_type == 'application/vnd.openxmlformats-officedocument.wordprocessingml.document':
                    source_text = await extract_text_from_docx(tmp_file.name)
                else:
                    raise FileValidationError("Unsupported file type. Supported types: PDF, images, Excel, DOC, and DOCX")
            finally:
                # Clean up the temporary file
                os.unlink(tmp_file.name)
            
        print(f"Successfully extracted text of length: {len(source_text)}")
        return source_text
    except FileValidationError as e:
        raise FileValidationError(str(e))
    except Exception as e:
        logger.error(f"Error processing file: {str(e)}")
        raise FileExtractionError(f"Failed to extract text from file: {str(e)}")

def split_text_into_chunks(text: str) -> list[str]:
    """
    Split text into chunks of maximum 10000 bytes.

    Args:
        text (str): The text to split.

    Returns:
        list[str]: A list of text chunks.
    """
    max_chunk_size = MAX_CHUNK_SIZE

    if len(text.encode('utf-8')) < max_chunk_size:
        return [text]

    lines = text.split('.')
    chunks = []
    current_chunk = ""

    for line in lines:
        line_bytes = len(line.encode('utf-8'))
        if len(current_chunk.encode('utf-8')) + line_bytes + 1 < max_chunk_size:
            if current_chunk:
                current_chunk += line
            else:
                current_chunk = line
        else:
            chunks.append(current_chunk)
            current_chunk = line

    if current_chunk:
        chunks.append(current_chunk)

    return chunks

def is_valid_file_format_for_translation(file: UploadFile, allowed_extensions = ALLOWED_EXTENSIONS) -> bool:
    """Check if the uploaded file is a supported format for AWS Translation."""
    try:
        suffix = Path(file.filename).suffix.lower()
        if suffix not in allowed_extensions:
            raise FileValidationError("Unsupported file format. Supported formats: PDF, DOCX, TXT")
        return True
    except FileValidationError:
        return False

async def get_text_from_material_id(db: Session, material_id: list[str]) -> str:
    """
    Extract text from a list of material IDs.
    
    Args:
        db (Session): Database session
        material_id (list[str]): List of material IDs
        
    Returns:
        str: Combined text from all materials
    """
    combined_text = ""
    for id in material_id:
        # Assuming get_material_text is a function that retrieves text based on ID
        material = get_material(db, id)

        # Get data from material
        material_s3_uri = material.s3_uri
        material_type = material.type
        material_title = material.title

        # Get S3 objet using get_s3_object
        s3_object = await get_s3_object(material_s3_uri)

        try:
            # Convert S3 object to UploadFile
            file = UploadFile(
                file=BytesIO(s3_object["Body"].read()),
                filename=material_title,
                size=len(s3_object),
                headers={"Content-Type": material_type}
            )
        except Exception as e:
            logger.error(f"Error converting S3 object to file: {str(e)}")
        
        # Extract text from the file
        extracted_text = await extract_text_from_data(file)
        if extracted_text:
            combined_text += f'''
            <RESOURCE>
                <RESOURCE_TITLE>{material_title}</RESOURCE_TITLE>
                <RESOURCE_CONTENT>{extracted_text}</RESOURCE_CONTENT>
            </RESOURCE>
            '''
        else:
            logger.warning(f"No text extracted from material ID: {id}")
    
    # Clean up the combined text
    return combined_text.strip()

LANGUAGE_CODE_MAPPING = {
    "chinese": "zh",
    "chinese (simplified)": "zh",
    "chinese (traditional)": "zh",
    "czech": "cs",
    "danish": "da",
    "dutch": "nl",
    "finnish": "fi",
    "french": "fr",
    "german": "de",
    "greek": "el",
    "hebrew": "he",
    "hindi": "hi",
    "hungarian": "hu",
    "italian": "it",
    "japanese": "ja",
    "korean": "ko",
    "norwegian": "no",
    "polish": "pl",
    "portuguese": "pt",
    "russian": "ru",
    "spanish": "es",
    "swedish": "sv",
    "turkish": "tr",
    "arabic": "ar",
    "indonesian": "id",
    "english": "en",
    "thai": "th",
    "vietnamese": "vi",
    "malay": "ms",
    "filipino": "fil",
    "urdu": "ur"
}

def convert_large_language_to_code(lang: str) -> str:
    """Convert language name to language code for large language models."""
    return LANGUAGE_CODE_MAPPING.get(lang.lower(), lang.lower())
def model_to_dict(model, drop_keys: List[str] = []) -> dict:
    data = {column.name: getattr(model, column.name) for column in model.__table__.columns}
    if drop_keys:
        for key in drop_keys:
            data.pop(key, None)
    return data

def convert_to_gift(questions: List[Dict]) -> str:
    """
    Converts a list of questions into GIFT format.
    Args:
        questions (List[Dict]): List of question dictionaries. Each question should have 
                                'type', 'question', 'options', and 'correct_answer' keys.
    Returns:
        str: GIFT formatted string.
    """
    gift_questions = []

    for index, question in enumerate(questions):
        gift_question = f"::Question {index + 1}:: {question.get('question')} {{"

        if question.get("type") == "mcq":
            gift_question += "\n"
            options = question.get("options", [])
            if options:
                answers = [
                    f"{'=' if question.get('correct_answer') == option else '~'}{option}"
                    for option in options
                ]
                gift_question += "\n".join(answers) + "\n}"
            else:
                gift_question += "Invalid question (no options provided)\n}"

        elif question.get("type") == "tf":
            correct = "T" if question.get("correct_answer", "").strip().lower() == "true" else "F"
            gift_question += f"{correct}}}\n"

        elif question.get("type") == "open":
            gift_question += "}\n"

        gift_questions.append(gift_question)

    return "\n\n".join(gift_questions)