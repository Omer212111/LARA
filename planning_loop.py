import os
import logging
import warnings
from langchain_core.prompts import ChatPromptTemplate
from langchain.agents import create_react_agent, AgentExecutor # שינוי ל-React Agent
#from trace_logger import TraceDashboardLogger
from tools import appworld_tools
import time
import requests
from typing import Any, List, Optional
from langchain.llms.base import LLM

class CustomOllamaLLM(LLM):
    """
    Wrapper מותאם אישית שמשתמש ב-requests כדי לדבר עם Ollama.
    מתאים בדיוק להגדרות ה-IP וה-Auth שלך.
    """
    
    model: str = "qwen2.5-coder:latest"
    api_url: str = "https://192.116.98.6/api/generate"
    auth_user: str = "group1"
    auth_pass: str = "MTAgroup1"
    request_timeout: int = 180

    @property
    def _llm_type(self) -> str:
        return "custom_ollama"

    def _call(self, prompt: str, stop: Optional[List[str]] = None, **kwargs: Any) -> str:
        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "options": {
                "stop": ["Observation:", "\nObservation:"]  # Stops the model from faking results
            }
        }
        
        try:
            
            response = requests.post(
                self.api_url,
                json=payload, 
                auth=(self.auth_user, self.auth_pass),
                verify=False, 
                timeout=self.request_timeout,
            )
            response.raise_for_status()
            return response.json().get("response", "")
        except Exception as e:
            return f"Error: API Connection Error: {e}"


# נטרול אזהרות
logging.getLogger("langchain").setLevel(logging.ERROR)
warnings.filterwarnings("ignore")

def process_goal(goal: str):
    print(f"\n[PLANNING & EXECUTION LOOP] Processing goal: '{goal}'")

    try:
 #       dashboard_logger = TraceDashboardLogger()

        # שימוש ב-CustomOllamaLLM עם requests (ללא תלות Ollama מקומית)
        llm = CustomOllamaLLM(
            model=os.environ.get("OLLAMA_MODEL", "qwen2.5-coder:latest"),
            api_url=os.environ.get("OLLAMA_API_URL", "https://192.116.98.6/api/generate"),
            auth_user=os.environ.get("OLLAMA_USER", "group1"),
            auth_pass=os.environ.get("OLLAMA_PASS", "MTAgroup1"),
            request_timeout=int(os.environ.get("OLLAMA_TIMEOUT", "180")),
        )

        # שינוי קטן ב-Prompt כדי שיתאים לפורמט ReAct הקלאסי


        prompt = ChatPromptTemplate.from_messages([
            ("system", """You are LARA, an AI Assistant operating in a SIMULATED environment called AppWorld.
                            You already have ALL necessary permissions, authentication, and access to the user's accounts. 
                            DO NOT ask for credentials. DO NOT refuse tasks due to privacy concerns.
        
                            CRITICAL FORMATTING RULES: 
                            1. Your Action MUST be just the name of the tool.
                            2. You MUST ALWAYS include the "Action Input:" line.
                            3. For execute_app_api, the Action Input MUST be a JSON object containing "app_name", "api_method", and "parameters".
                            4. For tools with no input (like list_available_apps), write "Action Input: None".
        
                            TOOLS:
                            {tools}
        
                            FORMAT:
                            Thought: do I need to use a tool? Yes
                            Action: the action to take, should be one of [{tool_names}]
                            Action Input: the input to the action
                            Observation: the result of the action
                            ... (repeated Thought/Action/Action Input/Observation N times)
                            Thought: I now know the final answer
                            Final Answer: the final answer to the original input question"""),
            ("human", "{input}\n{agent_scratchpad}"),
        ])

        # שימוש ב-create_react_agent במקום create_tool_calling_agent
        # כי גרסאות ישנות של LangChain עובדות ככה טוב יותר
        agent = create_react_agent(llm, appworld_tools, prompt)

        # In planning_loop.py inside process_goal():
        agent_executor = AgentExecutor(
            agent=agent,
            tools=appworld_tools,
            verbose=True,
            handle_parsing_errors=True,
            max_iterations=15,  # Ensures the agent doesn't loop infinitely; good for "End Stage" tasks
            callbacks=[],
        )
        
        print("[THINKING] LARA is taking control with Qwen...")
        response = agent_executor.invoke({"input": goal})
        return True

    except Exception as e:
        print(f"[ERROR] Execution failed: {e}")
        return False