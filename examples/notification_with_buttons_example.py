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

"""
Example of how to use the notification system with action buttons
in the context of chatbot and other services.
"""

from datetime import datetime, timedelta, timezone
from uuid import uuid4
from database.schemas import NotificationAction
from utility.async_manager import AsyncManager

# Example 1: Chatbot completion notification with action buttons
async def send_chatbot_completion_notification(db, user_id: str, chatbot_id: str, chatbot_name: str):
    """
    Send a notification when a chatbot is completed with action buttons.
    """
    app_sync = AsyncManager()
    app_sync.set_parameters()
    
    # Define the actions/buttons
    actions = [
        NotificationAction(
            label="Open chatbot",
            action="open_chatbot",
            url=f"/chatbot/{chatbot_id}",
            data={"chatbot_id": chatbot_id},
            style="primary"
        ),
        NotificationAction(
            label="View materials",
            action="view_materials",
            url=f"/chatbot/{chatbot_id}/materials",
            data={"chatbot_id": chatbot_id},
            style="secondary"
        ),
        NotificationAction(
            label="Share",
            action="share_chatbot",
            data={"chatbot_id": chatbot_id, "chatbot_name": chatbot_name},
            style="secondary"
        )
    ]
    
    # Send notification with real-time events
    result = await app_sync.send_event_with_notification(
        db=db,
        user_id=user_id,
        service_id="chatbot_creation",
        title="Chatbot completed",
        body=f"Your chatbot '{chatbot_name}' is ready to use.",
        data={
            "chatbot_id": chatbot_id,
            "chatbot_name": chatbot_name,
            "stage": "completed",
            "materials_count": 3  # Example of additional data
        },
        actions=actions,
        notification_type="success",
        priority="high"
    )
    
    return result

# Example 2: Error notification with retry options
async def send_chatbot_error_notification(db, user_id: str, chatbot_id: str, error_message: str):
    """
    Send an error notification with retry options.
    """
    app_sync = AsyncManager()
    app_sync.set_parameters()
    
    actions = [
        NotificationAction(
            label="Retry",
            action="retry_chatbot_creation",
            data={"chatbot_id": chatbot_id, "operation": "create"},
            style="primary"
        ),
        NotificationAction(
            label="View details",
            action="view_error_details",
            data={"chatbot_id": chatbot_id, "error": error_message},
            style="secondary"
        ),
        NotificationAction(
            label="Contact support",
            action="contact_support",
            url="/support",
            data={"issue_type": "chatbot_creation", "chatbot_id": chatbot_id},
            style="danger"
        )
    ]
    
    result = await app_sync.send_event_with_notification(
        db=db,
        user_id=user_id,
        service_id="chatbot_creation",
        title="Error in chatbot creation",
        body=f"There was a problem creating your chatbot: {error_message}",
        data={
            "chatbot_id": chatbot_id,
            "error": error_message,
            "stage": "error",
            "timestamp": datetime.now(timezone.utc).isoformat()
        },
        actions=actions,
        notification_type="error",
        priority="urgent"
    )
    
    return result

# Example 3: Course invitation notification with accept/reject buttons
async def send_course_invitation_notification(db, user_id: str, course_id: str, course_name: str, teacher_name: str):
    """
    Send a course invitation notification with accept/reject buttons.
    """
    app_sync = AsyncManager()
    app_sync.set_parameters()
    
    actions = [
        NotificationAction(
            label="Accept invitation",
            action="accept_course_invitation",
            data={"course_id": course_id, "course_name": course_name},
            style="primary"
        ),
        NotificationAction(
            label="Reject",
            action="reject_course_invitation",
            data={"course_id": course_id},
            style="danger"
        ),
        NotificationAction(
            label="View course details",
            action="view_course_details",
            url=f"/courses/{course_id}",
            data={"course_id": course_id},
            style="secondary"
        )
    ]
    
    result = await app_sync.send_event_with_notification(
        db=db,
        user_id=user_id,
        service_id="course_invitation",
        title="Course invitation",
        body=f"You have been invited by {teacher_name} to join the course '{course_name}'",
        data={
            "course_id": course_id,
            "course_name": course_name,
            "teacher_name": teacher_name,
            "invitation_type": "course"
        },
        actions=actions,
        notification_type="info",
        priority="high",
        expires_at=datetime.now(timezone.utc) + timedelta(days=7)  # Expira en 7 días
    )
    
    return result

# Example 4: Task reminder notification with postpone options
async def send_task_reminder_notification(db, user_id: str, task_id: str, task_name: str, due_date: str):
    """
    Send a task reminder notification with postpone options.
    """
    app_sync = AsyncManager()
    app_sync.set_parameters()
    
    actions = [
        NotificationAction(
            label="Complete now",
            action="complete_task",
            data={"task_id": task_id, "task_name": task_name},
            style="primary"
        ),
        NotificationAction(
            label="Postpone 1 hour",
            action="postpone_task",
            data={"task_id": task_id, "delay_minutes": 60},
            style="secondary"
        ),
        NotificationAction(
            label="Postpone until tomorrow",
            action="postpone_task",
            data={"task_id": task_id, "delay_minutes": 1440},
            style="secondary"
        ),
        NotificationAction(
            label="View details",
            action="view_task_details",
            url=f"/tasks/{task_id}",
            data={"task_id": task_id},
            style="secondary"
        )
    ]
    
    result = await app_sync.send_event_with_notification(
        db=db,
        user_id=user_id,
        service_id="task_reminder",
        title="Pending task",
        body=f"You have a pending task: '{task_name}'. It expires on {due_date}",
        data={
            "task_id": task_id,
            "task_name": task_name,
            "due_date": due_date,
            "reminder_type": "task"
        },
        actions=actions,
        notification_type="warning",
        priority="normal",
        expires_at=datetime.now(timezone.utc) + timedelta(hours=24)
    )
    
    return result

# Example 5: Chat message notification with quick response buttons
async def send_chat_message_notification(db, user_id: str, chat_id: str, sender_name: str, message_preview: str):
    """
    Send a chat message notification with quick response buttons.
    """
    app_sync = AsyncManager()
    app_sync.set_parameters()
    
    actions = [
        NotificationAction(
            label="Responder",
            action="reply_to_message",
            data={"chat_id": chat_id, "sender": sender_name},
            style="primary"
        ),
        NotificationAction(
            label="Open chat",
            action="open_chat",
            url=f"/chat/{chat_id}",
            data={"chat_id": chat_id},
            style="secondary"
        ),
        NotificationAction(
            label="Mark as read",
            action="mark_as_read",
            data={"chat_id": chat_id},
            style="secondary"
        ),
        NotificationAction(
            label="Mute chat",
            action="mute_chat",
            data={"chat_id": chat_id, "duration_minutes": 60},
            style="secondary"
        )
    ]
    
    result = await app_sync.send_event_with_notification(
        db=db,
        user_id=user_id,
        service_id="chat_system",
        title=f"New message from {sender_name}",
        body=message_preview,
        data={
            "chat_id": chat_id,
            "sender_name": sender_name,
            "message_preview": message_preview,
            "timestamp": datetime.now(timezone.utc).isoformat()
        },
        actions=actions,
        notification_type="info",
        priority="normal"
    )
    
    return result

# Example 6: Integration with the existing chatbot system
async def enhanced_chatbot_completion_notification(db, user_id: str, chatbot_id: str, chatbot_name: str, response: dict):
    """
    Enhanced chatbot completion notification with action buttons.
    """
    app_sync = AsyncManager()
    app_sync.set_parameters()
    
    # Determinar el tipo de respuesta para mostrar botones apropiados
    response_type = response.get("type", "general")
    
    if response_type == "question_answer":
        actions = [
            NotificationAction(
                label="View full response",
                action="view_full_response",
                data={"chatbot_id": chatbot_id, "response_id": response.get("id")},
                style="primary"
            ),
            NotificationAction(
                label="Ask follow-up question",
                action="ask_follow_up",
                data={"chatbot_id": chatbot_id, "context": response.get("context")},
                style="secondary"
            ),
            NotificationAction(
                label="Save response",
                action="save_response",
                data={"chatbot_id": chatbot_id, "response_id": response.get("id")},
                style="secondary"
            )
        ]
    else:
        actions = [
            NotificationAction(
                label="Continue conversation",
                action="continue_conversation",
                url=f"/chatbot/{chatbot_id}",
                data={"chatbot_id": chatbot_id},
                style="primary"
            ),
            NotificationAction(
                label="View conversation history",
                action="view_conversation_history",
                url=f"/chatbot/{chatbot_id}/history",
                data={"chatbot_id": chatbot_id},
                style="secondary"
            )
        ]
    
    result = await app_sync.send_event_with_notification(
        db=db,
        user_id=user_id,
        service_id="chatbot_conversation",
        title="Chatbot response ready",
        body=f"Your chatbot '{chatbot_name}' has responded to your question.",
        data={
            "chatbot_id": chatbot_id,
            "chatbot_name": chatbot_name,
            "stage": "completed",
            "response": response,
            "response_type": response_type
        },
        actions=actions,
        notification_type="success",
        priority="normal"
    )
    
    return result

# Utility function to process frontend actions
def process_notification_action(action: str, data: dict, user_id: str):
    """
    Processes the actions of the notifications in the frontend.
    This function would be called when the user clicks on a button.
    """
    action_handlers = {
        "open_chatbot": lambda d: f"Navigate to chatbot {d.get('chatbot_id')}",
        "retry_chatbot_creation": lambda d: f"Retry creation of chatbot {d.get('chatbot_id')}",
        "accept_course_invitation": lambda d: f"Accept invitation to course {d.get('course_id')}",
        "reject_course_invitation": lambda d: f"Reject invitation to course {d.get('course_id')}",
        "complete_task": lambda d: f"Complete task {d.get('task_id')}",
        "postpone_task": lambda d: f"Postpone task {d.get('task_id')} for {d.get('delay_minutes')} minutes",
        "reply_to_message": lambda d: f"Reply to message in chat {d.get('chat_id')}",
        "open_chat": lambda d: f"Open chat {d.get('chat_id')}",
        "view_full_response": lambda d: f"View full response for chatbot {d.get('chatbot_id')}",
        "ask_follow_up": lambda d: f"Ask follow-up question to chatbot {d.get('chatbot_id')}",
        "save_response": lambda d: f"Save response {d.get('response_id')} from chatbot {d.get('chatbot_id')}",
        "continue_conversation": lambda d: f"Continue conversation with chatbot {d.get('chatbot_id')}",
        "view_conversation_history": lambda d: f"View history of chatbot {d.get('chatbot_id')}",
        "contact_support": lambda d: f"Contact support for issue {d.get('issue_type')}",
        "mark_as_read": lambda d: f"Mark chat {d.get('chat_id')} as read",
        "mute_chat": lambda d: f"Mute chat {d.get('chat_id')} for {d.get('duration_minutes')} minutes"
    }
    
    handler = action_handlers.get(action)
    if handler:
        return handler(data)
    else:
        return f"Unknown action: {action}"

# Example of usage in the real context of chatbot
async def example_usage_in_chatbot_router(db, user_id: str, chatbot_id: str, response: dict):
    """
    Example of how to use the enhanced notifications in the chatbot router.
    """
    try:
        
        # Send notification with action buttons
        await enhanced_chatbot_completion_notification(
            db=db,
            user_id=user_id,
            chatbot_id=chatbot_id,
            chatbot_name="My Chatbot",
            response=response
        )
        
        return response
        
    except Exception as e:
        # Send error notification with retry options
        await send_chatbot_error_notification(
            db=db,
            user_id=user_id,
            chatbot_id=chatbot_id,
            error_message=str(e)
        )
        raise 