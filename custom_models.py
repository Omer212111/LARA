import requests
import json
import warnings
from typing import Any, List, Optional, Iterator
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import BaseMessage, AIMessage, HumanMessage, SystemMessage, AIMessageChunk
from langchain_core.outputs import ChatResult, ChatGeneration, ChatGenerationChunk

warnings.filterwarnings("ignore", message="Unverified HTTPS request")

OLLAMA_API_URL = "https://192.116.98.6/api/generate"
OLLAMA_AUTH    = ("group1", "MTAgroup1")
MODEL_NAME     = "gpt-oss:20b"

class CustomChatOllama(BaseChatModel):
    """
    Bridge מותאם אישית ל-Ollama עבור LangChain ReAct בסביבת AppWorld.
    משתמש ב-/api/generate עם chat-ml template ידני.
    """
    model_name: str = MODEL_NAME
    api_url:    str = OLLAMA_API_URL
    auth:       tuple = OLLAMA_AUTH

    @property
    def _llm_type(self) -> str:
        return "custom_chat_ollama"

    def _format_prompt(self, messages: List[BaseMessage]) -> str:
        """ממיר רשימת LangChain messages ל-ChatML string שהמודל מבין."""
        prompt = ""
        for msg in messages:
            if isinstance(msg, SystemMessage):
                prompt += f"<|im_start|>system\n{msg.content}<|im_end|>\n"
            elif isinstance(msg, HumanMessage):
                prompt += f"<|im_start|>user\n{msg.content}<|im_end|>\n"
            elif isinstance(msg, AIMessage):
                prompt += f"<|im_start|>assistant\n{msg.content}<|im_end|>\n"
        prompt += "<|im_start|>assistant\n"
        return prompt

    def _generate(self, messages: List[BaseMessage], stop: Optional[List[str]] = None, **kwargs: Any) -> ChatResult:
        full_text = ""
        for chunk in self._stream(messages, stop=stop, **kwargs):
            full_text += chunk.message.content
        return ChatResult(generations=[ChatGeneration(message=AIMessage(content=full_text))])

    def _stream(self, messages: List[BaseMessage], stop: Optional[List[str]] = None, **kwargs: Any) -> Iterator[ChatGenerationChunk]:
        formatted_prompt = self._format_prompt(messages)

        # FIX: payload הוא dict רגיל — לא f-string, אז סוגריים רגילים {}
        payload = {
            "model": self.model_name,
            "prompt": formatted_prompt,
            "stream": True,
            "raw": True,
            "options": {
                "temperature": 0,
                # stop tokens: מונע מהמודל להמשיך מעבר לתגובה אחת
                "stop": ["Observation:", "<|im_start|>", "<|im_end|>"]
            }
        }

        try:
            response = requests.post(
                self.api_url,
                json=payload,
                auth=self.auth,
                verify=False,
                timeout=180,
                stream=True
            )
            response.raise_for_status()

            for line in response.iter_lines():
                if line:
                    chunk_json = json.loads(line)
                    chunk_text = chunk_json.get("response", "")
                    yield ChatGenerationChunk(message=AIMessageChunk(content=chunk_text))
                    if chunk_json.get("done"):
                        break

        except Exception as e:
            yield ChatGenerationChunk(message=AIMessageChunk(content=f"Error: {str(e)}"))

    class Config:
        arbitrary_types_allowed = True
        extra = "ignore"