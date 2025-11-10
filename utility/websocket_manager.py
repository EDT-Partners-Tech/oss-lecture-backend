# © [2025] EDT&Partners. Licensed under CC BY 4.0.

from fastapi import WebSocket, WebSocketDisconnect
from typing import Dict, List
import json
import uuid
from icecream import ic

class ConnectionManager:
    def __init__(self):
        # Almacena las conexiones activas por usuario
        self.active_connections: Dict[str, List[WebSocket]] = {}
        
    async def connect(self, websocket: WebSocket, user_id: str):
        await websocket.accept()
        if user_id not in self.active_connections:
            self.active_connections[user_id] = []
        self.active_connections[user_id].append(websocket)
        ic(f"Cliente conectado. Total de conexiones para usuario {user_id}: {len(self.active_connections[user_id])}")

    def disconnect(self, websocket: WebSocket, user_id: str):
        if user_id in self.active_connections:
            self.active_connections[user_id].remove(websocket)
            if not self.active_connections[user_id]:
                del self.active_connections[user_id]
        ic(f"Cliente desconectado. Conexiones restantes para usuario {user_id}: {len(self.active_connections.get(user_id, []))}")

    async def send_event(self, user_id: str, service_id: str, title: str, body: str, data: dict = None, use_push_notification: bool = True):
        """
        Envía un evento a todos los clientes conectados de un usuario específico.
        Simula la estructura de eventos de AppSync.
        """
        if user_id not in self.active_connections:
            return

        event_data = {
            "id": str(uuid.uuid4()),
            "type": "event",
            "event": {
                "service_id": service_id,
                "use_push_notification": use_push_notification,
                "title": title,
                "body": body,
                "data": data or {}
            }
        }

        # Send the event to all user connections
        for connection in self.active_connections[user_id]:
            try:
                await connection.send_json(event_data)
            except WebSocketDisconnect:
                self.disconnect(connection, user_id)
            except Exception as e:
                ic(f"Error enviando evento: {str(e)}")
                self.disconnect(connection, user_id)

# Instancia global del ConnectionManager
manager = ConnectionManager() 