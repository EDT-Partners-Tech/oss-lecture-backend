# © [2025] EDT&Partners. Licensed under CC BY 4.0.

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy.orm import Session
from database.db import get_db
from database.models import UserRole, ETLTaskType, ETLTaskStatus
from database.schemas import ETLTaskTopicsAnalysisConfiguration
from utility.auth import require_token_types
from utility.tokens import JWTLectureTokenPayload
from database.crud import get_user_by_cognito_id, get_chatbot_ids_by_group, create_etl_task, get_etl_task_configuration_by_type_and_group, create_etl_task_configuration, update_etl_task_configuration, delete_etl_task_configuration, get_conversation_topics_for_chatbots, delete_conversation_topics_for_chatbots, check_if_etl_task_is_running
from tasks.conversation_topics_task import process_conversation_topics
from collections import defaultdict
from icecream import ic

router = APIRouter()

@router.post("/etl_task", tags=["Topics"])
async def launch_etl(
    background_tasks: BackgroundTasks,
    token: JWTLectureTokenPayload = Depends(require_token_types(allowed_types=["cognito"])),
    db: Session = Depends(get_db)
):
    try:
        ic(f"Launching ETL topics analysis task for user {token.sub}")
        user = get_user_by_cognito_id(db, token.sub)
        if user.role != UserRole.admin:
            raise HTTPException(
                status_code=403,
                detail="You are not authorized to launch ETL topics analysis task"
            )
        
        # Check if there is a topics analysis task running
        if await check_if_etl_task_is_running(db, ETLTaskType.topics_analysis, user.group_id):
            raise HTTPException(
                status_code=400,
                detail="A topic analysis task is already running. Please wait for it to finish before launching a new one."
            )
        
        configuration = await get_etl_task_configuration_by_type_and_group(db, ETLTaskType.topics_analysis, user.group_id)
        if not configuration:
            raise HTTPException(
                status_code=400,
                detail="No configuration found for the user's group. You must create a configuration first."
            )
        topics_analysis_configuration = ETLTaskTopicsAnalysisConfiguration(**configuration.configuration)

        chatbot_ids = await get_chatbot_ids_by_group(db, user.group_id)
        if not chatbot_ids:
            raise HTTPException(
                status_code=400,
                detail="No chatbots found for the user's group"
            )
        ic(f"Found {len(chatbot_ids)} chatbots for group {user.group_id}")

        etl_task = await create_etl_task(db, ETLTaskType.topics_analysis, user.group_id, ETLTaskStatus.pending)
        ic(f"Created ETL task with ID: {etl_task.id}")

        background_tasks.add_task(
            process_conversation_topics,
            db=db,
            user_id=str(user.id),
            chatbot_ids=chatbot_ids,
            configuration=topics_analysis_configuration,
            etl_task_id=etl_task.id
        )
        return {"message": "ETL topics analysis task launched", "etl_task_id": etl_task.id}
    except HTTPException as e:
        raise e
    except Exception as e:
        raise HTTPException(
            status_code=500, 
            detail=f"Failed to launch ETL topics analysis task: {str(e)}"
        )

@router.get("/distribution", tags=["Topics"])
async def get_distribution(
    token: JWTLectureTokenPayload = Depends(require_token_types(allowed_types=["cognito"])),
    db: Session = Depends(get_db)
):
    try:
        user = get_user_by_cognito_id(db, token.sub)
        if user.role != UserRole.admin:
            raise HTTPException(
                status_code=403,
                detail="You are not authorized to access topics information."
            )
        
        chatbot_ids = await get_chatbot_ids_by_group(db, user.group_id)
        if not chatbot_ids:
            ic(f"No chatbots found for group {user.group_id}")
            return {}
        
        conversation_topics = await get_conversation_topics_for_chatbots(db, chatbot_ids)
        if not conversation_topics:
            ic(f"No conversation topics found for group {user.group_id}")
            return {}
        
        grouped_by_global_topic = defaultdict(list)
        for conversation_topic in conversation_topics:
            grouped_by_global_topic[conversation_topic.global_topic].append(conversation_topic)

        response = {
            global_topic: {
                "count": len(topics_list),
                "chatbots": [
                    {
                        "id": str(topic.chatbot_id),
                        "topics": ",".join(topic.topics)
                    }
                    for topic in topics_list
                ]
            }
            for global_topic, topics_list in grouped_by_global_topic.items()
        }

        return response
    except HTTPException as e:
        raise e
    except Exception as e:
        raise HTTPException(
            status_code=500, 
            detail=f"Failed to get topics distribution: {str(e)}"
        )

@router.post("/configuration", tags=["Topics"])
async def create_configuration(
    configuration: ETLTaskTopicsAnalysisConfiguration,
    token: JWTLectureTokenPayload = Depends(require_token_types(allowed_types=["cognito"])),
    db: Session = Depends(get_db)
):
    try:
        user = get_user_by_cognito_id(db, token.sub)
        if user.role != UserRole.admin:
            raise HTTPException(
                status_code=403,
                detail="You are not authorized to create ETL task configurations"
            )

        if await get_etl_task_configuration_by_type_and_group(db, ETLTaskType.topics_analysis, user.group_id):
            raise HTTPException(
                status_code=400,
                detail="A configuration already exists for the user's group"
            )

        await create_etl_task_configuration(db, ETLTaskType.topics_analysis, user.group_id, configuration.model_dump())
        return {"message": "ETL task configuration created"}
    except HTTPException as e:
        raise e
    except Exception as e:
        raise HTTPException(
            status_code=500, 
            detail=f"Failed to create ETL task configuration: {str(e)}"
        )

@router.get("/configuration", tags=["Topics"])
async def get_configuration(
    token: JWTLectureTokenPayload = Depends(require_token_types(allowed_types=["cognito"])),
    db: Session = Depends(get_db)
):
    try:
        user = get_user_by_cognito_id(db, token.sub)
        if user.role != UserRole.admin:
            raise HTTPException(
                status_code=403,
                detail="You are not authorized to access ETL task configurations"
            )
        
        configuration = await get_etl_task_configuration_by_type_and_group(db, ETLTaskType.topics_analysis, user.group_id)
        if not configuration:
            return {}
        
        return {
            "id": configuration.id,
            "type": configuration.type,
            "configuration": configuration.configuration,
            "created_at": configuration.created_at,
            "updated_at": configuration.updated_at
        }
    except HTTPException as e:
        raise e
    except Exception as e:
        raise HTTPException(
            status_code=500, 
            detail=f"Failed to get ETL task configuration: {str(e)}"
        )

@router.patch("/configuration", tags=["Topics"])
async def update_configuration(
    configuration: ETLTaskTopicsAnalysisConfiguration,
    token: JWTLectureTokenPayload = Depends(require_token_types(allowed_types=["cognito"])),
    db: Session = Depends(get_db)
):
    try:
        user = get_user_by_cognito_id(db, token.sub)
        if user.role != UserRole.admin:
            raise HTTPException(
                status_code=403,
                detail="You are not authorized to update ETL task configurations"
            )
        
        updated_config = await update_etl_task_configuration(db, ETLTaskType.topics_analysis, user.group_id, configuration.model_dump())
        if not updated_config:
            raise HTTPException(
                status_code=404,
                detail="No configuration found for the user's group to update"
            )
        
        return {"message": "ETL task configuration updated successfully"}
    except HTTPException as e:
        raise e
    except Exception as e:
        raise HTTPException(
            status_code=500, 
            detail=f"Failed to update ETL task configuration: {str(e)}"
        )

@router.delete("/configuration", tags=["Topics"])
async def delete_configuration(
    token: JWTLectureTokenPayload = Depends(require_token_types(allowed_types=["cognito"])),
    db: Session = Depends(get_db)
):
    try:
        user = get_user_by_cognito_id(db, token.sub)
        if user.role != UserRole.admin:
            raise HTTPException(
                status_code=403,
                detail="You are not authorized to delete ETL task configurations"
            )
        
        # Check if configuration exists before deletion
        configuration = await get_etl_task_configuration_by_type_and_group(db, ETLTaskType.topics_analysis, user.group_id)
        if not configuration:
            raise HTTPException(
                status_code=404,
                detail="No configuration found for the user's group to delete"
            )
        
        # Get chatbot IDs for the group to clean up conversation topics
        chatbot_ids = await get_chatbot_ids_by_group(db, user.group_id)
        if chatbot_ids:
            # Delete all conversation topics for this group's chatbots
            deleted_topics_count = await delete_conversation_topics_for_chatbots(db, chatbot_ids)
            ic(f"Deleted {deleted_topics_count} conversation topics for group {user.group_id}")
        
        # Delete the configuration
        deleted = await delete_etl_task_configuration(db, ETLTaskType.topics_analysis, user.group_id)
        if not deleted:
            raise HTTPException(
                status_code=404,
                detail="Failed to delete configuration"
            )
        
        return {"message": "ETL task configuration and related conversation topics deleted successfully"}
    except HTTPException as e:
        raise e
    except Exception as e:
        raise HTTPException(
            status_code=500, 
            detail=f"Failed to delete ETL task configuration: {str(e)}"
        )

