from langchain.agents import create_react_agent, AgentExecutor
from langchain.memory import ConversationSummaryBufferMemory
from langchain_core.prompts import PromptTemplate
from tools import appworld_tools
from custom_models import CustomChatOllama


# הפרומפט חייב להכיל בדיוק את המשתנים שcreate_react_agent מצפה להם:
#   {tools}            — תיאור הכלים (מולא אוטומטית)
#   {tool_names}       — שמות הכלים בלבד (מולא אוטומטית)
#   {input}            — המשימה (מולא דרך invoke)
#   {chat_history}     — היסטוריית זיכרון (מולא מה-memory)
#   {agent_scratchpad} — מחרוזת ה-Thought/Action/Observation (מולא אוטומטית)
#
# input_variables חייב להיות מוצהר במפורש כי from_template לא תמיד מזהה את כולם
REACT_PROMPT = PromptTemplate(
    input_variables=["tools", "tool_names", "input", "chat_history", "agent_scratchpad"],
    template="""You are a super intelligent AI Assistant for AppWorld.
Your job is to complete tasks autonomously by calling APIs through the provided tools.

TOOLS AVAILABLE:
{tools}

### RULES:
1. Always reason as Python comments (#).
2. Never ask for clarification — decide autonomously.
3. One Action per step. Wait for Observation before next Action.
4. When done, call execute_app_api with supervisor.complete_task.
5. To get available apps: use list_available_apps.
6. To explore an app's APIs: use explore_app_apis.
7. To read a specific API spec: use get_api_spec.
8. To call any API: use execute_app_api.

### FORMAT — follow exactly:
Thought: <your reasoning>
Action: <one of [{tool_names}]>
Action Input: <json>
Observation: <filled by environment>
... (repeat)
Thought: <done>
Action: execute_app_api
Action Input: {{"app_name": "supervisor", "api_method": "complete_task", "parameters": {{"answer": "<answer>"}}}}

### TASK:
{input}

### HISTORY:
{chat_history}

{agent_scratchpad}"""
)


def process_goal(goal: str) -> bool:
    try:
        # 1. אתחול המודל
        llm = CustomChatOllama()

        # 2. זיכרון — return_messages=False מחזיר string ולא list (נדרש לפרומפט שלנו)
        memory = ConversationSummaryBufferMemory(
            llm=llm,
            max_token_limit=2000,
            memory_key="chat_history",
            return_messages=False
        )

        # 3. יצירת הסוכן
        agent = create_react_agent(llm, appworld_tools, REACT_PROMPT)

        agent_executor = AgentExecutor(
            agent=agent,
            tools=appworld_tools,
            memory=memory,
            verbose=True,
            handle_parsing_errors=True,
            max_iterations=50
        )

        print(f"\n[LARA] Starting task: {goal}")

        # FIX: רק "input" נדרש כאן — LangChain ממלא את השאר (tools, tool_names, agent_scratchpad)
        agent_executor.invoke({"input": goal})
        return True

    except Exception as e:
        print(f"❌ Critical Error in process_goal: {e}")
        import traceback
        traceback.print_exc()
        return False