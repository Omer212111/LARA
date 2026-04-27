import json
import os
from langchain_core.callbacks import BaseCallbackHandler

class TraceDashboardLogger(BaseCallbackHandler):
    """
    [TECH LEAD TOOL]: Intercepts agent thoughts and actions and saves them to a JSON file for the UI.
    """
    def __init__(self, filepath="trace_output.json"):
        self.filepath = filepath
        self.trace_data = []
        # איפוס קובץ קודם אם קיים
        self._save_to_disk()

    def on_agent_action(self, action, **kwargs):
        """מופעל כשהסוכן מחליט להשתמש בכלי"""
        step = {
            "type": "thought_and_action",
            "thought": action.log.split("Action:")[0].strip() if "Action:" in action.log else action.log,
            "tool_name": action.tool,
            "tool_input": action.tool_input
        }
        self.trace_data.append(step)
        self._save_to_disk()

    def on_tool_end(self, output, **kwargs):
        """מופעל כשהכלי מסיים לרוץ ומחזיר תוצאה (תצפית)"""
        step = {
            "type": "observation",
            "result": str(output)
        }
        self.trace_data.append(step)
        self._save_to_disk()

    def _save_to_disk(self):
        with open(self.filepath, "w", encoding="utf-8") as f:
            json.dump(self.trace_data, f, indent=4, ensure_ascii=False)