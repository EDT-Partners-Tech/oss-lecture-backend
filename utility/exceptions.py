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