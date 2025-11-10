# © [2025] EDT&Partners. Licensed under CC BY 4.0.

import json
from datetime import datetime, timedelta, timezone
from typing import List, Optional
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Query, logger
from sqlalchemy.orm import Session
from database.db import get_db
from database.crud import (
    create_notification,
    get_notifications_by_user_id,
    get_notification_by_id,
    mark_notification_as_read,
    mark_all_notifications_as_read,
    update_notification,
    delete_notification,
    delete_expired_notifications,
    get_unread_notifications_count
)
from database.models import Notification
from database.schemas import (
    NotificationCreate,
    NotificationUpdate,
    NotificationResponse
)
from utility.auth import require_token_types
from utility.async_manager import AsyncManager
from utility.tokens import JWTLectureTokenPayload
from sqlalchemy import func

router = APIRouter()

@router.post("/", response_model=NotificationResponse)
async def create_new_notification(
    notification: NotificationCreate,
    db: Session = Depends(get_db),
    token: JWTLectureTokenPayload = Depends(require_token_types(allowed_types=["cognito"]))
):
    """
    Create a new notification.
    """
    try:
        notification_data = notification.model_dump()
        created_notification = await create_notification(db, notification_data)
        
        # Send event in real time if enabled
        if notification.use_push_notification:
            app_sync = AsyncManager()
            app_sync.set_parameters()
            
            await app_sync.send_event(
                user_id=str(notification.user_id),
                service_id=notification.service_id,
                title=notification.title,
                body=notification.body,
                data=notification.data,
                use_push_notification=True
            )
        
        return created_notification
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error creating notification: {str(e)}"
        )

@router.get("/", response_model=List[NotificationResponse])
async def get_user_notifications(
    is_read: Optional[bool] = Query(None, description="Filter by read status"),
    notification_type: Optional[str] = Query(None, description="Filter by notification type"),
    priority: Optional[str] = Query(None, description="Filter by priority"),
    service_id: Optional[str] = Query(None, description="Filter by service"),
    limit: int = Query(50, ge=1, le=100, description="Result limit"),
    offset: int = Query(0, ge=0, description="Pagination offset"),
    db: Session = Depends(get_db),
    token: JWTLectureTokenPayload = Depends(require_token_types(allowed_types=["cognito"]))
):
    """
    Get notifications for the current user with optional filters.
    """
    try:
        user_id = token.sub
        user = get_user_by_cognito_id(db, user_id)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        
        filters = {}
        if is_read is not None:
            filters["is_read"] = is_read
        if notification_type:
            filters["notification_type"] = notification_type
        if priority:
            filters["priority"] = priority
        if service_id:
            filters["service_id"] = service_id
        
        notifications = await get_notifications_by_user_id(
            db, user.id, filters, limit, offset
        )
        
        # Convert SQLAlchemy objects to Pydantic models
        notification_responses = []
        for notification in notifications:
            notification_response = NotificationResponse.model_validate(notification)
            notification_responses.append(notification_response)
        
        return notification_responses
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error retrieving notifications: {str(e)}"
        )

@router.get("/unread-count")
async def get_unread_count(
    db: Session = Depends(get_db),
    token: JWTLectureTokenPayload = Depends(require_token_types(allowed_types=["cognito"]))
):
    """
    Get the number of unread notifications for the user.
    """
    try:
        user_id = token.sub
        user = get_user_by_cognito_id(db, user_id)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        
        count = await get_unread_notifications_count(db, user.id)
        return {"unread_count": count}
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error getting unread count: {str(e)}"
        )

@router.get("/{notification_id}", response_model=NotificationResponse)
async def get_notification(
    notification_id: UUID,
    db: Session = Depends(get_db),
    token: JWTLectureTokenPayload = Depends(require_token_types(allowed_types=["cognito"]))
):
    """
    Get a specific notification by ID.
    """
    try:
        user_id = token.sub
        user = get_user_by_cognito_id(db, user_id)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        
        notification = await get_notification_by_id(db, notification_id)
        if not notification:
            raise HTTPException(status_code=404, detail="Notification not found")
        
        # Verify that the notification belongs to the user
        if str(notification.user_id) != str(user.id):
            raise HTTPException(status_code=403, detail="Access denied")
        
        # Convert SQLAlchemy object to Pydantic model
        notification_response = NotificationResponse.model_validate(notification)
        return notification_response
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error retrieving notification: {str(e)}"
        )

@router.patch("/{notification_id}/read", response_model=NotificationResponse)
async def mark_as_read(
    notification_id: UUID,
    db: Session = Depends(get_db),
    token: JWTLectureTokenPayload = Depends(require_token_types(allowed_types=["cognito"]))
):
    """
    Mark a notification as read.
    """
    try:
        user_id = token.sub
        user = get_user_by_cognito_id(db, user_id)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        
        notification = await get_notification_by_id(db, notification_id)
        if not notification:
            raise HTTPException(status_code=404, detail="Notification not found")
        
        # Verify that the notification belongs to the user
        if str(notification.user_id) != str(user.id):
            raise HTTPException(status_code=403, detail="Access denied")
        
        updated_notification = await mark_notification_as_read(db, notification_id)
        
        # Convert SQLAlchemy object to Pydantic model
        notification_response = NotificationResponse.model_validate(updated_notification)
        return notification_response
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error marking notification as read: {str(e)}"
        )

@router.patch("/mark-all-read")
async def mark_all_as_read(
    db: Session = Depends(get_db),
    token: JWTLectureTokenPayload = Depends(require_token_types(allowed_types=["cognito"]))
):
    """
    Mark all notifications for the user as read.
    """
    try:
        user_id = token.sub
        user = get_user_by_cognito_id(db, user_id)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        
        count = await mark_all_notifications_as_read(db, user.id)
        return {"message": f"Marked {count} notifications as read"}
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error marking all notifications as read: {str(e)}"
        )

@router.put("/read-all")
async def mark_all_as_read_put(
    db: Session = Depends(get_db),
    token: JWTLectureTokenPayload = Depends(require_token_types(allowed_types=["cognito"]))
):
    """
    Mark all notifications for the user as read (PUT method).
    """
    try:
        user_id = token.sub
        user = get_user_by_cognito_id(db, user_id)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        
        count = await mark_all_notifications_as_read(db, user.id)
        return {"message": f"Marked {count} notifications as read"}
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error marking all notifications as read: {str(e)}"
        )

@router.put("/{notification_id}", response_model=NotificationResponse)
async def update_notification_by_id(
    notification_id: UUID,
    notification_update: NotificationUpdate,
    db: Session = Depends(get_db),
    token: JWTLectureTokenPayload = Depends(require_token_types(allowed_types=["cognito"]))
):
    """
    Update an existing notification.
    """
    try:
        user_id = token.sub
        user = get_user_by_cognito_id(db, user_id)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        
        notification = await get_notification_by_id(db, notification_id)
        if not notification:
            raise HTTPException(status_code=404, detail="Notification not found")
        
        # Verify that the notification belongs to the user
        if str(notification.user_id) != str(user.id):
            raise HTTPException(status_code=403, detail="Access denied")
        
        update_data = notification_update.model_dump(exclude_unset=True)
        updated_notification = await update_notification(db, notification_id, update_data)
        
        # Convert SQLAlchemy object to Pydantic model
        notification_response = NotificationResponse.model_validate(updated_notification)
        return notification_response
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error updating notification: {str(e)}"
        )

@router.delete("/{notification_id}")
async def delete_notification_by_id(
    notification_id: UUID,
    db: Session = Depends(get_db),
    token: JWTLectureTokenPayload = Depends(require_token_types(allowed_types=["cognito"]))
):
    """
    Delete a notification.
    """
    try:
        user_id = token.sub
        user = get_user_by_cognito_id(db, user_id)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        
        notification = await get_notification_by_id(db, notification_id)
        if not notification:
            raise HTTPException(status_code=404, detail="Notification not found")
        
        # Verify that the notification belongs to the user
        if str(notification.user_id) != str(user.id):
            raise HTTPException(status_code=403, detail="Access denied")
        
        success = await delete_notification(db, notification_id)
        if success:
            return {"message": "Notification deleted successfully"}
        else:
            raise HTTPException(status_code=500, detail="Failed to delete notification")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error deleting notification: {str(e)}"
        )

@router.get("/metrics/statistics")
async def get_notification_statistics(
    days: int = Query(30, description="Period in days for statistics"),
    db: Session = Depends(get_db),
    token: JWTLectureTokenPayload = Depends(require_token_types(allowed_types=["cognito"]))
):
    """
    Get general notification statistics.
    
    Args:
        days: Period in days for statistics (default 30)
        db: Database session
        token: Current user token payload
        
    Returns:
        dict: Notification statistics
    """
    try:
        # Get user from database
        user_id = token.sub
        user = get_user_by_cognito_id(db, user_id)
        if not user:
            raise HTTPException(
                status_code=404,
                detail="User not found"
            )
        
        # Calculate start date
        from_date = datetime.now(timezone.utc) - timedelta(days=days)
        
        # Base query for the period
        base_query = db.query(Notification).filter(
            Notification.user_id == user.id,
            Notification.created_at >= from_date
        )
        
        # General statistics
        total_notifications = base_query.count()
        read_notifications = base_query.filter(Notification.is_read == True).count()
        unread_notifications = base_query.filter(Notification.is_read == False).count()
        
        # Expired notifications
        expired_notifications = base_query.filter(
            Notification.expires_at.isnot(None),
            Notification.expires_at < datetime.now(timezone.utc)
        ).count()
        
        # Statistics by type
        type_stats = {}
        for notification_type in ["info", "success", "warning", "error"]:
            type_query = base_query.filter(Notification.notification_type == notification_type)
            type_stats[notification_type] = {
                "total": type_query.count(),
                "read": type_query.filter(Notification.is_read == True).count(),
                "unread": type_query.filter(Notification.is_read == False).count()
            }
        
        # Statistics by priority
        priority_stats = {}
        for priority in ["low", "normal", "high", "urgent"]:
            priority_query = base_query.filter(Notification.priority == priority)
            priority_stats[priority] = {
                "total": priority_query.count(),
                "read": priority_query.filter(Notification.is_read == True).count(),
                "unread": priority_query.filter(Notification.is_read == False).count()
            }
        
        # Top services by notifications
        top_services = db.query(
            Notification.service_id,
            func.count(Notification.id).label('total'),
            func.sum(func.case((Notification.is_read == True, 1), else_=0)).label('read'),
            func.sum(func.case((Notification.is_read == False, 1), else_=0)).label('unread')
        ).filter(
            Notification.user_id == user.id,
            Notification.created_at >= from_date
        ).group_by(Notification.service_id).order_by(
            func.count(Notification.id).desc()
        ).limit(10).all()
        
        services_stats = []
        for service_id, total, read_count, unread_count in top_services:
            services_stats.append({
                "service_id": service_id,
                "total": total,
                "read": read_count,
                "unread": unread_count
            })
        
        # Statistics by day (last 7 days)
        daily_stats = []
        for i in range(7):
            date = datetime.now(timezone.utc) - timedelta(days=i)
            start_of_day = date.replace(hour=0, minute=0, second=0, microsecond=0)
            end_of_day = start_of_day + timedelta(days=1)
            
            daily_query = db.query(Notification).filter(
                Notification.user_id == user.id,
                Notification.created_at >= start_of_day,
                Notification.created_at < end_of_day
            )
            
            daily_stats.append({
                "date": start_of_day.date().isoformat(),
                "total": daily_query.count(),
                "read": daily_query.filter(Notification.is_read == True).count(),
                "unread": daily_query.filter(Notification.is_read == False).count()
            })
        
        # Notifications with actions
        notifications_with_actions = base_query.filter(
            Notification.actions.isnot(None)
        ).count()
        
        # Read rate (percentage of read notifications)
        read_rate = (read_notifications / total_notifications * 100) if total_notifications > 0 else 0
        
        return {
            "period_days": days,
            "summary": {
                "total_notifications": total_notifications,
                "read_notifications": read_notifications,
                "unread_notifications": unread_notifications,
                "expired_notifications": expired_notifications,
                "notifications_with_actions": notifications_with_actions,
                "read_rate_percentage": round(read_rate, 2)
            },
            "by_type": type_stats,
            "by_priority": priority_stats,
            "top_services": services_stats,
            "daily_stats": list(reversed(daily_stats))  # Sort from oldest to newest
        }
        
    except Exception as e:
        logger.error(f"Error getting notification statistics: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail="Error getting notification statistics"
        )

@router.get("/metrics/unread-count")
async def get_notification_metrics(
    days: int = Query(None, description="Filter by last N days"),
    db: Session = Depends(get_db),
    token: JWTLectureTokenPayload = Depends(require_token_types(allowed_types=["cognito"]))
):
    """
    Get unread notification metrics.
    
    Args:
        days: Filter by last N days (optional)
        db: Database session
        token: Current user token payload
        
    Returns:
        dict: Notification metrics
    """
    try:
        # Get user from database
        user_id = token.sub
        user = get_user_by_cognito_id(db, user_id)
        if not user:
            raise HTTPException(
                status_code=404,
                detail="User not found"
            )
        
        # Build base query
        query = db.query(Notification).filter(
            Notification.user_id == user.id,
            Notification.is_read == False,
            (Notification.expires_at.is_(None)) | 
            (Notification.expires_at > datetime.now(timezone.utc))
        )
        
        # Apply days filter if specified
        if days:
            from_date = datetime.now(timezone.utc) - timedelta(days=days)
            query = query.filter(Notification.created_at >= from_date)
        
        # Get total count
        total_unread = query.count()
        
        # Get count by notification type
        type_counts = {}
        for notification_type in ["info", "success", "warning", "error"]:
            type_query = query.filter(Notification.notification_type == notification_type)
            type_counts[notification_type] = type_query.count()
        
        # Get count by priority
        priority_counts = {}
        for priority in ["low", "normal", "high", "urgent"]:
            priority_query = query.filter(Notification.priority == priority)
            priority_counts[priority] = priority_query.count()
        
        # Get count by service (top 10)
        service_counts = db.query(
            Notification.service_id,
            func.count(Notification.id).label('count')
        ).filter(
            Notification.user_id == user.id,
            Notification.is_read == False,
            (Notification.expires_at.is_(None)) | 
            (Notification.expires_at > datetime.now(timezone.utc))
        ).group_by(Notification.service_id).order_by(
            func.count(Notification.id).desc()
        ).limit(10).all()
        
        service_counts_dict = {service: count for service, count in service_counts}
        
        # Get recent notifications (last 5)
        recent_notifications = query.order_by(
            Notification.created_at.desc()
        ).limit(5).all()
        
        recent_notifications_data = []
        for notification in recent_notifications:
            recent_notifications_data.append({
                "id": str(notification.id),
                "title": notification.title,
                "body": notification.body,
                "notification_type": notification.notification_type,
                "priority": notification.priority,
                "service_id": notification.service_id,
                "created_at": notification.created_at.isoformat(),
                "has_actions": notification.actions is not None
            })
        
        return {
            "total_unread": total_unread,
            "by_type": type_counts,
            "by_priority": priority_counts,
            "by_service": service_counts_dict,
            "recent_notifications": recent_notifications_data,
            "filter_days": days
        }
        
    except Exception as e:
        logger.error(f"Error getting notification metrics: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail="Error getting notification metrics"
        )

@router.get("/metrics/by-type")
async def get_notifications_by_type(
    notification_type: str = Query(..., description="Notification type"),
    days: int = Query(None, description="Filter by last N days"),
    db: Session = Depends(get_db),
    token: JWTLectureTokenPayload = Depends(require_token_types(allowed_types=["cognito"]))
):
    """
    Get notifications by specific type.
    
    Args:
        notification_type: Notification type (info, success, warning, error)
        days: Filter by last N days (optional)
        db: Database session
        token: Current user token payload
        
    Returns:
        dict: Notifications of the specified type
    """
    try:
        # Validate notification type
        valid_types = ["info", "success", "warning", "error"]
        if notification_type not in valid_types:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid notification type. Must be one of: {valid_types}"
            )
        
        # Get user from database
        user_id = token.sub
        user = get_user_by_cognito_id(db, user_id)
        if not user:
            raise HTTPException(
                status_code=404,
                detail="User not found"
            )
        
        # Build query
        query = db.query(Notification).filter(
            Notification.user_id == user.id,
            Notification.notification_type == notification_type,
            (Notification.expires_at.is_(None)) | 
            (Notification.expires_at > datetime.now(timezone.utc))
        )
        
        # Apply days filter if specified
        if days:
            from_date = datetime.now(timezone.utc) - timedelta(days=days)
            query = query.filter(Notification.created_at >= from_date)
        
        # Get notifications
        notifications = query.order_by(Notification.created_at.desc()).all()
        
        # Convert to response format
        notifications_data = []
        for notification in notifications:
            actions = []
            if notification.actions:
                try:
                    actions = json.loads(notification.actions)
                except json.JSONDecodeError:
                    actions = []
            
            notifications_data.append({
                "id": str(notification.id),
                "title": notification.title,
                "body": notification.body,
                "data": notification.data,
                "is_read": notification.is_read,
                "notification_type": notification.notification_type,
                "priority": notification.priority,
                "service_id": notification.service_id,
                "actions": actions,
                "created_at": notification.created_at.isoformat(),
                "read_at": notification.read_at.isoformat() if notification.read_at else None,
                "expires_at": notification.expires_at.isoformat() if notification.expires_at else None
            })
        
        return {
            "notification_type": notification_type,
            "count": len(notifications_data),
            "notifications": notifications_data,
            "filter_days": days
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting notifications by type: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail="Error getting notifications by type"
        )

@router.get("/metrics/by-priority")
async def get_notifications_by_priority(
    priority: str = Query(..., description="Notification priority"),
    days: int = Query(None, description="Filter by last N days"),
    db: Session = Depends(get_db),
    token: JWTLectureTokenPayload = Depends(require_token_types(allowed_types=["cognito"]))
):
    """
    Get notifications by specific priority.
    
    Args:
        priority: Notification priority (low, normal, high, urgent)
        days: Filter by last N days (optional)
        db: Database session
        token: Current user token payload
        
    Returns:
        dict: Notifications of the specified priority
    """
    try:
        # Validate priority
        valid_priorities = ["low", "normal", "high", "urgent"]
        if priority not in valid_priorities:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid priority. Must be one of: {valid_priorities}"
            )
        
        # Get user from database
        user_id = token.sub
        user = get_user_by_cognito_id(db, user_id)
        if not user:
            raise HTTPException(
                status_code=404,
                detail="User not found"
            )
        
        # Build query
        query = db.query(Notification).filter(
            Notification.user_id == user.id,
            Notification.priority == priority,
            (Notification.expires_at.is_(None)) | 
            (Notification.expires_at > datetime.now(timezone.utc))
        )
        
        # Apply days filter if specified
        if days:
            from_date = datetime.now(timezone.utc) - timedelta(days=days)
            query = query.filter(Notification.created_at >= from_date)
        
        # Get notifications
        notifications = query.order_by(Notification.created_at.desc()).all()
        
        # Convert to response format
        notifications_data = []
        for notification in notifications:
            actions = []
            if notification.actions:
                try:
                    actions = json.loads(notification.actions)
                except json.JSONDecodeError:
                    actions = []
            
            notifications_data.append({
                "id": str(notification.id),
                "title": notification.title,
                "body": notification.body,
                "data": notification.data,
                "is_read": notification.is_read,
                "notification_type": notification.notification_type,
                "priority": notification.priority,
                "service_id": notification.service_id,
                "actions": actions,
                "created_at": notification.created_at.isoformat(),
                "read_at": notification.read_at.isoformat() if notification.read_at else None,
                "expires_at": notification.expires_at.isoformat() if notification.expires_at else None
            })
        
        return {
            "priority": priority,
            "count": len(notifications_data),
            "notifications": notifications_data,
            "filter_days": days
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting notifications by priority: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail="Error getting notifications by priority"
        )

@router.delete("/cleanup/expired")
async def cleanup_expired_notifications(
    db: Session = Depends(get_db),
    token: JWTLectureTokenPayload = Depends(require_token_types(allowed_types=["cognito"]))
):
    """
    Delete expired notifications (only for administrators).
    
    Args:
        db: Database session
        token: Current user token payload
        
    Returns:
        dict: Cleanup result
    """
    try:
        # Get user from database
        user_id = token.sub
        user = get_user_by_cognito_id(db, user_id)
        if not user:
            raise HTTPException(
                status_code=404,
                detail="User not found"
            )
        
        # Verify that the user is an administrator
        if user.role != "admin":
            raise HTTPException(
                status_code=403,
                detail="Admin access required"
            )
        
        deleted_count = await delete_expired_notifications(db)
        return {
            "message": f"Deleted {deleted_count} expired notifications",
            "deleted_count": deleted_count
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error cleaning up expired notifications: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Error cleaning up expired notifications: {str(e)}"
        )

@router.put("/{notification_id}/read", response_model=NotificationResponse)
async def mark_as_read_put(
    notification_id: UUID,
    db: Session = Depends(get_db),
    token: JWTLectureTokenPayload = Depends(require_token_types(allowed_types=["cognito"]))
):
    """
    Mark a notification as read (PUT method).
    """
    try:
        user_id = token.sub
        user = get_user_by_cognito_id(db, user_id)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        
        notification = await get_notification_by_id(db, notification_id)
        if not notification:
            raise HTTPException(status_code=404, detail="Notification not found")
        
        # Verify that the notification belongs to the user
        if str(notification.user_id) != str(user.id):
            raise HTTPException(status_code=403, detail="Access denied")
        
        updated_notification = await mark_notification_as_read(db, notification_id)
        
        # Convert SQLAlchemy object to Pydantic model
        notification_response = NotificationResponse.model_validate(updated_notification)
        return notification_response
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error marking notification as read: {str(e)}"
        )

# Auxiliary function to import
def get_user_by_cognito_id(db: Session, cognito_id: str):
    from database.crud import get_user_by_cognito_id as get_user
    return get_user(db, cognito_id) 