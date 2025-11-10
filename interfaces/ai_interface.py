# © [2025] EDT&Partners. Licensed under CC BY 4.0.

"""
Interfaz para servicios de IA
"""
from abc import ABC, abstractmethod
from typing import Optional

class AIServiceInterface(ABC):
    """Interfaz para servicios de inteligencia artificial"""
    
    @abstractmethod
    async def generate_content(
        self, 
        prompt: str, 
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None
    ) -> str:
        """
        Genera contenido usando IA
        
        Args:
            prompt (str): Prompt para generar contenido
            max_tokens (Optional[int]): Número máximo de tokens
            temperature (Optional[float]): Temperatura para la generación
            
        Returns:
            str: Contenido generado
        """
        pass
    
    @abstractmethod
    async def get_status(self) -> str:
        """
        Obtiene el estado del servicio de IA
        
        Returns:
            str: Estado del servicio
        """
        pass
    
    @abstractmethod
    async def generate_html_content(self, prompt: str, system_prompt: str) -> str:
        """
        Genera contenido HTML usando IA
        
        Args:
            prompt (str): Prompt para generar contenido HTML
            system_prompt (str): Prompt del sistema para definir el comportamiento
            
        Returns:
            str: Contenido HTML generado
        """
        pass 