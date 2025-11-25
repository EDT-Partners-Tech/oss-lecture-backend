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
Examples of using the notification system with action buttons.

This file shows how to create notifications with different types of actions
that can be used in webpush notifications and internal notifications.
"""

from datetime import datetime, timedelta, timezone
from uuid import uuid4
from database.schemas import NotificationCreate, NotificationAction
from database.crud import create_notification_from_event
from utility.async_manager import AsyncManager

# Example 1: Simple notification without action buttons
async def create_simple_notification(db, user_id: str):
    """
    Create a simple notification without action buttons.
    """
    notification_data = {
        "user_id": user_id,
        "service_id": "course_generation",
        "title": "Curso completado",
        "body": "Tu curso 'Introducción a Python' ha sido procesado exitosamente.",
        "data": {
            "course_id": str(uuid4()),
            "stage": "completed"
        },
        "notification_type": "success",
        "priority": "normal"
    }
    
    return await create_notification_from_event(db, **notification_data)

# Example 2: Notification with action button
async def create_notification_with_action_button(db, user_id: str):
    """
    Create a notification with an action button.
    """
    actions = [
        NotificationAction(
            label="View course",
            action="navigate_to_course",
            url="/courses/123",
            data={"course_id": "123"},
            style="primary"
        )
    ]
    
    notification_data = {
        "user_id": user_id,
        "service_id": "course_generation",
        "title": "New course available",
        "body": "Your course 'Machine Learning Basic' is ready to use.",
        "data": {
            "course_id": "123",
            "stage": "completed"
        },
        "actions": actions,
        "notification_type": "info",
        "priority": "high"
    }
    
    return await create_notification_from_event(db, **notification_data)

# Example 3: Notification with multiple buttons
async def create_notification_with_multiple_buttons(db, user_id: str):
    """
    Create a notification with multiple action buttons.
    """
    actions = [
        NotificationAction(
            label="Accept",
            action="accept_invitation",
            data={"invitation_id": "456"},
            style="primary"
        ),
        NotificationAction(
            label="Reject",
            action="reject_invitation",
            data={"invitation_id": "456"},
            style="danger"
        ),
        NotificationAction(
            label="View details",
            action="view_invitation_details",
            url="/invitations/456",
            style="secondary"
        )
    ]
    
    notification_data = {
        "user_id": user_id,
        "service_id": "course_invitation",
        "title": "Course invitation",
        "body": "You have been invited to join the course 'Advanced Data Analysis'.",
        "data": {
            "invitation_id": "456",
            "course_name": "Análisis de Datos Avanzado",
            "teacher_name": "Dr. García"
        },
        "actions": actions,
        "notification_type": "info",
        "priority": "high",
        "expires_at": datetime.now(timezone.utc) + timedelta(days=7)
    }
    
    return await create_notification_from_event(db, **notification_data)

# Example 4: Error notification with retry button
async def create_error_notification_with_retry(db, user_id: str):
    """
    Create an error notification with a retry button.
    """
    actions = [
        NotificationAction(
            label="Retry",
            action="retry_operation",
            data={"operation_id": "789", "operation_type": "course_generation"},
            style="primary"
        ),
        NotificationAction(
            label="Contact support",
            action="contact_support",
            url="/support",
            style="secondary"
        )
    ]
    
    notification_data = {
        "user_id": user_id,
        "service_id": "course_generation",
        "title": "Processing error",
        "body": "There was a problem processing your course. Please try again.",
        "data": {
            "operation_id": "789",
            "error_code": "PROCESSING_ERROR",
            "error_message": "Timeout en el procesamiento"
        },
        "actions": actions,
        "notification_type": "error",
        "priority": "urgent"
    }
    
    return await create_notification_from_event(db, **notification_data)

# Example 5: Reminder notification with postpone button
async def create_reminder_notification(db, user_id: str):
    """
    Create a reminder notification with a postpone button.
    """
    actions = [
        NotificationAction(
            label="Complete now",
            action="complete_task",
            data={"task_id": "101", "task_type": "assignment"},
            style="primary"
        ),
        NotificationAction(
            label="Postpone 1 hour",
            action="postpone_task",
            data={"task_id": "101", "delay_minutes": 60},
            style="secondary"
        ),
        NotificationAction(
            label="Postpone until tomorrow",
            action="postpone_task",
            data={"task_id": "101", "delay_minutes": 1440},
            style="secondary"
        )
    ]
    
    notification_data = {
        "user_id": user_id,
        "service_id": "task_reminder",
        "title": "Pending task",
        "body": "You have a pending task: 'Python Exercises - Chapter 3'",
        "data": {
            "task_id": "101",
            "task_name": "Python Exercises - Chapter 3",
            "due_date": "2024-01-15T23:59:59Z"
        },
        "actions": actions,
        "notification_type": "warning",
        "priority": "normal",
        "expires_at": datetime.now(timezone.utc) + timedelta(hours=24)
    }
    
    return await create_notification_from_event(db, **notification_data)

# Example 6: Integration with app_sync.send_event
async def send_notification_with_realtime_event(db, user_id: str):
    """
    Example of how to integrate notifications with the real-time event system.
    """
    # Create the notification in the database
    actions = [
        NotificationAction(
            label="View results",
            action="view_results",
            url="/analytics/results/202",
            style="primary"
        )
    ]
    
    notification_data = {
        "user_id": user_id,
        "service_id": "analytics_report",
        "title": "Analytics report ready",
        "body": "Your analytics report is available.",
        "data": {
            "report_id": "202",
            "report_type": "performance_analysis"
        },
        "actions": actions,
        "notification_type": "success",
        "priority": "normal"
    }
    
    # Save the notification in the database
    notification = await create_notification_from_event(db, **notification_data)
    
    # Send event in real time
    app_sync = AsyncManager()
    app_sync.set_parameters()
    
    await app_sync.send_event(
        user_id=user_id,
        service_id=notification_data["service_id"],
        title=notification_data["title"],
        body=notification_data["body"],
        data=notification_data["data"],
        use_push_notification=True
    )
    
    return notification

# Example 7: Notification with rich data for webpush
async def create_webpush_notification_with_rich_data(db, user_id: str):
    """
    Create a rich notification for webpush with rich data.
    """
    actions = [
        NotificationAction(
            label="Open chat",
            action="open_chat",
            data={
                "chat_id": "chat_123",
                "chat_type": "course_support",
                "course_id": "course_456"
            },
            style="primary"
        ),
        NotificationAction(
            label="Mute",
            action="mute_notifications",
            data={"duration_minutes": 60},
            style="secondary"
        )
    ]
    
    notification_data = {
        "user_id": user_id,
        "service_id": "chat_system",
        "title": "New message in the chat",
        "body": "The teacher has answered your question about exercise 3.",
        "data": {
            "chat_id": "chat_123",
            "message_id": "msg_789",
            "sender": "Prof. Martinez",
            "course_name": "Advanced Programming",
            "preview": "Excellent question. The answer is...",
            "timestamp": datetime.now(timezone.utc).isoformat()
        },
        "actions": actions,
        "notification_type": "info",
        "priority": "normal",
        "use_push_notification": True
    }
    
    return await create_notification_from_event(db, **notification_data)

# Utility function to process notification actions
def process_notification_action(action: str, data: dict):
    """
    Process the actions of the notifications.
    This function would be called from the frontend when the user clicks on a button.
    """
    action_handlers = {
        "navigate_to_course": lambda d: f"Navigate to course {d.get('course_id')}",
        "accept_invitation": lambda d: f"Accept invitation {d.get('invitation_id')}",
        "reject_invitation": lambda d: f"Reject invitation {d.get('invitation_id')}",
        "retry_operation": lambda d: f"Retry operation {d.get('operation_id')}",
        "complete_task": lambda d: f"Complete task {d.get('task_id')}",
        "postpone_task": lambda d: f"Postpone task {d.get('task_id')} for {d.get('delay_minutes')} minutes",
        "open_chat": lambda d: f"Open chat {d.get('chat_id')}",
        "mute_notifications": lambda d: f"Mute notifications for {d.get('duration_minutes')} minutes"
    }
    
    handler = action_handlers.get(action)
    if handler:
        return handler(data)
    else:
        return f"Unknown action: {action}"

# Example of usage in a real context
async def example_usage_in_course_generation(db, user_id: str, course_id: str):
    """
    Example of how to use the notifications in the context of course generation.
    """
    # Start notification
    await create_notification_from_event(
        db=db,
        user_id=user_id,
        service_id="course_generation",
        title="Procesamiento iniciado",
        body="Tu curso está siendo procesado. Te notificaremos cuando esté listo.",
        data={"course_id": course_id, "stage": "started"},
        notification_type="info",
        priority="normal"
    )
    
    # Simulate processing...
    # ... processing code ...
    
    # Success notification with buttons
    actions = [
        NotificationAction(
            label="View course",
            action="navigate_to_course",
            url=f"/courses/{course_id}",
            data={"course_id": course_id},
            style="primary"
        ),
        NotificationAction(
            label="Share",
            action="share_course",
            data={"course_id": course_id},
            style="secondary"
        )
    ]
    
    await create_notification_from_event(
        db=db,
        user_id=user_id,
        service_id="course_generation",
        title="Course completed",
        body="Your course has been processed successfully and is ready to use.",
        data={"course_id": course_id, "stage": "completed"},
        actions=actions,
        notification_type="success",
        priority="high"
    ) 