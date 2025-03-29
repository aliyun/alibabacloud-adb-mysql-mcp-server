import asyncio
import os

import pymysql
from mcp.server import Server
from mcp.types import Resource, ResourceTemplate, Tool, TextContent
from pydantic import AnyUrl


def get_db_config():
    config = {
        "host": os.getenv("ADB_MYSQL_HOST", "localhost"),
        "port": int(os.getenv("ADB_MYSQL_PORT", 3306)),
        "user": os.getenv("ADB_MYSQL_USER"),
        "password": os.getenv("ADB_MYSQL_PASSWORD"),
        "database": os.getenv("ADB_MYSQL_DATABASE"),
    }

    if not all([config["user"], config["password"], config["database"]]):
        raise ValueError("Missing required database configuration")

    return config


app = Server(
    name="adb-mysql-mcp-server",
    version="1.0.0"
)


@app.list_resources()
async def list_resources() -> list[Resource]:
    return [
        Resource(
            uri="adbmysql:///databases",
            name="All of the databases",
            description="Display all of the databases in Adb MySQL",
            mimeType="text/plain"
        )
    ]


@app.list_resource_templates()
async def list_resource_templates() -> list[ResourceTemplate]:
    return [
        ResourceTemplate(
            uriTemplate="adbmysql:///{database}/tables",
            name="Database Tables",
            description="Get all the tables in a specific database",
            mimeType="text/plain"
        ),
        ResourceTemplate(
            uriTemplate="adbmysql:///{database}/{table}/ddl",
            name="Table DDL",
            description="Get the DDL script of a table in a specific database",
            mimeType="text/plain"
        ),
        ResourceTemplate(
            uriTemplate="adbmysql:///config/{key}/value",
            name="Database Config",
            description="Get the value for a config key in the cluster",
            mimeType="text/plain"
        ),
    ]


@app.read_resource()
async def read_resource(uri: AnyUrl) -> str:
    config = get_db_config()
    uri_str = str(uri)

    if not uri_str.startswith("adbmysql:///"):
        raise ValueError(f"Invalid URI: {uri_str}")

    conn = pymysql.connect(**config)
    conn.autocommit(True)
    cursor = conn.cursor()

    try:
        if uri_str.startswith("adbmysql:///"):
            paths = uri_str[12:].split("/")
            if paths[0] == "databases":
                query = "show databases;"
                cursor.execute(query)
                databases = cursor.fetchall()
                return "\n".join([database[0] for database in databases])
            elif len(paths) == 2 and paths[1] == "tables":
                database = paths[0]
                query = f"show tables from {database};"
                cursor.execute(query)
                tables = cursor.fetchall()
                return "\n".join([table[0] for table in tables])
            elif len(paths) == 3 and paths[2] == "ddl":
                database = paths[0]
                table = paths[1]
                query = f"show create table {database}.{table};"
                cursor.execute(query)
                ddl = cursor.fetchone()
                return ddl[1] if ddl and ddl[1] else f"No DDL Found for {database}.{table}"
            elif len(paths) == 3 and paths[0] == "config" and paths[2] == "value":
                key = paths[1]
                query = f"""show adb_config key={key}"""
                cursor.execute(query)
                value = cursor.fetchone()
                return value[1] if value and value[1] else f"No Config Value Found for {key}"
            else:
                raise ValueError(f"Invalid mcp resource URI format:  {uri_str}")
        else:
            raise ValueError(f"Invalid resource URI format:  {uri_str}")

    except pymysql.Error as e:
        raise RuntimeError(f"Database error: {str(e)}")
    finally:
        if cursor:
            cursor.close()
        if conn.open:
            conn.close()


@app.list_tools()
async def list_tools() -> list[Tool]:
    return [
        Tool(
            name="execute_sql",
            description="Execute a SQL query in the Adb MySQL Cluster",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "The SQL query to execute"
                    }
                },
                "required": ["query"]
            },
        ),
        Tool(
            name="get_query_plan",
            description="Get the query plan for a SQL query",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "The SQL query to analyze"
                    }
                },
                "required": ["query"]
            },
        ),
        Tool(
            name="get_execution_plan",
            description="Get the actual execution plan with runtime statistics for a SQL query",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "The SQL query to analyze"
                    }
                },
                "required": ["query"]
            }
        )
    ]


@app.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    """Execute SQL commands."""
    config = get_db_config()

    if name == "execute_sql":
        query = arguments.get("query")
        if not query:
            raise ValueError("Query is required")
    elif name == "get_query_plan":
        query = arguments.get("query")
        if not query:
            raise ValueError("Query is required")
        query = f"EXPLAIN {query}"
    elif name == "get_execution_plan":
        query = arguments.get("query")
        if not query:
            raise ValueError("Query is required")
        query = f"EXPLAIN ANALYZE {query}"
    else:
        raise ValueError(f"Unknown tool: {name}")

    conn = pymysql.connect(**config)
    conn.autocommit(True)
    cursor = conn.cursor()

    try:
        # Execute the query
        cursor.execute(query)

        columns = [desc[0] for desc in cursor.description]
        rows = cursor.fetchall()
        result = [",".join(map(str, row)) for row in rows]
        return [TextContent(type="text", text="\n".join([",".join(columns)] + result))]
    except Exception as e:
        return [TextContent(type="text", text=f"Error executing query: {str(e)}")]
    finally:
        if cursor:
            cursor.close()
        if conn.open:
            conn.close()


async def main():
    from mcp.server.stdio import stdio_server

    async with stdio_server() as (read_stream, write_stream):
        try:
            await app.run(
                read_stream,
                write_stream,
                app.create_initialization_options()
            )
        except Exception as e:
            raise


if __name__ == "__main__":
    asyncio.run(main())
