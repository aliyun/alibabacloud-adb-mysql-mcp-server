# Adb MySQL MCP Server

Adb MySQL MCP Server serves as a universal interface between AI Agents and Adb MySQL databases. It enables seamless communication between AI Agents and Adb MySQL, helping AI Agents
retrieve Adb MySQL database metadata and execute SQL operations.

## 1. MCP Client Configuration

### Mode 1: Using Local File

#### 1. Download the GitHub repository

```shell
git clone https://github.com/aliyun/alibabacloud-adb-mysql-mcp-server
```

#### 2. MCP Integration

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

#### 1. Installation

Install MCP Server using the following package:

```bash
pip install adb-mysql-mcp-server
```

#### 2. MCP Integration

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

## 2. Develop your own Adb MySQL MCP server

If you want to develop your own Adb MySQL MCP Server, you can install the python dependency packages using the following command:

1. Download the [Adb MySQL MCP Server from GitHub](https://github.com/aliyun/alibabacloud-adb-mysql-mcp-server).
2. Install  [uv](https://docs.astral.sh/uv/getting-started/installation/) package manager.
3. Install [nodejs](https://nodejs.org/en/download) which provides a node package tool whose name is `npx`
3. Install the python dependencies in the root diretory of the project using the following command:

```shell
uv pip install -r pyproject.toml 
```

4. If you want to debug the mcp server locally, you could start up a [MCP Inspector](https://modelcontextprotocol.io/docs/tools/inspector) using the following command:

```shell
npx @modelcontextprotocol/inspector  \
-e ADB_MYSQL_HOST=your_host \
-e ADB_MYSQL_PORT=your_port \
-e ADB_MYSQL_USER=your_username \
-e ADB_MYSQL_PASSWORD=your_password \
-e ADB_MYSQL_DATABASE=your_database \
uv --directory /path/to/alibabacloud-adb-mysql-mcp-server run adb-mysql-mcp-server 
```

## 3. Introduction to the components of Adb MySQL MCP Server

### 3.1. Tools

* `execute_sql`: Execute a SQL query in the Adb MySQL Cluster

* `get_query_plan`: Get the query plan for a SQL query

* `get_execution_plan`: Get the actual execution plan with runtime statistics for a SQL query

### 3.2. Resources

#### Built-in Resources

* `adbmysql:///databases`: Get all the databases in the adb mysql cluster

#### 3.3 Resource Templates

* `adbmysql:///{schema}/tables`: Get all the tables in a specific database

* `adbmysql:///{database}/{table}/ddl`: Get the DDL script of a table in a specific database

* `adbmysql:///{config}/{key}/value`: Get the value for a config key in the cluster

### Prompts

Not provided at the present moment.