import os
import asyncio
import time
import logging
from typing import Optional, List, Dict
import openai
from anthropic import Anthropic
import re
from google import genai
from google.genai import types, errors
import requests
import hashlib
import json
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

logger = logging.getLogger(__name__)


class TestCache:
    """Simple disk cache for LLM responses during testing."""

    def __init__(self, cache_file: str = ".pytest_cache/llm_cache.json"):
        self.cache_file = Path(cache_file)
        self.cache_dir = self.cache_file.parent
        self._data = {}
        self._load()

    def _load(self):
        if self.cache_file.exists():
            try:
                with open(self.cache_file, "r") as f:
                    self._data = json.load(f)
            except Exception as e:
                logger.error(f"Failed to load LLM cache: {e}")

    def _save(self):
        try:
            self.cache_dir.mkdir(parents=True, exist_ok=True)
            with open(self.cache_file, "w") as f:
                json.dump(self._data, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save LLM cache: {e}")

    def get(self, model: str, system: str, user: str) -> Optional[str]:
        key = self._make_key(model, system, user)
        return self._data.get(key)

    def set(self, model: str, system: str, user: str, response: str):
        key = self._make_key(model, system, user)
        self._data[key] = response
        self._save()

    def _make_key(self, model: str, system: str, user: str) -> str:
        content = f"{model}|{system}|{user}"
        return hashlib.sha256(content.encode()).hexdigest()


class LLMService:
    def __init__(self, event_bus=None):
        self.event_bus = event_bus
        openai_key = os.getenv("OPENAI_API_KEY")
        # FIX MAJ-05: Add timeout to OpenAI client to prevent indefinite hangs
        llm_timeout = int(os.getenv("LLM_TIMEOUT", "120"))
        self.openai_client = (
            openai.OpenAI(api_key=openai_key, timeout=llm_timeout)
            if openai_key
            else None
        )

        anthropic_key = os.getenv("ANTHROPIC_API_KEY")
        self.anthropic_client = (
            Anthropic(api_key=anthropic_key) if anthropic_key else None
        )

        gemini_key = os.getenv("GEMINI_API_KEY")
        if gemini_key:
            self.gemini_client = genai.Client(api_key=gemini_key)
            self.gemini_enabled = True
        else:
            self.gemini_enabled = False

        self.mistral_api_key = os.getenv("MISTRAL_API_KEY")
        self.local_url = os.getenv("LOCAL_LLM_URL", "http://localhost:11434/api/chat")
        self.local_model_name = os.getenv("LOCAL_MODEL_NAME")
        self.provider_override = os.getenv("LLM_PROVIDER")  # e.g., 'local'

        # Specific timeouts for local LLM: (connect, read)
        # Read timeout is large to allow for long generations
        self.timeout = (10, int(os.getenv("LLM_TIMEOUT", "600")))

        self.session = requests.Session()
        self.session.headers.update({"Connection": "keep-alive"})

        # Testing Cache
        self.testing = os.getenv("IRON_COUNCIL_TESTING") == "1"
        self.cache = TestCache() if self.testing else None

        # Aliases for testing and routing
        self._call_openai = self._generate_openai
        self._call_anthropic = self._generate_anthropic
        self._call_ollama = self._generate_local

        # Usage Tracking
        self.total_requests = 0
        self.active_requests = 0
        self.pending_requests = 0  # Requests awaiting first byte
        self.request_start_times = {}  # ID -> timestamp
        self.total_input_tokens = 0
        self.total_output_tokens = 0

    def _record_completion(self, tokens_in: int = 0, tokens_out: int = 0):
        """
        Single point of truth for incrementing cumulative metrics.
        """
        self.total_requests += 1
        self.total_input_tokens += tokens_in
        self.total_output_tokens += tokens_out

    def get_active_model_name(self, requested_model: str = "") -> str:
        """
        Returns the actual model name being used based on override/config.
        """
        if self.provider_override == "local":
            return f"LOCAL:{self.local_model_name}"
        if requested_model.startswith("local"):
            return f"LOCAL:{requested_model}"
        if requested_model:
            return f"CLOUD:{requested_model}"
        # Default
        if self.gemini_enabled and not self.openai_client:
            return "CLOUD:gemini-flash-latest"
        return "CLOUD:gpt-3.5-turbo"

    def generate_response(
        self,
        model_name: str,
        system_prompt: str,
        user_message: str,
        agent_name: str = "SYS",
    ) -> str:
        """
        Generates a response from the specified LLM model.
        Falls back to gpt-3.5-turbo if the request fails (unless local is forced).
        """
        # Emit Activity START Signal
        start_time = time.time()
        # FIX: Use real model name
        provider_type = self.get_active_model_name(model_name)

        if self.event_bus:
            from core.event_bus import EventType

            self.active_requests += 1
            self.pending_requests += 1
            request_id = f"req_{int(time.time()*1000)}"
            self.request_start_times[request_id] = start_time

            # Calculate Queue Latency (Pressure)
            now = time.time()
            queue_latency = 0
            if self.request_start_times:
                queue_latency = int(
                    sum(now - t for t in self.request_start_times.values())
                    / len(self.request_start_times)
                    * 1000
                )

            self.event_bus.publish_threadsafe(
                EventType.LLM_ACTIVITY,
                {
                    "status": "START",
                    "model": model_name,
                    "provider": provider_type,
                    "agent": agent_name,
                    "active_requests": self.active_requests,
                    "pending_requests": self.pending_requests,
                    "queue_latency": queue_latency,
                    "total_requests": self.total_requests,
                    "total_input_tokens": self.total_input_tokens,
                    "total_output_tokens": self.total_output_tokens,
                },
            )

        response_content = ""
        try:
            if self.testing:
                cached = self.cache.get(model_name, system_prompt, user_message)
                if cached:
                    response_content = cached
                    # Cache hit, still record completion
                    self._record_completion(0, len(cached) // 4)  # Estimate tokens
                    return cached

            if self.provider_override == "local":
                response_content = self._generate_local(
                    model_name, system_prompt, user_message
                )
            elif model_name.startswith("gpt"):
                response_content = self._generate_openai(
                    model_name, system_prompt, user_message
                )
            elif model_name.startswith("claude"):
                response_content = self._generate_anthropic(
                    model_name, system_prompt, user_message
                )
            elif model_name.startswith("gemini"):
                response_content = self._generate_gemini(
                    model_name, system_prompt, user_message
                )
            elif model_name.startswith("local") or self.provider_override == "local":
                response_content = self._generate_local(
                    model_name, system_prompt, user_message
                )
            else:
                if self.provider_override == "local":
                    logger.info(
                        f"[LLM] Routing '{model_name}' to LOCAL via provider_override."
                    )
                    response_content = self._generate_local(
                        model_name, system_prompt, user_message
                    )
                elif self.gemini_enabled and not self.openai_client:
                    logger.info(
                        f"[LLM] Routing unknown model '{model_name}' to Gemini Default (gemini-flash-latest)"
                    )
                    response_content = self._generate_gemini(
                        "gemini-flash-latest", system_prompt, user_message
                    )
                else:
                    logger.warning(
                        f"Unknown model prefix for {model_name}. Falling back to OpenAI if possible."
                    )
                    response_content = self._generate_openai(
                        "gpt-3.5-turbo", system_prompt, user_message
                    )

            # PHASE 4 LOGGING: Trace full interaction
            logger.info(
                f"\n[LLM_TRACE] MODEL: {model_name}\n[PROMPT]: {user_message[:500]}...\n[RESPONSE]: {response_content[:500]}...\n[STATS] Len: {len(response_content)}"
            )

            return response_content

        except Exception as e:
            logger.error(f"Error generating response with {model_name}: {e}")
            # Fallback response also calls _record_completion
            return self._fallback_response(system_prompt, user_message)
        finally:
            # Calculate Metrics
            self.active_requests = max(0, self.active_requests - 1)
            self.pending_requests = max(0, self.pending_requests - 1)
            end_time = time.time()
            duration = end_time - start_time
            char_count = len(response_content) if response_content else 0

            # If response failed and no tokens were recorded by child methods, record a 0-token completion
            # This ensures total_requests is incremented even for failures.
            # If a child method successfully recorded tokens, total_requests is already incremented.
            # We need a way to know if _record_completion was called.
            # For now, let's assume child methods always call it on success.
            # If an exception occurs before _record_completion is called, it won't be counted.
            # The _fallback_response will call _record_completion.
            # So, if we reach here with an exception and no fallback, total_requests won't increment.
            # Let's ensure _record_completion is called for *every* request that starts.
            # The current logic in generate_response is that _generate_xxx methods call _record_completion.
            # If an exception happens *before* a _generate_xxx method is called, or *inside* it before tokens are known,
            # then _record_completion might not be called.
            # The _fallback_response handles this for failures.
            # For cache hits, I added a _record_completion.
            # So, this `finally` block doesn't need to call _record_completion again.

            if char_count == 0:
                latency_ms = -1
                baud_rate = 0
            else:
                latency_ms = int(duration * 1000)
                # Approx baud: chars * 8 bits (rough estimate for effect)
                baud_rate = int((char_count * 8) / duration) if duration > 0 else 0

            # Emit Activity END Signal with Metrics
            if self.event_bus:
                from core.event_bus import EventType

                # Calculate Creative Metrics
                tps = 0
                if duration > 0:
                    # Very rough estimate if we don't have token count for THIS request
                    # For sync calls we can use char_count / 4
                    tps = int((char_count / 4) / duration)

                fidelity = "HIGH"
                if latency_ms > 3000:
                    fidelity = "LOW"
                elif latency_ms > 1500:
                    fidelity = "MED"

                # Cleanup tracking
                if "request_id" in locals():
                    self.request_start_times.pop(request_id, None)

                self.event_bus.publish_threadsafe(
                    EventType.LLM_ACTIVITY,
                    {
                        "status": "END",
                        "model": model_name,
                        "latency": latency_ms,
                        "baud": baud_rate,
                        "provider": provider_type,
                        "agent": agent_name,
                        "total_requests": self.total_requests,
                        "active_requests": self.active_requests,
                        "pending_requests": self.pending_requests,
                        "total_input_tokens": self.total_input_tokens,
                        "total_output_tokens": self.total_output_tokens,
                        "tps": tps,
                        "signal": fidelity,
                        "synaptic_load": min(
                            100, int((char_count / 500) * 100)
                        ),  # High sensitivity: 500 chars = 100% load
                    },
                )

    def _generate_openai(
        self, model_name: str, system_prompt: str, user_message: str
    ) -> str:
        if not self.openai_client:
            raise ValueError("OPENAI_API_KEY not configured. Cannot use OpenAI models.")

        logger.info(f"[LLM] Generating with OpenAI ({model_name})...")
        response = self.openai_client.chat.completions.create(
            model=model_name,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
        )
        # Tracking
        self._record_completion(
            response.usage.prompt_tokens, response.usage.completion_tokens
        )
        logger.info(
            f"[LLM] OpenAI Usage: {response.usage.prompt_tokens} in, {response.usage.completion_tokens} out."
        )

        if self.testing:
            self.cache.set(
                model_name,
                system_prompt,
                user_message,
                response.choices[0].message.content,
            )
        return response.choices[0].message.content

    def _generate_anthropic(
        self, model_name: str, system_prompt: str, user_message: str
    ) -> str:
        if not self.anthropic_client:
            raise ValueError(
                "ANTHROPIC_API_KEY not configured. Cannot use Anthropic models."
            )

        logger.info(f"[LLM] Generating with Anthropic ({model_name})...")
        response = self.anthropic_client.messages.create(
            model=model_name,
            max_tokens=1024,
            system=system_prompt,
            messages=[{"role": "user", "content": user_message}],
        )
        # Tracking
        self._record_completion(
            response.usage.input_tokens, response.usage.output_tokens
        )
        logger.info(
            f"[LLM] Anthropic Usage: {response.usage.input_tokens} in, {response.usage.output_tokens} out."
        )

        if self.testing:
            self.cache.set(
                model_name, system_prompt, user_message, response.content[0].text
            )
        return response.content[0].text

    def _generate_gemini(
        self, model_name: str, system_prompt: str, user_message: str
    ) -> str:
        if not self.gemini_enabled:
            raise ValueError("GEMINI_API_KEY not configured. Cannot use Gemini models.")

        max_retries = 10  # Increased for stability
        backoff = 2
        import random

        for attempt in range(max_retries):
            try:
                logger.info(
                    f"[LLM] Generating with Gemini ({model_name}) [Attempt {attempt+1}]..."
                )
                response = self.gemini_client.models.generate_content(
                    model=model_name,
                    config=types.GenerateContentConfig(
                        system_instruction=system_prompt,
                    ),
                    contents=user_message,
                )
                # Tracking
                usage = response.usage_metadata
                if usage:
                    self._record_completion(
                        (usage.prompt_token_count or 0),
                        (usage.candidates_token_count or 0),
                    )
                    logger.info(
                        f"[LLM] Gemini Usage: {usage.prompt_token_count} in, {usage.candidates_token_count} out."
                    )
                else:
                    # Estimate if usage_metadata is missing
                    self._record_completion(
                        len(user_message) // 4, len(response.text) // 4
                    )

                if self.testing:
                    self.cache.set(
                        model_name, system_prompt, user_message, response.text
                    )
                return response.text

            except (errors.ClientError, errors.APIError) as e:
                # Handle 429 Resource Exhausted (and other transient errors if needed)
                is_rate_limit = False
                if isinstance(e, errors.ClientError) and e.code == 429:
                    is_rate_limit = True
                elif "429" in str(e) or "RESOURCE_EXHAUSTED" in str(e):
                    is_rate_limit = True

                if is_rate_limit:
                    if attempt < max_retries - 1:
                        # Add jitter to prevent thundering herd
                        jitter = random.uniform(0.5, 1.5)
                        wait_time = backoff * jitter

                        # Try to extract wait time from error message if available
                        match = re.search(r"retry in ([0-9.]+)s", str(e))
                        if match:
                            wait_time = float(match.group(1)) + 1.0

                        logger.warning(
                            f"Gemini Rate Limit Hit (429). Retrying in {wait_time:.2f}s... (Attempt {attempt+1}/{max_retries})"
                        )
                        time.sleep(wait_time)
                        backoff *= 2  # Exponential backoff
                        continue
                logger.error(f"Gemini error: {e}")
                self._record_completion(0, 0)  # Record failure
                raise e
            except Exception as e:
                logger.error(f"Gemini unexpected error: {e}")
                self._record_completion(0, 0)  # Record failure
                raise e

    async def _run_blocking_stream(self, generator_func, *args, **kwargs):
        """
        FIX CRIT-03: Runs a blocking generator in a separate thread and yields
        items asynchronously AS THEY ARRIVE (not after the entire stream completes).
        The producer thread fills a queue; we consume it concurrently.
        """
        import queue

        q = queue.Queue()
        sentinel = object()

        def producer():
            try:
                for item in generator_func(*args, **kwargs):
                    q.put(item)
            except Exception as e:
                logger.error(f"Stream producer error: {e}")
                q.put(e)  # Pass error to consumer
            finally:
                q.put(sentinel)

        # FIX CRIT-03: Start producer in background thread — do NOT await it here.
        # Old code: `await loop.run_in_executor(None, producer)` blocked until
        # the entire producer finished, defeating the purpose of streaming.
        loop = asyncio.get_running_loop()
        future = loop.run_in_executor(None, producer)

        # Consume from queue AS items arrive
        while True:
            try:
                item = q.get_nowait()
            except queue.Empty:
                await asyncio.sleep(0.01)  # Yield to event loop, let producer work
                continue

            if item is sentinel:
                break
            if isinstance(item, Exception):
                raise item
            yield item

        # Ensure the background thread has completed cleanly
        await future

    async def generate_response_stream(
        self,
        model_name: str,
        system_prompt: str,
        user_message: str,
        agent_name: str = "SYS",
    ):
        """
        Asynchronously streams a response using the specified model.
        """
        # STREAMING METRICS
        start_time = time.time()
        first_token_time = None
        char_count = 0
        provider_type = self.get_active_model_name(model_name)

        if self.event_bus:
            from core.event_bus import EventType

            self.active_requests += 1
            self.pending_requests += 1
            request_id = f"stream_{int(time.time()*1000)}"
            self.request_start_times[request_id] = start_time

            # Queue Latency
            now = time.time()
            queue_latency = int(
                sum(now - t for t in self.request_start_times.values())
                / len(self.request_start_times)
                * 1000
            )

            await self.event_bus.publish(
                EventType.LLM_ACTIVITY,
                {
                    "status": "START",
                    "model": model_name,
                    "provider": provider_type,
                    "agent": agent_name,
                    "active_requests": self.active_requests,
                    "pending_requests": self.pending_requests,
                    "queue_latency": queue_latency,
                    "total_requests": self.total_requests,
                    "total_input_tokens": self.total_input_tokens,
                    "total_output_tokens": self.total_output_tokens,
                },
            )

        try:
            # Helper to wrap the stream and track metrics
            async def metric_wrapper(async_gen):
                nonlocal first_token_time, char_count
                usage_data = None
                async for chunk in async_gen:
                    if isinstance(chunk, dict) and "usage" in chunk:
                        usage_data = chunk["usage"]
                        continue

                    if first_token_time is None:
                        first_token_time = time.time()
                        latency = int((first_token_time - start_time) * 1000)
                        # Request transitioned from Pending to Active (streaming started)
                        self.pending_requests = max(0, self.pending_requests - 1)
                        if "request_id" in locals():
                            self.request_start_times.pop(request_id, None)

                        # Emit First Token Latency immediately
                        if self.event_bus:
                            await self.event_bus.publish(
                                EventType.LLM_ACTIVITY,
                                {
                                    "status": "lat_update",  # Intermediate update
                                    "latency": latency,
                                    "provider": provider_type,
                                    "active_requests": self.active_requests,
                                    "pending_requests": self.pending_requests,
                                    "total_requests": self.total_requests,
                                    "total_input_tokens": self.total_input_tokens,
                                    "total_output_tokens": self.total_output_tokens,
                                },
                            )

                    if isinstance(chunk, str):
                        char_count += len(chunk)
                        yield chunk

                # Update global trackers if usage_data was found (e.g. OpenAI stream_options)
                if usage_data:
                    self._record_completion(
                        usage_data.get("prompt_tokens", 0),
                        usage_data.get("completion_tokens", 0),
                    )
                else:
                    # If no usage data (typical for local stream without 'done' payload in wrapper)
                    # We'll rely on the child method to call record_completion or do it here
                    # actually, generate_local_stream_blocking does it.
                    # If it's something else, we estimate.
                    if char_count > 0:
                        self._record_completion(len(user_message) // 4, char_count // 4)
                    else:
                        self._record_completion(0, 0)

            # Local Override
            if self.provider_override == "local":
                async for chunk in metric_wrapper(
                    self._generate_local_stream(model_name, system_prompt, user_message)
                ):
                    yield chunk
                return

            if model_name.startswith("gpt"):
                # Wrap the blocking OpenAI call
                async for chunk in metric_wrapper(
                    self._run_blocking_stream(
                        self._generate_openai_stream_blocking,
                        model_name,
                        system_prompt,
                        user_message,
                    )
                ):
                    yield chunk

            elif model_name.startswith("claude"):
                # Wrap the blocking Anthropic call
                async for chunk in metric_wrapper(
                    self._run_blocking_stream(
                        self._generate_anthropic_stream_blocking,
                        model_name,
                        system_prompt,
                        user_message,
                    )
                ):
                    yield chunk

            elif model_name.startswith("gemini"):
                async for chunk in metric_wrapper(
                    self._run_blocking_stream(
                        self._generate_gemini_stream_blocking,
                        model_name,
                        system_prompt,
                        user_message,
                    )
                ):
                    yield chunk

            elif model_name.startswith("local") or self.provider_override == "local":
                async for chunk in metric_wrapper(
                    self._generate_local_stream(model_name, system_prompt, user_message)
                ):
                    yield chunk
            else:
                # Default fallback logic
                if self.gemini_enabled and not self.openai_client:
                    async for chunk in metric_wrapper(
                        self._run_blocking_stream(
                            self._generate_gemini_stream_blocking,
                            "gemini-flash-latest",
                            system_prompt,
                            user_message,
                        )
                    ):
                        yield chunk
                else:
                    async for chunk in metric_wrapper(
                        self._run_blocking_stream(
                            self._generate_openai_stream_blocking,
                            "gpt-3.5-turbo",
                            system_prompt,
                            user_message,
                        )
                    ):
                        yield chunk

        except Exception as e:
            logger.error(f"Error streaming response with {model_name}: {e}")
            self._record_completion(0, 0)  # Record failure
            yield "[Agent Silent - Neural Link Severed]"
        finally:
            self.active_requests = max(0, self.active_requests - 1)
            # Calculate Final Baud Rate
            end_time = time.time()
            duration = end_time - start_time

            # FIX NET-01: Detect timeout/failure (0 chars) and report as error
            if char_count == 0:
                latency_ms = -1
                baud_rate = 0
            else:
                # Use First Token Latency if available, else Total Duration
                latency_ms = (
                    int((first_token_time - start_time) * 1000)
                    if first_token_time
                    else int(duration * 1000)
                )
                # Baud rate based on streaming duration
                baud_rate = int((char_count * 8) / duration) if duration > 0 else 0

            if self.event_bus:
                from core.event_bus import EventType

                # Calculate Creative Metrics
                tps = 0
                if duration > 0:
                    tps = int((char_count / 4) / duration)

                fidelity = "HIGH"
                if latency_ms > 3000:
                    fidelity = "LOW"
                elif latency_ms > 1500:
                    fidelity = "MED"

                if "request_id" in locals():
                    self.request_start_times.pop(request_id, None)

                self.event_bus.publish(
                    EventType.LLM_ACTIVITY,
                    {
                        "status": "END",
                        "model": model_name,
                        "latency": latency_ms,
                        "baud": baud_rate,
                        "provider": provider_type,
                        "agent": agent_name,
                        "total_requests": self.total_requests,
                        "active_requests": self.active_requests,
                        "pending_requests": self.pending_requests,
                        "total_input_tokens": self.total_input_tokens,
                        "total_output_tokens": self.total_output_tokens,
                        "tps": tps,
                        "signal": fidelity,
                        "synaptic_load": min(
                            100, int((char_count / 2000) * 100)
                        ),  # More sensitive
                    },
                )

    # --- BLOCKING GENERATORS (Run in Thread) ---

    def _generate_openai_stream_blocking(
        self, model_name: str, system_prompt: str, user_message: str
    ):
        if not self.openai_client:
            raise ValueError("OPENAI_API_KEY not configured.")

        response = self.openai_client.chat.completions.create(
            model=model_name,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
            stream=True,
            stream_options={"include_usage": True},
        )
        for chunk in response:
            if chunk.usage:
                yield {
                    "usage": {
                        "prompt_tokens": chunk.usage.prompt_tokens,
                        "completion_tokens": chunk.usage.completion_tokens,
                    }
                }
            if chunk.choices and chunk.choices[0].delta.content:
                yield chunk.choices[0].delta.content

    def _generate_anthropic_stream_blocking(
        self, model_name: str, system_prompt: str, user_message: str
    ):
        if not self.anthropic_client:
            raise ValueError("ANTHROPIC_API_KEY not configured.")

        with self.anthropic_client.messages.stream(
            model=model_name,
            max_tokens=1024,
            system=system_prompt,
            messages=[{"role": "user", "content": user_message}],
        ) as stream:
            for text in stream.text_stream:
                yield text

            # Capture final usage
            try:
                final = stream.get_final_message()
                yield {
                    "usage": {
                        "prompt_tokens": final.usage.input_tokens,
                        "completion_tokens": final.usage.output_tokens,
                    }
                }
            except:
                pass

    def _generate_gemini_stream_blocking(
        self, model_name: str, system_prompt: str, user_message: str
    ):
        if not self.gemini_enabled:
            raise ValueError("GEMINI_API_KEY not configured.")

        max_retries = 10  # Increased
        backoff = 2
        responses = None
        import random

        for attempt in range(max_retries):
            try:
                responses = self.gemini_client.models.generate_content_stream(
                    model=model_name,
                    config=types.GenerateContentConfig(
                        system_instruction=system_prompt,
                    ),
                    contents=user_message,
                )
                break
            except (errors.ClientError, errors.APIError) as e:
                is_rate_limit = False
                if isinstance(e, errors.ClientError) and e.code == 429:
                    is_rate_limit = True
                elif "429" in str(e) or "RESOURCE_EXHAUSTED" in str(e):
                    is_rate_limit = True

                if is_rate_limit:
                    if attempt < max_retries - 1:
                        # Jittered backoff
                        jitter = random.uniform(0.5, 1.5)
                        wait_time = backoff * jitter

                        match = re.search(r"retry in ([0-9.]+)s", str(e))
                        if match:
                            wait_time = float(match.group(1)) + 1.0

                        logger.warning(
                            f"Gemini Stream Rate Limit (429). Retrying in {wait_time:.2f}s... (Attempt {attempt+1}/{max_retries})"
                        )
                        time.sleep(wait_time)
                        backoff *= 2
                        continue
                self._record_completion(0, 0)  # Record failure
                raise e
            except Exception as e:
                logger.error(f"Gemini stream unexpected error: {e}")
                self._record_completion(0, 0)  # Record failure
                raise e

        # FIX MIN-02: Handle exhausted retries — don't iterate over None
        if responses is None:
            logger.error(
                f"Gemini stream failed after {max_retries} retries — no response obtained."
            )
            self._record_completion(0, 0)  # Record failure
            return

        for response in responses:
            if response.usage_metadata:
                usage = response.usage_metadata
                # For Gemini stream, usage metadata is per-chunk, but we only want to record once.
                # The metric_wrapper will handle the final token count.
                # We can yield usage data as a special chunk for the wrapper to process.
                yield {
                    "usage": {
                        "prompt_token_count": usage.prompt_token_count,
                        "candidates_token_count": usage.candidates_token_count,
                    }
                }

            if response.text:
                yield response.text

    # --- LOCAL (Requests is already blocking, but run_in_executor needs strict func) ---
    # Since requests stream needs to yield lines, we can wrap this too or leave as is if we wrap the call.
    # But wait, the existing _generate_local_stream was async def.
    # It used self.session.post inside.
    # To make it non-blocking, we should wrap the synchronous requests iteration.

    async def _generate_local_stream(
        self, model_name: str, system_prompt: str, user_message: str
    ):
        # Wrapper for local
        async for chunk in self._run_blocking_stream(
            self._generate_local_stream_blocking,
            model_name,
            system_prompt,
            user_message,
        ):
            yield chunk

    def _generate_local_stream_blocking(
        self, model_name: str, system_prompt: str, user_message: str
    ):
        import json

        actual_model = self._get_actual_model(model_name)

        payload = {
            "model": actual_model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
            "stream": True,
        }

        try:
            max_retries = 3
            backoff_delay = 2

            for attempt in range(max_retries):
                try:
                    with self.session.post(
                        self.local_url, json=payload, timeout=self.timeout, stream=True
                    ) as response:
                        response.raise_for_status()
                        for line in response.iter_lines():
                            if line:
                                chunk = json.loads(line)
                                if "message" in chunk and "content" in chunk["message"]:
                                    yield chunk["message"]["content"]
                                if chunk.get("done"):
                                    # Tracking for local stream
                                    self._record_completion(
                                        chunk.get("prompt_eval_count", 0),
                                        chunk.get("eval_count", 0),
                                    )
                                    break
                    return
                except (
                    requests.exceptions.ConnectionError,
                    requests.exceptions.ChunkedEncodingError,
                    requests.exceptions.Timeout,
                    requests.exceptions.HTTPError,
                ) as e:
                    if attempt < max_retries - 1:
                        import time

                        # Check if it's a 500 error specifically to retry
                        if (
                            isinstance(e, requests.exceptions.HTTPError)
                            and e.response.status_code >= 500
                        ):
                            logger.warning(
                                f"Local LLM 500 Error. Retrying (Attempt {attempt+1}/{max_retries})..."
                            )
                        elif not isinstance(e, requests.exceptions.HTTPError):
                            logger.warning(f"Local LLM Network Error: {e}. Retrying...")

                        time.sleep(backoff_delay)
                        backoff_delay *= 2
                    else:
                        self._record_completion(0, 0)  # Record failure
                        raise e
        except Exception as e:
            logger.error(f"Local LLM streaming error: {e}")
            self._record_completion(0, 0)  # Record failure
            yield "[Agent Silent - Neural Link Severed]"

    def _generate_local(
        self, model_name: str, system_prompt: str, user_message: str
    ) -> str:
        """
        Synchronous call to local Ollama API (non-streaming).
        Used by PhysicsEngine for atomic calculations.
        """
        import json

        actual_model = self._get_actual_model(model_name)

        payload = {
            "model": actual_model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
            "stream": False,
        }

        try:
            # Retry logic for resilience
            max_retries = 3
            backoff_delay = 2

            for attempt in range(max_retries):
                try:
                    response = self.session.post(
                        self.local_url, json=payload, timeout=self.timeout
                    )
                    response.raise_for_status()
                    result = response.json()
                    content = result["message"]["content"]

                    # Tracking (Ollama sends token counts in non-streaming response)
                    self._record_completion(
                        result.get("prompt_eval_count", 0), result.get("eval_count", 0)
                    )
                    logger.info(
                        f"[LLM] Local Usage: {result.get('prompt_eval_count', 0)} in, {result.get('eval_count', 0)} out."
                    )

                    if self.testing:
                        self.cache.set(model_name, system_prompt, user_message, content)
                    return content
                except (
                    requests.exceptions.ConnectionError,
                    requests.exceptions.Timeout,
                    requests.exceptions.HTTPError,
                ) as e:
                    if attempt < max_retries - 1:
                        # Check if it's a 500 error specifically to retry
                        if (
                            isinstance(e, requests.exceptions.HTTPError)
                            and e.response.status_code >= 500
                        ):
                            logger.warning(
                                f"Local LLM 500 Error. Retrying (Attempt {attempt+1}/{max_retries})..."
                            )
                        elif not isinstance(e, requests.exceptions.HTTPError):
                            logger.warning(f"Local LLM Network Error: {e}. Retrying...")

                        time.sleep(backoff_delay)
                        backoff_delay *= 2
                    else:
                        raise e
        except Exception as e:
            logger.error(f"Local LLM error: {e}")
            return self._fallback_response(system_prompt, user_message)

    def _get_actual_model(self, model_name: str) -> str:
        """
        Resolves generic model names to specific local versions.
        """
        # If we are in local mode, FORCE the local model (unless valid local override is possible, but let's stick to simple)
        if self.provider_override == "local":
            return self.local_model_name or "qwen2.5:7b"

        if model_name == "local" or model_name.startswith("local/"):
            return self.local_model_name or "qwen2.5:7b"
        # If it's a specific model name passed through (like 'qwen2.5:14b'), use it
        return model_name

    def _fallback_response(self, system_prompt: str, user_message: str) -> str:
        if self.provider_override == "local":
            return "[Agent Silent - Neural Link Severed]"

        logger.info("Using fallback model: gpt-3.5-turbo")
        try:
            return self._generate_openai("gpt-3.5-turbo", system_prompt, user_message)
        except Exception:
            return "[Agent Silent - Neural Link Severed]"
