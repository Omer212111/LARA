"""
One-shot script to dump all Amazon API docs from AppWorld.
Run with: python probe_amazon.py
Delete after use.
"""
from appworld import AppWorld, load_task_ids
from tools import set_appworld_env, _execute_code_raw

task_ids = load_task_ids("train")

with AppWorld(task_id=task_ids[0], experiment_name="probe") as world:
    set_appworld_env(world)

    print("=" * 60)
    print("AMAZON API LIST")
    print("=" * 60)
    print(_execute_code_raw("print(apis.api_docs.show_api_descriptions(app_name='amazon'))"))

    print("\n" + "=" * 60)
    print("AMAZON API DETAILS")
    print("=" * 60)
    result = _execute_code_raw("""
for api_name in dir(apis.amazon):
    if api_name.startswith('_'):
        continue
    try:
        doc = apis.api_docs.show_api_doc(app_name='amazon', api_name=api_name)
        print('\\n--- ' + api_name + ' ---')
        print(doc)
    except Exception as e:
        pass
""")
    print(result)
