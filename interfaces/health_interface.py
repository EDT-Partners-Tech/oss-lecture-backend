# © [2025] EDT&Partners. Licensed under CC BY 4.0.

"""
Interfaz para servicios de health check
"""
from abc import ABC, abstractmethod
from pydantic import BaseModel

class HealthResponse(BaseModel):
    """Modelo de respuesta para health check"""
    status: str
    version: str
    project_name: str
    message: str

class HealthServiceInterface(ABC):
    """Interfaz para servicios de health check"""
    
    @abstractmethod
    def get_health_status(self) -> HealthResponse:
        """
        Obtiene el estado de salud del servicio
        
        Returns:
            HealthResponse: Información del estado del servicio
        """
        pass 