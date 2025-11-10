# © [2025] EDT&Partners. Licensed under CC BY 4.0.

from database.crud import (
    get_messages_by_chatbot_id,  
    update_etl_task_status,
    save_conversation_topics,
    get_all_conversation_topics,
)
from sqlalchemy.orm import Session
from typing import List, Optional
from icecream import ic
from database.schemas import ETLTaskTopicsAnalysisConfiguration, NotificationAction
from uuid import UUID

from utility.topics_utils import extract_topics_from_messages, compute_global_topics
from utility.async_manager import AsyncManager


async def process_conversation_topics(
    db: Session,
    user_id: str,
    chatbot_ids: List[UUID],
    configuration: ETLTaskTopicsAnalysisConfiguration,
    etl_task_id: Optional[UUID] = None
):
    """
    Process conversations for each chatbot and extract topics.
    Saves results to ConversationTopics table.
    """
    ic("Starting conversation topics processing...")
    
    try:
        appsync_manager = AsyncManager()
        appsync_manager.set_parameters()

        # Update ETL task status to running
        if etl_task_id:
            await update_etl_task_status(db, etl_task_id, "running")
            await appsync_manager.send_event_with_notification(
                db=db,
                user_id=user_id,
                service_id="topic_analysis",
                title="Topics analysis task started",
                body="Topics analysis task in progress...",
                use_push_notification=True,
                notification_type="info",
            )
        
        # Get processed chatbot IDs if overwrite is disabled
        if not configuration.overwrite:
            ic("Overwrite is disabled, retrieving conversations with topics...")
            conversations_with_topics = await get_all_conversation_topics(db)
            processed_chatbot_ids = [str(conversation.chatbot_id) for conversation in conversations_with_topics]
        else:
            processed_chatbot_ids = []

        # Filter out already processed chatbots
        chatbot_ids = [chatbot_id for chatbot_id in chatbot_ids if str(chatbot_id) not in processed_chatbot_ids]
        ic(f"Found {len(chatbot_ids)} chatbots to process")
        
        if not chatbot_ids:
            ic("No chatbots to process")
            if etl_task_id:
                await update_etl_task_status(db, etl_task_id, "completed", "success")
                await appsync_manager.send_event_with_notification(
                    db=db,
                    user_id=user_id,
                    service_id="topic_analysis",
                    title="Topics analysis task completed!",
                    body="No chatbots to process.",
                    use_push_notification=True,
                    notification_type="warning",
                )
            return

        # Process each chatbot
        processed_count = 0
        failed_count = 0
        
        for i, chatbot_id in enumerate(chatbot_ids):
            try:
                ic(f"Processing chatbot {i+1}/{len(chatbot_ids)}: {chatbot_id}")
                
                # Get messages for this chatbot, ordered by created_at
                messages_data = await get_messages_by_chatbot_id(db, chatbot_id)
                
                if not messages_data:
                    ic(f"No messages found for chatbot {chatbot_id}")
                    continue
                
                # Extract message content
                messages = []
                for msg in messages_data:
                    if hasattr(msg, 'content') and msg.content:
                        # Skip very short messages (likely just greetings)
                        if len(msg.content.strip()) > 5:
                            messages.append(msg.content.strip())
                
                if not messages:
                    ic(f"No meaningful messages found for chatbot {chatbot_id}")
                    continue
                
                ic(f"Found {len(messages)} messages for chatbot {chatbot_id}")
                
                # Extract topics using LLM
                topics = await extract_topics_from_messages(messages)
                ic(f"Extracted topics for chatbot {chatbot_id}: {topics}")
                
                # Save topics to database
                await save_conversation_topics(db, chatbot_id, topics)
                processed_count += 1
                
                ic(f"Saved topics for chatbot {chatbot_id}: {topics}")
                
            except Exception as e:
                ic(f"Error processing chatbot {chatbot_id}: {str(e)}")
                failed_count += 1
                continue
        
        ic(f"Processing completed. Processed: {processed_count}, Failed: {failed_count}")
        
        ic("Computing global topics...")
        await compute_global_topics(db, chatbot_ids, configuration.max_supertopics)
        ic("Global topics computed")

        # Update ETL task status
        if etl_task_id:
            if failed_count > 0 and processed_count == 0:
                await update_etl_task_status(db, etl_task_id, "failed", "error")
                await appsync_manager.send_event_with_notification(
                    db=db,
                    user_id=user_id,
                    service_id="topic_analysis",
                    title="Topics analysis task failed!",
                    body="Some chatbots failed to process.",
                    use_push_notification=True,
                    notification_type="error",
                )
            else:
                await update_etl_task_status(db, etl_task_id, "completed", "success")
                await appsync_manager.send_event_with_notification(
                    db=db,
                    user_id=user_id,
                    service_id="topic_analysis",
                    title="Topics analysis task completed!",
                    body="All chatbots processed successfully. You can now view the analysis results in the analytics dashboard.",
                    use_push_notification=True,
                    notification_type="success",
                    actions=[
                        NotificationAction(
                            label="Go to analytics dashboard",
                            action="navigate",
                            url="/analytics",
                            style="default"
                        )
                    ]
                )
    except Exception as e:
        ic(f"Critical error in conversation topics processing: {str(e)}")
        if etl_task_id:
            await update_etl_task_status(db, etl_task_id, "failed", "error")
            await appsync_manager.send_event_with_notification(
                db=db,
                user_id=user_id,
                service_id="topic_analysis",
                title="Topics analysis task failed!",
                body="Critical error while processing chatbots.",
                use_push_notification=True,
                notification_type="error",
            )
        raise
