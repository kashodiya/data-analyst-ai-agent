"""Session and message models."""

from datetime import datetime
from typing import List, Optional, Any, Dict
from pydantic import BaseModel, Field
import uuid


class ToolCall(BaseModel):
    """Represents a tool call made by the agent."""

    name: str = Field(..., description="Name of the tool")
    parameters: Dict[str, Any] = Field(default_factory=dict, description="Parameters passed to the tool")
    response: Any = Field(None, description="Response from the tool")
    execution_time: float = Field(0.0, description="Time taken to execute the tool in seconds")
    explanation: str = Field("", description="Explanation of why this tool was used")


class Message(BaseModel):
    """Represents a message in a conversation."""

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    session_id: str = Field(..., description="ID of the session this message belongs to")
    role: str = Field(..., description="Role of the message sender (user/assistant)")
    content: str = Field(..., description="Content of the message")
    tool_calls: List[ToolCall] = Field(default_factory=list, description="Tool calls made in this message")
    timestamp: datetime = Field(default_factory=datetime.utcnow, description="When the message was created")
    approach_explanation: Optional[str] = Field(None, description="Explanation of the agent's approach")
    sql_explanation: Optional[str] = Field(None, description="Plain language explanation of SQL queries")
    visualizations: Optional[List[Dict[str, Any]]] = Field(None, description="Chart configurations for data visualization")


class Session(BaseModel):
    """Represents a conversation session."""

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    title: str = Field("New Session", description="Title of the session")
    created_at: datetime = Field(default_factory=datetime.utcnow, description="When the session was created")
    updated_at: datetime = Field(default_factory=datetime.utcnow, description="When the session was last updated")
    messages: List[Message] = Field(default_factory=list, description="Messages in the session")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Additional session metadata")