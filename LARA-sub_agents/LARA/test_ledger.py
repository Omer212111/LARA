"""Verify the SHIPPED BOOTSTRAP_CODE (executor_helpers.py) against a live sandbox.

Mimics base.py:467 exactly — BOOTSTRAP_CODE + "\n" + code on every block.
"""
import sys
sys.path.insert(0, "/home/omer2/LARA_project/wt-partner/LARA-sub_agents/LARA")

from executor_helpers import BOOTSTRAP_CODE
from appworld import AppWorld

FAILS = []


def main():
    w = AppWorld(task_id="82e2fac_1", experiment_name="ledger_shipped")

    def ex(code):
        return w.execute(BOOTSTRAP_CODE + "\n" + code)

    def _norm(t):
        return t.replace("'", "").replace('"', "").replace(" ", "")

    def check(label, code, expect):
        out = ex(code)
        ok = _norm(expect) in _norm(out)
        print(f"[{'PASS' if ok else 'FAIL'}] {label}")
        if not ok:
            FAILS.append(label)
            print(f"       expected {expect!r} in:\n       {out.rstrip()[:300]}")
        return out

    # --- persistence across the re-injected bootstrap -----------------------
    ex("remember_entity('Andrew', venmo_id=118, amount=42.5)")
    check("entity survives next block", "print(recall_entity('Andrew'))", "'venmo_id': 118")
    check("merge does not overwrite",
          "remember_entity('ANDREW  ', splitwise_email='a@x.com')\nprint(recall_entity('andrew'))",
          "'amount': 42.5")
    check("None fields ignored",
          "remember_entity('Andrew', venmo_id=None)\nprint(recall_entity('Andrew')['venmo_id'])",
          "118")
    check("artifact round-trip",
          "remember('rows', [{'n':'A'},{'n':'M'}])\nprint(len(recall('rows')))", "2")
    check("recall default", "print(recall('nope', 'DEFAULT'))", "DEFAULT")
    check("recall_entity default", "print(recall_entity('ghost', 'NONE_FOUND'))", "NONE_FOUND")

    # --- hostile / accidental model behaviour -------------------------------
    ex("LARA_LEDGER = {'entities':{},'tokens':{},'artifacts':{}}")
    check("survives model rebinding LARA_LEDGER",
          "print(recall_entity('Andrew'))", "'venmo_id': 118")
    ex("del LARA_LEDGER")
    check("survives model deleting the alias", "print(recall_entity('Andrew'))", "'venmo_id': 118")
    ex("raise ValueError('boom')")
    check("survives a raised exception", "print(recall_entity('Andrew'))", "'venmo_id': 118")
    ex("def (")  # syntax error
    check("survives a syntax error", "print(recall_entity('Andrew'))", "'venmo_id': 118")
    ex("remember_entity('Zoe', x=1)\nraise RuntimeError('half')")
    check("partial write before crash is kept", "print(recall_entity('Zoe'))", "'x': 1")

    # --- token caching -------------------------------------------------------
    check("login works + caches", "t=login_to_app('venmo')\nprint('cached:', LARA_LEDGER['tokens'].get('venmo')==t)", "cached: True")
    check("second login is a cache hit",
          "print('same:', login_to_app('venmo')==login_to_app('venmo'))", "same: True")
    check("second app caches independently",
          "login_to_app('phone')\nprint(sorted(LARA_LEDGER['tokens']))", "'phone', 'venmo'")

    # --- the actual join pattern from the prompt -----------------------------
    ex("""rows=[{'name':'Andrew','amount':42.5},{'name':'Maria','amount':17.0}]
remember('csv_rows', rows)
for r in rows: remember_entity(r['name'], amount=r['amount'])""")
    ex("remember_entity('Andrew', venmo_id=118)")   # only Andrew has venmo
    out = check("join: routes each person correctly", """
sent, split = [], []
for e in all_entities():
    if e.get('amount') is None: continue
    (sent if e.get('venmo_id') else split).append(e['name'])
print('venmo:', sorted(sent), 'splitwise:', sorted(split))""", "venmo: ['Andrew'] splitwise: ['Maria']")

    check("ledger_summary renders", "print(ledger_summary())", "LEDGER:")

    w.close()
    print("\n" + ("ALL PASS" if not FAILS else f"{len(FAILS)} FAILURES: {FAILS}"))
    return 1 if FAILS else 0




# Cross-task isolation: a fresh AppWorld context must start with an empty ledger,
# or a stale venmo_id from a previous task would silently corrupt the next one.
def test_isolation():
    with AppWorld(task_id="82e2fac_1", experiment_name="iso_a") as w:
        w.execute(BOOTSTRAP_CODE + "\nremember_entity('Andrew', venmo_id=999)")
    with AppWorld(task_id="82e2fac_2", experiment_name="iso_b") as w:
        out = w.execute(BOOTSTRAP_CODE + "\nprint(recall_entity('Andrew'))")
    assert "999" not in out, "LEDGER LEAKED ACROSS TASKS"
    print("[PASS] no leak across tasks")


if __name__ == "__main__":
    rc = main()
    test_isolation()
    sys.exit(rc)
