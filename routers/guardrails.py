# © [2025] EDT&Partners. Licensed under CC BY 4.0.

from utility.agent_registry import AgentRegistry
from utility.aws import get_guardrails
from utility.auth import require_token_types
from database.db import get_db
from sqlalchemy.orm import Session
from fastapi import APIRouter, HTTPException, Depends
from utility.tokens import JWTLectureTokenPayload

router = APIRouter()

@router.get("/")
async def get_all_guardrails(
    token: JWTLectureTokenPayload = Depends(require_token_types(["cognito"])), 
    db: Session = Depends(get_db)
):
    try:
        guardrails = await get_guardrails()
        return guardrails
    except Exception as he:
        raise he

@router.get("/by-agent")
async def get_all_guardrails(
    token: JWTLectureTokenPayload = Depends(require_token_types(["cognito"])), 
    db: Session = Depends(get_db)
):
    try:
        agent_registry = AgentRegistry()
        all_agents = agent_registry.get_list_agents()
        guardrails = await get_guardrails()

        for agent in all_agents.get("agentSummaries", []):
            if(agent.get("guardrailConfiguration") is None):
                agent["guardrailConfiguration"] = {}
            else:
                guardrail = agent.get("guardrailConfiguration", {})
                print("agent:", agent)
                guardrail_id = guardrail.get("guardrailIdentifier", None)
                guardrail_ver = guardrail.get("guardrailVersion", None)
                if guardrail_id:
                    guardrail_details = next(
                        (gr for gr in guardrails if gr["id"] == guardrail_id),
                        {}
                    )
                    guardrail_details["published_version"] = guardrail_ver
                    agent["guardrailConfiguration"] = guardrail_details
                print("Guardrail Configuration:", guardrail_details)
            

        return all_agents.get("agentSummaries", [])
    except Exception as he:
        raise he
    
    
@router.get("/{guardrail_id}")
async def get_guardrail_by_id(
    guardrail_id: str,
    token: JWTLectureTokenPayload = Depends(require_token_types(["cognito"])),
    db: Session = Depends(get_db)
):
    try:
        guardrails = await get_guardrails()
        guardrail = next((gr for gr in guardrails if gr["id"] == guardrail_id), None)
        if not guardrail:
            raise HTTPException(status_code=404, detail="Guardrail not found")
        return guardrail
    except Exception as he:
        raise he
