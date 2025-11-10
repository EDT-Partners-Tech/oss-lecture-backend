# © [2025] EDT&Partners. Licensed under CC BY 4.0.

from typing import Optional

from utility.aws import bedrock_agent_client

class AgentRegistry:
    def __init__(self):
        print("AgentRegistry: Create the client")
        self.client = bedrock_agent_client
        print("AgentRegistry: Load the agents")
        self.agent_map = self._load_agents()

    def _load_agents(self) -> dict:
        """Loads the agents and their latest aliases when the class is instantiated."""
        print("AgentRegistry: Load the agents")
        try:
            agent_map = {}
            response = self.client.list_agents()

            for agent in response.get("agentSummaries", []):
                agent_id = agent.get("agentId")
                agent_name = agent.get("agentName")

                alias_response = self.client.list_agent_aliases(agentId=agent_id)
                aliases = sorted(
                    alias_response.get("agentAliasSummaries", []),
                    key=lambda a: a.get("createdAt", ""),
                    reverse=True
                )
                latest_alias = aliases[0] if aliases else {}

                agent_map[agent_name.lower()] = {
                    "agent_id": agent_id,
                    "alias_id": latest_alias.get("agentAliasId")
                }
                agent_map[agent_id] = {
                    "agent_id": agent_id,
                    "alias_id": latest_alias.get("agentAliasId")
                }

            return agent_map
        except Exception as e:
            print(f"AgentRegistry: Error loading the agents: {e}")
            return {}

    def get_ids_by_name(self, name: str) -> Optional[dict]:
        """Returns the IDs by name (case-insensitive)."""
        return self.agent_map.get(name.lower())
    
    def get_all_agents(self) -> dict:
        """Returns all agents."""
        return self.agent_map
    
    def get_alias_id_by_agent_id(self, agent_id: str) -> str:
        """Returns the alias ID by agent ID."""
        return self.agent_map.get(agent_id).get("alias_id")
    
    def get_list_agents(self) -> list:
        """Returns a list of all agents."""
        return self.client.list_agents()