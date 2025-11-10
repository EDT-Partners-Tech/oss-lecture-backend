# © [2025] EDT&Partners. Licensed under CC BY 4.0.

class FileProcessingError(Exception):
    """Base exception for file processing errors"""
    pass

class FileValidationError(FileProcessingError):
    """Raised when file validation fails"""
    pass

class FileExtractionError(FileProcessingError):
    """Raised when text extraction fails"""
    pass

class StepFunctionExecutionError(Exception):
    """Raised when a Step Function execution fails"""
    pass

class StepFunctionTimeoutError(Exception):
    """Raised when a Step Function execution times out"""
    pass

class DocxExtractionError(Exception):
    """Raised when DOCX extraction fails"""
    pass

class TxtExtractionError(Exception):
    """Raised when TXT extraction fails"""
    pass

class PdfExtractionError(Exception):
    """Raised when PDF extraction fails"""
    pass