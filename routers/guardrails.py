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
