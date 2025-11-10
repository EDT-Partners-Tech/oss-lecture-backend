# © [2025] EDT&Partners. Licensed under CC BY 4.0.

"""
Service for health check
"""
from icecream import ic
from services.strands_service import StrandsService
from interfaces.health_interface import HealthServiceInterface, HealthResponse
import os
from dotenv import load_dotenv
load_dotenv()

class HealthService(HealthServiceInterface):
    """Service for health check"""
    
    @staticmethod
    async def get_health_status() -> HealthResponse:
        """Gets the health status of the service"""
        strands_service = StrandsService()
        response = await strands_service.get_status()
        ic(response)
        return HealthResponse(
            status="healthy",
            version=os.getenv("VERSION", "1.0.0"),
            project_name=os.getenv("PROJECT_NAME", "Content Generator"),
            message=f"Service is running correctly. {response}"
        ) 