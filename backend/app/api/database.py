"""Database configuration API endpoints."""

from fastapi import APIRouter, HTTPException, Depends

from ..models.requests import DatabaseConnectionRequest
from ..models.responses import DatabaseSchemaResponse
from ..services.sql_tool import SQLTool
from ..utils.dependencies import get_sql_tool

router = APIRouter(prefix="/api/database", tags=["database"])


@router.post("/connect")
async def connect_database(
    request: DatabaseConnectionRequest,
    sql_tool: SQLTool = Depends(get_sql_tool)
):
    """Configure database connection."""
    try:
        sql_tool.set_connection(
            connection_string=request.connection_string,
            database_type=request.database_type
        )

        # Test connection by getting schema
        schema = await sql_tool.get_schema()

        if "error" in schema:
            raise HTTPException(status_code=400, detail=schema["error"])

        return {
            "message": "Database connected successfully",
            "database_type": request.database_type,
            "tables_count": len(schema.get("tables", []))
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/schema", response_model=DatabaseSchemaResponse)
async def get_database_schema(
    table_name: str = None,
    sql_tool: SQLTool = Depends(get_sql_tool)
):
    """Get database schema information."""
    try:
        schema = await sql_tool.get_schema(table_name)

        if "error" in schema:
            raise HTTPException(status_code=400, detail=schema["error"])

        return DatabaseSchemaResponse(
            tables=schema.get("tables", []),
            connection_status="connected" if schema.get("tables") else "disconnected",
            database_type=schema.get("database_type", "unknown")
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))