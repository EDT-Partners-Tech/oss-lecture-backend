# © [2025] EDT&Partners. Licensed under CC BY 4.0.

import os
import string
import pytest
import tempfile
import re
from unittest.mock import patch, MagicMock, AsyncMock
from fastapi import UploadFile, HTTPException

from utility.common import (
    validate_file_type, 
    extract_text_from_data,
    save_uploaded_file,
    extract_text_from_file,
    extract_text_from_pdf,
    extract_text_from_docx,
    extract_text_from_txt,
    extract_text_from_epub,
    extract_text_from_url,
    get_selected_text,
    process_uploaded_files,
    generate_temporary_password,
    clean_document_for_prompt,
    clean_line,
    handle_section_headers,
    join_and_clean_lines,
    replace_selected_text,
    clean_raw_data,
    parse_failure_reasons,
    process_pdf_span,
    _clean_formatted_text,
    _process_pdf_with_formatting,
    _extract_text_from_excel,
    _extract_text_from_doc,
    process_and_extract_text,
    MAX_FILE_SIZE,
)
from utility.exceptions import FileValidationError, FileExtractionError, PdfExtractionError, TxtExtractionError

# Fixtures
@pytest.fixture
def sample_pdf_bytes():
    """Create sample PDF bytes for testing."""
    return b"%PDF-1.5\nSample PDF content"

@pytest.fixture
def sample_docx_bytes():
    """Create sample DOCX bytes for testing."""
    return b"PK\x03\x04\x14\x00\x06\x00Sample DOCX content"

@pytest.fixture
def sample_txt_bytes():
    """Create sample TXT bytes for testing."""
    return b"Sample TXT content"

@pytest.fixture
def sample_epub_bytes():
    """Create sample EPUB bytes for testing."""
    return b"PK\x03\x04\x14\x00\x00\x00\x00\x00Sample EPUB content"

@pytest.fixture
def mock_upload_file():
    """Create a mock UploadFile for testing."""
    file = MagicMock(spec=UploadFile)
    file.filename = "test.pdf"
    file.size = 1000
    file.file = MagicMock()
    return file

@pytest.fixture
def temp_pdf_file():
    """Create a temporary PDF file for testing."""
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
        f.write(b"%PDF-1.5\nSample PDF content")
        temp_path = f.name
    yield temp_path
    if os.path.exists(temp_path):
        os.unlink(temp_path)

@pytest.fixture
def temp_docx_file():
    """Create a temporary DOCX file for testing."""
    with tempfile.NamedTemporaryFile(suffix=".docx", delete=False) as f:
        f.write(b"PK\x03\x04\x14\x00\x06\x00Sample DOCX content")
        temp_path = f.name
    yield temp_path
    if os.path.exists(temp_path):
        os.unlink(temp_path)

@pytest.fixture
def temp_txt_file():
    """Create a temporary TXT file for testing."""
    with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as f:
        f.write(b"Sample TXT content")
        temp_path = f.name
    yield temp_path
    if os.path.exists(temp_path):
        os.unlink(temp_path)


# Tests for validate_file_type
class TestValidateFileType:
    def test_valid_pdf(self, sample_pdf_bytes):
        with patch('filetype.guess') as mock_guess:
            mock_type = MagicMock()
            mock_type.mime = 'application/pdf'
            mock_guess.return_value = mock_type
            assert validate_file_type(sample_pdf_bytes, '.pdf') == True

    def test_invalid_pdf(self, sample_pdf_bytes):
        with patch('filetype.guess') as mock_guess:
            mock_type = MagicMock()
            mock_type.mime = 'text/plain'  # Wrong MIME type
            mock_guess.return_value = mock_type
            assert validate_file_type(sample_pdf_bytes, '.pdf') == False

    def test_no_file_type_detected(self):
        with patch('filetype.guess') as mock_guess:
            mock_guess.return_value = None
            assert validate_file_type(b"xyz", '.pdf') == False

    def test_audio_file_type(self):
        with patch('filetype.guess') as mock_guess:
            mock_type = MagicMock()
            mock_type.mime = 'audio/mp3'
            mock_guess.return_value = mock_type
            assert validate_file_type(b"audio_data", '.mp3') == True

    def test_video_file_type(self):
        with patch('filetype.guess') as mock_guess:
            mock_type = MagicMock()
            mock_type.mime = 'video/mp4'
            mock_guess.return_value = mock_type
            assert validate_file_type(b"video_data", '.mp4') == True

    def test_filetype_exception(self):
        with patch('filetype.guess', side_effect=Exception("Test error")):
            assert validate_file_type(b"xyz", '.pdf') == False


# Tests for extract_text_from_data
class TestExtractTextFromData:
    @pytest.mark.asyncio
    async def test_valid_pdf_extraction(self, mock_upload_file, sample_pdf_bytes):
        # Setup mock
        mock_upload_file.filename = "test.pdf"
        mock_upload_file.read = AsyncMock(return_value=sample_pdf_bytes)
        
        with patch('utility.common.validate_file_type', return_value=True), \
             patch('utility.common.extract_text_from_file', new_callable=AsyncMock, return_value="Extracted text"):
            result = await extract_text_from_data(mock_upload_file)
            assert result == "Extracted text"

    @pytest.mark.asyncio
    async def test_unsupported_file_format(self, mock_upload_file):
        mock_upload_file.filename = "test.xyz"
        mock_upload_file.read = AsyncMock(return_value=b"xyz")
        
        with pytest.raises(HTTPException) as exc_info:
            await extract_text_from_data(mock_upload_file)

        assert "Unsupported file format" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_file_too_large(self, mock_upload_file):
        mock_upload_file.filename = "test.pdf"
        mock_upload_file.size = MAX_FILE_SIZE + 1
        mock_upload_file.read = AsyncMock(return_value=b"large file")
        
        with pytest.raises(HTTPException) as exc_info:
            await extract_text_from_data(mock_upload_file)

        assert "File too large" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_invalid_file_type(self, mock_upload_file, sample_txt_bytes):
        mock_upload_file.filename = "test.pdf"  # Claims to be PDF
        mock_upload_file.read = AsyncMock(return_value=sample_txt_bytes)  # But is actually TXT
        
        with patch('utility.common.validate_file_type', return_value=False):
            with pytest.raises(HTTPException) as exc_info:
                await extract_text_from_data(mock_upload_file)

        assert "Invalid file type" in exc_info.value.detail


# Tests for save_uploaded_file
class TestSaveUploadedFile:
    @pytest.mark.asyncio
    async def test_save_valid_file(self):
        with patch('utility.common.validate_file_type', return_value=True), \
             patch('tempfile.NamedTemporaryFile') as mock_temp_file, \
             patch('aiofiles.open', new_callable=MagicMock) as mock_aiofiles, \
             tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as temp_file:
                
            mock_temp_file.return_value.__enter__.return_value = temp_file
            
            file_object = AsyncMock()
            mock_aiofiles.return_value.__aenter__ = AsyncMock(return_value=file_object)
            mock_aiofiles.return_value.__aexit__ = AsyncMock()
            
            await save_uploaded_file(b"sample data", "test.pdf")
            file_object.write.assert_called_once_with(b"sample data")

    @pytest.mark.asyncio
    async def test_file_too_large(self):
        large_data = b"x" * (MAX_FILE_SIZE + 1)
        
        with pytest.raises(ValueError, match="File too large"):
            await save_uploaded_file(large_data, "large.pdf")

    @pytest.mark.asyncio
    async def test_invalid_file_type(self):
        with patch('utility.common.validate_file_type', return_value=False):
            with pytest.raises(ValueError, match="File type does not match extension"):
                await save_uploaded_file(b"data", "test.pdf")


# Tests for extract_text_from_file
class TestExtractTextFromFile:
    @pytest.mark.asyncio
    async def test_pdf_extraction(self, temp_pdf_file):
        with patch('utility.common.extract_text_from_pdf', new_callable=AsyncMock, return_value="PDF text"):
            result = await extract_text_from_file(temp_pdf_file)
            assert result == "PDF text"

    @pytest.mark.asyncio
    async def test_docx_extraction(self, temp_docx_file):
        with patch('utility.common.extract_text_from_docx', new_callable=AsyncMock, return_value="DOCX text"):
            result = await extract_text_from_file(temp_docx_file)
            assert result == "DOCX text"

    @pytest.mark.asyncio
    async def test_txt_extraction(self, temp_txt_file):
        with patch('utility.common.extract_text_from_txt', new_callable=AsyncMock, return_value="TXT text"):
            result = await extract_text_from_file(temp_txt_file)
            assert result == "TXT text"

    @pytest.mark.asyncio
    async def test_file_not_found(self):
        with pytest.raises(FileExtractionError) as exc_info:
            await extract_text_from_file("/nonexistent/path.pdf")
        assert "File not found" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_unsupported_format(self):
        with tempfile.NamedTemporaryFile(suffix=".xyz", delete=False) as f:
            path = f.name
        try:
            with pytest.raises(FileExtractionError) as exc_info:
                await extract_text_from_file(path)
            assert "Unsupported file format" in str(exc_info.value)
        finally:
            os.unlink(path)


# Tests for specific file format extraction functions
class TestFileFormatExtraction:
    @pytest.mark.asyncio
    async def test_extract_text_from_pdf(self):
        with patch('asyncio.get_event_loop') as mock_loop, \
             patch('utility.common._sync_extract_pdf', return_value="PDF content"):
            mock_loop.return_value.run_in_executor = AsyncMock(return_value="PDF content")
            result = await extract_text_from_pdf("test.pdf")
            assert result == "PDF content"

    @pytest.mark.asyncio
    async def test_extract_text_from_pdf_error(self):
        with patch('asyncio.get_event_loop') as mock_loop:
            mock_loop.return_value.run_in_executor = AsyncMock(side_effect=Exception("PDF error"))
            with pytest.raises(PdfExtractionError):
                await extract_text_from_pdf("test.pdf")

    @pytest.mark.asyncio
    async def test_extract_text_from_docx(self):
        with patch('asyncio.get_event_loop') as mock_loop, \
             patch('utility.common._sync_extract_docx', return_value="DOCX content"):
            mock_loop.return_value.run_in_executor = AsyncMock(return_value="DOCX content")
            result = await extract_text_from_docx("test.docx")
            assert result == "DOCX content"

    @pytest.mark.asyncio
    async def test_extract_text_from_txt(self):
        mock_file = MagicMock()
        mock_file.__aenter__ = AsyncMock(return_value=mock_file)
        mock_file.__aexit__ = AsyncMock(return_value=None)
        mock_file.read = AsyncMock(return_value="TXT content")
        
        with patch('aiofiles.open', return_value=mock_file):
            result = await extract_text_from_txt("test.txt")
            assert result == "TXT content"

    @pytest.mark.asyncio
    async def test_extract_text_from_txt_error(self):
        with patch('aiofiles.open', side_effect=Exception("TXT error")):
            with pytest.raises(TxtExtractionError):
                await extract_text_from_txt("test.txt")

    @pytest.mark.asyncio
    async def test_extract_text_from_epub(self):
        with patch('asyncio.get_event_loop') as mock_loop, \
             patch('ebooklib.epub.read_epub') as mock_read_epub:
            # Setup mock EPUB content
            mock_item1 = MagicMock()
            mock_item1.get_content.return_value = b"<html><body><p>Chapter 1</p></body></html>"
            mock_item2 = MagicMock()
            mock_item2.get_content.return_value = b"<html><body><p>Chapter 2</p></body></html>"
            
            mock_book = MagicMock()
            mock_book.get_items_of_type.return_value = [mock_item1, mock_item2]
            mock_read_epub.return_value = mock_book
            
            # Setup loop mock to return results from run_in_executor
            mock_loop.return_value.run_in_executor = AsyncMock(side_effect=[
                mock_book,               # First call to run_in_executor returns the mock book
                b"<html><body><p>Chapter 1</p></body></html>",  # Second call returns first content
                b"<html><body><p>Chapter 2</p></body></html>"   # Third call returns second content
            ])
            
            # With patched BeautifulSoup
            with patch('utility.common.BeautifulSoup') as mock_bs:
                mock_soup1 = MagicMock()
                mock_soup1.get_text.return_value = "Chapter 1\n\n"
                mock_soup2 = MagicMock()
                mock_soup2.get_text.return_value = "Chapter 2\n\n"
                mock_bs.side_effect = [mock_soup1, mock_soup2]
                
                result = await extract_text_from_epub("test.epub")
                assert "Chapter 1" in result
                assert "Chapter 2" in result


# Tests for URL extraction
class TestExtractTextFromUrl:
    @pytest.mark.asyncio
    async def test_extract_text_from_valid_url(self):
        mock_response = AsyncMock()
        mock_response.read = AsyncMock(return_value=b"<html><p>Web content</p></html>")
        mock_session = MagicMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)
        mock_session.get.return_value.__aenter__.return_value = mock_response
        
        with patch('aiohttp.ClientSession', return_value=mock_session), \
             patch('utility.common._parse_html_content', return_value="Parsed web content"):
            
            result = await extract_text_from_url("https://example.com")
            assert result == "Parsed web content"

    @pytest.mark.asyncio
    async def test_extract_text_from_invalid_url(self):
        with pytest.raises(ValueError, match="Invalid URL"):
            await extract_text_from_url("invalid-url")

    @pytest.mark.asyncio
    async def test_extract_text_response_too_large(self):
        mock_response = AsyncMock()
        mock_response.read = AsyncMock(return_value=b"x" * (MAX_FILE_SIZE + 1))
        mock_session = MagicMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)
        mock_session.get.return_value.__aenter__.return_value = mock_response
        
        with patch('aiohttp.ClientSession', return_value=mock_session):
            with pytest.raises(ValueError, match="Response too large"):
                await extract_text_from_url("https://example.com")


# Tests for text selection and manipulation
class TestTextManipulation:
    def test_get_selected_text_valid_range(self):
        text = "This is a test string"
        result = get_selected_text(text, 6, 10)
        assert result == "is a"

    def test_get_selected_text_none_indices(self):
        text = "This is a test string"
        result = get_selected_text(text, None, None)
        assert result is None

    def test_replace_selected_text(self):
        original = "This is a test string"
        result = replace_selected_text(original, 10, 14, "sample")
        assert result == "This is a sample string"


# Tests for document cleaning and formatting
class TestDocumentCleaning:
    def test_clean_document_for_prompt(self):
        text = "1\nSection Header\n2\n• Point 1\n3\n- Point 2\n"
        expected = "Section Header\nPoint 1\nPoint 2"
        result = clean_document_for_prompt(text)
        assert result == expected

    def test_clean_line(self):
        assert clean_line("1. Item") == "Item"
        assert clean_line("• Point") == "Point"
        assert clean_line("∗ Note") == "Note"
        assert clean_line("- - Double dash") == "Double dash"

    def test_handle_section_headers(self):
        # Test uppercase header
        section, line = handle_section_headers("HEADER TEXT", "")
        assert section == "Header Text:"
        assert line == "\nHeader Text:"
        
        # Test header ending with colon
        section, line = handle_section_headers("Header:", "Previous")
        assert section == "Header:"
        assert line == "\nHeader:"
        
        # Test normal line with bullet
        section, line = handle_section_headers("- Bullet point", "Current Section")
        assert section == "Current Section"
        assert line == "  - Bullet point"

    def test_join_and_clean_lines(self):
        lines = ["Line 1", "\n", "Line 2", "\n", "\n", "Line 3"]
        result = join_and_clean_lines(lines)
        assert "\n\n\n" not in result
        assert "Line 1\n\nLine 2\n\nLine 3" == result


# Tests for raw data cleaning and processing
class TestRawDataProcessing:
    def test_clean_raw_data_valid_json(self):
        raw_data = '{"key1": "value1"} {"key2": "value2"}'
        expected = [{"key1": "value1"}, {"key2": "value2"}]
        result = clean_raw_data(raw_data)
        assert result == expected

    def test_clean_raw_data_invalid_json(self):
        raw_data = '{"key1": "value1"} {invalid_json}'
        with pytest.raises(ValueError, match="Error parsing JSON"):
            clean_raw_data(raw_data)

    def test_clean_raw_data_empty_input(self):
        with pytest.raises(ValueError, match="Invalid input data size"):
            clean_raw_data("")

    def test_clean_raw_data_too_large(self):
        with pytest.raises(ValueError, match="Invalid input data size"):
            clean_raw_data("x" * (MAX_FILE_SIZE + 1))

    def test_parse_failure_reasons(self):
        failure_reasons = '[\"Encountered error: Invalid file format [Files: s3://bucket/file1.pdf]"]'
        result = parse_failure_reasons(failure_reasons)
        assert len(result) == 1
        assert result[0]["file"] == "s3://bucket/file1.pdf"
        assert "Invalid file format" in result[0]["error"]

    def test_parse_failure_reasons_list_input(self):
        failure_reasons = ["Encountered error: Invalid file format [Files: s3://bucket/file1.pdf]"]
        result = parse_failure_reasons(failure_reasons)
        assert len(result) == 1
        assert result[0]["file"] == "s3://bucket/file1.pdf"
        assert "Invalid file format" in result[0]["error"]


# Tests for password generation
class TestPasswordGeneration:
    def test_generate_temporary_password_length(self):
        password = generate_temporary_password(12)
        assert len(password) == 12

    def test_generate_temporary_password_complexity(self):
        password = generate_temporary_password()
        # Check for required character types
        assert re.search(r'[a-z]', password)  # lowercase
        assert re.search(r'[A-Z]', password)  # uppercase
        assert re.search(r'\d', password)     # digit
        # Use a pattern that matches all possible punctuation characters
        # special characters from string.punctuation which includes: !"#$%&'()*+,-./:;<=>?@[\]^_`{|}~
        assert any(c in string.punctuation for c in password)  # special char

    def test_generate_temporary_password_invalid_length(self):
        with pytest.raises(ValueError):
            generate_temporary_password(5)  # Too short
        with pytest.raises(ValueError):
            generate_temporary_password(200)  # Too long


# Tests for PDF processing functions
class TestPdfProcessing:
    def test_process_pdf_span(self):
        span = {"text": "Sample text", "size": 12, "font": "Arial-Bold"}
        result = process_pdf_span(span, 1)
        assert "Sample text" in result
        assert "Font size: 12" in result
        assert "Bold: True" in result

    def test_process_pdf_span_empty_text(self):
        span = {"text": "  ", "size": 12}
        result = process_pdf_span(span, 1)
        assert result is None

    def test_clean_formatted_text(self):
        text = "Page 1: 'Sample text' [Font size: 12, Bold: True]"
        result = _clean_formatted_text(text)
        assert result == "Sample text"
        assert "Page 1:" not in result
        assert "Font size" not in result

    @patch('utility.common.fitz.open')
    def test_process_pdf_with_formatting(self, mock_open):
        mock_doc = MagicMock()
        mock_page = MagicMock()
        mock_page.get_text.return_value = "Plain text content"
        mock_page.get_text.return_value = "Plain text content"
        mock_doc.__iter__ = lambda self: iter([mock_page])
        mock_open.return_value = mock_doc
        
        # Without formatting
        result = _process_pdf_with_formatting("test.pdf", False)
        assert result == ["Plain text content"]
        
        # With formatting (mocked dict structure)
        mock_blocks = [
            {
                "lines": [
                    {
                        "spans": [
                            {"text": "Formatted text", "size": 12, "font": "Arial-Bold"}
                        ]
                    }
                ]
            }
        ]
        mock_page.get_text.return_value = "Plain text content"
        mock_page.get_text.side_effect = None  # Reset side_effect
        mock_page.get_text.return_value = {"blocks": mock_blocks}
        
        result = _process_pdf_with_formatting("test.pdf", True)
        assert any("Formatted text" in r for r in result)


# Tests for Excel and DOC extraction
class TestOtherFormatExtraction:
    def test_extract_text_from_excel(self):
        with patch('pandas.read_excel') as mock_read_excel:
            # Mock DataFrame with sample data
            mock_df1 = MagicMock()
            mock_df1.columns = ["Col1", "Col2"]
            mock_df1.iterrows.return_value = [
                (0, ["Value1", "Value2"]),
                (1, ["Value3", "Value4"])
            ]
            
            # Mock DataFrames dict returned by read_excel
            mock_read_excel.return_value = {"Sheet1": mock_df1}
            
            result = _extract_text_from_excel("test.xlsx")
            assert "Sheet: Sheet1" in result
            assert "Headers: Col1, Col2" in result

    def test_extract_text_from_excel_error(self):
        with patch('pandas.read_excel', side_effect=Exception("Excel error")):
            with pytest.raises(FileExtractionError):
                _extract_text_from_excel("test.xlsx")

    def test_extract_text_from_doc(self):
        # Test when antiword is available
        with patch('os.system', return_value=0), \
             patch('os.popen') as mock_popen:
            mock_popen.return_value.read.return_value = "DOC content"
            result = _extract_text_from_doc("test.doc")
            assert result == "DOC content"
            
        # Test when antiword is not available
        with patch('os.system', return_value=1):
            with pytest.raises(FileExtractionError, match="antiword not installed"):
                _extract_text_from_doc("test.doc")


# Tests for process_and_extract_text
class TestProcessAndExtractText:
    @pytest.mark.asyncio
    async def test_process_and_extract_text_pdf(self):
        upload_file = MagicMock(spec=UploadFile)
        upload_file.filename = "test.pdf"
        upload_file.content_type = "application/pdf"
        upload_file.read = AsyncMock(return_value=b"%PDF-1.5\nContent")
        
        with patch('tempfile.NamedTemporaryFile') as mock_temp_file, \
             patch('os.unlink') as mock_unlink, \
             patch('utility.common._process_pdf_with_formatting', return_value=["PDF content"]), \
             tempfile.NamedTemporaryFile(suffix=".pdf") as temp_file:
            
            mock_temp_file.return_value.__enter__.return_value = temp_file
            
            result = await process_and_extract_text(upload_file, False)
            assert result == "PDF content"
            mock_unlink.assert_called_once()

    @pytest.mark.asyncio
    async def test_process_and_extract_text_image(self):
        upload_file = MagicMock(spec=UploadFile)
        upload_file.filename = "test.jpg"
        upload_file.content_type = "image/jpeg"
        upload_file.read = AsyncMock(return_value=b"JPEG image data")
        
        with patch('tempfile.NamedTemporaryFile') as mock_temp_file, \
             patch('os.unlink') as mock_unlink, \
             patch('utility.common.extract_text_from_image', return_value="OCR text"), \
             tempfile.NamedTemporaryFile(suffix=".jpg") as temp_file:
            
            mock_temp_file.return_value.__enter__.return_value = temp_file
            
            result = await process_and_extract_text(upload_file, False)
            assert result == "OCR text"

    @pytest.mark.asyncio
    async def test_process_and_extract_text_empty_file(self):
        upload_file = MagicMock(spec=UploadFile)
        upload_file.filename = "test.pdf"
        upload_file.read = AsyncMock(return_value=b"")
        
        with pytest.raises(FileValidationError, match="Empty file received"):
            await process_and_extract_text(upload_file, False)

    @pytest.mark.asyncio
    async def test_process_and_extract_text_unsupported_type(self):
        upload_file = MagicMock(spec=UploadFile)
        upload_file.filename = "test.xyz"
        upload_file.content_type = "application/octet-stream"
        upload_file.read = AsyncMock(return_value=b"Content")
        
        with tempfile.NamedTemporaryFile() as mock_temp_file, \
             patch('os.unlink'), \
             pytest.raises(FileValidationError, match="Unsupported file type"):
            
            await process_and_extract_text(upload_file, False)

    @pytest.mark.asyncio
    async def test_process_and_extract_text_excel(self):
        upload_file = MagicMock(spec=UploadFile)
        upload_file.filename = "test.xlsx"
        upload_file.content_type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        upload_file.read = AsyncMock(return_value=b"Excel content")
        
        # Create a mock event loop with an awaitable run_in_executor method
        mock_loop = MagicMock()
        mock_run_in_executor = AsyncMock(return_value="Extracted Excel content")
        mock_loop.run_in_executor = mock_run_in_executor
        
        with patch('tempfile.NamedTemporaryFile') as mock_temp_file, \
             patch('os.unlink') as mock_unlink, \
             patch('asyncio.get_event_loop', return_value=mock_loop), \
             patch('utility.common._extract_text_from_excel', return_value="Extracted Excel content"), \
             tempfile.NamedTemporaryFile(suffix=".xlsx") as temp_file:
            
            mock_temp_file.return_value.__enter__.return_value = temp_file
            
            result = await process_and_extract_text(upload_file, False)
            assert result == "Extracted Excel content"
            mock_unlink.assert_called_once()
            # Verify the event loop's run_in_executor was called correctly
            mock_run_in_executor.assert_called_once()

    @pytest.mark.asyncio
    async def test_process_and_extract_text_doc(self):
        upload_file = MagicMock(spec=UploadFile)
        upload_file.filename = "test.doc"
        upload_file.content_type = "application/msword"
        upload_file.read = AsyncMock(return_value=b"DOC content")
        
        # Create a mock event loop with an awaitable run_in_executor method
        mock_loop = MagicMock()
        mock_run_in_executor = AsyncMock(return_value="Extracted DOC content")
        mock_loop.run_in_executor = mock_run_in_executor
        
        with patch('tempfile.NamedTemporaryFile') as mock_temp_file, \
             patch('os.unlink') as mock_unlink, \
             patch('asyncio.get_event_loop', return_value=mock_loop), \
             patch('utility.common._extract_text_from_doc', return_value="Extracted DOC content"), \
             tempfile.NamedTemporaryFile(suffix=".doc") as temp_file:
            
            mock_temp_file.return_value.__enter__.return_value = temp_file
            
            result = await process_and_extract_text(upload_file, False)
            assert result == "Extracted DOC content"
            mock_unlink.assert_called_once()

    @pytest.mark.asyncio
    async def test_process_and_extract_text_docx(self):
        upload_file = MagicMock(spec=UploadFile)
        upload_file.filename = "test.docx"
        upload_file.content_type = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        upload_file.read = AsyncMock(return_value=b"DOCX content")
        
        with patch('tempfile.NamedTemporaryFile') as mock_temp_file, \
             patch('os.unlink') as mock_unlink, \
             patch('utility.common.extract_text_from_docx', new_callable=AsyncMock, return_value="Extracted DOCX content"), \
             tempfile.NamedTemporaryFile(suffix=".docx") as temp_file:
            
            mock_temp_file.return_value.__enter__.return_value = temp_file
            
            result = await process_and_extract_text(upload_file, False)
            assert result == "Extracted DOCX content"
            mock_unlink.assert_called_once()

    @pytest.mark.asyncio
    async def test_process_and_extract_text_extraction_error(self):
        upload_file = MagicMock(spec=UploadFile)
        upload_file.filename = "test.pdf"
        upload_file.content_type = "application/pdf"
        upload_file.read = AsyncMock(return_value=b"%PDF-1.5\nContent")
        
        with patch('tempfile.NamedTemporaryFile') as mock_temp_file, \
             patch('os.unlink') as mock_unlink, \
             patch('utility.common._process_pdf_with_formatting', side_effect=Exception("Processing error")), \
             tempfile.NamedTemporaryFile(suffix=".pdf") as temp_file:
            
            mock_temp_file.return_value.__enter__.return_value = temp_file
            
            with pytest.raises(FileExtractionError, match="Failed to extract text from file"):
                await process_and_extract_text(upload_file, False)
            
            # Ensure we still clean up the temp file even if an error occurs
            mock_unlink.assert_called_once()


# Tests for process_uploaded_files
class TestProcessUploadedFiles:
    @pytest.mark.asyncio
    async def test_process_uploaded_files_single_file(self):
        upload_file = MagicMock(spec=UploadFile)
        upload_file.filename = "test.pdf"
        
        with patch('utility.common.process_and_extract_text', new_callable=AsyncMock, return_value="Extracted PDF content"):
            result = await process_uploaded_files([upload_file], False)
            assert result == "Extracted PDF content"

    @pytest.mark.asyncio
    async def test_process_uploaded_files_multiple_files(self):
        upload_file1 = MagicMock(spec=UploadFile)
        upload_file1.filename = "test1.pdf"
        upload_file2 = MagicMock(spec=UploadFile)
        upload_file2.filename = "test2.pdf"
        
        # Mock implementation for process_and_extract_text that returns different content for each file
        async def mock_extract_text(file, formatting):
            if file.filename == "test1.pdf":
                return "Content from file 1"
            else:
                return "Content from file 2"
        
        with patch('utility.common.process_and_extract_text', new_callable=AsyncMock, side_effect=mock_extract_text):
            result = await process_uploaded_files([upload_file1, upload_file2], False)
            assert "Content from file 1" in result
            assert "Content from file 2" in result

    @pytest.mark.asyncio
    async def test_process_uploaded_files_empty_list(self):
        result = await process_uploaded_files([], False)
        assert result is None

    @pytest.mark.asyncio
    async def test_process_uploaded_files_with_formatting(self):
        upload_file = MagicMock(spec=UploadFile)
        upload_file.filename = "test.pdf"
        
        with patch('utility.common.process_and_extract_text', new_callable=AsyncMock, return_value="Formatted PDF content") as mock_extract:
            result = await process_uploaded_files([upload_file], with_formatting=True)
            mock_extract.assert_called_once_with(upload_file, True)
            assert result == "Formatted PDF content"

    @pytest.mark.asyncio
    async def test_process_uploaded_files_validation_error(self):
        upload_file = MagicMock(spec=UploadFile)
        upload_file.filename = "test.pdf"
        
        with patch('utility.common.process_and_extract_text', 
                  new_callable=AsyncMock, 
                  side_effect=FileValidationError("Invalid file")):
            with pytest.raises(HTTPException) as excinfo:
                await process_uploaded_files([upload_file], False)
            assert excinfo.value.status_code == 400
            assert "Invalid file" in str(excinfo.value.detail)

    @pytest.mark.asyncio
    async def test_process_uploaded_files_extraction_error(self):
        upload_file = MagicMock(spec=UploadFile)
        upload_file.filename = "test.pdf"
        
        with patch('utility.common.process_and_extract_text', 
                  new_callable=AsyncMock, 
                  side_effect=FileExtractionError("Extraction failed")):
            with pytest.raises(HTTPException) as excinfo:
                await process_uploaded_files([upload_file], False)
            assert excinfo.value.status_code == 500
            assert "Extraction failed" in str(excinfo.value.detail)