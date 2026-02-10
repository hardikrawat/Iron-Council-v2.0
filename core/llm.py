import os
import logging
from typing import Optional, List, Dict
import openai
from anthropic import Anthropic
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
        
        self.mistral_api_key = os.getenv("MISTRAL_API_KEY")
        self.local_url = os.getenv("LOCAL_LLM_URL", "http://localhost:11434/api/chat")
        self.local_model_name = os.getenv("LOCAL_MODEL_NAME")
        self.provider_override = os.getenv("LLM_PROVIDER") # e.g., 'local'
        
        # Specific timeouts for local LLM: (connect, read)
        # Read timeout is large to allow for long generations
        self.timeout = (10, int(os.getenv("LLM_TIMEOUT", "300")))
        
        # Persistent session for local Ollama connection pooling
        self.session = requests.Session()
        self.session.headers.update({"Connection": "keep-alive"})

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
            elif model_name.startswith("local") or self.provider_override == "local":
                return self._generate_local(model_name, system_prompt, user_message)
            else:
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

    def _generate_local(self, model_name: str, system_prompt: str, user_message: str) -> str:
        """
        Generates a response using a local Ollama instance (Chat Mode).
        """
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
            response = self.session.post(self.local_url, json=payload, timeout=self.timeout)
            response.raise_for_status()
            return response.json()['message']['content']
        except (requests.exceptions.ConnectionError, requests.exceptions.Timeout):
            print("\nCRITICAL: Neural link to Ollama timed out or failed. Is the server overloaded?")
            return "[Agent Silent - Neural Link Severed]"
        except Exception as e:
            logger.error(f"Local LLM error: {e}")
            return "[Agent Silent - Neural Link Severed]"

    def _get_actual_model(self, model_name: str) -> str:
        """
        Resolves the final model name to used for local inference, 
        handling overrides and prefixes.
        """
        if self.local_model_name and (
            model_name.startswith("gpt") or 
            model_name.startswith("claude") or 
            model_name.startswith("mistral")
        ):
            return self.local_model_name
        
        return model_name.split(":")[1] if model_name.startswith("local:") else model_name

    async def generate_response_stream(self, model_name: str, system_prompt: str, user_message: str):

        """
        Asynchronously streams a response using the specified model.
        """
        if self.provider_override == "local":
            async for chunk in self._generate_local_stream(model_name, system_prompt, user_message):
                yield chunk
            return

        try:
            if model_name.startswith("gpt"):
                async for chunk in self._generate_openai_stream(model_name, system_prompt, user_message):
                    yield chunk
            elif model_name.startswith("claude"):
                async for chunk in self._generate_anthropic_stream(model_name, system_prompt, user_message):
                    yield chunk
            elif model_name.startswith("local") or self.provider_override == "local":
                async for chunk in self._generate_local_stream(model_name, system_prompt, user_message):
                    yield chunk
            else:
                logger.warning(f"Unknown model prefix for {model_name}. Falling back to OpenAI stream if possible.")
                async for chunk in self._generate_openai_stream("gpt-3.5-turbo", system_prompt, user_message):
                    yield chunk
        except Exception as e:
            logger.error(f"Error streaming response with {model_name}: {e}")
            yield "[Agent Silent - Neural Link Severed]"

    async def _generate_openai_stream(self, model_name: str, system_prompt: str, user_message: str):
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

    async def _generate_anthropic_stream(self, model_name: str, system_prompt: str, user_message: str):
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

    async def _generate_local_stream(self, model_name: str, system_prompt: str, user_message: str):
        """
        Streams a response from local Ollama.
        """
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
            # Persistent session helps with throughput/stability
            max_retries = 3
            backoff_delay = 2
            
            for attempt in range(max_retries):
                try:
                    # We use self.session for connection pooling
                    with self.session.post(self.local_url, json=payload, timeout=self.timeout, stream=True) as response:
                        response.raise_for_status()
                        for line in response.iter_lines():
                            if line:
                                chunk = json.loads(line)
                                if 'message' in chunk and 'content' in chunk['message']:
                                    yield chunk['message']['content']
                                if chunk.get('done'):
                                    break
                    return # Success
                except (requests.exceptions.ConnectionError, requests.exceptions.ChunkedEncodingError, requests.exceptions.Timeout) as e:
                    if attempt < max_retries - 1:
                        error_type = "Timeout" if isinstance(e, requests.exceptions.Timeout) else "Connection Lost"
                        logger.warning(f"{error_type} to local LLM (attempt {attempt+1}/{max_retries}). Retrying in {backoff_delay}s...")
                        import time
                        time.sleep(backoff_delay)
                        backoff_delay *= 2
                    else:
                        raise e

        except (requests.exceptions.ConnectionError, requests.exceptions.Timeout):
            print("\nCRITICAL: Neural stream timed out or severed. Ollama may be struggling with long context.")
            yield "[Agent Silent - Neural Link Severed]"
        except Exception as e:
            logger.error(f"Local LLM streaming error: {e}")
            yield "[Agent Silent - Neural Link Severed]"

    def _fallback_response(self, system_prompt: str, user_message: str) -> str:
        if self.provider_override == "local":
            return "[Agent Silent - Neural Link Severed]"
            
        logger.info("Using fallback model: gpt-3.5-turbo")
        try:
            return self._generate_openai("gpt-3.5-turbo", system_prompt, user_message)
        except:
            return "[Agent Silent - Neural Link Severed]"

