"""
L3: Organizational Cognition Layer.
Focuses on organizational-level insights, knowledge gaps, best practices, and skill candidates.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

from scripts.config import AdbConfig
from scripts.db import execute_query, execute_query_async
from scripts.llm_client import LlmClient
from scripts.types import TimeRange, time_range_to_sql_params
from scripts.analysis.behavior_insight import _extract_user_message


# ─── Technology Dictionary ───

TECHNOLOGY_DICTIONARY: dict[str, dict[str, list[str]]] = {
    "Languages": {
        "Java": ["java", "spring", "maven", "gradle", "jvm"],
        "Python": ["python", "pip", "django", "flask", "fastapi", "pytorch"],
        "TypeScript": ["typescript", "ts-node", "tsx", "tsc"],
        "Go": ["golang", "go mod", "goroutine"],
        "Rust": ["rust", "cargo", "tokio"],
    },
    "Frameworks": {
        "React": ["react", "jsx", "next.js", "nextjs", "usestate", "useeffect"],
        "Vue": ["vue", "vuex", "nuxt", "pinia"],
    },
    "Databases": {
        "MySQL": ["mysql", "innodb", "mysqldump"],
        "PostgreSQL": ["postgresql", "postgres", "psql"],
        "Redis": ["redis", "jedis", "lettuce"],
        "MongoDB": ["mongodb", "mongoose", "mongosh"],
    },
    "Infrastructure": {
        "Kubernetes": ["kubernetes", "k8s", "kubectl", "helm", "pod", "deployment"],
        "Docker": ["docker", "dockerfile", "docker-compose", "container"],
    },
}


# ─── L3-1: Build Tech Stack Heatmap ───

_TECH_STACK_SYSTEM_PROMPT = """You are a technology stack analyst. For each user message from an enterprise AI agent assistant session, identify ALL technologies, frameworks, libraries, databases, infrastructure tools, and programming languages mentioned or implied.

Return a JSON array where each element has:
- technologies: array of strings — normalized technology names (e.g., "React", "Python", "Kubernetes", "MySQL", "Docker")

Rules:
- Use canonical names: "React" not "reactjs", "Kubernetes" not "k8s", "TypeScript" not "ts"
- Include both explicitly mentioned and strongly implied technologies (e.g., if user mentions "useEffect", include "React")
- If no technology is identifiable, return an empty array for that message
- Each technology name should be a single well-known technology (not a description)"""

async def build_tech_stack_heatmap(
    adb_config: AdbConfig,
    table_name: str,
    range_: TimeRange,
    llm_client: LlmClient,
) -> dict:
    """Build a tech stack heatmap using LLM to identify technologies from user messages."""
    print("[L3-1] Building tech stack heatmap...")

    try:
        start_time, end_time = time_range_to_sql_params(range_)

        sql = f"""
            SELECT row_id, session_id, sender_id, content_text
            FROM `{table_name}`
            WHERE role = 'user'
              AND timestamp >= %s AND timestamp < %s
              AND content_text IS NOT NULL AND content_text != ''
              AND sender_id IS NOT NULL AND sender_id != ''
            ORDER BY session_id, timestamp
        """

        rows = await execute_query_async(adb_config, sql, (start_time, end_time))

        if not rows:
            return {"technologies": []}

        # Extract actual user messages
        for row in rows:
            row["user_prompt"] = _extract_user_message(row.get("content_text") or "")

        rows = [row for row in rows if row["user_prompt"]]

        if not rows:
            print("[L3-1] No valid user prompts after metadata extraction")
            return {"technologies": []}

        messages = [row["user_prompt"] for row in rows]

        # Apply 128K single-batch strategy
        total_chars = sum(len(msg) for msg in messages)
        estimated_tokens = int(total_chars * 1.5)
        max_single_batch_tokens = 128_000

        if estimated_tokens < max_single_batch_tokens:
            batch_size = len(messages)
            print(f"[L3-1] Estimated {estimated_tokens} tokens (< 128K), sending all in one batch")
        else:
            batch_size = 15
            print(f"[L3-1] Estimated {estimated_tokens} tokens (>= 128K), splitting into batches of {batch_size}")

        def build_user_prompt(batch: list[str], start_index: int) -> str:
            numbered = "\n\n---\n\n".join(
                f"[{start_index + i + 1}]\n{msg}" for i, msg in enumerate(batch)
            )
            return (
                f"Identify technologies mentioned in these user messages.\n\n"
                f"{numbered}\n\n"
                f"Return a JSON array with a 'technologies' field (array of strings) for each message."
            )

        print(f"[L3-1] Queried {len(rows)} user messages, sending to LLM for tech stack identification...")
        results = await llm_client.batch_classify(
            messages, _TECH_STACK_SYSTEM_PROMPT, batch_size,
            build_user_prompt, label="L3-1:tech_stack",
        )

        # Aggregate: count sessions and unique users per technology
        tech_sessions: dict[str, set[str]] = {}
        tech_users: dict[str, set[str]] = {}

        for i, row in enumerate(rows):
            raw_result = results[i] if i < len(results) else {"technologies": []}
            techs = raw_result.get("technologies", [])
            if not isinstance(techs, list):
                continue

            session_id = row["session_id"]
            sender_id = row.get("sender_id") or "unknown"

            for tech_name in techs:
                if not isinstance(tech_name, str) or not tech_name.strip():
                    continue
                normalized = tech_name.strip()
                if normalized not in tech_sessions:
                    tech_sessions[normalized] = set()
                    tech_users[normalized] = set()
                tech_sessions[normalized].add(session_id)
                tech_users[normalized].add(sender_id)

        technologies = sorted(
            [
                {
                    "tech": tech_name,
                    "sessionCount": len(sessions),
                    "uniqueUsers": len(tech_users[tech_name]),
                }
                for tech_name, sessions in tech_sessions.items()
            ],
            key=lambda x: x["sessionCount"],
            reverse=True,
        )

        print(f"[L3-1] Found {len(technologies)} technologies")
        return {"technologies": technologies}

    except Exception as error:
        print(f"[L3-1] Error building tech stack heatmap: {error}")
        return {"technologies": []}


# ─── L3-2: Discover High-Frequency Repeated Questions ───

_REPEATED_QUESTION_SYSTEM_PROMPT = """You are an analyst identifying repeated questions across users in an enterprise AI agent assistant.

You will receive a list of user messages from different users. Your task is to:
1. Group messages that are essentially asking the SAME question (even if worded differently)
2. Only report groups where 2+ DIFFERENT users asked the same question
3. For each group, provide a canonical question summary

A "repeated question" means different people independently asked the AI the same thing — this wastes tokens and should be solved once (via documentation, a Skill, or a shared tool).

Return a JSON object:
{
  "repeatedQuestions": [
    {
      "canonicalQuestion": "string — a clear summary of what they all asked",
      "messageIndices": [1, 5, 12],
      "category": "one of: knowledge_query | routine_task | config_lookup | code_generation | debugging | other"
    }
  ]
}

Rules:
- Only group messages that are semantically the SAME question, not just the same topic
- Ignore messages that are unique one-off questions
- If no repeated questions are found, return an empty array"""


async def discover_repeated_questions(
    adb_config: AdbConfig,
    table_name: str,
    range_: TimeRange,
    llm_client: LlmClient,
) -> dict:
    """Discover high-frequency repeated questions asked by multiple users.

    Identifies questions that multiple different users independently asked the AI,
    which wastes tokens and should be addressed via documentation, Skills, or shared tools.
    """
    print("[L3-2] Discovering high-frequency repeated questions...")

    try:
        start_time, end_time = time_range_to_sql_params(range_)

        sql = f"""
            SELECT row_id, session_id, sender_id, content_text
            FROM `{table_name}`
            WHERE role = 'user'
              AND timestamp >= %s AND timestamp < %s
              AND content_text IS NOT NULL AND content_text != ''
              AND sender_id IS NOT NULL AND sender_id != ''
            ORDER BY timestamp
        """

        rows = await execute_query_async(adb_config, sql, (start_time, end_time))

        if not rows:
            print("[L3-2] No user messages found")
            return {"repeatedQuestions": [], "totalMessagesAnalyzed": 0}

        for row in rows:
            row["user_prompt"] = _extract_user_message(row.get("content_text") or "")

        rows = [row for row in rows if row["user_prompt"]]

        if not rows:
            print("[L3-2] No valid user prompts after extraction")
            return {"repeatedQuestions": [], "totalMessagesAnalyzed": 0}

        # Build numbered message list with sender info for LLM
        messages_for_llm = [
            f"[{i + 1}] (user: {row.get('sender_id', 'unknown')})\n{row['user_prompt']}"
            for i, row in enumerate(rows)
        ]

        total_chars = sum(len(msg) for msg in messages_for_llm)
        estimated_tokens = int(total_chars * 1.5)
        max_single_batch_tokens = 128_000

        if estimated_tokens < max_single_batch_tokens:
            print(f"[L3-2] Estimated {estimated_tokens} tokens (< 128K), sending all in one batch")
            combined_messages = "\n\n---\n\n".join(messages_for_llm)
            user_prompt = (
                f"Analyze these {len(messages_for_llm)} user messages from an enterprise AI agent assistant. "
                f"Find questions that DIFFERENT users asked independently but are essentially the same question.\n\n"
                f"{combined_messages}"
            )
            raw_result = await llm_client.chat_json(_REPEATED_QUESTION_SYSTEM_PROMPT, user_prompt)
        else:
            print(f"[L3-2] Estimated {estimated_tokens} tokens (>= 128K), splitting into batches")
            batch_size = 15
            all_repeated: list[dict] = []
            for batch_start in range(0, len(messages_for_llm), batch_size):
                batch = messages_for_llm[batch_start:batch_start + batch_size]
                combined = "\n\n---\n\n".join(batch)
                user_prompt = (
                    f"Analyze these {len(batch)} user messages. "
                    f"Find questions that DIFFERENT users asked independently but are essentially the same.\n\n"
                    f"{combined}"
                )
                batch_result = await llm_client.chat_json(_REPEATED_QUESTION_SYSTEM_PROMPT, user_prompt)
                all_repeated.extend(batch_result.get("repeatedQuestions", []))
            raw_result = {"repeatedQuestions": all_repeated}

        # Enrich results with actual user counts and sender details
        repeated_questions = []
        for group in raw_result.get("repeatedQuestions", []):
            indices = group.get("messageIndices", [])
            senders = set()
            sample_messages = []
            for idx in indices:
                actual_idx = idx - 1
                if 0 <= actual_idx < len(rows):
                    sender = rows[actual_idx].get("sender_id", "unknown")
                    senders.add(sender)
                    if len(sample_messages) < 3:
                        sample_messages.append({
                            "senderId": sender,
                            "sessionId": rows[actual_idx]["session_id"],
                            "preview": rows[actual_idx]["user_prompt"][:150],
                        })

            if len(senders) < 2:
                continue

            repeated_questions.append({
                "canonicalQuestion": group.get("canonicalQuestion", ""),
                "category": group.get("category", "other"),
                "uniqueUsers": len(senders),
                "totalOccurrences": len(indices),
                "senders": sorted(senders),
                "sampleMessages": sample_messages,
            })

        repeated_questions.sort(key=lambda x: x["uniqueUsers"], reverse=True)

        print(f"[L3-2] Found {len(repeated_questions)} repeated questions across multiple users")
        return {
            "repeatedQuestions": repeated_questions,
            "totalMessagesAnalyzed": len(rows),
        }

    except Exception as error:
        print(f"[L3-2] Error discovering repeated questions: {error}")
        return {"repeatedQuestions": [], "totalMessagesAnalyzed": 0}


# ─── L3-3: Extract Best Practices ───

async def extract_best_practices(
    adb_config: AdbConfig,
    table_name: str,
    range_: TimeRange,
    llm_client: LlmClient,
) -> dict:
    print("[L3-3] Extracting best practices from successful sessions...")

    try:
        start_time, end_time = time_range_to_sql_params(range_)

        sql = f"""
            WITH session_stats AS (
                SELECT session_id, sender_id,
                    SUM(CASE WHEN role = 'user' THEN 1 ELSE 0 END) AS user_turns,
                    SUM(CASE WHEN is_error = 1 THEN 1 ELSE 0 END) AS error_count
                FROM `{table_name}`
                WHERE timestamp >= %s AND timestamp < %s
                GROUP BY session_id, sender_id
            ),
            last_stop AS (
                SELECT session_id, stop_reason,
                    ROW_NUMBER() OVER (PARTITION BY session_id ORDER BY timestamp DESC) AS rn
                FROM `{table_name}`
                WHERE timestamp >= %s AND timestamp < %s AND stop_reason IS NOT NULL
            )
            SELECT ss.session_id, ss.sender_id
            FROM session_stats ss
            LEFT JOIN last_stop ls ON ss.session_id = ls.session_id AND ls.rn = 1
            WHERE ss.user_turns <= 3
              AND ss.error_count = 0
              AND ls.stop_reason IN ('stop', 'end_turn')
            LIMIT 100
        """

        session_rows = await execute_query_async(
            adb_config, sql,
            (start_time, end_time, start_time, end_time)
        )

        if not session_rows:
            print("[L3-3] No successful sessions found")
            return {"bestPractices": [], "commonPatterns": []}

        session_ids = [row["session_id"] for row in session_rows]
        placeholders = ", ".join(["%s"] * len(session_ids))

        message_sql = f"""
            WITH first_msgs AS (
                SELECT session_id, content_text,
                    ROW_NUMBER() OVER (PARTITION BY session_id ORDER BY timestamp ASC) AS rn
                FROM `{table_name}`
                WHERE role = 'user'
                  AND session_id IN ({placeholders})
                  AND content_text IS NOT NULL AND content_text != ''
            )
            SELECT session_id, content_text FROM first_msgs WHERE rn = 1
        """

        message_rows = await execute_query_async(
            adb_config, message_sql, tuple(session_ids)
        )

        user_prompts = [row["content_text"][:500] for row in message_rows[:50]]

        system_prompt = """You are an expert in AI prompt engineering and enterprise AI agent assistant best practices.
Analyze successful user prompts to identify patterns and extract actionable best practices."""

        user_prompt = f"""Analyze the following successful user prompts from enterprise AI agent assistant sessions.
These prompts resulted in successful task completion (<=3 user turns, 0 errors, normal completion).

User Prompts:
{chr(10).join(f"{i + 1}. {prompt}..." for i, prompt in enumerate(user_prompts))}

Extract 5-10 best practices and identify common patterns.

Return a JSON object with this structure:
{{
  "bestPractices": [
    {{"title": "string", "description": "string", "example": "string"}}
  ],
  "commonPatterns": ["string"]
}}"""

        result = await llm_client.chat_json(system_prompt, user_prompt)
        print(f"[L3-3] Extracted {len(result.get('bestPractices', []))} best practices")
        return result

    except Exception as error:
        print(f"[L3-3] Error extracting best practices: {error}")
        return {"bestPractices": [], "commonPatterns": []}


# ─── L3-4: Discover Skill Candidates ───

async def discover_skill_candidates(
    tool_chain_result: dict,
    topic_cluster_result: dict,
    intent_result: dict,
    llm_client: LlmClient,
) -> dict:
    print("[L3-4] Discovering skill candidates...")

    try:
        top_tool_patterns = tool_chain_result.get("topTrigrams", [])[:10]
        top_topics = topic_cluster_result.get("topTags", [])[:10]
        top_intents = sorted(
            intent_result.get("distribution", {}).items(),
            key=lambda x: x[1],
            reverse=True,
        )[:10]

        tool_summary = "\n".join(f"- {p['pattern']} (count: {p['count']})" for p in top_tool_patterns)
        topic_summary = "\n".join(f"- {t['tag']} (count: {t['count']}, users: {t['uniqueUsers']})" for t in top_topics)
        intent_summary = "\n".join(f"- {intent} (count: {count})" for intent, count in top_intents)

        system_prompt = """You are an AI workflow automation specialist who understands the Skill specification for enterprise AI agent assistants.

## What is a Skill?

A Skill is a self-contained, reusable automation package that an AI agent can invoke to complete a specific, well-defined task. It is NOT a generic assistant or a vague capability.

A valid Skill MUST satisfy ALL of the following criteria:
1. **Deterministic workflow**: The Skill follows a clear, repeatable sequence of steps (e.g., read config → modify → validate → deploy). It is not an open-ended conversation.
2. **Clear input/output contract**: The Skill has well-defined inputs (e.g., a file path, a service name, a config template) and produces a concrete output (e.g., a deployed service, a generated report, a validated config).
3. **Tool-chain backed**: The Skill leverages specific tool calls (exec, read, write, web_fetch, etc.) in a predictable pattern. The tool chain pattern should be observable in the usage data.
4. **Domain-specific**: The Skill solves a specific domain problem (e.g., "K8s ingress configuration", "database migration"), NOT a generic capability (e.g., "answer questions", "run commands").
5. **Automatable end-to-end**: The entire workflow can be automated without human intervention once triggered. If it requires subjective judgment at every step, it is NOT a Skill.
6. **High frequency + multi-user**: The workflow is performed frequently (multiple times per week) by multiple different users, indicating organizational-level demand.

## What is NOT a Skill:
- Generic Q&A or knowledge retrieval (that's just the base agent capability)
- Running arbitrary shell commands (too generic, no domain specificity)
- Vague categories like "security testing" or "code review" without a specific workflow
- One-off tasks that don't recur

Only recommend candidates that can realistically be developed into a Skill package with a YAML/Markdown spec, system prompt, and tool definitions."""

        user_prompt = f"""Analyze the following usage data to identify the TOP 3 most valuable Skill candidates.

Top Tool Chain Patterns (Trigrams):
{tool_summary}

Top Topics:
{topic_summary}

Top Intents:
{intent_summary}

Based on the Skill specification above, identify exactly 3 Skill candidates that:
1. Have a clear, deterministic workflow (observable tool chain pattern)
2. Are domain-specific (not generic)
3. Have the highest combination of frequency × unique users × automation potential
4. Can be realistically packaged as a self-contained Skill with input/output contract

For each candidate, also explain WHY it qualifies as a Skill (which tool chain pattern supports it, what the concrete input/output would be).

Return a JSON object with this structure:
{{
  "skillCandidates": [
    {{
      "name": "string",
      "description": "string",
      "trigger": "string",
      "workflow": "string — the concrete step-by-step workflow (e.g., read config → modify → validate → apply)",
      "inputContract": "string — what inputs the Skill needs",
      "outputContract": "string — what the Skill produces",
      "supportingEvidence": "string — which tool chain pattern / topic / intent supports this",
      "estimatedWeeklyUsage": number,
      "uniqueUsers": number,
      "automationPotential": "high|medium|low"
    }}
  ]
}}"""

        result = await llm_client.chat_json(system_prompt, user_prompt)
        print(f"[L3-4] Discovered {len(result.get('skillCandidates', []))} skill candidates")
        return result

    except Exception as error:
        print(f"[L3-4] Error discovering skill candidates: {error}")
        return {"skillCandidates": []}


# ─── L3-5: Generate Narrative Report ───

async def generate_narrative_report(
    all_results: dict,
    range_: TimeRange,
    llm_client: LlmClient,
) -> dict:
    print("[L3-5] Generating narrative report...")

    try:
        system_prompt = """You are a senior technology analyst writing an insight report for engineering leadership.

## Critical Context: Understanding the Data

The data you are analyzing comes from **OpenClaw**, an enterprise AI agent assistant platform. Each "session" or "task chain" represents an **AI Agent autonomously executing tasks** on behalf of a user — NOT a human manually operating a computer.

Key distinctions you MUST apply throughout the report:
- **Tool calls** (exec, read, write, web_fetch, etc.) are executed by the **AI Agent**, not by the user directly.
- When you see patterns like "exec->exec->exec", it means the **Agent ran a sequence of commands**, not that a user typed commands manually.
- **Users interact with the Agent through natural language messages**. The Agent then autonomously decides which tools to call and in what sequence.
- Therefore, phrases like "用户手动执行命令" or "用户正在手动操作" are INCORRECT. The correct framing is "Agent 自动执行了..." or "AI 助理调用了...".
- When discussing Skill candidates, the value proposition is NOT "减少用户的手动操作" but rather "将 Agent 的重复工作流封装为标准化 Skill，提升一致性和可复用性".

## Report Requirements

This is NOT a weekly report. It is an analysis report for a specific time range. Do NOT use terms like "本周", "周报", "weekly". Instead, refer to the analysis period using the exact dates provided.

## Language Detection Rules

Determine the report language based on the dominant language found in the user messages within the analysis data:
- If the majority of user messages are in **Chinese**, write the entire report in **Chinese (中文)**.
- If the majority of user messages are in **English**, write the entire report in **English**.
- If the messages are evenly mixed, default to **Chinese**.

Apply this language choice consistently throughout the entire report — do NOT mix languages within the report.

## Writing Style
- Write in a natural, conversational tone. Use the tone of a trusted advisor briefing a VP of Engineering.
- Tell a STORY, not a data dump. Lead with insights and conclusions, then support with data.
- Use analogies and plain language to explain technical patterns. Avoid jargon where possible.
- Highlight what's SURPRISING, what's CONCERNING, and what's an OPPORTUNITY.
- Be opinionated — make clear recommendations, don't just present options.
- Use Markdown formatting for readability (headers, bold, bullet points).
- Do NOT limit the report length. Include all data tables and narrative analysis in full. Completeness is more important than brevity."""

        # ── Assemble all available data into the prompt ──
        l1 = all_results.get("l1", {})
        l2 = all_results.get("l2", {})
        l3 = all_results.get("l3", {})

        data_sections = []

        def append_section(label: str, data: dict) -> None:
            if data:
                data_sections.append(f"【{label}】\n{json.dumps(data, ensure_ascii=False, default=str)}")

        # L1: Operational Efficiency
        append_section("L1-1 Token 消耗与成本效率", l1.get("tokenEfficiency", {}))
        append_section("L1-2 任务链深度分布", l1.get("sessionDepth", {}))
        append_section("L1-3 工具链模式", l1.get("toolChains", {}))
        append_section("L1-4 高成本会话 Top20", l1.get("highCostSessions", {}))
        append_section("L1-5 异常检测", l1.get("anomalies", {}))

        # L2: User Behavior
        append_section("L2-1 意图分类分布", l2.get("intents", {}))
        append_section("L2-2 任务复杂度", l2.get("complexity", {}))
        append_section("L2-3 任务成功率", l2.get("successRate", {}))
        append_section("L2-4 Prompt 质量评分", l2.get("promptQuality", {}))
        append_section("L2-5 话题聚类", l2.get("topics", {}))
        append_section("L2-6 重试行为检测", l2.get("retryBehavior", {}))
        append_section("L2-7 思考深度分布", l2.get("thinkingDepth", {}))
        append_section("L2-8 用户成熟度趋势", l2.get("userMaturity", {}))

        # L3: Organizational Cognition
        append_section("L3-1 技术栈热力图", l3.get("techStack", {}))
        append_section("L3-2 高频重复问题", l3.get("repeatedQuestions", {}))
        append_section("L3-3 最佳实践", l3.get("bestPractices", {}))
        append_section("L3-4 技能候选", l3.get("skillCandidates", {}))

        all_data_text = "\n\n".join(data_sections) if data_sections else "暂无分析数据"

        user_prompt = f"""Based on the following OpenClaw enterprise AI agent assistant usage analysis data, write an insight report for engineering leadership.

Analysis period: {range_.start_date} to {range_.end_date}

IMPORTANT — Language selection: First, examine the user messages in the intent classification (L2-1) and topic clustering (L2-5) data below to determine whether the majority of user messages are in Chinese or English. Then write the ENTIRE report in that language. Do NOT mix languages within the report.

This is NOT a weekly report. Refer to the analysis period using the exact dates above, not terms like "this week" or "weekly".

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Analysis data from the three-layer insight engine:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

{all_data_text}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

The report must include BOTH narrative analysis and complete data metric displays. Each section should first tell a story and give conclusions in natural language, then immediately follow with a Markdown table or formatted list showing the key metrics for that section.

Report structure:

## 1. Executive Summary
2-3 sentences summarizing the most noteworthy findings — be direct, like messaging your boss.

## 2. L1 Operational Efficiency

### 2.1 Token Consumption & Cost Efficiency
- 1-2 paragraphs of narrative interpreting trends and anomalies
- Markdown table: input/output tokens, cache hit rate, total cost per model
- If user-level data is available, a table showing top users by consumption

### 2.2 Task Chain Depth Distribution
- Narrative interpreting the distribution characteristics
- Table showing each depth bucket (single/short/medium/deep/marathon) with counts and percentages

### 2.3 Tool Chain Patterns
- Narrative interpreting the most common tool usage patterns
- Table showing top tool chain patterns (pattern, count, unique users)

### 2.4 High-Cost Sessions
- Narrative commentary on which scenarios are "burning tokens"
- Table showing top 5 high-cost sessions (session_id, user, cost, cost drivers)

### 2.5 Anomaly Detection
- Narrative interpreting what anomalies were found
- List showing counts of each anomaly type (cost spike, error spike, abnormal stop, off-hours usage)

## 3. L2 User Behavior

### 3.1 Intent Classification
- Narrative interpreting what users are mainly doing
- Table showing each intent category with count and percentage

### 3.2 Task Complexity
- Narrative interpreting the complexity distribution
- Distribution statistics for complexity scores

### 3.3 Task Success Rate
- Narrative interpreting the success rate situation
- Table showing success/partial/failure counts and percentages

### 3.4 Prompt Quality
- Narrative interpreting the overall prompt quality level
- Table showing top 3 best users and bottom 3 users with scores

### 3.5 Topic Clustering
- Narrative interpreting the hot topics
- Table showing top topic tags (tag name, count, unique users)

### 3.6 Retry Behavior
- Narrative interpreting what the retry rate indicates
- Retry rate metric display

### 3.7 Thinking Depth
- Narrative interpreting the model reasoning depth distribution

### 3.8 User Maturity
- Narrative interpreting user growth trends

## 4. L3 Organizational Cognition

### 4.1 Tech Stack Heatmap
- Narrative interpreting the team's technology focus areas
- Table showing top tech stack (technology name, session count, unique users)

### 4.2 High-Frequency Repeated Questions
- Narrative interpreting knowledge consolidation opportunities
- Table showing questions asked repeatedly by multiple users (question, unique users, occurrences, category)

### 4.3 Best Practices
- List of extracted best practices (title + brief description)

### 4.4 Skill Candidates
- Narrative interpreting automation opportunities
- Table showing candidate Skills (name, description, trigger, estimated weekly usage)

## 5. Action Recommendations
3-5 specific, actionable recommendations in priority order, each with rationale and expected benefit.

Notes:
- Every section must have BOTH narrative analysis AND data display — neither can be omitted
- Skip entire subsections where data is missing — do not mention the absence
- Numbers should be interpreted (e.g., "accounting for Y% of total"); use absolute values with qualitative judgment when no baseline exists
- Use standard Markdown table syntax
- The report should be understandable to a non-technical manager

Return a JSON object:
{{
  "report": "complete Markdown-formatted report text"
}}"""

        result = await llm_client.chat_json(system_prompt, user_prompt)

        # Normalize: LLM may return a list instead of a dict
        if isinstance(result, list):
            result = result[0] if result and isinstance(result[0], dict) else {"report": str(result)}
        if not isinstance(result, dict) or "report" not in result:
            result = {"report": str(result)}

        print("[L3-5] Narrative report generated successfully")
        return result

    except Exception as error:
        print(f"[L3-5] Error generating narrative report: {error}")
        return {"report": "Report generation failed due to LLM error. Please check LLM configuration."}


# ─── L3 Analysis Orchestration ───

async def run_l3_analysis(
    adb_config: AdbConfig,
    table_name: str,
    range_: TimeRange,
    llm_client: LlmClient,
    l1_results: dict,
    l2_results: dict,
) -> dict:
    print("[L3] Starting L3 organizational cognition analysis...")

    tech_stack = await build_tech_stack_heatmap(adb_config, table_name, range_, llm_client)
    repeated_questions = await discover_repeated_questions(adb_config, table_name, range_, llm_client)
    best_practices = await extract_best_practices(adb_config, table_name, range_, llm_client)
    skill_candidates = await discover_skill_candidates(
        l1_results.get("toolChains", {}),
        l2_results.get("topics", {}),
        l2_results.get("intents", {}),
        llm_client,
    )

    print("[L3] L3 analysis completed successfully")

    return {
        "techStack": tech_stack,
        "repeatedQuestions": repeated_questions,
        "bestPractices": best_practices,
        "skillCandidates": skill_candidates,
    }
