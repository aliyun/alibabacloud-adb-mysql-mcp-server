"""
L1: Operational Efficiency Analysis Layer.
Pure SQL + Python computation — no LLM required.
"""

from __future__ import annotations

import math
from typing import Any

from scripts.config import AdbConfig
from scripts.db import execute_query
from scripts.types import TimeRange, time_range_to_sql_params


# ─── L1-1: Token Efficiency Analysis ───

def analyze_token_efficiency(
    adb_config: AdbConfig,
    table_name: str,
    range_: TimeRange,
) -> dict:
    print("[L1-1] Starting token efficiency analysis...")

    try:
        start_time, end_time = time_range_to_sql_params(range_)

        overall_sql = f"""
            SELECT
                COUNT(DISTINCT session_id) AS total_sessions,
                SUM(input_tokens) AS total_input,
                SUM(output_tokens) AS total_output,
                CASE WHEN SUM(input_tokens) > 0
                     THEN ROUND(SUM(output_tokens) / SUM(input_tokens), 4)
                     ELSE 0 END AS output_input_ratio,
                CASE WHEN SUM(input_tokens + cache_read_tokens) > 0
                     THEN ROUND(SUM(cache_read_tokens) / SUM(input_tokens + cache_read_tokens) * 100, 2)
                     ELSE 0 END AS cache_hit_rate_pct,
                CASE WHEN COUNT(DISTINCT session_id) > 0
                     THEN ROUND(SUM(total_tokens) / COUNT(DISTINCT session_id), 2)
                     ELSE 0 END AS avg_tokens_per_session,
                CASE WHEN COUNT(DISTINCT session_id) > 0
                     THEN ROUND(SUM(total_cost) / COUNT(DISTINCT session_id), 6)
                     ELSE 0 END AS avg_cost_per_session
            FROM `{table_name}`
            WHERE timestamp >= %s AND timestamp < %s
              AND role = 'assistant'
        """

        by_model_sql = f"""
            SELECT
                COALESCE(model, 'unknown') AS model,
                COUNT(*) AS call_count,
                CASE WHEN SUM(input_tokens) > 0
                     THEN ROUND(SUM(output_tokens) / SUM(input_tokens), 4)
                     ELSE 0 END AS output_input_ratio,
                CASE WHEN SUM(input_tokens + cache_read_tokens) > 0
                     THEN ROUND(SUM(cache_read_tokens) / SUM(input_tokens + cache_read_tokens) * 100, 2)
                     ELSE 0 END AS cache_hit_rate_pct,
                CASE WHEN COUNT(DISTINCT session_id) > 0
                     THEN ROUND(SUM(total_cost) / COUNT(DISTINCT session_id), 6)
                     ELSE 0 END AS avg_cost_per_session
            FROM `{table_name}`
            WHERE timestamp >= %s AND timestamp < %s
              AND role = 'assistant'
            GROUP BY model
            ORDER BY call_count DESC
        """

        by_user_sql = f"""
            WITH ordered_msgs AS (
                SELECT
                    row_id, session_id, role, sender_id,
                    input_tokens, output_tokens, cache_read_tokens,
                    total_tokens, total_cost, timestamp,
                    SUM(CASE WHEN role = 'user' THEN 1 ELSE 0 END)
                        OVER (PARTITION BY session_id ORDER BY timestamp, row_id) AS task_chain_id
                FROM `{table_name}`
                WHERE timestamp >= %s AND timestamp < %s
            ),
            chain_sender AS (
                SELECT session_id, task_chain_id,
                    MIN(CASE WHEN role = 'user' THEN sender_id END) AS sender_id
                FROM ordered_msgs
                GROUP BY session_id, task_chain_id
            ),
            user_tokens AS (
                SELECT
                    cs.sender_id,
                    om.session_id,
                    om.input_tokens,
                    om.output_tokens,
                    om.cache_read_tokens,
                    om.total_cost
                FROM ordered_msgs om
                JOIN chain_sender cs
                    ON om.session_id = cs.session_id AND om.task_chain_id = cs.task_chain_id
                WHERE om.role = 'assistant' AND cs.sender_id IS NOT NULL
            )
            SELECT
                sender_id,
                COUNT(DISTINCT session_id) AS session_count,
                SUM(input_tokens) AS total_input,
                SUM(output_tokens) AS total_output,
                CASE WHEN SUM(input_tokens) > 0
                     THEN ROUND(SUM(output_tokens) / SUM(input_tokens), 4)
                     ELSE 0 END AS output_input_ratio,
                CASE WHEN SUM(input_tokens + cache_read_tokens) > 0
                     THEN ROUND(SUM(cache_read_tokens) / SUM(input_tokens + cache_read_tokens) * 100, 2)
                     ELSE 0 END AS cache_hit_rate_pct,
                SUM(total_cost) AS total_cost,
                CASE WHEN COUNT(DISTINCT session_id) > 0
                     THEN ROUND(SUM(total_cost) / COUNT(DISTINCT session_id), 6)
                     ELSE 0 END AS avg_cost_per_session
            FROM user_tokens
            GROUP BY sender_id
            ORDER BY total_input DESC
        """

        overall_rows = execute_query(adb_config, overall_sql, (start_time, end_time))
        by_model_rows = execute_query(adb_config, by_model_sql, (start_time, end_time))
        by_user_rows = execute_query(adb_config, by_user_sql, (start_time, end_time))

        overall_row = overall_rows[0] if overall_rows else {}

        overall = {
            "totalSessions": overall_row.get("total_sessions") or 0,
            "totalInput": overall_row.get("total_input") or 0,
            "totalOutput": overall_row.get("total_output") or 0,
            "outputInputRatio": float(overall_row.get("output_input_ratio") or 0),
            "cacheHitRatePct": float(overall_row.get("cache_hit_rate_pct") or 0),
            "avgTokensPerSession": float(overall_row.get("avg_tokens_per_session") or 0),
            "avgCostPerSession": float(overall_row.get("avg_cost_per_session") or 0),
        }

        by_model = [
            {
                "model": row["model"],
                "callCount": row.get("call_count") or 0,
                "outputInputRatio": float(row.get("output_input_ratio") or 0),
                "cacheHitRatePct": float(row.get("cache_hit_rate_pct") or 0),
                "avgCostPerSession": float(row.get("avg_cost_per_session") or 0),
            }
            for row in by_model_rows
        ]

        by_user = [
            {
                "senderId": row["sender_id"],
                "sessionCount": row.get("session_count") or 0,
                "totalInput": row.get("total_input") or 0,
                "totalOutput": row.get("total_output") or 0,
                "outputInputRatio": float(row.get("output_input_ratio") or 0),
                "cacheHitRatePct": float(row.get("cache_hit_rate_pct") or 0),
                "totalCost": float(row.get("total_cost") or 0),
                "avgCostPerSession": float(row.get("avg_cost_per_session") or 0),
            }
            for row in by_user_rows
        ]

        print(f"[L1-1] Token efficiency analysis completed: {overall['totalSessions']} sessions")
        return {"overall": overall, "byModel": by_model, "byUser": by_user}

    except Exception as error:
        print(f"[L1-1] Error in token efficiency analysis: {error}")
        return {
            "overall": {
                "totalSessions": 0, "totalInput": 0, "totalOutput": 0,
                "outputInputRatio": 0, "cacheHitRatePct": 0,
                "avgTokensPerSession": 0, "avgCostPerSession": 0,
            },
            "byModel": [],
            "byUser": [],
        }


# ─── L1-2: Task Chain Depth Analysis ───

def analyze_session_depth(
    adb_config: AdbConfig,
    table_name: str,
    range_: TimeRange,
) -> dict:
    print("[L1-2] Starting task chain depth analysis...")

    try:
        start_time, end_time = time_range_to_sql_params(range_)

        task_chain_depth_sql = f"""
            WITH ordered_msgs AS (
                SELECT
                    row_id, session_id, role, sender_id, tool_name, is_error,
                    input_tokens, output_tokens, total_tokens, total_cost,
                    thinking_text, timestamp,
                    SUM(CASE WHEN role = 'user' THEN 1 ELSE 0 END)
                        OVER (PARTITION BY session_id ORDER BY timestamp, row_id) AS task_chain_id
                FROM `{table_name}`
                WHERE timestamp >= %s AND timestamp < %s
            ),
            chain_sender AS (
                SELECT session_id, task_chain_id,
                    MIN(CASE WHEN role = 'user' THEN sender_id END) AS sender_id
                FROM ordered_msgs
                GROUP BY session_id, task_chain_id
            ),
            task_chain_metrics AS (
                SELECT
                    om.session_id,
                    om.task_chain_id,
                    cs.sender_id,
                    COUNT(*) AS message_count,
                    SUM(CASE WHEN om.tool_name IS NOT NULL THEN 1 ELSE 0 END) AS tool_call_count,
                    SUM(CASE WHEN om.is_error = 1 THEN 1 ELSE 0 END) AS tool_error_count,
                    TIMESTAMPDIFF(SECOND, MIN(om.timestamp), MAX(om.timestamp)) AS duration_seconds,
                    SUM(om.total_tokens) AS total_tokens,
                    SUM(om.total_cost) AS total_cost,
                    SUM(CASE WHEN om.role = 'assistant' THEN LENGTH(COALESCE(om.thinking_text, '')) ELSE 0 END) AS thinking_length
                FROM ordered_msgs om
                JOIN chain_sender cs
                    ON om.session_id = cs.session_id AND om.task_chain_id = cs.task_chain_id
                GROUP BY om.session_id, om.task_chain_id, cs.sender_id
            )
            SELECT
                CASE
                    WHEN message_count <= 2 THEN '1_single'
                    WHEN message_count <= 5 THEN '2_short'
                    WHEN message_count <= 10 THEN '3_medium'
                    WHEN message_count <= 20 THEN '4_deep'
                    ELSE '5_marathon'
                END AS depth_bucket,
                COUNT(*) AS chain_count,
                ROUND(AVG(message_count), 1) AS avg_messages,
                ROUND(AVG(duration_seconds), 1) AS avg_duration_seconds,
                ROUND(AVG(tool_call_count), 1) AS avg_tool_calls,
                ROUND(AVG(total_tokens), 0) AS avg_tokens,
                ROUND(AVG(total_cost), 4) AS avg_cost,
                SUM(total_tokens) AS sum_tokens
            FROM task_chain_metrics
            GROUP BY depth_bucket
            ORDER BY depth_bucket
        """

        rows = execute_query(adb_config, task_chain_depth_sql, (start_time, end_time))

        bucket_distribution = [
            {
                "depthBucket": row["depth_bucket"],
                "chainCount": row["chain_count"],
                "avgMessages": float(row["avg_messages"] or 0),
                "avgDurationSeconds": float(row["avg_duration_seconds"] or 0),
                "avgToolCalls": float(row["avg_tool_calls"] or 0),
                "avgTokens": float(row["avg_tokens"] or 0),
                "avgCost": float(row["avg_cost"] or 0),
                "sumTokens": row["sum_tokens"] or 0,
            }
            for row in rows
        ]

        total_chains = sum(b["chainCount"] for b in bucket_distribution)
        print(f"[L1-2] Task chain depth analysis completed: {total_chains} task chains")
        return {"bucketDistribution": bucket_distribution, "totalChains": total_chains}

    except Exception as error:
        print(f"[L1-2] Error in task chain depth analysis: {error}")
        return {"bucketDistribution": [], "totalChains": 0}


# ─── L1-3: Tool Chain Analysis ───

def analyze_tool_chains(
    adb_config: AdbConfig,
    table_name: str,
    range_: TimeRange,
) -> dict:
    print("[L1-3] Starting tool chain analysis...")

    try:
        start_time, end_time = time_range_to_sql_params(range_)

        tool_sequence_sql = f"""
            WITH numbered_messages AS (
                SELECT
                    session_id, sender_id, role, tool_name, is_error, timestamp,
                    SUM(CASE WHEN role = 'user' THEN 1 ELSE 0 END) OVER (
                        PARTITION BY session_id ORDER BY timestamp
                    ) AS task_chain_id
                FROM `{table_name}`
                WHERE timestamp >= %s AND timestamp <= %s
            ),
            tool_chains AS (
                SELECT
                    session_id, sender_id, task_chain_id,
                    GROUP_CONCAT(
                        CASE WHEN tool_name IS NOT NULL THEN tool_name ELSE NULL END
                        ORDER BY timestamp
                        SEPARATOR '->'
                    ) AS tool_sequence
                FROM numbered_messages
                GROUP BY session_id, sender_id, task_chain_id
            )
            SELECT session_id AS sessionId, sender_id AS senderId,
                   task_chain_id AS taskChainId, tool_sequence
            FROM tool_chains
            WHERE tool_sequence IS NOT NULL AND tool_sequence != ''
        """

        rows = execute_query(adb_config, tool_sequence_sql, (start_time, end_time))

        bigram_counts: dict[str, int] = {}
        trigram_counts: dict[str, int] = {}
        tool_call_stats: dict[str, dict] = {}

        for row in rows:
            tools = [t.strip() for t in row["tool_sequence"].split("->") if t.strip()]

            for i in range(len(tools) - 1):
                bigram = f"{tools[i]}->{tools[i + 1]}"
                bigram_counts[bigram] = bigram_counts.get(bigram, 0) + 1

            for i in range(len(tools) - 2):
                trigram = f"{tools[i]}->{tools[i + 1]}->{tools[i + 2]}"
                trigram_counts[trigram] = trigram_counts.get(trigram, 0) + 1

            for tool in tools:
                if tool not in tool_call_stats:
                    tool_call_stats[tool] = {"total": 0, "success": 0}
                tool_call_stats[tool]["total"] += 1
                tool_call_stats[tool]["success"] += 1

        top_bigrams = sorted(bigram_counts.items(), key=lambda x: x[1], reverse=True)[:20]
        top_trigrams = sorted(trigram_counts.items(), key=lambda x: x[1], reverse=True)[:20]

        tool_success_rates = [
            {
                "toolName": tool_name,
                "totalCalls": stats["total"],
                "successRate": round(stats["success"] / stats["total"] * 100) if stats["total"] > 0 else 0,
            }
            for tool_name, stats in sorted(tool_call_stats.items(), key=lambda x: x[1]["total"], reverse=True)
        ]

        return {
            "topBigrams": [{"pattern": p, "count": c} for p, c in top_bigrams],
            "topTrigrams": [{"pattern": p, "count": c} for p, c in top_trigrams],
            "toolSuccessRates": tool_success_rates,
        }

    except Exception as error:
        print(f"[L1-3] Error in tool chain analysis: {error}")
        return {"topBigrams": [], "topTrigrams": [], "toolSuccessRates": []}


# ─── L1-4: High Token Task Chains Analysis ───

def analyze_high_cost_sessions(
    adb_config: AdbConfig,
    table_name: str,
    range_: TimeRange,
) -> dict:
    print("[L1-4] Starting high token task chain analysis...")

    try:
        start_time, end_time = time_range_to_sql_params(range_)

        high_token_sql = f"""
            WITH ordered_msgs AS (
                SELECT
                    row_id, session_id, role, sender_id, tool_name, is_error,
                    input_tokens, output_tokens, cache_read_tokens,
                    total_tokens, total_cost, content_text, content_length,
                    thinking_text, timestamp,
                    SUM(CASE WHEN role = 'user' THEN 1 ELSE 0 END)
                        OVER (PARTITION BY session_id ORDER BY timestamp, row_id) AS task_chain_id
                FROM `{table_name}`
                WHERE timestamp >= %s AND timestamp < %s
            ),
            chain_sender AS (
                SELECT session_id, task_chain_id,
                    MIN(CASE WHEN role = 'user' THEN sender_id END) AS sender_id,
                    LEFT(MIN(CASE WHEN role = 'user' THEN content_text END), 500) AS user_first_message
                FROM ordered_msgs
                GROUP BY session_id, task_chain_id
            ),
            chain_metrics AS (
                SELECT
                    om.session_id,
                    om.task_chain_id,
                    cs.sender_id,
                    cs.user_first_message,
                    COUNT(*) AS message_count,
                    SUM(CASE WHEN om.role = 'user' THEN 1 ELSE 0 END) AS user_turns,
                    SUM(CASE WHEN om.tool_name IS NOT NULL THEN 1 ELSE 0 END) AS tool_call_count,
                    SUM(CASE WHEN om.is_error = 1 THEN 1 ELSE 0 END) AS tool_error_count,
                    SUM(om.input_tokens) AS total_input,
                    SUM(om.output_tokens) AS total_output,
                    SUM(om.total_tokens) AS total_tokens,
                    SUM(om.total_cost) AS total_cost,
                    SUM(CASE WHEN om.role = 'assistant' THEN LENGTH(COALESCE(om.thinking_text, '')) ELSE 0 END) AS thinking_length,
                    TIMESTAMPDIFF(SECOND, MIN(om.timestamp), MAX(om.timestamp)) AS duration_seconds,
                    MIN(om.row_id) AS start_row_id,
                    MAX(om.row_id) AS end_row_id
                FROM ordered_msgs om
                JOIN chain_sender cs
                    ON om.session_id = cs.session_id AND om.task_chain_id = cs.task_chain_id
                GROUP BY om.session_id, om.task_chain_id, cs.sender_id, cs.user_first_message
            )
            SELECT *
            FROM chain_metrics
            ORDER BY total_tokens DESC
            LIMIT 20
        """

        rows = execute_query(adb_config, high_token_sql, (start_time, end_time))

        task_chains = []
        for row in rows:
            cost_drivers: list[str] = []
            tool_call_count = row.get("tool_call_count") or 0
            tool_error_count = row.get("tool_error_count") or 0
            thinking_length = row.get("thinking_length") or 0
            message_count = row.get("message_count") or 0
            total_input = row.get("total_input") or 0
            total_output = row.get("total_output") or 0

            if tool_call_count > 0 and tool_error_count / tool_call_count > 0.3:
                cost_drivers.append("高工具错误率")
            if thinking_length > 10000:
                cost_drivers.append("深度推理")
            if message_count > 20:
                cost_drivers.append("超长对话")
            if tool_call_count > 10:
                cost_drivers.append("重度工具使用")
            if total_input > 500000:
                cost_drivers.append("大量输入token")
            if not cost_drivers:
                cost_drivers.append("正常")

            raw_first_msg = row.get("user_first_message") or ""
            truncated_first_msg = raw_first_msg[:500] if raw_first_msg else None

            task_chains.append({
                "sessionId": row["session_id"],
                "taskChainId": row["task_chain_id"],
                "senderId": row.get("sender_id"),
                "totalInput": total_input,
                "totalOutput": total_output,
                "totalTokens": row.get("total_tokens") or 0,
                "totalCost": float(row.get("total_cost") or 0),
                "messageCount": message_count,
                "toolCallCount": tool_call_count,
                "toolErrorCount": tool_error_count,
                "thinkingLength": thinking_length,
                "durationSeconds": row.get("duration_seconds") or 0,
                "startRowId": row.get("start_row_id"),
                "endRowId": row.get("end_row_id"),
                "userFirstMessage": truncated_first_msg,
                "costDrivers": cost_drivers,
            })

        return {"taskChains": task_chains}

    except Exception as error:
        print(f"[L1-4] Error in high token task chain analysis: {error}")
        return {"taskChains": []}


# ─── L1-5: Anomaly Detection ───

def _detect_off_hours_anomalies(stats: list[dict], sender_id: str) -> list[dict]:
    anomalies = []
    for stat in stats:
        date_val = stat["date"]
        if hasattr(date_val, "weekday"):
            day_of_week = date_val.weekday()  # Monday=0, Sunday=6
            hour = date_val.hour if hasattr(date_val, "hour") else 0
        else:
            from datetime import datetime
            try:
                dt = datetime.fromisoformat(str(date_val))
                day_of_week = dt.weekday()
                hour = dt.hour
            except Exception:
                continue

        is_weekend = day_of_week >= 5
        is_late_night = hour >= 22 or hour < 6

        if (is_weekend or is_late_night) and (stat.get("daily_sessions") or 0) > 5:
            anomalies.append({
                "senderId": sender_id,
                "anomalyType": "OFF_HOURS",
                "actualValue": stat.get("daily_sessions") or 0,
                "mean": 0,
                "stddev": 0,
                "zScore": 0,
                "severity": "medium",
            })
    return anomalies


def analyze_anomalies(
    adb_config: AdbConfig,
    table_name: str,
    range_: TimeRange,
) -> dict:
    print("[L1-5] Starting anomaly detection...")

    try:
        from datetime import datetime, timedelta
        # range_.start_date may contain time part (e.g. "2026-03-09 20:46:10")
        start_date = datetime.fromisoformat(range_.start_date).date()
        baseline_start_date = start_date - timedelta(days=30)

        baseline_start_time = f"{baseline_start_date.isoformat()} 00:00:00"
        start_time, end_time = time_range_to_sql_params(range_)

        daily_stats_sql = f"""
            SELECT
                sender_id AS senderId,
                DATE(timestamp) AS date,
                SUM(total_cost) AS daily_cost,
                COUNT(DISTINCT session_id) AS daily_sessions,
                SUM(CASE WHEN is_error = 1 THEN 1 ELSE 0 END) AS daily_errors,
                COUNT(*) AS daily_messages,
                SUM(CASE WHEN stop_reason != 'toolUse'
                          AND stop_reason NOT IN ('stop', 'end_turn')
                          AND stop_reason IS NOT NULL
                     THEN 1 ELSE 0 END) AS daily_abnormal_stops
            FROM `{table_name}`
            WHERE timestamp >= %s AND timestamp <= %s
            GROUP BY sender_id, DATE(timestamp)
        """

        rows = execute_query(adb_config, daily_stats_sql, (baseline_start_time, end_time))

        user_stats: dict[str, list[dict]] = {}
        for row in rows:
            sender_id = row["senderId"]
            if sender_id not in user_stats:
                user_stats[sender_id] = []
            user_stats[sender_id].append({
                "date": row["date"],
                "daily_cost": float(row.get("daily_cost") or 0),
                "daily_sessions": int(row.get("daily_sessions") or 0),
                "daily_errors": int(row.get("daily_errors") or 0),
                "daily_messages": int(row.get("daily_messages") or 0),
                "daily_abnormal_stops": int(row.get("daily_abnormal_stops") or 0),
            })

        anomalies: list[dict] = []

        for sender_id, stats in user_stats.items():
            if len(stats) < 5:
                continue

            metrics = [
                ("COST_SPIKE", [s["daily_cost"] for s in stats]),
                ("SESSION_SPIKE", [s["daily_sessions"] for s in stats]),
                ("ERROR_SPIKE", [s["daily_errors"] for s in stats]),
                ("ABNORMAL_STOP_SPIKE", [s["daily_abnormal_stops"] for s in stats]),
                ("MESSAGE_SPIKE", [s["daily_messages"] for s in stats]),
            ]

            for metric_name, values in metrics:
                mean = sum(values) / len(values)
                variance = sum((v - mean) ** 2 for v in values) / len(values)
                stddev = math.sqrt(variance)

                if stddev == 0:
                    continue

                recent_stats = stats[-7:]
                for stat in recent_stats:
                    value_map = {
                        "COST_SPIKE": stat["daily_cost"],
                        "SESSION_SPIKE": stat["daily_sessions"],
                        "ERROR_SPIKE": stat["daily_errors"],
                        "ABNORMAL_STOP_SPIKE": stat["daily_abnormal_stops"],
                        "MESSAGE_SPIKE": stat["daily_messages"],
                    }
                    value = value_map[metric_name]
                    z_score = (value - mean) / stddev

                    if abs(z_score) > 3:
                        anomalies.append({
                            "senderId": sender_id,
                            "anomalyType": metric_name,
                            "actualValue": value,
                            "mean": round(mean * 100) / 100,
                            "stddev": round(stddev * 100) / 100,
                            "zScore": round(z_score * 100) / 100,
                            "severity": "critical" if abs(z_score) > 5 else "high",
                        })

            anomalies.extend(_detect_off_hours_anomalies(stats, sender_id))

        severity_order = {"critical": 0, "high": 1, "medium": 2}
        anomalies.sort(key=lambda a: (severity_order.get(a["severity"], 3), -abs(a["zScore"])))

        return {"anomalies": anomalies}

    except Exception as error:
        print(f"[L1-5] Error in anomaly detection: {error}")
        return {"anomalies": []}


# ─── L1 Analysis Runner ───

def run_l1_analysis(
    adb_config: AdbConfig,
    table_name: str,
    range_: TimeRange,
) -> dict:
    print("[L1] Starting L1 operational efficiency analysis...")

    token_efficiency = analyze_token_efficiency(adb_config, table_name, range_)
    session_depth = analyze_session_depth(adb_config, table_name, range_)
    tool_chains = analyze_tool_chains(adb_config, table_name, range_)
    high_cost_sessions = analyze_high_cost_sessions(adb_config, table_name, range_)
    anomalies = analyze_anomalies(adb_config, table_name, range_)

    print("[L1] L1 analysis completed.")

    return {
        "tokenEfficiency": token_efficiency,
        "sessionDepth": session_depth,
        "toolChains": tool_chains,
        "highCostSessions": high_cost_sessions,
        "anomalies": anomalies,
    }
