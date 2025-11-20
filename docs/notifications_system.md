<!--
 Copyright 2022 Google LLC

 Licensed under the Apache License, Version 2.0 (the "License");
 you may not use this file except in compliance with the License.
 You may obtain a copy of the License at

      http://www.apache.org/licenses/LICENSE-2.0

 Unless required by applicable law or agreed to in writing, software
 distributed under the License is distributed on an "AS IS" BASIS,
 WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 See the License for the specific language governing permissions and
 limitations under the License.
-->

# Notification System

## General Description

The notification system allows creating, managing, and sending internal notifications and webpush notifications with button action support. It is designed to be compatible with the existing `app_sync.send_event` system and provides a persistent database for notification history.

## Main Features

- ✅ **Persistent notifications**: PostgreSQL database storage
- ✅ **Button actions**: Support for multiple buttons with different styles
- ✅ **app_sync integration**: Compatible with real-time event system
- ✅ **Notification types**: info, success, warning, error
- ✅ **Priorities**: low, normal, high, urgent
- ✅ **Automatic expiration**: Notifications with expiration date
- ✅ **Filters and pagination**: Advanced notification search
- ✅ **Automatic migration**: Script to update existing calls

## Integration with app_sync.send_event

### Enhanced Function: `send_event_with_notification`

To maintain compatibility with the existing system, a function has been created that combines real-time event sending with persistent database storage:
```python
from utility.async_manager import AsyncManager

app_sync = AsyncManager()
app_sync.set_parameters()

# Send event and save notification
result = await app_sync.send_event_with_notification(
    db=db,
    user_id=user_id,
    service_id="chatbot_conversation",
    title="Response ready",
    body="Your chatbot has responded",
    data={"chatbot_id": chatbot_id},
    actions=[
        NotificationAction(
            label="View response",
            action="view_response",
            url=f"/chatbot/{chatbot_id}",
            style="primary"
        )
    ],
    notification_type="success",
    priority="normal"
)
```

### Synchronous Version: `send_event_with_notification_sync`

For contexts where `asyncio.run()` is used:

```python
# For functions that use asyncio.run()
app_sync.send_event_with_notification_sync(
    db=db,
    user_id=user_id,
    service_id="course_deletion",
    title="Course deleted",
    body="The course was deleted successfully",
    notification_type="success",
    priority="normal"
)
```

## Existing Code Migration

### Automatic Migration Script

A script has been created to automatically migrate existing calls:

```bash
python scripts/migrate_notifications.py
```

This script:
- Finds all calls to `app_sync.send_event`
- Replaces them with `send_event_with_notification`
- Adds appropriate notification parameters
- Handles both async and synchronous calls

### Manual Migration

To migrate manually, replace:

```python
# Before
await app_sync.send_event(
    user_id=user_id,
    service_id="chatbot_conversation",
    title="Title",
    body="Message",
    data={"key": "value"}
)

# After
await app_sync.send_event_with_notification(
    db=db,
    user_id=user_id,
    service_id="chatbot_conversation",
    title="Title",
    body="Message",
    data={"key": "value"},
    notification_type="info",
    priority="normal"
)
```

## Database Structure

### `notifications` Table

```sql
CREATE TABLE notifications (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID NOT NULL REFERENCES users(id),
    service_id VARCHAR NOT NULL,
    title VARCHAR NOT NULL,
    body TEXT NOT NULL,
    data JSONB,
    use_push_notification BOOLEAN DEFAULT TRUE,
    is_read BOOLEAN DEFAULT FALSE,
    actions JSONB,  -- For buttons/actions
    notification_type VARCHAR DEFAULT 'info',
    priority VARCHAR DEFAULT 'normal',
    expires_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT NOW(),
    read_at TIMESTAMP
);
```

### Action Fields (JSONB)

```json
[
    {
        "label": "Accept",
        "action": "accept_invitation",
        "url": "/courses/123",
        "data": {"course_id": "123"},
        "style": "primary"
    }
]
```

## API Endpoints

### Create Notification

```http
POST /notifications/
Content-Type: application/json

{
    "user_id": "uuid",
    "service_id": "chatbot_conversation",
    "title": "Title",
    "body": "Message",
    "actions": [
        {
            "label": "View",
            "action": "view",
            "url": "/chatbot/123",
            "style": "primary"
        }
    ],
    "notification_type": "success",
    "priority": "high"
}
```

### Get Notifications

```http
GET /notifications/?limit=20&offset=0&is_read=false&notification_type=success
```

### Mark as Read

```http
PUT /notifications/{notification_id}/read
```

### Mark All as Read

```http
PUT /notifications/read-all
```

## Button Usage Examples

### 1. Chatbot Completion Notification

```python
actions = [
    NotificationAction(
        label="Open chatbot",
        action="open_chatbot",
        url=f"/chatbot/{chatbot_id}",
        style="primary"
    ),
    NotificationAction(
        label="View materials",
        action="view_materials",
        url=f"/chatbot/{chatbot_id}/materials",
        style="secondary"
    ),
    NotificationAction(
        label="Share",
        action="share_chatbot",
        data={"chatbot_id": chatbot_id},
        style="secondary"
    )
]

await app_sync.send_event_with_notification(
    db=db,
    user_id=user_id,
    service_id="chatbot_creation",
    title="Chatbot completed!",
    body=f"Your chatbot '{chatbot_name}' is ready to use.",
    actions=actions,
    notification_type="success",
    priority="high"
)
```

### 2. Error Notification with Retry

```python
actions = [
    NotificationAction(
        label="Retry",
        action="retry_operation",
        data={"operation": "create_chatbot"},
        style="primary"
    ),
    NotificationAction(
        label="View details",
        action="view_error_details",
        data={"error": error_message},
        style="secondary"
    ),
    NotificationAction(
        label="Contact support",
        action="contact_support",
        url="/support",
        style="danger"
    )
]

await app_sync.send_event_with_notification(
    db=db,
    user_id=user_id,
    service_id="chatbot_creation",
    title="Creation error",
    body=f"There was a problem: {error_message}",
    actions=actions,
    notification_type="error",
    priority="urgent"
)
```

### 3. Invitation Notification

```python
actions = [
    NotificationAction(
        label="Accept invitation",
        action="accept_course_invitation",
        data={"course_id": course_id},
        style="primary"
    ),
    NotificationAction(
        label="Decline",
        action="reject_course_invitation",
        data={"course_id": course_id},
        style="danger"
    ),
    NotificationAction(
        label="View details",
        action="view_course_details",
        url=f"/courses/{course_id}",
        style="secondary"
    )
]

await app_sync.send_event_with_notification(
    db=db,
    user_id=user_id,
    service_id="course_invitation",
    title="Course invitation",
    body=f"You have been invited to the course '{course_name}'",
    actions=actions,
    notification_type="info",
    priority="high",
    expires_at=datetime.now() + timedelta(days=7)
)
```

## Button Styles

- **primary**: Primary button (blue)
- **secondary**: Secondary button (gray)
- **danger**: Destructive action button (red)
- **default**: Default button

## Notification Types

- **info**: General information
- **success**: Successful operation
- **warning**: Warning
- **error**: Error or problem

## Priorities

- **low**: Low priority
- **normal**: Normal priority
- **high**: High priority
- **urgent**: Urgent priority

## Action Processing in Frontend

```javascript
// Example of processing in the frontend
function handleNotificationAction(action, data) {
    switch (action) {
        case 'open_chatbot':
            window.location.href = `/chatbot/${data.chatbot_id}`;
            break;
        case 'retry_operation':
            retryOperation(data.operation);
            break;
        case 'accept_course_invitation':
            acceptCourseInvitation(data.course_id);
            break;
        case 'contact_support':
            window.open('/support', '_blank');
            break;
        default:
            console.log('Unrecognized action:', action);
    }
}
```

## Configuration

### Environment Variables

```bash
# Database configuration
DATABASE_URL=postgresql://user:password@localhost/dbname

# Notification configuration
NOTIFICATION_RETENTION_DAYS=30
NOTIFICATION_CLEANUP_INTERVAL=3600
```

### Automatic Cleanup Configuration

The system includes automatic cleanup of expired notifications:

```python
# Run periodically
await delete_expired_notifications(db)
```

## Monitoring and Metrics

### Metrics Endpoints

#### Unread Count
```http
GET /notifications/metrics/unread-count?days=7
```

**Response:**
```json
{
    "total_unread": 15,
    "by_type": {
        "info": 5,
        "success": 3,
        "warning": 4,
        "error": 3
    },
    "by_priority": {
        "low": 2,
        "normal": 8,
        "high": 4,
        "urgent": 1
    },
    "by_service": {
        "chatbot_conversation": 8,
        "course_generation": 4,
        "course_deletion": 3
    },
    "recent_notifications": [
        {
            "id": "uuid",
            "title": "Chatbot completed",
            "body": "Your chatbot is ready",
            "notification_type": "success",
            "priority": "normal",
            "service_id": "chatbot_conversation",
            "created_at": "2024-01-15T10:30:00Z",
            "has_actions": true
        }
    ],
    "filter_days": 7
}
```

#### Notifications by Type
```http
GET /notifications/metrics/by-type?notification_type=error&days=30
```

**Response:**
```json
{
    "notification_type": "error",
    "count": 5,
    "notifications": [
        {
            "id": "uuid",
            "title": "Processing error",
            "body": "There was a problem",
            "data": {"error": "details"},
            "is_read": false,
            "notification_type": "error",
            "priority": "high",
            "service_id": "course_generation",
            "actions": [
                {
                    "label": "Retry",
                    "action": "retry",
                    "style": "primary"
                }
            ],
            "created_at": "2024-01-15T10:30:00Z",
            "read_at": null,
            "expires_at": null
        }
    ],
    "filter_days": 30
}
```

#### Notifications by Priority
```http
GET /notifications/metrics/by-priority?priority=urgent&days=7
```

**Response:**
```json
{
    "priority": "urgent",
    "count": 2,
    "notifications": [...],
    "filter_days": 7
}
```

#### General Statistics
```http
GET /notifications/metrics/statistics?days=30
```

**Response:**
```json
{
    "period_days": 30,
    "summary": {
        "total_notifications": 150,
        "read_notifications": 120,
        "unread_notifications": 30,
        "expired_notifications": 5,
        "notifications_with_actions": 45,
        "read_rate_percentage": 80.0
    },
    "by_type": {
        "info": {
            "total": 60,
            "read": 50,
            "unread": 10
        },
        "success": {
            "total": 40,
            "read": 35,
            "unread": 5
        },
        "warning": {
            "total": 30,
            "read": 20,
            "unread": 10
        },
        "error": {
            "total": 20,
            "read": 15,
            "unread": 5
        }
    },
    "by_priority": {
        "low": {
            "total": 20,
            "read": 18,
            "unread": 2
        },
        "normal": {
            "total": 80,
            "read": 65,
            "unread": 15
        },
        "high": {
            "total": 35,
            "read": 25,
            "unread": 10
        },
        "urgent": {
            "total": 15,
            "read": 12,
            "unread": 3
        }
    },
    "top_services": [
        {
            "service_id": "chatbot_conversation",
            "total": 50,
            "read": 40,
            "unread": 10
        },
        {
            "service_id": "course_generation",
            "total": 30,
            "read": 25,
            "unread": 5
        }
    ],
    "daily_stats": [
        {
            "date": "2024-01-09",
            "total": 5,
            "read": 4,
            "unread": 1
        },
        {
            "date": "2024-01-10",
            "total": 8,
            "read": 7,
            "unread": 1
        }
    ]
}
```

### Notification Cleanup

#### Delete Expired Notifications
```http
DELETE /notifications/cleanup/expired
```

**Response:**
```json
{
    "message": "15 expired notifications were deleted",
    "deleted_count": 15
}
```

**Note:** This endpoint requires administrator permissions.

## Performance Considerations

1. **Indexes**: The table includes indexes on `user_id`, `created_at`, `is_read`
2. **Pagination**: All queries include pagination
3. **Expiration**: Expired notifications are automatically deleted
4. **Cache**: Consider implementing cache for frequent queries

## Security

1. **Validation**: All inputs are validated with Pydantic
2. **Authorization**: Permission verification per user
3. **Sanitization**: Input data is sanitized
4. **Rate Limiting**: Implement rate limits for creation

## Testing

### Unit Tests

```bash
pytest tests/unit/test_notifications.py
```

### Integration Tests

```bash
pytest tests/integration/test_notification_flow.py
```

## Troubleshooting

### Common Issues

1. **Notifications not saved**: Check database connection
2. **Events not arriving**: Check WebSocket configuration
3. **Buttons not working**: Check frontend processing

### Debug Logs

```python
import logging
logging.getLogger('notifications').setLevel(logging.DEBUG)
```

## Roadmap

- [ ] Native push notification support
- [ ] Notification templates
- [ ] Scheduled notifications
- [ ] Notification grouping
- [ ] Multi-language support
- [ ] Integration with external services (Slack, Teams, etc.) 
