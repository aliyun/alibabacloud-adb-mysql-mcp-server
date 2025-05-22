# AnalyticDB for MySQL MCP Server

AnalyticDB for MySQL MCP Server serves as a universal interface between AI Agents and [AnalyticDB for MySQL](https://www.alibabacloud.com/en/product/analyticdb-for-mysql) databases. It enables seamless communication between AI Agents and AnalyticDB for MySQL, helping AI Agents
retrieve AnalyticDB for MySQL database metadata and execute SQL operations.

## 1. MCP Client Configuration

### Mode 1: Using Local File

- #### Download the GitHub repository

```shell
git clone https://github.com/aliyun/alibabacloud-adb-mysql-mcp-server
```

- #### MCP Integration

Add the following configuration to the MCP client configuration file:

```json
{
  "mcpServers": {
    "adb-mysql-mcp-server": {
      "command": "uv",
      "args": [
        "--directory",
        "/path/to/alibabacloud-adb-mysql-mcp-server",
        "run",
        "adb-mysql-mcp-server"
      ],
      "env": {
        "ADB_MYSQL_HOST": "host",
        "ADB_MYSQL_PORT": "port",
        "ADB_MYSQL_USER": "database_user",
        "ADB_MYSQL_PASSWORD": "database_password",
        "ADB_MYSQL_DATABASE": "database"
      }
    }
  }
}
```

### Mode 2: Using PIP Mode

- #### Installation

Install MCP Server using the following package:

```bash
pip install adb-mysql-mcp-server
```

-  #### MCP Integration

Add the following configuration to the MCP client configuration file:

```json
 {
  "mcpServers": {
    "adb-mysql-mcp-server": {
      "command": "uv",
      "args": [
        "run",
        "--with",
        "adb-mysql-mcp-server",
        "adb-mysql-mcp-server"
      ],
      "env": {
        "ADB_MYSQL_HOST": "host",
        "ADB_MYSQL_PORT": "port",
        "ADB_MYSQL_USER": "database_user",
        "ADB_MYSQL_PASSWORD": "database_password",
        "ADB_MYSQL_DATABASE": "database"
      }
    }
  }
}
```

## 2. Develop your own AnalyticDB for MySQL MCP server

If you want to develop your own AnalyticDB for MySQL MCP Server, you can install the python dependency packages using the following command:

1. Download the [source code from GitHub](https://github.com/aliyun/alibabacloud-adb-mysql-mcp-server).
2. Install  [uv](https://docs.astral.sh/uv/getting-started/installation/) package manager.
3. Install [Node.js](https://nodejs.org/en/download) which provides a node package tool whose name is `npx`
4. Install the python dependencies in the root diretory of the project using the following command:

```shell
uv pip install -r pyproject.toml 
```

5. If you want to debug the mcp server locally, you could start up an [MCP Inspector](https://modelcontextprotocol.io/docs/tools/inspector) using the following command:

```shell
npx @modelcontextprotocol/inspector  \
-e ADB_MYSQL_HOST=your_host \
-e ADB_MYSQL_PORT=your_port \
-e ADB_MYSQL_USER=your_username \
-e ADB_MYSQL_PASSWORD=your_password \
-e ADB_MYSQL_DATABASE=your_database \
uv --directory /path/to/alibabacloud-adb-mysql-mcp-server run adb-mysql-mcp-server 
```

## 3. Introduction to the components of AnalyticDB for MySQL MCP Server

- ### Tools

    - `execute_sql`: Execute a SQL query in the AnalyticDB for MySQL Cluster

    - `get_query_plan`: Get the query plan for a SQL query

    - `get_execution_plan`: Get the actual execution plan with runtime statistics for a SQL query

- ### Resources

    - #### Built-in Resources

        - `adbmysql:///databases`: Get all the databases in the analytic for mysql cluster

    - #### Resource Templates

        - `adbmysql:///{schema}/tables`: Get all the tables in a specific database

        - `adbmysql:///{database}/{table}/ddl`: Get the DDL script of a table in a specific database

        - `adbmysql:///{config}/{key}/value`: Get the value for a config key in the cluster

- ### Prompts

Not provided at the present moment.


## Resources 

### Open MCP Marketplace API Support 
![MCP Marketplace User Review Rating Badge](http://www.deepnlp.org/api/marketplace/svg?aliyun/alibabacloud-adb-mysql-mcp-server)|[GitHub](https://github.com/AI-Agent-Hub/mcp-marketplace)|[Doc](http://www.deepnlp.org/doc/mcp_marketplace)|[MCP Marketplace](http://www.deepnlp.org/store/ai-agent/mcp-server)
- Allow AI App/Agent/LLM to find this MCP Server via common python/typescript API, search and explore relevant servers and tools

***Example: Search Server and Tools***
```python
    import anthropic
    import mcp_marketplace as mcpm

    result_q = mcpm.search(query="alibabacloud adb mysql mcp server", mode="list", page_id=0, count_per_page=100, config_name="deepnlp") # search server by category choose various endpoint
    result_id = mcpm.search(id="aliyun/alibabacloud-adb-mysql-mcp-server", mode="list", page_id=0, count_per_page=100, config_name="deepnlp")      # search server by id choose various endpoint 
    tools = mcpm.list_tools(id="aliyun/alibabacloud-adb-mysql-mcp-server", config_name="deepnlp_tool")

    # Call Claude to Choose Tools Function Calls 
    client = anthropic.Anthropic()
    response = client.messages.create(model="claude-3-7-sonnet-20250219", max_tokens=1024, tools=tools, messages=[])
```

