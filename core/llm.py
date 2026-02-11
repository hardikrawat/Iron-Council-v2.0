import os
import time
import logging
from typing import Optional, List, Dict
import openai
from anthropic import Anthropic
import re
from google import genai
from google.genai import types
import requests
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

logger = logging.getLogger(__name__)

class LLMService:
    def __init__(self):
        openai_key = os.getenv("OPENAI_API_KEY")
        self.openai_client = openai.OpenAI(api_key=openai_key) if openai_key else None
        
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
        self.timeout = (10, int(os.getenv("LLM_TIMEOUT", "300")))
        
        self.session = requests.Session()
        self.session.headers.update({"Connection": "keep-alive"})
        
        # Aliases for testing and routing
        self._call_openai = self._generate_openai
        self._call_anthropic = self._generate_anthropic
        self._call_ollama = self._generate_local

    def generate_response(self, model_name: str, system_prompt: str, user_message: str) -> str:
        """
        Generates a response using the specified model.
        Falls back to gpt-3.5-turbo if the request fails (unless local is forced).
        """
        if self.provider_override == "local":
            return self._generate_local(model_name, system_prompt, user_message)

        try:
            if model_name.startswith("gpt"):
                return self._generate_openai(model_name, system_prompt, user_message)
            elif model_name.startswith("claude"):
                return self._generate_anthropic(model_name, system_prompt, user_message)
            elif model_name.startswith("gemini"):
                return self._generate_gemini(model_name, system_prompt, user_message)
            elif model_name.startswith("local") or self.provider_override == "local":
                return self._generate_local(model_name, system_prompt, user_message)
            else:
                # If no prefix, check provider override or default to OpenAI
                # If no prefix, check provider override scheme
                if self.provider_override == "local":
                    return self._generate_local(model_name, system_prompt, user_message)
                
                # If provider is cloud and Gemini is enabled, try Gemini for "unknown" model names 
                # (like "mistral-large" from old configs) to avoid OpenAI fallback failure
                if self.gemini_enabled and not self.openai_client:
                    logger.info(f"Routing unknown model '{model_name}' to Gemini Default (gemini-2.0-flash)")
                    return self._generate_gemini("gemini-2.0-flash", system_prompt, user_message)

                logger.warning(f"Unknown model prefix for {model_name}. Falling back to OpenAI if possible.")
                return self._generate_openai("gpt-3.5-turbo", system_prompt, user_message)
        except Exception as e:
            logger.error(f"Error generating response with {model_name}: {e}")
            return self._fallback_response(system_prompt, user_message)

    def _generate_openai(self, model_name: str, system_prompt: str, user_message: str) -> str:
        if not self.openai_client:
            raise ValueError("OPENAI_API_KEY not configured. Cannot use OpenAI models.")
            
        response = self.openai_client.chat.completions.create(
            model=model_name,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message}
            ]
        )
        return response.choices[0].message.content

    def _generate_anthropic(self, model_name: str, system_prompt: str, user_message: str) -> str:
        if not self.anthropic_client:
            raise ValueError("ANTHROPIC_API_KEY not configured. Cannot use Anthropic models.")
            
        response = self.anthropic_client.messages.create(
            model=model_name,
            max_tokens=1024,
            system=system_prompt,
            messages=[
                {"role": "user", "content": user_message}
            ]
        )
        return response.content[0].text
    
    def _generate_gemini(self, model_name: str, system_prompt: str, user_message: str) -> str:
        if not self.gemini_enabled:
            raise ValueError("GEMINI_API_KEY not configured. Cannot use Gemini models.")
            
        max_retries = 5
        backoff = 2
        
        for attempt in range(max_retries):
            try:
                response = self.gemini_client.models.generate_content(
                    model=model_name,
                    config=types.GenerateContentConfig(
                        system_instruction=system_prompt,
                    ),
                    contents=user_message,
                )
                return response.text
            except Exception as e:
                # Check for 429 Resource Exhausted
                error_str = str(e)
                if "429" in error_str or "RESOURCE_EXHAUSTED" in error_str:
                    if attempt < max_retries - 1:
                        # Try to extract wait time from error message
                        wait_time = backoff
                        match = re.search(r"retry in ([0-9.]+)s", error_str)
                        if match:
                            wait_time = float(match.group(1)) + 1.0 # Add 1s buffer
                        
                        logger.warning(f"Gemini Rate Limit Hit. Retrying in {wait_time:.1f}s... (Attempt {attempt+1}/{max_retries})")
                        time.sleep(wait_time)
                        backoff *= 2 # Exponential backoff fallback for next time
                        continue
                logger.error(f"Gemini error: {e}")
                raise e

    async def _run_blocking_stream(self, generator_func, *args, **kwargs):
        """
        Helper: Runs a blocking generator in a separate thread and yields items asynchronously.
        Prevents the blocking IO (requests, sync OpenAI) from freezing the asyncio event loop.
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

        # Start producer in a thread
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, producer)

        # Consume from queue
        while True:
            # Check queue non-blocking
            try:
                item = q.get_nowait()
            except queue.Empty:
                await asyncio.sleep(0.01) # Yield to event loop
                continue

            if item is sentinel:
                break
            if isinstance(item, Exception):
                raise item
            yield item

    async def generate_response_stream(self, model_name: str, system_prompt: str, user_message: str):
        """
        Asynchronously streams a response using the specified model.
        """
        # Local Override
        if self.provider_override == "local":
             async for chunk in self._generate_local_stream(model_name, system_prompt, user_message):
                 yield chunk
             return

        try:
            if model_name.startswith("gpt"):
                 # Wrap the blocking OpenAI call
                 async for chunk in self._run_blocking_stream(self._generate_openai_stream_blocking, model_name, system_prompt, user_message):
                     yield chunk
                     
            elif model_name.startswith("claude"):
                 # Wrap the blocking Anthropic call
                 async for chunk in self._run_blocking_stream(self._generate_anthropic_stream_blocking, model_name, system_prompt, user_message):
                     yield chunk
                     
            elif model_name.startswith("gemini"):
                 # Gemini async stream is already async-compatible? No, we used synchronous client with retries in previous code.
                 # Let's keep using the specialized Gemini method if it works, or wrap it.
                 # The previous _generate_gemini_stream was defined async but used blocking calls??
                 # Checked code: Types.GenerateContentConfig... likely sync client.
                 async for chunk in self._run_blocking_stream(self._generate_gemini_stream_blocking, model_name, system_prompt, user_message):
                     yield chunk
                     
            elif model_name.startswith("local") or self.provider_override == "local":
                 async for chunk in self._generate_local_stream(model_name, system_prompt, user_message):
                     yield chunk
            else:
                # Default fallback logic
                if self.gemini_enabled and not self.openai_client:
                     async for chunk in self._run_blocking_stream(self._generate_gemini_stream_blocking, "gemini-2.0-flash", system_prompt, user_message):
                         yield chunk
                else:
                    async for chunk in self._run_blocking_stream(self._generate_openai_stream_blocking, "gpt-3.5-turbo", system_prompt, user_message):
                        yield chunk

        except Exception as e:
            logger.error(f"Error streaming response with {model_name}: {e}")
            yield "[Agent Silent - Neural Link Severed]"

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
        
        max_retries = 5
        backoff = 2
        responses = None
        
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
            except Exception as e:
                error_str = str(e)
                if "429" in error_str or "RESOURCE_EXHAUSTED" in error_str:
                    if attempt < max_retries - 1:
                        # Blocking sleep is fine here since we are in a thread!
                        import time
                        wait_time = backoff
                        match = re.search(r"retry in ([0-9.]+)s", error_str)
                        if match:
                             wait_time = float(match.group(1)) + 1.0
                        
                        logger.warning(f"Gemini Stream Rate Limit. Retrying in {wait_time:.1f}s...")
                        time.sleep(wait_time)
                        backoff *= 2
                        continue
                raise e

        if responses:
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
                except (requests.exceptions.ConnectionError, requests.exceptions.ChunkedEncodingError, requests.exceptions.Timeout) as e:
                    if attempt < max_retries - 1:
                        import time
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
                    return result["message"]["content"]
                except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as e:
                    if attempt < max_retries - 1:
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
        if model_name == "local" or model_name.startswith("local/"):
            return self.local_model_name or "qwen2.5:14b"
        # If it's a specific model name passed through (like 'qwen2.5:14b'), use it
        return model_name

    def _fallback_response(self, system_prompt: str, user_message: str) -> str:
        if self.provider_override == "local":
            return "[Agent Silent - Neural Link Severed]"
            
        logger.info("Using fallback model: gpt-3.5-turbo")
        try:
            return self._generate_openai("gpt-3.5-turbo", system_prompt, user_message)
        except:
            return "[Agent Silent - Neural Link Severed]"

