# © [2025] EDT&Partners. Licensed under CC BY 4.0.

"""
Service for handling generated content storage and versioning
"""
import os
import base64
import tempfile
import uuid
import json
from typing import Optional, List, Dict, Any
from datetime import datetime
from sqlalchemy.orm import Session
from sqlalchemy import and_
from fastapi import UploadFile

from database.schemas import FilePayload

from services.aws_service import AWSService
from utility.aws import upload_file_to_s3, get_s3_object

class ContentStorageService:
    def __init__(self):
        self.aws_service = AWSService()
        self.max_db_size = 10 * 1024  # 10KB límite para DB
    
    async def retrieve_content(self, db: Session, content_id: str, version_number: Optional[int] = None) -> Optional[str]:
        """Recupera el contenido de una versión específica o la activa"""
        if version_number:
            version = await self.get_version(db, content_id, version_number)
        else:
            version = await self.get_active_version(db, content_id)
        
        if version and version.content_s3_uri:
            # Remove s3:// and bucket name from the URI
            s3_uri = version.content_s3_uri.replace(f"s3://{self.aws_service.s3_bucket}/", "")
            content = self.aws_service.get_file_from_s3(s3_uri)
            return content
        
        return None
    
    async def delete_version(self, db: Session, content_id: str, version_number: int) -> bool:
        """Elimina una versión específica (no la activa)"""
        version = await self.get_version(db, content_id, version_number)
        if not version:
            return False
        
        if version.is_active:
            raise ValueError("Cannot delete active version")
        
        # Eliminar archivo de S3
        await self._delete_content_from_s3(version.content_s3_uri)
        
        # Eliminar de la base de datos
        db.delete(version)
        db.commit()
        
        return True
    
    async def _upload_content_to_s3(self, content: str, content_type: str, user_id: str) -> str:
        """Sube contenido a S3"""
        filename = f"""{uuid.uuid4()}.{"html" if content_type == "ai_html" else "md"}"""
        s3_key = f"generated_content/{content_type}/{user_id}/{filename}"
        
        # Crear archivo temporal
        import tempfile
        import os
        
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', suffix='.html', delete=False) as tmp_file:
            tmp_file.write(content)
            tmp_path = tmp_file.name
        
        try:
            s3_uri = await upload_file_to_s3('content', tmp_path, s3_key)
            return s3_uri
        finally:
            os.unlink(tmp_path)
    
    async def _get_content_from_s3(self, s3_uri: str) -> str:
        """Obtiene contenido desde S3"""
        content_bytes = await get_s3_object(s3_uri)
        return content_bytes.decode('utf-8')
    
    async def _delete_content_from_s3(self, s3_uri: str) -> None:
        """Elimina contenido de S3"""
        # Implementar eliminación de S3
        # Por ahora solo un placeholder
        pass
    
        
