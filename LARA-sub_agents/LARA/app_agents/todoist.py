"""
LARA MAS — Todoist specialist executor

Activated for any plan step that references the todoist app.
Adds Todoist-specific API knowledge on top of the base ReAct prompt.

All API/field names verified against data/api_docs/standard/todoist.json.
"""

from .base import BaseAppExecutor


class TodoistExecutor(BaseAppExecutor):
    app_name = "todoist"
    app_system_prompt = """\
=== SURFACE: todoist_specialist:prompt === BEGIN
╔═══════════════════════════════════════════════════════════════════════════╗
║ TODOIST — projects contain tasks; tasks can have sub-tasks, labels,        ║
║ sections, due dates and priorities. project_id 0 is always the Inbox.      ║
╚═══════════════════════════════════════════════════════════════════════════╝

⚠️ CALLING CONVENTION — call EVERY todoist API the same way:
     call_api('todoist', '<api_name>', token, **kwargs)
   login: token = login_to_app('todoist')

🔑 THE TWO FIELD-NAME TRAPS (these cause most wrong answers):
   1. A TASK's name field is **'title'**.  A PROJECT's name field is **'name'**.
      Never read task['name'] — it does not exist. Use task['title'].
   2. **priority is a STRING enum: 'high' | 'medium' | 'low'** (default 'medium').
      It is NOT an integer and NOT p1/p2/p3/p4. Filter/create with the string.

⚠️ show_tasks RETURNS A DICT, NOT A LIST:
     data = call_api('todoist', 'show_tasks', token, project_id=<pid>)
     # data = {'project_id', 'no_section_tasks':[...], 'sections':[{'section_id','tasks':[...]}]}
     all_tasks = data['no_section_tasks'] + [t for s in data['sections'] for t in s['tasks']]
   To iterate ALL tasks in a project you MUST concat no_section_tasks + every section's tasks.

═══ EXACT API NAMES (wrong name = instant crash) ═══

  # Projects  (name field = 'name'; project_id=0 = Inbox)
  show_projects(access_token, query='', is_favorite=None, is_archived=None, sort_by=None) → paginated
  show_project(access_token, project_id)                → single project dict
  create_project(access_token, name, color='charcoal', description='', is_favorite=False) → {message, project_id}
  update_project / delete_project(access_token, project_id, ...)

  # Tasks  (title field = 'title'; priority = 'high'|'medium'|'low')
  show_tasks(access_token, project_id, section_id=None, assignee_email=None, priority=None,
             is_completed=None, due_today=False, overdue=False, label_id=None,
             min_due_date='1500-01-01', max_due_date='3000-01-01', sort_by='+order_index')
             → DICT (see above), NOT a flat list
  show_task(access_token, task_id)                      → {task_id, title, description, due_date,
             priority, is_completed, project_id, section_id, duration, duration_unit, order_index,
             assignee_id, assigner_id, created_at, labels:[{id,color,name}], creator:{}, num_sub_tasks}
  create_task(access_token, project_id, title, section_id=None, description='', due_date=None,
              duration=None, duration_unit=None, order_index=-1, priority='medium') → {message, task_id}
  update_task(access_token, task_id, title=None, description=None, due_date=None, duration=None,
              duration_unit=None, is_completed=None, order_index=None, priority=None) → {message}
  delete_task(access_token, task_id)
  assign_or_unassign_task(access_token, task_id, assignee_email=None)   # None → unassign

  # Sub-tasks / sections
  show_sub_tasks(access_token, task_id)  → list [{sub_task_id, title, is_completed, priority, due_date, ...}]
  create_sub_task(access_token, task_id, title, description='', due_date=None, priority='medium', order_index=-1)
  update_sub_task / delete_sub_task(access_token, sub_task_id, ...)
  show_sections(access_token, project_id) → list [{section_id, name, order_index, num_tasks, project_id, created_at}]
  create_section(access_token, project_id, name, order_index=-1)

  # Labels
  search_labels(access_token, query='', task_id=None, color=None, task_attached=True) → paginated
  create_label(access_token, name, color='charcoal')     show_label(label_id)
  add_label_to_task(access_token, task_id, label_id)      remove_label_from_task(access_token, task_id, label_id)

═══ MARKING A TASK DONE ═══
  There is NO "complete_task" API in todoist. Mark a task complete with:
      call_api('todoist', 'update_task', token, task_id=tid, is_completed=True)
  ⚠️ Do NOT confuse this with apis.supervisor.complete_task() (that ends the LARA task).

═══ DATES / TIME-RELATIVE ═══
  The sandbox clock ≠ today. For "due today"/"overdue" prefer show_tasks(due_today=True) /
  show_tasks(overdue=True) (they use the sandbox clock internally). For explicit windows, get the
  date from the phone app (get_current_date_and_time), then pass due_date / min_due_date /
  max_due_date as 'YYYY-MM-DD'. Never compute dates with datetime.now().

═══ PAGINATION ═══
  Paginated (5/page) — use fetch_all_pages:  show_projects, search_labels, search_users, show_notifications
  NOT paginated — use call_api:  show_tasks (returns the nested dict), show_task, show_project,
                                 show_sections, show_sub_tasks

═══ COMMON TASK PATTERNS ═══

  "How many tasks are in my Groceries project?":
    token    = login_to_app('todoist')
    projects = fetch_all_pages('todoist', 'show_projects', token)
    pid      = get_field(projects, 'name', 'Groceries', 'project_id')
    data     = call_api('todoist', 'show_tasks', token, project_id=pid)
    tasks    = data['no_section_tasks'] + [t for s in data['sections'] for t in s['tasks']]
    apis.supervisor.complete_task(answer=str(len(tasks)))

  "Add a task 'Buy milk' to my Inbox":
    token = login_to_app('todoist')
    call_api('todoist', 'create_task', token, project_id=0, title='Buy milk')
    apis.supervisor.complete_task(answer=None)

  "Mark the task 'Buy milk' as complete":
    token = login_to_app('todoist')
    data  = call_api('todoist', 'show_tasks', token, project_id=0)
    tasks = data['no_section_tasks'] + [t for s in data['sections'] for t in s['tasks']]
    tid   = get_field(tasks, 'title', 'Buy milk', 'task_id')
    call_api('todoist', 'update_task', token, task_id=tid, is_completed=True)
    apis.supervisor.complete_task(answer=None)

═══ CRITICAL RULES ═══
  • create / update / delete / assign / add_label / create_section / create_sub_task = ACTION tasks
    → apis.supervisor.complete_task(answer=None). NEVER pass a task_id or 'done'.
  • "How many tasks / which task / what is the ..." = VALUE tasks → pass the computed value.
  • Task name = task['title']; Project name = project['name']. Never mix them up.
  • priority is the string 'high' / 'medium' / 'low' — never an integer.
  • show_tasks returns a dict — always flatten no_section_tasks + sections[].tasks before iterating.
  • project_id=0 is the Inbox everywhere (show_tasks, create_task, show_project).
=== SURFACE: todoist_specialist:prompt === END
"""
