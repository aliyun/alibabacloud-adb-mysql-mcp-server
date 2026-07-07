"""SQL safety helpers for MCP-exposed ADB MySQL query tools."""

import os
import re
from dataclasses import dataclass


@dataclass(frozen=True)
class SqlToken:
    kind: str
    value: str


def _tokenize_sql(sql: str) -> list[SqlToken]:
    tokens: list[SqlToken] = []
    i = 0
    n = len(sql)

    while i < n:
        ch = sql[i]

        if ch.isspace():
            i += 1
            continue

        if ch in ("'", '"', "`"):
            quote = ch
            kind = "QUOTED_IDENT" if quote == "`" else "STRING"
            start = i
            i += 1
            closed = False
            while i < n:
                if sql[i] == "\\":
                    i += 2
                    continue
                if sql[i] == quote:
                    if i + 1 < n and sql[i + 1] == quote:
                        i += 2
                        continue
                    i += 1
                    closed = True
                    break
                i += 1
            if not closed:
                raise ValueError("SQL quoted string or identifier is not closed.")
            tokens.append(SqlToken(kind, sql[start:i]))
            continue

        if sql.startswith("--", i) or sql.startswith("/*", i) or ch == "#":
            raise ValueError("SQL must be a single statement without comments.")

        if ch == ";":
            if sql[i + 1:].strip():
                raise ValueError("SQL must be a single statement without comments.")
            i += 1
            continue

        if ch.isalpha() or ch == "_":
            start = i
            i += 1
            while i < n and (sql[i].isalnum() or sql[i] in ("_", "$")):
                i += 1
            tokens.append(SqlToken("WORD", sql[start:i].lower()))
            continue

        tokens.append(SqlToken("SYMBOL", ch))
        i += 1

    return tokens


class SqlSafetyValidator:
    """Small allowlist validator for SQL exposed to MCP clients."""

    DEFAULT_MAX_SQL_LENGTH = 10000
    MAX_SQL_LENGTH = DEFAULT_MAX_SQL_LENGTH
    MAX_SQL_LENGTH_ENV = "ADB_MYSQL_MAX_SQL_LENGTH"
    SQL_WRITE_ENV = "ENABLE_SQL_WRITE_TOOLS"

    _EXPLAIN_PREFIX_PATTERN = re.compile(r"^\s*explain\s+(?:analyze\s+)?", re.IGNORECASE)
    _READ_ONLY_KEYWORDS = ("select", "show", "describe", "desc", "explain", "with")
    _WRITE_KEYWORDS = (
        "alter", "call", "create", "delete", "drop", "execute", "exec", "grant",
        "insert", "kill", "load", "lock", "optimize", "replace", "revoke", "set",
        "truncate", "unlock", "update", "use",
    )
    _READ_DANGEROUS_KEYWORDS = set(_WRITE_KEYWORDS) | {"into", "outfile", "dumpfile"}

    @classmethod
    def validate_sql(cls, sql: str, *, allow_write: bool = False) -> str:
        if allow_write:
            return cls._validate_sql_text(sql)

        stripped_sql = cls._validate_single_statement(sql)
        leading_keyword = cls._get_leading_keyword(stripped_sql)
        if leading_keyword in cls._READ_ONLY_KEYWORDS:
            cls._validate_read_only_body(stripped_sql, leading_keyword)
            return stripped_sql
        if leading_keyword not in cls._WRITE_KEYWORDS:
            raise ValueError("SQL must start with a supported keyword.")
        raise ValueError(f"{cls.SQL_WRITE_ENV}=true is required before executing SQL write statements.")

    @classmethod
    def validate_read_only_sql(cls, sql: str) -> str:
        stripped_sql = cls._validate_single_statement(sql)
        leading_keyword = cls._get_leading_keyword(stripped_sql)
        if leading_keyword not in cls._READ_ONLY_KEYWORDS:
            raise ValueError("Only read-only SQL statements are allowed.")
        cls._validate_read_only_body(stripped_sql, leading_keyword)
        return stripped_sql

    @classmethod
    def validate_explain_sql(cls, sql: str) -> str:
        stripped_sql = cls._validate_single_statement(sql)
        cls._validate_explain_body(stripped_sql)
        return stripped_sql

    @classmethod
    def _validate_read_only_body(cls, sql: str, leading_keyword: str) -> None:
        if leading_keyword in ("select", "with") and cls._has_dangerous_keyword(sql):
            raise ValueError("Only read-only SQL statements are allowed.")
        if leading_keyword == "explain":
            cls._validate_explain_body(cls._strip_explain_prefix(sql))

    @classmethod
    def _validate_explain_body(cls, sql: str) -> None:
        if cls._get_leading_keyword(sql) not in ("select", "with"):
            raise ValueError("EXPLAIN only supports SELECT or read-only WITH statements.")
        if cls._has_dangerous_keyword(sql):
            raise ValueError("EXPLAIN only supports SELECT or read-only WITH statements.")

    @classmethod
    def _has_dangerous_keyword(cls, sql: str) -> bool:
        return any(
            token.kind == "WORD" and token.value in cls._READ_DANGEROUS_KEYWORDS
            for token in _tokenize_sql(sql)
        )

    @classmethod
    def _strip_explain_prefix(cls, sql: str) -> str:
        stripped_sql = cls._EXPLAIN_PREFIX_PATTERN.sub("", sql, count=1).strip()
        if not stripped_sql:
            raise ValueError("EXPLAIN only supports SELECT or read-only WITH statements.")
        return stripped_sql

    @classmethod
    def _validate_single_statement(cls, sql: str) -> str:
        stripped_sql = cls._validate_sql_text(sql)
        _tokenize_sql(stripped_sql)
        if stripped_sql.endswith(";"):
            stripped_sql = stripped_sql[:-1].rstrip()
        return stripped_sql

    @classmethod
    def _validate_sql_text(cls, sql: str) -> str:
        if not isinstance(sql, str):
            raise ValueError("SQL must be a string.")
        stripped_sql = sql.strip()
        if not stripped_sql:
            raise ValueError("SQL must not be empty.")
        if len(stripped_sql) > cls._get_max_sql_length():
            raise ValueError("SQL is too long.")
        return stripped_sql

    @classmethod
    def _get_max_sql_length(cls) -> int:
        configured = os.getenv(cls.MAX_SQL_LENGTH_ENV, "").strip()
        if not configured:
            return cls.DEFAULT_MAX_SQL_LENGTH
        try:
            max_length = int(configured)
        except ValueError:
            raise ValueError(f"{cls.MAX_SQL_LENGTH_ENV} must be a positive integer.")
        if max_length <= 0:
            raise ValueError(f"{cls.MAX_SQL_LENGTH_ENV} must be a positive integer.")
        return max_length

    @classmethod
    def _get_leading_keyword(cls, sql: str) -> str:
        for token in _tokenize_sql(sql):
            if token.kind == "SYMBOL" and token.value == "(":
                continue
            if token.kind == "WORD":
                return token.value
            break
        raise ValueError("SQL must start with a supported keyword.")
