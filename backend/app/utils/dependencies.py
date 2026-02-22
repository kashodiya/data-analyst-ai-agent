"""Dependency injection for FastAPI."""

from functools import lru_cache
from typing import Generator

from ..services.session_manager import SessionManager
from ..services.llm_client import LLMClient
from ..services.sql_tool import SQLTool
from ..services.agent import Agent
from ..services.agent_direct import DirectAgent
from ..config import settings


@lru_cache()
def get_session_manager() -> SessionManager:
    """Get session manager instance."""
    return SessionManager(settings.database_path)


@lru_cache()
def get_llm_client() -> LLMClient:
    """Get LLM client instance."""
    return LLMClient(
        base_url=settings.llm_base_url,
        api_key=settings.llm_api_key,
        model=settings.llm_model
    )


@lru_cache()
def get_sql_tool() -> SQLTool:
    """Get SQL tool instance."""
    from pathlib import Path
    sql_tool = SQLTool()

    # Auto-connect to Chinook database if it exists
    chinook_path = Path(__file__).parent.parent.parent.parent / "data" / "chinook.db"
    if chinook_path.exists():
        sql_tool.set_connection(str(chinook_path), "sqlite")
        import logging
        logging.getLogger(__name__).info(f"Auto-connected to Chinook database at {chinook_path}")

    return sql_tool


@lru_cache()
def get_agent():
    """Get agent instance - using DirectAgent for non-function-calling LLMs."""
    llm_client = get_llm_client()
    sql_tool = get_sql_tool()

    # Use DirectAgent which extracts SQL from response text
    # This works with LLMs that don't support function calling
    import logging
    logging.getLogger(__name__).info("Using DirectAgent for SQL extraction from text")
    return DirectAgent(llm_client, sql_tool)