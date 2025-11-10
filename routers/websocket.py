# © [2025] EDT&Partners. Licensed under CC BY 4.0.

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from utility.websocket_manager import manager
from icecream import ic

router = APIRouter()

@router.websocket("/{user_id}")
async def websocket_endpoint(websocket: WebSocket, user_id: str):
    """
    Endpoint WebSocket para la comunicación en tiempo real.
    Simula la funcionalidad de AppSync para desarrollo local.
    
    Args:
        websocket (WebSocket): Conexión WebSocket
        user_id (str): ID del usuario que se conecta
    """
    await manager.connect(websocket, user_id)
    try:
        while True:
            # Mantener la conexión viva
            data = await websocket.receive_text()
            # Aquí podrías procesar mensajes entrantes si es necesario
    except WebSocketDisconnect:
        manager.disconnect(websocket, user_id)
    except Exception as e:
        ic(f"Error en WebSocket: {str(e)}")
        manager.disconnect(websocket, user_id) 