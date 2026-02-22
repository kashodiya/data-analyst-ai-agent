"""SQL tool service for database operations."""

import re
import time
import sqlite3
import asyncio
from typing import Dict, Any, List, Optional, Tuple
from pathlib import Path
import logging

from ..config import settings

logger = logging.getLogger(__name__)


class SQLTool:
    """SQL tool for safe database operations."""

    def __init__(self, connection_string: Optional[str] = None):
        """Initialize the SQL tool."""
        self.connection_string = connection_string
        self.database_type = "sqlite"
        self.max_results = settings.max_sql_results
        self.query_timeout = settings.sql_query_timeout

    def set_connection(self, connection_string: str, database_type: str = "sqlite"):
        """Set the database connection."""
        self.connection_string = connection_string
        self.database_type = database_type

    def _is_safe_query(self, query: str) -> bool:
        """Check if a query is safe to execute (read-only)."""
        # Remove comments and normalize whitespace
        cleaned_query = re.sub(r'--.*$', '', query, flags=re.MULTILINE)
        cleaned_query = re.sub(r'/\*.*?\*/', '', cleaned_query, flags=re.DOTALL)
        cleaned_query = cleaned_query.strip().upper()

        # Check for dangerous operations
        dangerous_keywords = [
            'INSERT', 'UPDATE', 'DELETE', 'DROP', 'CREATE', 'ALTER',
            'TRUNCATE', 'REPLACE', 'MERGE', 'CALL', 'EXEC', 'EXECUTE'
        ]

        for keyword in dangerous_keywords:
            if re.search(r'\b' + keyword + r'\b', cleaned_query):
                return False

        # Must start with SELECT or WITH
        if not (cleaned_query.startswith('SELECT') or cleaned_query.startswith('WITH')):
            return False

        return True

    async def execute_query(self, query: str) -> Tuple[List[Dict[str, Any]], float, Optional[str]]:
        """
        Execute a SQL query safely.

        Returns:
            Tuple of (results, execution_time, error_message)
        """
        logger.info(f"SQL Tool - Connection string: {self.connection_string is not None}, Query: {query[:100]}")

        if not self.connection_string:
            logger.warning("No database connection configured")
            return [], 0.0, "No database connection configured"

        if not self._is_safe_query(query):
            return [], 0.0, "Query contains potentially unsafe operations. Only SELECT queries are allowed."

        start_time = time.time()
        error_message = None
        results = []

        try:
            if self.database_type == "sqlite":
                # For SQLite, we'll use a synchronous connection in an executor
                results = await asyncio.get_event_loop().run_in_executor(
                    None,
                    self._execute_sqlite_query,
                    query
                )
            else:
                error_message = f"Database type '{self.database_type}' not yet supported"

        except Exception as e:
            error_message = str(e)
            logger.error(f"Query execution error: {e}")

        execution_time = time.time() - start_time
        return results, execution_time, error_message

    def _execute_sqlite_query(self, query: str) -> List[Dict[str, Any]]:
        """Execute a query on SQLite database."""
        conn = sqlite3.connect(self.connection_string)
        conn.row_factory = sqlite3.Row
        conn.execute(f"PRAGMA query_timeout = {self.query_timeout * 1000}")  # Convert to ms

        try:
            cursor = conn.cursor()
            cursor.execute(query)
            rows = cursor.fetchmany(self.max_results)

            results = []
            for row in rows:
                results.append(dict(row))

            return results

        finally:
            conn.close()

    async def get_schema(self, table_name: Optional[str] = None) -> Dict[str, Any]:
        """Get database schema information."""
        if not self.connection_string:
            return {
                "error": "No database connection configured",
                "tables": []
            }

        schema_info = {
            "database_type": self.database_type,
            "tables": []
        }

        try:
            if self.database_type == "sqlite":
                schema_info["tables"] = await asyncio.get_event_loop().run_in_executor(
                    None,
                    self._get_sqlite_schema,
                    table_name
                )
            else:
                schema_info["error"] = f"Database type '{self.database_type}' not yet supported"

        except Exception as e:
            schema_info["error"] = str(e)
            logger.error(f"Schema retrieval error: {e}")

        return schema_info

    def _get_sqlite_schema(self, table_name: Optional[str] = None) -> List[Dict[str, Any]]:
        """Get SQLite database schema."""
        conn = sqlite3.connect(self.connection_string)
        conn.row_factory = sqlite3.Row

        try:
            cursor = conn.cursor()
            tables = []

            if table_name:
                # Get specific table schema
                cursor.execute(f"PRAGMA table_info({table_name})")
                columns = []
                for row in cursor.fetchall():
                    columns.append({
                        "name": row["name"],
                        "type": row["type"],
                        "nullable": not row["notnull"],
                        "default": row["dflt_value"],
                        "primary_key": bool(row["pk"])
                    })

                if columns:
                    tables.append({
                        "name": table_name,
                        "columns": columns
                    })

            else:
                # Get all tables
                cursor.execute("""
                    SELECT name FROM sqlite_master
                    WHERE type='table' AND name NOT LIKE 'sqlite_%'
                    ORDER BY name
                """)
                table_names = [row["name"] for row in cursor.fetchall()]

                for tbl in table_names:
                    cursor.execute(f"PRAGMA table_info({tbl})")
                    columns = []
                    for row in cursor.fetchall():
                        columns.append({
                            "name": row["name"],
                            "type": row["type"],
                            "nullable": not row["notnull"],
                            "default": row["dflt_value"],
                            "primary_key": bool(row["pk"])
                        })

                    # Get row count
                    cursor.execute(f"SELECT COUNT(*) as count FROM {tbl}")
                    row_count = cursor.fetchone()["count"]

                    tables.append({
                        "name": tbl,
                        "columns": columns,
                        "row_count": row_count
                    })

            return tables

        finally:
            conn.close()

    def explain_query(self, query: str, results: Optional[List[Dict[str, Any]]] = None) -> str:
        """Generate a plain language explanation of a SQL query."""
        explanation_parts = []
        query_upper = query.upper()

        # Extract table names from the query
        tables_mentioned = []
        from_match = re.search(r'FROM\s+(\w+)', query_upper)
        if from_match:
            tables_mentioned.append(from_match.group(1).lower())
        join_matches = re.findall(r'JOIN\s+(\w+)', query_upper)
        tables_mentioned.extend([t.lower() for t in join_matches])

        # Build natural language explanation
        explanation_parts.append("**Query Breakdown:**\n")

        # Main action
        if "COUNT(" in query_upper and "GROUP BY" in query_upper:
            explanation_parts.append("• Counting records for each group")
        elif "COUNT(" in query_upper:
            explanation_parts.append("• Counting the number of records")
        elif "SUM(" in query_upper:
            explanation_parts.append("• Calculating total/sum values")
        elif "AVG(" in query_upper:
            explanation_parts.append("• Computing average values")
        elif "MAX(" in query_upper and "MIN(" in query_upper:
            explanation_parts.append("• Finding both maximum and minimum values")
        elif "MAX(" in query_upper:
            explanation_parts.append("• Finding maximum values")
        elif "MIN(" in query_upper:
            explanation_parts.append("• Finding minimum values")
        else:
            explanation_parts.append("• Selecting data")

        # Tables involved
        if tables_mentioned:
            if len(tables_mentioned) == 1:
                explanation_parts.append(f"• From the {tables_mentioned[0]} table")
            else:
                explanation_parts.append(f"• From tables: {', '.join(set(tables_mentioned))}")

        # JOIN explanation
        if "JOIN" in query_upper:
            join_count = query_upper.count("JOIN")
            if "INNER JOIN" in query_upper:
                explanation_parts.append(f"• Using {join_count} inner join(s) to connect related data")
            elif "LEFT JOIN" in query_upper:
                explanation_parts.append(f"• Using {join_count} left join(s) to include all records from the primary table")
            elif "RIGHT JOIN" in query_upper:
                explanation_parts.append(f"• Using {join_count} right join(s)")
            else:
                explanation_parts.append(f"• Joining {join_count + 1} tables together based on relationships")

        # WHERE clause
        if "WHERE" in query_upper:
            where_conditions = []
            if ">" in query or "<" in query or ">=" in query or "<=" in query:
                where_conditions.append("numeric comparisons")
            if "LIKE" in query_upper:
                where_conditions.append("pattern matching")
            if "IN (" in query_upper:
                where_conditions.append("checking against a list of values")
            if "BETWEEN" in query_upper:
                where_conditions.append("range checking")
            if "IS NULL" in query_upper or "IS NOT NULL" in query_upper:
                where_conditions.append("null value checking")

            if where_conditions:
                explanation_parts.append(f"• Filtering with: {', '.join(where_conditions)}")
            else:
                explanation_parts.append("• Applying filter conditions")

        # GROUP BY
        if "GROUP BY" in query_upper:
            explanation_parts.append("• Grouping results by specific columns for aggregation")

        # HAVING
        if "HAVING" in query_upper:
            explanation_parts.append("• Filtering grouped results based on aggregate conditions")

        # ORDER BY
        if "ORDER BY" in query_upper:
            if "DESC" in query_upper:
                explanation_parts.append("• Sorting results in descending order (highest to lowest)")
            else:
                explanation_parts.append("• Sorting results in ascending order (lowest to highest)")

        # CASE statements
        if "CASE" in query_upper:
            explanation_parts.append("• Using conditional logic to categorize or transform data")

        # Window functions
        if "OVER (" in query_upper or "OVER(" in query_upper:
            if "ROW_NUMBER()" in query_upper:
                explanation_parts.append("• Assigning row numbers for ranking")
            elif "RANK()" in query_upper:
                explanation_parts.append("• Ranking records with ties")
            elif "PERCENT" in query_upper:
                explanation_parts.append("• Calculating percentages or proportions")
            else:
                explanation_parts.append("• Using window functions for advanced calculations")

        # Subqueries
        if query_upper.count("SELECT") > 1:
            explanation_parts.append("• Using subqueries for complex data retrieval")

        # LIMIT
        if "LIMIT" in query_upper:
            limit_match = re.search(r'LIMIT\s+(\d+)', query_upper)
            if limit_match:
                limit_value = limit_match.group(1)
                explanation_parts.append(f"• Restricting output to {limit_value} records")

        # Add result summary
        if results is not None:
            explanation_parts.append("\n**Results:**")
            result_count = len(results)

            if result_count == 0:
                explanation_parts.append("• No matching records found")
            elif result_count == 1:
                explanation_parts.append("• Found 1 matching record")
            else:
                explanation_parts.append(f"• Retrieved {result_count} records")

            if result_count > 0:
                columns = list(results[0].keys())
                if len(columns) <= 5:
                    explanation_parts.append(f"• Columns returned: {', '.join(columns)}")
                else:
                    explanation_parts.append(f"• Returned {len(columns)} columns of data")

                # Describe the nature of results if we can infer it
                if "revenue" in str(columns).lower() or "total" in str(columns).lower() or "sum" in str(columns).lower():
                    explanation_parts.append("• Shows financial/numerical summaries")
                if "count" in str(columns).lower():
                    explanation_parts.append("• Shows frequency or quantity data")
                if "name" in str(columns).lower() or "title" in str(columns).lower():
                    explanation_parts.append("• Includes descriptive information")

        return "\n".join(explanation_parts)