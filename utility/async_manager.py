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

from utility.ssm_parameter_store import SSMParameterStore
from fastapi import HTTPException
import aiohttp
import json
import uuid
from utility.websocket_manager import manager
import os
from typing import List
from datetime import datetime

class AsyncManager:
    _instance = None
    _initialized = False
    _settings = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(AsyncManager, cls).__new__(cls)
        return cls._instance

    def __init__(self):
        if not self._initialized:
            self.endpoint = None
            self.region = None
            self.api_key = None
            self.default_auth_mode = None
            self.use_websocket = os.getenv('USE_WEBSOCKET', 'false').lower() == 'true'
            self._initialized = True
    
    def set_parameters(self):
        if self._settings is None:
            parameter_store = SSMParameterStore()
            self.endpoint = parameter_store.get_parameter("/lecture/global/AWS_APP_SYNC_ENDPOINT")
            self.region = parameter_store.get_parameter("/lecture/global/AWS_REGION_NAME")
            self.api_key = parameter_store.get_parameter("/lecture/global/AWS_APP_SYNC_API_KEY")
            self.default_auth_mode = "apiKey"
            self._settings = {
                "API": {
                    "Events": {
                        "endpoint": self.endpoint + "/event",
                        "region": self.region,
                        "defaultAuthMode": self.default_auth_mode,
                        "apiKey": self.api_key
                    }
                }
            }
    
    def get_settings(self):
        if self._settings is None:
            self.set_parameters()
        return self._settings if self.endpoint and self.region and self.api_key else None

    def create_event_payload(self, service_id: str, title: str, body: str, data: dict = None, use_push_notification: bool = True) -> dict:
        """
        Crea un payload de evento siguiendo la estructura AppSyncPayload.
        
        Args:
            service_id (str): ID del servicio que envía el evento
            title (str): Título del evento
            body (str): Cuerpo del mensaje
            data (dict, optional): Datos adicionales del evento
            use_push_notification (bool, optional): Si se debe enviar como notificación push
            
        Returns:
            dict: Payload estructurado según AppSyncPayload
        """
        return {
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

    async def send_event(self, user_id: str, service_id: str, title: str, body: str, data: dict = None, use_push_notification: bool = True, actions: List[dict] = None) -> dict:
        """
        Envía un evento usando WebSocket o AppSync según la configuración.
        """
        if self.use_websocket:
            # Usar WebSocket para desarrollo local
            await manager.send_event(user_id, service_id, title, body, data, use_push_notification)
            return {"message": "Event sent via WebSocket"}
        else:
            # Use AppSync for production
            try:
                settings = self.get_settings()
                if not settings:
                    raise HTTPException(status_code=500, detail="AppSync settings not configured")

                endpoint = settings["API"]["Events"]["endpoint"]
                api_key = settings["API"]["Events"]["apiKey"]

                # Build the endpoint URL according to AWS documentation
                url = f"{endpoint}"

                # Create the event payload according to AWS documentation
                event_data = {
                    "service_id": service_id,
                    "use_push_notification": use_push_notification,
                    "title": title,
                    "body": body,
                    "data": data or {},
                    "actions": actions or []
                }

                # El payload debe seguir la estructura de AWS AppSync Events
                payload = {
                    "channel": f"lecture-appsync-namespace/event/{user_id}",
                    "events": [json.dumps(event_data)]
                }

                # Configure headers according to documentation
                headers = {
                    "Content-Type": "application/json",
                    "x-api-key": api_key
                }

                # Send the request
                async with aiohttp.ClientSession() as session:
                    async with session.post(url, json=payload, headers=headers) as response:
                        response_text = await response.text()
                        
                        if response.status != 200:
                            raise HTTPException(
                                status_code=response.status,
                                detail=f"Error sending event: {response_text}"
                            )
                        
                        try:
                            return json.loads(response_text)
                        except json.JSONDecodeError:
                            return {"message": response_text}

            except Exception as e:
                raise HTTPException(
                    status_code=500,
                    detail=f"Failed to send event: {str(e)}"
                )

    @classmethod
    def reset_settings(cls):
        """Method to reset cache if necessary"""
        cls._settings = None
        if cls._instance:
            cls._instance.endpoint = None
            cls._instance.region = None
            cls._instance.api_key = None
            cls._instance.default_auth_mode = None

    async def send_event_with_notification(
        self, 
        db, 
        user_id: str, 
        service_id: str, 
        title: str, 
        body: str, 
        data: dict = None, 
        use_push_notification: bool = True,
        actions: List[dict] = None,
        notification_type: str = "info",
        priority: str = "normal",
        expires_at: datetime = None
    ) -> dict:
        """
        Send an event and save it as a notification in the database.
        This function combines send_event with persistent saving.
        
        Args:
            db: Database session
            user_id: User ID
            service_id: Service ID
            title: Event/notification title
            body: Message body
            data: Additional data
            use_push_notification: If it should be sent as push notification
            actions: List of actions/buttons for the notification
            notification_type: Notification type (info, success, warning, error)
            priority: Notification priority (low, normal, high, urgent)
            expires_at: Notification expiration date
            
        Returns:
            dict: Result of the event sending
        """
        try:
            # Import here to avoid circular dependencies
            from database.crud import create_notification_from_event
            
            # Create the notification in the database
            notification = await create_notification_from_event(
                db=db,
                user_id=user_id,
                service_id=service_id,
                title=title,
                body=body,
                data=data,
                use_push_notification=use_push_notification,
                actions=actions,
                notification_type=notification_type,
                priority=priority,
                expires_at=expires_at
            )
            
            # Send the event in real time
            event_result = await self.send_event(
                user_id=user_id,
                service_id=service_id,
                title=title,
                body=body,
                data=data,
                use_push_notification=use_push_notification,
                actions=actions if actions else None
            )
            
            # Combine the results
            return {
                "notification_id": str(notification.id),
                "event_result": event_result,
                "message": "Event sent and notification saved successfully"
            }
            
        except Exception as e:
            # If the saving in the database fails, still try to send the event
            try:
                event_result = await self.send_event(
                    user_id=user_id,
                    service_id=service_id,
                    title=title,
                    body=body,
                    data=data,
                    use_push_notification=use_push_notification
                )
                return {
                    "event_result": event_result,
                    "error": f"Event sent but notification save failed: {str(e)}"
                }
            except Exception as event_error:
                raise HTTPException(
                    status_code=500,
                    detail=f"Failed to send event and save notification: {str(e)}, Event error: {str(event_error)}"
                )

    def send_event_with_notification_sync(
        self, 
        db, 
        user_id: str, 
        service_id: str, 
        title: str, 
        body: str, 
        data: dict = None, 
        use_push_notification: bool = True,
        actions: List[dict] = None,
        notification_type: str = "info",
        priority: str = "normal",
        expires_at: datetime = None
    ) -> dict:
        """
        Synchronous version of send_event_with_notification for use with asyncio.run().
        """
        import asyncio
        
        async def _async_send():
            return await self.send_event_with_notification(
                db=db,
                user_id=user_id,
                service_id=service_id,
                title=title,
                body=body,
                data=data,
                use_push_notification=use_push_notification,
                actions=actions,
                notification_type=notification_type,
                priority=priority,
                expires_at=expires_at
            )
        
        return asyncio.run(_async_send()) 