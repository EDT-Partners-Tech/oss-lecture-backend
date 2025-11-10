# © [2025] EDT&Partners. Licensed under CC BY 4.0.

"""
Interfaz para servicios de manejo de HTML
"""
from abc import ABC, abstractmethod
from typing import Optional

class HTMLServiceInterface(ABC):
    """Interfaz para servicios de manipulación de HTML"""
    
    @abstractmethod
    def generate_initial_structure(self, title: str = "Document", language: str = "es") -> str:
        """
        Genera una estructura HTML inicial
        
        Args:
            title (str): Título del documento HTML
            language (str): Idioma del documento HTML
        Returns:
            str: HTML con estructura inicial
        """
        pass
    
    @abstractmethod
    def add_head_tags(self, html_content: str, tags: str) -> str:
        """
        Agrega tags en el head del HTML
        
        Args:
            html_content (str): Contenido HTML existente
            tags (str): Tags HTML a agregar en el head
            
        Returns:
            str: HTML con los tags agregados en el head
        """
        pass
    
    @abstractmethod
    def add_script(self, html_content: str, script: str, position: str = "body_end") -> str:
        """
        Agrega un script al HTML
        
        Args:
            html_content (str): Contenido HTML existente
            script (str): Script a agregar
            position (str): Posición donde agregar el script ('head', 'body_start', 'body_end')
            
        Returns:
            str: HTML con el script agregado
        """
        pass
    
    @abstractmethod
    def replace_element_by_id(self, html_content: str, element_id: str, new_html: str) -> str:
        """
        Reemplaza un elemento por ID con nueva estructura HTML
        
        Args:
            html_content (str): Contenido HTML existente
            element_id (str): ID del elemento a reemplazar
            new_html (str): Nueva estructura HTML
            
        Returns:
            str: HTML con el elemento reemplazado
        """
        pass
    
    @abstractmethod
    def add_identification_to_elements(self, html_content: str) -> str:
        """
        Recorre todos los elementos HTML y les asigna un UUID en data-identification
        
        Args:
            html_content (str): Contenido HTML a procesar
            
        Returns:
            str: HTML con data-identification agregado a todos los elementos
        """
        pass
    
    @abstractmethod
    def wrap_element_with_void_divs(self, html_element: str) -> str:
        """
        Envuelve un elemento HTML con divs vacíos con data-identification void-UUID
        
        Args:
            html_element (str): Elemento HTML a envolver
            
        Returns:
            str: HTML con el elemento original y dos divs void antes y después
        """
        pass
    
    @abstractmethod
    def clean_void_duplicates(self, html_content: str) -> str:
        """
        Limpia elementos void duplicados en el mismo nivel, dejando solo uno antes y después
        
        Args:
            html_content (str): Contenido HTML a procesar
            
        Returns:
            str: HTML con elementos void duplicados eliminados
        """
        pass 