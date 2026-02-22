"""Session management API endpoints."""

from typing import List, Optional
from fastapi import APIRouter, HTTPException, Depends

from ..models.requests import CreateSessionRequest
from ..models.responses import SessionResponse, SessionListResponse, MessageResponse
from ..models.session import Session, Message
from ..services.session_manager import SessionManager
from ..utils.dependencies import get_session_manager

router = APIRouter(prefix="/api/sessions", tags=["sessions"])


@router.post("", response_model=SessionResponse)
async def create_session(
    request: CreateSessionRequest,
    session_manager: SessionManager = Depends(get_session_manager)
):
    """Create a new session."""
    try:
        session = await session_manager.create_session(
            title=request.title,
            metadata=request.metadata
        )

        return SessionResponse(
            id=session.id,
            title=session.title,
            created_at=session.created_at,
            updated_at=session.updated_at,
            message_count=0,
            metadata=session.metadata
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("", response_model=SessionListResponse)
async def list_sessions(
    limit: int = 50,
    offset: int = 0,
    session_manager: SessionManager = Depends(get_session_manager)
):
    """List all sessions."""
    try:
        sessions = await session_manager.list_sessions(limit=limit, offset=offset)

        session_responses = []
        for session in sessions:
            session_responses.append(SessionResponse(
                id=session.id,
                title=session.title,
                created_at=session.created_at,
                updated_at=session.updated_at,
                message_count=len(session.messages),
                metadata=session.metadata
            ))

        return SessionListResponse(
            sessions=session_responses,
            total=len(session_responses)
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{session_id}", response_model=Session)
async def get_session(
    session_id: str,
    include_messages: bool = True,
    session_manager: SessionManager = Depends(get_session_manager)
):
    """Get a specific session."""
    try:
        session = await session_manager.get_session(
            session_id=session_id,
            include_messages=include_messages
        )

        if not session:
            raise HTTPException(status_code=404, detail="Session not found")

        return session
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{session_id}")
async def delete_session(
    session_id: str,
    session_manager: SessionManager = Depends(get_session_manager)
):
    """Delete a session."""
    try:
        success = await session_manager.delete_session(session_id)

        if not success:
            raise HTTPException(status_code=404, detail="Session not found")

        return {"message": "Session deleted successfully"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/{session_id}/title")
async def update_session_title(
    session_id: str,
    title: str,
    session_manager: SessionManager = Depends(get_session_manager)
):
    """Update session title."""
    try:
        success = await session_manager.update_session_title(session_id, title)

        if not success:
            raise HTTPException(status_code=404, detail="Session not found")

        return {"message": "Session title updated successfully"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))