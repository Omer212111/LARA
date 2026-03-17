import os
import time # <-- תוספת
import logging
import warnings
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.prompts import ChatPromptTemplate
from langchain.agents import create_tool_calling_agent, AgentExecutor
from langchain_core.callbacks import BaseCallbackHandler # <-- תוספת

# חיסול סופי של ההדפסות המעצבנות של ה-title
logging.getLogger("langchain_google_genai").setLevel(logging.ERROR)
warnings.filterwarnings("ignore", message=".*Key 'title' is not supported.*")

# --- הקלאס החדש שלנו לשליטה בקצב (Rate Limiter) ---
class RateLimitPacer(BaseCallbackHandler):
    """מאט את הסוכן כדי שלא נעבור את מגבלת 5 הבקשות בדקה של גוגל ב-Free Tier"""
    def on_llm_end(self, response, **kwargs):
        print("[SYSTEM] Pacing API requests to respect Free Tier limits (sleeping 13 seconds)...")
        time.sleep(13)

from agent.tools import appworld_tools

def process_goal(goal: str):
    print(f"\n[PLANNING & EXECUTION LOOP] Processing goal: '{goal}'")

    gemini_api_key = os.getenv("GEMINI_API_KEY")
    if not gemini_api_key:
        print("[ERROR] Missing GEMINI_API_KEY.")
        return False

    try:
        # אתחול המודל עם חיבור מנגנון ההאטה שלנו
        llm = ChatGoogleGenerativeAI(
            model="gemini-2.5-flash",
            google_api_key=gemini_api_key,
            temperature=0.0,
            max_retries=5,
            callbacks=[RateLimitPacer()]  # <-- התוספת שלנו
        )

        prompt = ChatPromptTemplate.from_messages([
            ("system", """You are LARA, a super-intelligent Autonomous AI Assistant. Your goal is to achieve tasks within the AppWorld environment.

        ### OPERATIONAL GUIDELINES:
        1. **Efficiency First**: You have strict rate limits. Minimize the number of tool calls.
        2. **Known Environment**: You already know the primary apps are usually 'spotify', 'supervisor', 'email', 'phone', 'amazon', etc.
           - DO NOT call `list_available_apps` unless you are completely stuck.
           - Go straight to fetching the API docs for the specific apps you need (e.g., 'spotify' and 'supervisor').
        3. **Authentication**: 
           - Check the `supervisor` app for login credentials (username/email, password).
           - Perform a `login` call to the target app to get an `access_token`.
           - Use that token in subsequent calls.

        ### KEY CONTEXT:
        - **Identity**: All personal info and passwords are in the `supervisor` app.
        - **Time**: Current date/time must be obtained via python's `datetime.now()` or the `phone` app.
        - **Completion**: When finished, you MUST call `execute_app_api` for the `supervisor` app using the `complete_task` method with your final `answer`.

        ### FORMATTING:
        Respond in a concise, step-by-step logical manner.
        """),
            ("human", "{input}"),
            ("placeholder", "{agent_scratchpad}"),
        ])

        agent = create_tool_calling_agent(llm, appworld_tools, prompt)

        agent_executor = AgentExecutor(
            agent=agent,
            tools=appworld_tools,
            verbose=False,  # אנחנו משאירים על False כדי שהטרמינל יישאר נקי
            max_iterations=8,
            early_stopping_method="force"  # <-- התיקון שלנו: חיתוך נקי במקרה של לולאה
        )

        print("[THINKING & ACTING] LARA is taking control...")

        response = agent_executor.invoke({"input": goal})

        print("\n================= LARA'S FINAL RESPONSE =================")
        print(response["output"])
        print("=========================================================")

        return True

    except Exception as e:
        print(f"[ERROR] Execution failed: {e}")
        return False