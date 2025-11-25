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