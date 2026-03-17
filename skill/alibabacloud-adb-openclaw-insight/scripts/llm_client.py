"""
LLM Client supporting both OpenAI-compatible and Anthropic API endpoints.
Uses official Python SDKs with async clients for non-blocking API communication.

API type is determined by the `api_type` field in LlmConfig:
- "openai" (default): OpenAI-compatible API (e.g. qwen, deepseek, GPT)
- "anthropic": Anthropic Messages API (e.g. Claude)
"""

from __future__ import annotations

import asyncio
import json
import re
import time
from typing import Any, Callable

from scripts.config import LlmConfig


def _extract_json_from_response(response: str) -> Any:
    """Extract and parse JSON from LLM response that may contain markdown code blocks.

    Handles common LLM output issues:
    - JSON wrapped in ```json ... ``` code blocks
    - Extra text before/after JSON
    - Multiple JSON objects instead of a single array (Extra data error)
    """
    # Step 1: Try to extract from markdown code block
    json_block_match = re.search(r"```(?:json)?\s*\n?([\s\S]*?)\n?```", response)
    candidate = json_block_match.group(1).strip() if json_block_match else None

    # Step 2: If no code block, try to find raw JSON
    if not candidate:
        json_match = re.search(r"(\[[\s\S]*\]|\{[\s\S]*\})", response)
        candidate = json_match.group(1).strip() if json_match else response.strip()

    # Step 3: Try strict parse first
    try:
        return json.loads(candidate)
    except json.JSONDecodeError:
        pass

    # Step 4: Handle "Extra data" — LLM may return multiple JSON objects
    # Try to parse as JSON Lines (one JSON object per line)
    lines = candidate.strip().splitlines()
    collected: list[Any] = []
    buffer = ""
    for line in lines:
        buffer += line.strip()
        try:
            parsed = json.loads(buffer)
            if isinstance(parsed, list):
                collected.extend(parsed)
            else:
                collected.append(parsed)
            buffer = ""
        except json.JSONDecodeError:
            buffer += "\n"

    if collected:
        return collected

    # Step 5: Try decoder with partial parsing
    decoder = json.JSONDecoder()
    results: list[Any] = []
    text = candidate.strip()
    pos = 0
    while pos < len(text):
        # Skip whitespace and commas between objects
        while pos < len(text) and text[pos] in " \t\n\r,":
            pos += 1
        if pos >= len(text):
            break
        try:
            obj, end_pos = decoder.raw_decode(text, pos)
            if isinstance(obj, list):
                results.extend(obj)
            else:
                results.append(obj)
            pos = end_pos
        except json.JSONDecodeError:
            pos += 1

    if results:
        return results

    raise json.JSONDecodeError("Failed to extract valid JSON from LLM response", candidate, 0)


def _build_openai_base_url(endpoint: str) -> str:
    """Normalize endpoint to OpenAI SDK base_url format (must end with /v1)."""
    url = endpoint.rstrip("/")
    if url.endswith("/v1/chat/completions"):
        url = url[: -len("/chat/completions")]
    elif not url.endswith("/v1"):
        url = url + "/v1"
    return url


def _build_anthropic_base_url(endpoint: str) -> str:
    """Normalize endpoint to Anthropic SDK base_url format."""
    url = endpoint.rstrip("/")
    if url.endswith("/v1/messages"):
        url = url[: -len("/v1/messages")]
    elif url.endswith("/v1"):
        url = url[: -len("/v1")]
    return url


# ─── LLM Client ───

class LlmClient:
    def __init__(self, config: LlmConfig) -> None:
        self._config = config
        self._semaphore = asyncio.Semaphore(config.max_concurrency)

        if config.api_type == "anthropic":
            import anthropic
            base_url = _build_anthropic_base_url(config.endpoint)
            self._anthropic_client = anthropic.AsyncAnthropic(
                api_key=config.api_key,
                base_url=base_url,
                timeout=600.0,
                max_retries=3,
            )
            self._openai_client = None
            print(f"[LLM] Initialized AsyncAnthropic SDK, model: {config.model}, base_url: {base_url}")
        else:
            import openai
            base_url = _build_openai_base_url(config.endpoint)
            self._openai_client = openai.AsyncOpenAI(
                api_key=config.api_key,
                base_url=base_url,
                timeout=600.0,
                max_retries=3,
            )
            self._anthropic_client = None
            print(f"[LLM] Initialized AsyncOpenAI SDK, model: {config.model}, base_url: {base_url}")

    async def _call_api(self, messages: list[dict]) -> str:
        """Async API call using official SDK with built-in retry."""
        start_time = time.time()

        try:
            if self._anthropic_client is not None:
                result = await self._call_anthropic(messages)
            else:
                result = await self._call_openai(messages)

            elapsed = time.time() - start_time
            print(f"[LLM] API call completed in {elapsed:.1f}s ({len(result)} chars)")
            return result

        except Exception as error:
            elapsed = time.time() - start_time
            print(f"[LLM] API call failed after {elapsed:.1f}s: {error}")
            raise

    async def _call_openai(self, messages: list[dict]) -> str:
        """Call OpenAI-compatible API using async SDK."""
        response = await self._openai_client.chat.completions.create(
            model=self._config.model,
            messages=messages,
            temperature=self._config.temperature,
            max_tokens=self._config.max_tokens or 4096,
        )
        content = response.choices[0].message.content
        if not content:
            raise ValueError("[LLM:OpenAI] Empty response: no content returned")
        return content

    async def _call_anthropic(self, messages: list[dict]) -> str:
        """Call Anthropic API using async SDK."""
        system_prompt: str | None = None
        anthropic_messages: list[dict] = []

        for message in messages:
            if message["role"] == "system":
                system_prompt = message["content"]
            else:
                anthropic_messages.append({
                    "role": message["role"],
                    "content": message["content"],
                })

        kwargs: dict[str, Any] = {
            "model": self._config.model,
            "max_tokens": self._config.max_tokens or 4096,
            "messages": anthropic_messages,
            "temperature": self._config.temperature,
        }
        if system_prompt:
            kwargs["system"] = system_prompt

        response = await self._anthropic_client.messages.create(**kwargs)

        for block in response.content:
            if block.type == "text":
                return block.text

        raise ValueError("[LLM:Anthropic] No text content block found in response")

    async def chat(self, system_prompt: str, user_prompt: str) -> str:
        """Simple chat completion returning raw text."""
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]
        async with self._semaphore:
            return await self._call_api(messages)

    async def chat_json(self, system_prompt: str, user_prompt: str) -> Any:
        """Chat completion that parses the response as JSON."""
        raw_response = await self.chat(system_prompt, user_prompt)
        return _extract_json_from_response(raw_response)

    async def batch_classify(
        self,
        items: list[str],
        system_prompt: str,
        batch_size: int,
        build_user_prompt: Callable[[list[str], int], str],
        label: str = "",
    ) -> list[Any]:
        """
        Batch classify items using LLM.
        Splits items into batches, sends each batch to LLM, and collects results.
        """
        total_items = len(items)
        batches: list[tuple[list[str], int]] = []
        for start_idx in range(0, total_items, batch_size):
            batch = items[start_idx : start_idx + batch_size]
            batches.append((batch, start_idx))

        total_batches = len(batches)
        tag = f"[LLM:{label}]" if label else "[LLM:batch]"
        print(f"{tag} Processing {total_items} items in {total_batches} batches (batch_size={batch_size})")

        completed_count = 0
        lock = asyncio.Lock()

        async def process_batch(batch: list[str], start_index: int) -> tuple[int, list[Any]]:
            nonlocal completed_count
            user_prompt = build_user_prompt(batch, start_index)
            batch_results = await self.chat_json(system_prompt, user_prompt)
            async with lock:
                completed_count += 1
                print(f"{tag} Batch {completed_count}/{total_batches} done (items {start_index+1}-{start_index+len(batch)})")
            return start_index, batch_results

        tasks = [process_batch(batch, start_index) for batch, start_index in batches]
        outputs = await asyncio.gather(*tasks)

        outputs_sorted = sorted(outputs, key=lambda x: x[0])
        results: list[Any] = []
        for _, batch_results in outputs_sorted:
            results.extend(batch_results)

        print(f"{tag} All {total_batches} batches completed, {len(results)} results collected")
        return results