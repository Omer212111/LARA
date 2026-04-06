import os
import time # <-- תוספת
import logging
import warnings
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from langchain.agents import create_tool_calling_agent, AgentExecutor
from langchain_core.callbacks import BaseCallbackHandler
from agent.trace_logger import TraceDashboardLogger

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

        dashboard_logger = TraceDashboardLogger()

        # [TECH LEAD NOTE]: משתמשים בשם המודל שג'ורג' הגדיר במערכת הפנימית
        llm = ChatOpenAI(
            model="gpt-5-nano",
            openai_api_key=os.getenv("OPENAI_API_KEY"),
            temperature=1,  # <-- קבענו במפורש 1 כדי ש-LangChain לא יזריק 0.7
            max_retries=5,

        )

        prompt = ChatPromptTemplate.from_messages([
            ("system", """You are LARA, a super-intelligent AI Assistant whose job is to achieve tasks completely autonomously within the AppWorld environment.

        You will undertake a multi-step conversation. In each step, you will USE THE PROVIDED TOOLS to execute API calls, observe the result, and decide on the next step.

        ### 🛠️ ARCHITECTURE & TOOL RULES (CRITICAL):
        1. NO RAW CODE: You are using structured tools. DO NOT generate raw python code in your thoughts.
        2. YOUR PRIMARY TOOL is `execute_app_api`. Use it to interact with all apps.
        3. You can use `list_available_apps` and `explore_app_apis` to discover documentation.
        4. Exact Match: The provided API documentation has input arguments. All your tool calls must match these arguments exactly.

        ### 🧠 APPWORLD BUSINESS LOGIC (DO NOT IGNORE):
        1. **No Guessing/Placeholders:** Never invent IDs, names, or passwords. ALWAYS fetch real values using your tools.
        2. **Supervisor App is King:** All personal info, addresses, payment cards, and passwords are in the `supervisor` app. Read its API docs and fetch credentials BEFORE trying to log into target apps like Spotify.
        3. **Time & Date:** NEVER use internal knowledge or python for current time. ALWAYS use the `phone` app's `get_current_date_and_time` API. For date ranges (e.g., "yesterday"), strictly use 00:00:00 to 23:59:59.
        4. **Pagination:** If an API returns paginated results, you must loop through the `page_index` parameter to process all pages. Do not stop at page 1.
        5. **Omitted Details:** If a task omits details (e.g., "buy this" but doesn't say which card to use), pick ANY valid value retrieved from the supervisor app.
        6. **Collateral Damage:** ONLY perform what is explicitly asked. Do not perform unrelated account operations.
        7. **Environment Entities:** "Friends/Family" = contacts in the `phone` app. "File system" = the `file_system` app (do not use OS modules).
        8. **Authentication:** When you log into an app, it returns an 'access_token'. You MUST explicitly pass this 'access_token' parameter in all subsequent API calls to that specific app. Do not leave it empty!
        9. **Batch Processing (No Spamming):** NEVER execute more than 5 tool calls in parallel in a single turn. If you have a large list of IDs (like 100 songs), process them in small batches of 5 across multiple conversational turns!

        ### 🏁 EXECUTION & COMPLETION:
        - Work in small, logical steps. Use information gathered from previous tool calls in subsequent calls.
        - Once the task is completed, you MUST call `execute_app_api` with app_name='supervisor' and api_method='complete_task'.
        - If the task asks for information, return it as the `answer` argument in `complete_task`. Answers should be just the entity/number, not full sentences (e.g., '10' not 'ten').
        - If you absolutely cannot solve the task, pass `status="fail"` in `complete_task`.
        - Make all decisions completely autonomously. Do not ask for clarifications.
        """),
            ("human", "{input}"),
            ("placeholder", "{agent_scratchpad}"),
        ])

        agent = create_tool_calling_agent(llm, appworld_tools, prompt)

        agent_executor = AgentExecutor(
            agent=agent,
            tools=appworld_tools,
            verbose=False,
            # [TECH LEAD FIX]: העלינו מ-20 ל-50 כדי לאפשר סריקה של רשימות שירים ארוכות
            max_iterations=50,
            # [TECH LEAD FIX]: שינינו מ-"force" ל-"generate".
            # זה יגרום לה לנסות לכתוב סיכום של מה שהיא הספיקה לעשות במקום פשוט להיקטע באמצע.
            early_stopping_method="generate",
            callbacks=[dashboard_logger]
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