# © [2025] EDT&Partners. Licensed under CC BY 4.0.

"""
Interfaz para servicios de Strands
"""
from abc import ABC, abstractmethod
from typing import Optional, Dict, Any

class StrandsServiceInterface(ABC):
    """Interfaz para servicios de Strands Agents"""
    
    @abstractmethod
    async def generate_text(
        self,
        prompt: str,
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None
    ) -> str:
        """
        Genera texto usando AWS Bedrock
        
        Args:
            prompt (str): Prompt para generar texto
            max_tokens (Optional[int]): Número máximo de tokens
            temperature (Optional[float]): Temperatura para la generación
            
        Returns:
            str: Texto generado
        """
        pass
    
    @abstractmethod
    async def get_status(self) -> str:
        """
        Obtiene el estado del servicio de Strands
        
        Returns:
            str: Estado del servicio
        """
        pass
    
    # @abstractmethod
    # def get_configuration(self) -> Dict[str, Any]:
    #     """
    #     Obtiene la configuración actual del servicio
        
    #     Returns:
    #         Dict[str, Any]: Configuración del servicio
    #     """
    #     pass
    
    @abstractmethod
    async def generate_html_content(self, prompt: str, system_prompt: str) -> str:
        """
        Genera contenido HTML usando AWS Bedrock
        
        Args:
            prompt (str): Prompt para generar contenido HTML
            system_prompt (str): Prompt del sistema para definir el comportamiento
            
        Returns:
            str: Contenido HTML generado
        """
        pass 