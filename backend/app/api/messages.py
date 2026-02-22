"""Message handling API endpoints."""

import json
from fastapi import APIRouter, HTTPException, Depends
from fastapi.responses import StreamingResponse
from sse_starlette.sse import EventSourceResponse

from ..models.requests import SendMessageRequest
from ..models.session import Message
from ..services.session_manager import SessionManager
from ..services.agent import Agent
from ..utils.dependencies import get_session_manager, get_agent

router = APIRouter(prefix="/api/sessions", tags=["messages"])


@router.post("/{session_id}/messages")
async def send_message(
    session_id: str,
    request: SendMessageRequest,
    session_manager: SessionManager = Depends(get_session_manager),
    agent: Agent = Depends(get_agent)
):
    """Send a message in a session and get streaming response."""
    try:
        # Get the session
        session = await session_manager.get_session(session_id)
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")

        # Add user message to session
        user_message = Message(
            session_id=session_id,
            role="user",
            content=request.content
        )
        await session_manager.add_message(session_id, user_message)

        # Create generator for SSE
        async def generate():
            assistant_content = ""
            tool_calls = []
            approach_explanation = None
            sql_explanation = None
            visualizations = []

            try:
                async for chunk in agent.process_message(
                    message=request.content,
                    session_messages=session.messages,
                    include_approach=request.include_approach,
                    include_sql_explanation=request.include_sql_explanation
                ):
                    # Send chunk to client
                    yield {
                        "event": "message",
                        "data": json.dumps(chunk.model_dump())
                    }

                    # Accumulate response for saving
                    if chunk.type == "text":
                        assistant_content += chunk.content
                    elif chunk.type == "tool_call":
                        tool_calls.append(chunk.tool_call)
                    elif chunk.type == "approach":
                        approach_explanation = chunk.content
                    elif chunk.type == "sql_explanation":
                        sql_explanation = chunk.content
                    elif chunk.type == "visualization":
                        visualizations.append(chunk.visualization)

                # Save assistant message
                assistant_message = Message(
                    session_id=session_id,
                    role="assistant",
                    content=assistant_content,
                    tool_calls=[],  # Tool calls are already serialized
                    approach_explanation=approach_explanation,
                    sql_explanation=sql_explanation,
                    visualizations=visualizations if visualizations else None
                )
                await session_manager.add_message(session_id, assistant_message)

                # Send completion event
                yield {
                    "event": "done",
                    "data": json.dumps({"message_id": assistant_message.id})
                }

            except Exception as e:
                yield {
                    "event": "error",
                    "data": json.dumps({"error": str(e)})
                }

        return EventSourceResponse(generate())

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{session_id}/stream")
async def stream_messages(
    session_id: str,
    session_manager: SessionManager = Depends(get_session_manager)
):
    """Get Server-Sent Events stream for a session."""
    try:
        # Verify session exists
        session = await session_manager.get_session(session_id, include_messages=False)
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")

        async def generate():
            yield {
                "event": "connected",
                "data": json.dumps({"session_id": session_id})
            }

        return EventSourceResponse(generate())

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))