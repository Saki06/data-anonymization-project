"""
AI Agent framework for dynamic recommendation improvement
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, List
from .models import RecommendationSet


class Agent(ABC):
    """Base class for any AI agent in the expert system."""

    @abstractmethod
    def analyze(self, profile: Dict[str, Any], recommendations: RecommendationSet) -> None:
        """Analyze profile and recommendations.
        Agents may modify the RecommendationSet in-place or
        provide feedback to the catalog/knowledge base.
        """
        pass

    @abstractmethod
    def name(self) -> str:
        """Return the agent's name or identifier."""
        pass


class AgentManager:
    """Orchestrates multiple agents and aggregates their insights."""

    def __init__(self):
        self.agents: List[Agent] = []

    def register_agent(self, agent: Agent) -> None:
        """Add an agent to the manager."""
        self.agents.append(agent)

    def evaluate(self, profile: Dict[str, Any], rec_set: RecommendationSet) -> None:
        """Run all agents against the profile and recommendations.
        Agents may update the recommendation set or attach notes.
        """
        for agent in self.agents:
            try:
                agent.analyze(profile, rec_set)
            except Exception as e:
                # log or ignore errors within agents
                print(f"Agent {agent.name()} failed: {e}")


# Example agents for illustration
class UtilityAgent(Agent):
    """Agent that evaluates utility impact and adjusts confidence."""

    def analyze(self, profile: Dict[str, Any], recommendations: RecommendationSet) -> None:
        # simple heuristic: if dataset is large, slightly increase confidence
        if profile.get('total_records', 0) > 10000:
            for rec in recommendations.recommendations:
                rec.confidence = min(1.0, rec.confidence + 0.05)

    def name(self) -> str:
        return "UtilityAgent"


class PrivacyAgent(Agent):
    """Agent that flags high privacy risk methods for monitoring."""

    def analyze(self, profile: Dict[str, Any], recommendations: RecommendationSet) -> None:
        # if more than 3 high-risk rules triggered, add a note
        if profile.get('num_high_risk', 0) >= 3:
            recommendations.additional_notes += " [PrivacyAgent: multiple high-risk conditions detected]"

    def name(self) -> str:
        return "PrivacyAgent"