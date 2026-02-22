"""Debug endpoints to test the agent and visualization pipeline."""

from fastapi import APIRouter, Depends
import json

from ..services.sql_tool import SQLTool
from ..services.agent_direct import DirectAgent
from ..utils.dependencies import get_sql_tool, get_llm_client

router = APIRouter(prefix="/api/debug", tags=["debug"])


@router.get("/test-sql")
async def test_sql_execution(sql_tool: SQLTool = Depends(get_sql_tool)):
    """Test SQL execution directly."""
    query = "SELECT Artist.Name, COUNT(Track.TrackId) as TrackCount FROM Artist JOIN Album ON Artist.ArtistId = Album.ArtistId JOIN Track ON Album.AlbumId = Track.AlbumId GROUP BY Artist.Name ORDER BY TrackCount DESC LIMIT 5"

    results, exec_time, error = await sql_tool.execute_query(query)

    return {
        "query": query,
        "results": results,
        "error": error,
        "execution_time": exec_time,
        "connection_string": sql_tool.connection_string is not None
    }


@router.get("/test-visualization")
async def test_visualization_generation():
    """Test visualization generation directly."""
    # Create a DirectAgent instance
    llm_client = get_llm_client()
    sql_tool = get_sql_tool()
    agent = DirectAgent(llm_client, sql_tool)

    # Test data
    test_results = [
        {"Name": "Iron Maiden", "TrackCount": 213},
        {"Name": "U2", "TrackCount": 135},
        {"Name": "Led Zeppelin", "TrackCount": 114},
        {"Name": "Metallica", "TrackCount": 112},
        {"Name": "Deep Purple", "TrackCount": 92}
    ]

    query = "SELECT Artist.Name, COUNT(*) as TrackCount FROM Artist GROUP BY Artist.Name ORDER BY TrackCount DESC LIMIT 5"
    question = "Show me the top 5 artists by number of tracks"

    visualizations = agent._generate_visualizations(test_results, query, question)

    return {
        "test_data": test_results,
        "visualizations_generated": len(visualizations),
        "visualizations": visualizations
    }


@router.post("/test-extraction")
async def test_sql_extraction(text: str):
    """Test SQL extraction from text."""
    llm_client = get_llm_client()
    sql_tool = get_sql_tool()
    agent = DirectAgent(llm_client, sql_tool)

    queries = agent._extract_sql_queries(text)

    return {
        "input_text": text,
        "extracted_queries": queries,
        "count": len(queries)
    }


@router.get("/test-full-pipeline")
async def test_full_pipeline():
    """Test the full pipeline with a simple query."""
    llm_client = get_llm_client()
    sql_tool = get_sql_tool()
    agent = DirectAgent(llm_client, sql_tool)

    # Simulate what should happen
    test_text = """
    I'll query the database to find the top 5 artists:

    ```sql
    SELECT Artist.Name, COUNT(Track.TrackId) as TrackCount
    FROM Artist
    JOIN Album ON Artist.ArtistId = Album.ArtistId
    JOIN Track ON Album.AlbumId = Track.AlbumId
    GROUP BY Artist.Name
    ORDER BY TrackCount DESC
    LIMIT 5
    ```

    This query joins the Artist, Album, and Track tables to count tracks per artist.
    """

    # Extract SQL
    queries = agent._extract_sql_queries(test_text)

    results_list = []
    visualizations_list = []

    for query in queries:
        # Execute query
        results, exec_time, error = await sql_tool.execute_query(query)
        results_list.append({
            "query": query,
            "results": results,
            "error": error,
            "row_count": len(results) if results else 0
        })

        # Generate visualizations
        if results:
            vizs = agent._generate_visualizations(results, query, "Top 5 artists")
            visualizations_list.extend(vizs)

    return {
        "test_text": test_text,
        "extracted_queries": queries,
        "execution_results": results_list,
        "visualizations": visualizations_list,
        "visualization_count": len(visualizations_list)
    }