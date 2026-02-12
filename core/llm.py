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
        self.openai_client = openai.OpenAI(api_key=openai_key, timeout=llm_timeout) if openai_key else None
        
        anthropic_key = os.getenv("ANTHROPIC_API_KEY")
        self.anthropic_client = Anthropic(api_key=anthropic_key) if anthropic_key else None
        
        gemini_key = os.getenv("GEMINI_API_KEY")
        if gemini_key:
            self.gemini_client = genai.Client(api_key=gemini_key)
            self.gemini_enabled = True
        else:
            self.gemini_enabled = False
        
        self.mistral_api_key = os.getenv("MISTRAL_API_KEY")
        self.local_url = os.getenv("LOCAL_LLM_URL", "http://localhost:11434/api/chat")
        self.local_model_name = os.getenv("LOCAL_MODEL_NAME")
        self.provider_override = os.getenv("LLM_PROVIDER") # e.g., 'local'
        
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
             return "CLOUD:gemini-2.0-flash"
        return "CLOUD:gpt-3.5-turbo"

    def generate_response(self, model_name: str, system_prompt: str, user_message: str) -> str:
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
            self.event_bus.publish_threadsafe(EventType.LLM_ACTIVITY, {
                "status": "START", 
                "model": model_name,
                "provider": provider_type
            })

        response_content = ""
        try:
            if self.testing:
                cached = self.cache.get(model_name, system_prompt, user_message)
                if cached:
                    response_content = cached
                    return cached

            if self.provider_override == "local":
                response_content = self._generate_local(model_name, system_prompt, user_message)
            elif model_name.startswith("gpt"):
                response_content = self._generate_openai(model_name, system_prompt, user_message)
            elif model_name.startswith("claude"):
                response_content = self._generate_anthropic(model_name, system_prompt, user_message)
            elif model_name.startswith("gemini"):
                response_content = self._generate_gemini(model_name, system_prompt, user_message)
            elif model_name.startswith("local") or self.provider_override == "local":
                response_content = self._generate_local(model_name, system_prompt, user_message)
            else:
                if self.provider_override == "local":
                    logger.info(f"[LLM] Routing '{model_name}' to LOCAL via provider_override.")
                    response_content = self._generate_local(model_name, system_prompt, user_message)
                elif self.gemini_enabled and not self.openai_client:
                    logger.info(f"[LLM] Routing unknown model '{model_name}' to Gemini Default (gemini-2.0-flash)")
                    response_content = self._generate_gemini("gemini-2.0-flash", system_prompt, user_message)
                else:
                    logger.warning(f"Unknown model prefix for {model_name}. Falling back to OpenAI if possible.")
                    response_content = self._generate_openai("gpt-3.5-turbo", system_prompt, user_message)
            
            # PHASE 4 LOGGING: Trace full interaction
            logger.info(f"\n[LLM_TRACE] MODEL: {model_name}\n[PROMPT]: {user_message[:500]}...\n[RESPONSE]: {response_content[:500]}...\n[STATS] Len: {len(response_content)}")
            
            return response_content

        except Exception as e:
            logger.error(f"Error generating response with {model_name}: {e}")
            return self._fallback_response(system_prompt, user_message)
        finally:
            # Calculate Metrics
            end_time = time.time()
            duration = end_time - start_time
            char_count = len(response_content) if response_content else 0
            
            # FIX NET-01: Detect timeout/failure (0 chars) and report as error
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
                self.event_bus.publish_threadsafe(EventType.LLM_ACTIVITY, {
                    "status": "END",
                    "latency": latency_ms,
                    "baud": baud_rate,
                    "provider": provider_type
                })

    def _generate_openai(self, model_name: str, system_prompt: str, user_message: str) -> str:
        if not self.openai_client:
            raise ValueError("OPENAI_API_KEY not configured. Cannot use OpenAI models.")
        
        logger.info(f"[LLM] Generating with OpenAI ({model_name})...")
        response = self.openai_client.chat.completions.create(
            model=model_name,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message}
            ]
        )
        if self.testing:
            self.cache.set(model_name, system_prompt, user_message, response.choices[0].message.content)
        return response.choices[0].message.content

    def _generate_anthropic(self, model_name: str, system_prompt: str, user_message: str) -> str:
        if not self.anthropic_client:
            raise ValueError("ANTHROPIC_API_KEY not configured. Cannot use Anthropic models.")
            
        logger.info(f"[LLM] Generating with Anthropic ({model_name})...")
        response = self.anthropic_client.messages.create(
            model=model_name,
            max_tokens=1024,
            system=system_prompt,
            messages=[
                {"role": "user", "content": user_message}
            ]
        )
        if self.testing:
            self.cache.set(model_name, system_prompt, user_message, response.content[0].text)
        return response.content[0].text
    
    def _generate_gemini(self, model_name: str, system_prompt: str, user_message: str) -> str:
        if not self.gemini_enabled:
            raise ValueError("GEMINI_API_KEY not configured. Cannot use Gemini models.")
            
        max_retries = 10  # Increased for stability
        backoff = 2
        import random
        
        for attempt in range(max_retries):
            try:
                logger.info(f"[LLM] Generating with Gemini ({model_name}) [Attempt {attempt+1}]...")
                response = self.gemini_client.models.generate_content(
                    model=model_name,
                    config=types.GenerateContentConfig(
                        system_instruction=system_prompt,
                    ),
                    contents=user_message,
                )
                if self.testing:
                    self.cache.set(model_name, system_prompt, user_message, response.text)
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
                        wait_time = (backoff * jitter)
                        
                        # Try to extract wait time from error message if available
                        match = re.search(r"retry in ([0-9.]+)s", str(e))
                        if match:
                            wait_time = float(match.group(1)) + 1.0
                        
                        logger.warning(f"Gemini Rate Limit Hit (429). Retrying in {wait_time:.2f}s... (Attempt {attempt+1}/{max_retries})")
                        time.sleep(wait_time)
                        backoff *= 2 # Exponential backoff
                        continue
                logger.error(f"Gemini error: {e}")
                raise e
            except Exception as e:
                logger.error(f"Gemini unexpected error: {e}")
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
                q.put(e) # Pass error to consumer
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
                await asyncio.sleep(0.01) # Yield to event loop, let producer work
                continue

            if item is sentinel:
                break
            if isinstance(item, Exception):
                raise item
            yield item

        # Ensure the background thread has completed cleanly
        await future

    async def generate_response_stream(self, model_name: str, system_prompt: str, user_message: str):
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
             await self.event_bus.publish(EventType.LLM_ACTIVITY, {
                 "status": "START", 
                 "model": model_name,
                 "provider": provider_type
            })

        try:
            # Helper to wrap the stream and track metrics
            async def metric_wrapper(async_gen):
                nonlocal first_token_time, char_count
                async for chunk in async_gen:
                    if first_token_time is None:
                        first_token_time = time.time()
                        latency = int((first_token_time - start_time) * 1000)
                        # Emit First Token Latency immediately
                        if self.event_bus:
                            await self.event_bus.publish(EventType.LLM_ACTIVITY, {
                                "status": "lat_update",  # Intermediate update
                                "latency": latency,
                                "provider": provider_type
                            })
                    
                    char_count += len(chunk)
                    yield chunk

            # Local Override
            if self.provider_override == "local":
                 async for chunk in metric_wrapper(self._generate_local_stream(model_name, system_prompt, user_message)):
                     yield chunk
                 return

            if model_name.startswith("gpt"):
                 # Wrap the blocking OpenAI call
                 async for chunk in metric_wrapper(self._run_blocking_stream(self._generate_openai_stream_blocking, model_name, system_prompt, user_message)):
                     yield chunk
                     
            elif model_name.startswith("claude"):
                 # Wrap the blocking Anthropic call
                 async for chunk in metric_wrapper(self._run_blocking_stream(self._generate_anthropic_stream_blocking, model_name, system_prompt, user_message)):
                     yield chunk
                     
            elif model_name.startswith("gemini"):
                 async for chunk in metric_wrapper(self._run_blocking_stream(self._generate_gemini_stream_blocking, model_name, system_prompt, user_message)):
                     yield chunk
                     
            elif model_name.startswith("local") or self.provider_override == "local":
                 async for chunk in metric_wrapper(self._generate_local_stream(model_name, system_prompt, user_message)):
                     yield chunk
            else:
                # Default fallback logic
                if self.gemini_enabled and not self.openai_client:
                     async for chunk in metric_wrapper(self._run_blocking_stream(self._generate_gemini_stream_blocking, "gemini-2.0-flash", system_prompt, user_message)):
                         yield chunk
                else:
                    async for chunk in metric_wrapper(self._run_blocking_stream(self._generate_openai_stream_blocking, "gpt-3.5-turbo", system_prompt, user_message)):
                        yield chunk

        except Exception as e:
            logger.error(f"Error streaming response with {model_name}: {e}")
            yield "[Agent Silent - Neural Link Severed]"
        finally:
            # Calculate Final Baud Rate
            end_time = time.time()
            duration = end_time - start_time
            
            # FIX NET-01: Detect timeout/failure (0 chars) and report as error
            if char_count == 0:
                latency_ms = -1
                baud_rate = 0
            else:
                # Use First Token Latency if available, else Total Duration
                latency_ms = int((first_token_time - start_time) * 1000) if first_token_time else int(duration * 1000)
                # Baud rate based on streaming duration
                baud_rate = int((char_count * 8) / duration) if duration > 0 else 0

            if self.event_bus:
                from core.event_bus import EventType
                await self.event_bus.publish(EventType.LLM_ACTIVITY, {
                    "status": "END",
                    "latency": latency_ms,
                    "baud": baud_rate,
                    "provider": provider_type
                })

    # --- BLOCKING GENERATORS (Run in Thread) ---

    def _generate_openai_stream_blocking(self, model_name: str, system_prompt: str, user_message: str):
        if not self.openai_client:
            raise ValueError("OPENAI_API_KEY not configured.")
        
        response = self.openai_client.chat.completions.create(
            model=model_name,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message}
            ],
            stream=True
        )
        for chunk in response:
            if chunk.choices[0].delta.content:
                yield chunk.choices[0].delta.content

    def _generate_anthropic_stream_blocking(self, model_name: str, system_prompt: str, user_message: str):
        if not self.anthropic_client:
            raise ValueError("ANTHROPIC_API_KEY not configured.")
            
        with self.anthropic_client.messages.stream(
            model=model_name,
            max_tokens=1024,
            system=system_prompt,
            messages=[{"role": "user", "content": user_message}]
        ) as stream:
            for text in stream.text_stream:
                yield text

    def _generate_gemini_stream_blocking(self, model_name: str, system_prompt: str, user_message: str):
        if not self.gemini_enabled:
            raise ValueError("GEMINI_API_KEY not configured.")
        
        max_retries = 10 # Increased
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
                        wait_time = (backoff * jitter)
                        
                        match = re.search(r"retry in ([0-9.]+)s", str(e))
                        if match:
                             wait_time = float(match.group(1)) + 1.0
                        
                        logger.warning(f"Gemini Stream Rate Limit (429). Retrying in {wait_time:.2f}s... (Attempt {attempt+1}/{max_retries})")
                        time.sleep(wait_time)
                        backoff *= 2
                        continue
                raise e
            except Exception as e:
                logger.error(f"Gemini stream unexpected error: {e}")
                raise e

        # FIX MIN-02: Handle exhausted retries — don't iterate over None
        if responses is None:
            logger.error(f"Gemini stream failed after {max_retries} retries — no response obtained.")
            return

        for response in responses:
            if response.text:
                yield response.text

    # --- LOCAL (Requests is already blocking, but run_in_executor needs strict func) ---
    # Since requests stream needs to yield lines, we can wrap this too or leave as is if we wrap the call.
    # But wait, the existing _generate_local_stream was async def.
    # It used self.session.post inside.
    # To make it non-blocking, we should wrap the synchronous requests iteration.
    
    async def _generate_local_stream(self, model_name: str, system_prompt: str, user_message: str):
        # Wrapper for local
        async for chunk in self._run_blocking_stream(self._generate_local_stream_blocking, model_name, system_prompt, user_message):
            yield chunk

    def _generate_local_stream_blocking(self, model_name: str, system_prompt: str, user_message: str):
        import json
        actual_model = self._get_actual_model(model_name)
        
        payload = {
            "model": actual_model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message}
            ],
            "stream": True
        }

        try:
            max_retries = 3
            backoff_delay = 2
            
            for attempt in range(max_retries):
                try:
                    with self.session.post(self.local_url, json=payload, timeout=self.timeout, stream=True) as response:
                        response.raise_for_status()
                        for line in response.iter_lines():
                            if line:
                                chunk = json.loads(line)
                                if 'message' in chunk and 'content' in chunk['message']:
                                    yield chunk['message']['content']
                                if chunk.get('done'):
                                    break
                    return 
                except (requests.exceptions.ConnectionError, requests.exceptions.ChunkedEncodingError, requests.exceptions.Timeout, requests.exceptions.HTTPError) as e:
                    if attempt < max_retries - 1:
                        import time
                        # Check if it's a 500 error specifically to retry
                        if isinstance(e, requests.exceptions.HTTPError) and e.response.status_code >= 500:
                            logger.warning(f"Local LLM 500 Error. Retrying (Attempt {attempt+1}/{max_retries})...")
                        elif not isinstance(e, requests.exceptions.HTTPError):
                            logger.warning(f"Local LLM Network Error: {e}. Retrying...")
                            
                        time.sleep(backoff_delay)
                        backoff_delay *= 2
                    else:
                        raise e
        except Exception as e:
            logger.error(f"Local LLM streaming error: {e}")
            yield "[Agent Silent - Neural Link Severed]"

    def _generate_local(self, model_name: str, system_prompt: str, user_message: str) -> str:
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
                {"role": "user", "content": user_message}
            ],
            "stream": False
        }

        try:
            # Retry logic for resilience
            max_retries = 3
            backoff_delay = 2
            
            for attempt in range(max_retries):
                try:
                    response = self.session.post(self.local_url, json=payload, timeout=self.timeout)
                    response.raise_for_status()
                    result = response.json()
                    content = result["message"]["content"]
                    if self.testing:
                        self.cache.set(model_name, system_prompt, user_message, content)
                    return content
                except (requests.exceptions.ConnectionError, requests.exceptions.Timeout, requests.exceptions.HTTPError) as e:
                    if attempt < max_retries - 1:
                         # Check if it's a 500 error specifically to retry
                        if isinstance(e, requests.exceptions.HTTPError) and e.response.status_code >= 500:
                            logger.warning(f"Local LLM 500 Error. Retrying (Attempt {attempt+1}/{max_retries})...")
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

