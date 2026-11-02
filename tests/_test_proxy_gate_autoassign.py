"""Egress latency gate and automatic slot assignment (no network).

Two things are pinned here:

1. The gate. A slot is only usable when the TCP+TLS handshake through the
   proxy is within WB_PROXY_RTT_LIMIT_MS (300ms by default). The whole-request
   number (fetching api.ipify.org through the proxy) is only the fallback for
   proxies whose handshake cannot be timed - it is a cross-border HTTPS call
   and is routinely above 300ms even on a good exit.
2. The plan. `N accounts per exit` has to be deterministic, wrap instead of
   piling accounts onto the last slot, and never move an account when it is
   told to leave existing bindings alone.
"""

import os
import sys
import tempfile
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import wb_accounts
import wb_proxy as proxy
import wb_settings

PASS = FAIL = 0


def check(label, cond, extra=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print("  [PASS] " + label)
    else:
        FAIL += 1
        print("  [FAIL] " + label + ("  " + str(extra) if extra else ""))


print("[1] proxy_gate: handshake is the primary limit, whole request the fallback")

check("299ms handshake passes on the RTT rule",
      proxy.proxy_gate(299, 9000) == (True, "rtt"), proxy.proxy_gate(299, 9000))
check("300ms handshake passes (limit is inclusive)",
      proxy.proxy_gate(300, 9000) == (True, "rtt"))
check("301ms handshake fails even when the whole request looks ok",
      proxy.proxy_gate(301, 400) == (False, "rtt"))
check("untimed handshake falls back to the whole-request limit",
      proxy.proxy_gate(None, 799) == (True, "latency"))
check("799ms whole request passes the fallback",
      proxy.proxy_gate(None, 799) == (True, "latency"))
check("801ms whole request fails the fallback",
      proxy.proxy_gate(None, 801) == (False, "latency"))
check("no measurement at all cannot pass",
      proxy.proxy_gate(None, None) == (False, "unreachable"))

print()
print("[2] _proxy_endpoint: only plain http proxies can be timed by hand")

check("bare host:port is accepted",
      proxy._proxy_endpoint("10.0.0.1:17901") == ("10.0.0.1", 17901))
check("http:// is accepted",
      proxy._proxy_endpoint("http://10.0.0.1:17901") == ("10.0.0.1", 17901))
check("socks5:// is not (urllib-only path)",
      proxy._proxy_endpoint("socks5://10.0.0.1:1080") is None)
check("empty is not an endpoint", proxy._proxy_endpoint("") is None)
check("a malformed port is not an endpoint",
      proxy._proxy_endpoint("http://10.0.0.1:notaport") is None)

print()
print("[3] probe_proxy_route: an unsupported URL has no timing")

hs, total, ip, err = proxy.probe_proxy_route("socks5://10.0.0.1:1080")
check("socks returns no handshake", hs is None)
check("socks returns no whole-request time", total is None)
check("socks returns no exit", ip == "")
check("socks explains itself", "unsupported" in err, err)

print()
print("[4] probe_proxy_intel: gate reflects the handshake, not the full request")

with mock.patch.object(proxy, "probe_proxy_route", return_value=(80, 420, "1.2.3.4", "")), \
        mock.patch.object(proxy.wb_ipintel, "lookup", return_value=proxy.wb_ipintel.empty()):
    fast = proxy.probe_proxy_intel("http://10.0.0.1:17901")
check("fast exit is reachable", fast["ok"] is True)
check("fast exit is healthy", fast["healthy"] is True, fast)
check("fast exit passes the gate", fast["gate_ok"] is True)
check("handshake is reported", fast["handshake_ms"] == 80)
check("whole request is reported separately", fast["latency_ms"] == 420)
check("limits are echoed for the panel", fast["rtt_limit_ms"] == proxy.PROXY_RTT_LIMIT_MS)

with mock.patch.object(proxy, "probe_proxy_route", return_value=(850, 4200, "1.2.3.4", "")), \
        mock.patch.object(proxy.wb_ipintel, "lookup", return_value=proxy.wb_ipintel.empty()):
    slow = proxy.probe_proxy_intel("http://10.0.0.2:17902")
check("slow exit is still reachable", slow["ok"] is True)
check("slow exit is not healthy", slow["healthy"] is False)
check("slow exit fails the gate", slow["gate_ok"] is False)
check("a slow exit is not silently dropped by the probe itself",
      slow["exit_ip"] == "1.2.3.4")

with mock.patch.object(proxy, "probe_proxy_route", return_value=(None, 12000, "", "timed out")), \
        mock.patch.object(proxy.wb_ipintel, "lookup", return_value=proxy.wb_ipintel.empty()):
    dead = proxy.probe_proxy_intel("http://10.0.0.3:17903")
check("unreachable is not ok", dead["ok"] is False)
check("unreachable is not healthy", dead["healthy"] is False)
check("unreachable says why", dead["gate"] == "unreachable" and dead["error"])

print()
print("[5] plan_slot_assignment: N per exit, deterministic, wraps instead of piling up")

uids24 = ["u%02d" % i for i in range(24)]
slots8 = ["slot-%d" % i for i in range(1, 9)]
plan = proxy.plan_slot_assignment(uids24, slots8, 3)
counts = {}
for uid, slot in plan:
    counts[slot] = counts.get(slot, 0) + 1
for slot in slots8:
    check("%s gets exactly 3" % slot, counts.get(slot) == 3, counts.get(slot))
check("every account is planned once",
      [uid for uid, _ in plan] == uids24)
check("account order decides the slot, slots are filled in order",
      plan[0] == ("u00", "slot-1") and plan[3] == ("u03", "slot-2")
      and plan[23] == ("u23", "slot-8"))

plan = proxy.plan_slot_assignment(["a", "b", "c", "d"], ["s1", "s2"], 3)
check("a short pool leaves the tail slots empty", plan == [
    ("a", "s1"), ("b", "s1"), ("c", "s1"), ("d", "s2")], plan)

plan = proxy.plan_slot_assignment(["u%d" % i for i in range(10)], ["s1", "s2"], 3)
counts = {}
for _, slot in plan:
    counts[slot] = counts.get(slot, 0) + 1
check("an oversized pool wraps around instead of overloading the last slot",
      counts == {"s1": 6, "s2": 4}, counts)

check("per_slot=0 is treated as 1",
      proxy.plan_slot_assignment(["a", "b"], ["s1", "s2"], 0)
      == [("a", "s1"), ("b", "s2")])
check("a huge per_slot is clamped, not fatal",
      len(proxy.plan_slot_assignment(["a", "b"], ["s1"], 10 ** 6)) == 2)
check("no slots means no plan",
      proxy.plan_slot_assignment(["a"], [], 3) == [])
check("no accounts means no plan",
      proxy.plan_slot_assignment([], ["s1"], 3) == [])


def make_store():
    return tempfile.mkdtemp(prefix="slotauto_")


def account(uid, slot="", enabled=True):
    return wb_accounts.Account({
        "uid": uid, "nickname": uid, "domain": "www.workbuddy.ai",
        "realm": "intl", "accessToken": "a.b.c", "refreshToken": "r",
        "expiresAt": 4102444800, "enabled": enabled, "proxySlot": slot,
    })


def build(work, uids, slots, per=None):
    stored = wb_settings.set_proxy_slots(work, slots)
    pool = wb_accounts.AccountPool(work)
    for uid in uids:
        pool.add(account(uid))
    pool.apply_proxy_slots(stored)
    proxy.POOL = pool
    proxy.ACCOUNTS_DIR = work
    if per is not None:
        wb_settings.set_proxy_auto_assign_per_slot(work, per)
    return pool, stored


print()
print("[6] assign_proxy_slots: idle accounts get no exit, three per exit")

work = make_store()
slots = [{"id": "", "name": label, "url": url, "enabled": True}
         for label, url in (("A", "http://10.0.0.1:17901"),
                            ("B", "http://10.0.0.2:17902"),
                            ("C", "http://10.0.0.3:17903"))]
pool, stored = build(work, ["u%d" % i for i in range(7)] + ["off1"], slots)
# Both flags off = the account does nothing at all, so its exit goes back.
pool.set_enabled("off1", False, tasks_enabled=False)
pool.apply_proxy_slots(stored)

report = proxy.assign_proxy_slots(per_slot=3, probe=False)
check("assignment succeeds", report["ok"] is True, report)
check("only active accounts are bound", report["assigned"] == 7, report["assigned"])
check("idle account keeps no binding",
      pool.get("off1").proxy_slot == "", pool.get("off1").proxy_slot)
bound = {}
for acc in pool.accounts:
    if acc.enabled:
        bound[acc.proxy_slot] = bound.get(acc.proxy_slot, 0) + 1
check("three accounts per exit, tail slot gets the remainder",
      bound == {stored[0]["id"]: 3, stored[1]["id"]: 3, stored[2]["id"]: 1}, bound)
check("the runtime proxy URL follows the slot",
      pool.get("u0").proxy == "http://10.0.0.1:17901",
      pool.get("u0").proxy)

print()
print("[6b] task-only accounts (enabled=false, tasksEnabled=true) keep an exit")

work = make_store()
slots = [{"id": "", "name": label, "url": url, "enabled": True}
         for label, url in (("A", "http://10.0.0.1:17901"),
                            ("B", "http://10.0.0.2:17902"))]
pool, stored = build(work, ["u%d" % i for i in range(4)] + ["idle"], slots,
                     per=2)
# u0/u1 task-only, u2/u3 API-only, one fully idle account
for uid in ("u0", "u1"):
    pool.set_enabled(uid, False, tasks_enabled=True)
pool.set_enabled("idle", False, tasks_enabled=False)
pool.apply_proxy_slots(stored)

report = proxy.assign_proxy_slots(per_slot=2, probe=False)
check("assignment succeeds with task-only accounts", report["ok"] is True, report)
check("task-only accounts are bound", report["assigned"] == 4, report["assigned"])
check("task-only account keeps its exit", pool.get("u0").proxy_slot != "",
      pool.get("u0").proxy_slot)
check("task-only account uses the slot URL",
      pool.get("u0").proxy.startswith("http://10.0.0."), pool.get("u0").proxy)
check("fully idle account is not bound", pool.get("idle").proxy_slot == "",
      pool.get("idle").proxy_slot)
check("task-only account appears in the slot view counts",
      any(entry["bound"] >= 2 for entry in proxy.proxy_slots_view()),
      proxy.proxy_slots_view())

print()
print("[6c] turning tasks on/off rebalances the plan")

# Tasks off on a task-only account releases its exit; tasks on binds it again.
pool.set_enabled("u0", False, tasks_enabled=False)
report = proxy.maybe_auto_assign_slots("tasks off")
check("tasks-off releases the exit", report["released"] == 1
      and pool.get("u0").proxy_slot == "", report)
pool.set_tasks_enabled("u0", True)
report = proxy.maybe_auto_assign_slots("tasks on")
check("tasks-on binds the exit again",
      report["assigned"] == 4 and pool.get("u0").proxy_slot != "", report)

print()
print("[7] assign_proxy_slots: a probe keeps slow exits out of the rotation")

work = make_store()
pool, stored = build(work, ["u%d" % i for i in range(6)],
                     [{"id": "", "name": "fast", "url": "http://10.0.0.1:17901"},
                      {"id": "", "name": "slow", "url": "http://10.0.0.2:17902"}])

def fake_probe(url, timeout=12):
    if url.endswith("17902"):
        return {"ok": True, "healthy": False, "exit_ip": "2.2.2.2",
                "handshake_ms": 900, "latency_ms": 1200, "gate_ok": False,
                "gate": "rtt", "error": "", "intel_ok": True}
    return {"ok": True, "healthy": True, "exit_ip": "1.1.1.1",
            "handshake_ms": 40, "latency_ms": 380, "gate_ok": True,
            "gate": "rtt", "error": "", "intel_ok": True}

with mock.patch.object(proxy, "probe_proxy_intel", side_effect=fake_probe):
    report = proxy.assign_proxy_slots(per_slot=3, probe=True)
check("only the fast exit is used", report["slots_used"] == [stored[0]["id"]],
      report["slots_used"])
check("all accounts land on the fast exit",
      all(acc.proxy_slot == stored[0]["id"] for acc in pool.accounts),
      [acc.proxy_slot for acc in pool.accounts])
check("the probe explains the slow exit",
      any(p["id"] == stored[1]["id"] and p["gate_ok"] is False
          for p in report["probes"]), report["probes"])

with mock.patch.object(proxy, "probe_proxy_intel", side_effect=fake_probe):
    report = proxy.assign_proxy_slots(per_slot=3, probe=True)
check("a rerun is idempotent", report["assigned"] == 6)

print()
print("[8] assign_proxy_slots: nothing to do and nothing usable are reported")

work = make_store()
pool, _ = build(work, ["u0"], [])
report = proxy.assign_proxy_slots(per_slot=3, probe=False)
check("no slot is a failure, not a silent no-op", report["ok"] is False)
check("no slot says so", "no enabled" in report["error"], report["error"])

work = make_store()
pool, _ = build(work, ["u0"], [
    {"id": "", "name": "off", "url": "http://10.0.0.1:17901", "enabled": False}])
report = proxy.assign_proxy_slots(per_slot=3, probe=False)
check("a disabled slot is not a slot", report["ok"] is False)

work = make_store()
pool, _ = build(work, ["u0"], [
    {"id": "", "name": "dead", "url": "http://10.0.0.1:17901"}])
with mock.patch.object(proxy, "probe_proxy_intel", return_value={
        "ok": False, "healthy": False, "exit_ip": "", "handshake_ms": None,
        "latency_ms": 12000, "gate_ok": False, "gate": "unreachable",
        "error": "timed out", "intel_ok": False}):
    report = proxy.assign_proxy_slots(per_slot=3, probe=True)
check("no gate-passing exit is a failure",
      report["ok"] is False and "gate" in report["error"], report)
check("nobody is bound to a failing exit", pool.get("u0").proxy_slot == "")

print()
print("[9] assign_proxy_slots: only_unbound leaves existing bindings alone")

work = make_store()
pool, stored = build(work, ["u0", "u1", "u2", "u3"],
                     [{"id": "", "name": "A", "url": "http://10.0.0.1:17901"},
                      {"id": "", "name": "B", "url": "http://10.0.0.2:17902"}])
pool.set_proxy_slot("u0", stored[1]["id"])
report = proxy.assign_proxy_slots(per_slot=1, probe=False, only_unbound=True)
check("only the unbound accounts are planned", report["assigned"] == 3,
      report["assigned"])
check("the existing binding is untouched", pool.get("u0").proxy_slot == stored[1]["id"],
      pool.get("u0").proxy_slot)

print()
print("[10] maybe_auto_assign_slots: off by default, runs when configured")

work = make_store()
pool, stored = build(work, ["u%d" % i for i in range(6)],
                     [{"id": "", "name": "A", "url": "http://10.0.0.1:17901"},
                      {"id": "", "name": "B", "url": "http://10.0.0.2:17902"}])
check("off by default (0)", wb_settings.proxy_auto_assign_per_slot(work) == 0)
check("off => no work", proxy.maybe_auto_assign_slots("test") is None)
check("nothing was bound while off",
      all(acc.proxy_slot == "" for acc in pool.accounts))

wb_settings.set_proxy_auto_assign_per_slot(work, 3)
report = proxy.maybe_auto_assign_slots("test")
check("configured => assignment runs", report and report.get("ok") is True, report)
check("configured width is honoured", report["per_slot"] == 3, report)
bound = {}
for acc in pool.accounts:
    bound[acc.proxy_slot] = bound.get(acc.proxy_slot, 0) + 1
check("3 accounts per exit", bound == {stored[0]["id"]: 3, stored[1]["id"]: 3}, bound)

wb_settings.set_proxy_auto_assign_per_slot(work, 0)
check("turning it off is allowed", wb_settings.proxy_auto_assign_per_slot(work) == 0)

for bad in (True, "3", 51, -1):
    try:
        wb_settings.set_proxy_auto_assign_per_slot(work, bad)
        check("rejects %r" % (bad,), False, "accepted")
    except ValueError:
        check("rejects %r" % (bad,), True)

print()
print("[11] auto mode: disabling releases the exit, re-enabling plans again")

work = make_store()
pool, stored = build(work, ["u%d" % i for i in range(6)],
                     [{"id": "", "name": "A", "url": "http://10.0.0.1:17901"},
                      {"id": "", "name": "B", "url": "http://10.0.0.2:17902"}],
                     per=3)
report = proxy.maybe_auto_assign_slots("setup")
check("setup assigns everyone", report["ok"] and report["assigned"] == 6, report)

pool.set_enabled("u0", False)
report = proxy.maybe_auto_assign_slots("account disabled")
check("the disabled account's binding is released",
      report["released"] == 1 and pool.get("u0").proxy_slot == "", report)
check("the released account runs direct again",
      pool.get("u0").proxy == "", pool.get("u0").proxy)
bound = {}
for acc in pool.accounts:
    if acc.enabled:
        bound[acc.proxy_slot] = bound.get(acc.proxy_slot, 0) + 1
check("the remaining five spread 3+2 over both exits",
      bound == {stored[0]["id"]: 3, stored[1]["id"]: 2}, bound)

pool.set_enabled("u0", True)
report = proxy.maybe_auto_assign_slots("account enabled")
check("re-enabling hands out an exit again",
      report["assigned"] == 6 and pool.get("u0").proxy_slot != "", report)
bound = {}
for acc in pool.accounts:
    bound[acc.proxy_slot] = bound.get(acc.proxy_slot, 0) + 1
check("the pool is back to 3+3",
      bound == {stored[0]["id"]: 3, stored[1]["id"]: 3}, bound)

print()
print("[12] auto off: disabling does not touch bindings")

work = make_store()
pool, stored = build(work, ["u0", "u1"],
                     [{"id": "", "name": "A", "url": "http://10.0.0.1:17901"},
                      {"id": "", "name": "B", "url": "http://10.0.0.2:17902"}])
pool.set_proxy_slot("u0", stored[1]["id"])
pool.set_enabled("u0", False)
check("auto off => no work", proxy.maybe_auto_assign_slots("x") is None)
check("the manual binding survives a disable",
      pool.get("u0").proxy_slot == stored[1]["id"], pool.get("u0").proxy_slot)


def route_handler():
    class H(proxy.Handler):
        def __init__(self):
            self.captured = None

        def _json_panel(self, code, obj):
            self.captured = (code, obj)

        def _error(self, code, message, err_type="server_error"):
            self.captured = (code, {"error": message})
    return H()


print()
print("[13] the panel routes trigger the rebalance themselves")

work = make_store()
pool, stored = build(work, ["r0", "r1", "r2", "r3"],
                     [{"id": "", "name": "A", "url": "http://10.0.0.1:17901"},
                      {"id": "", "name": "B", "url": "http://10.0.0.2:17902"}],
                     per=2)
proxy.maybe_auto_assign_slots("setup")

handler = route_handler()
handler._route_accounts_set({"uid": "r0", "enabled": False})
check("disabling via /accounts/set releases at once",
      pool.get("r0").proxy_slot == "", pool.get("r0").proxy_slot)
handler._route_accounts_set({"uid": "r0", "enabled": True})
check("enabling via /accounts/set plans again",
      pool.get("r0").proxy_slot != "", pool.get("r0").proxy_slot)

handler._route_accounts_set_all({"enabled": False})
check("set-all disable releases every exit",
      all(acc.proxy_slot == "" for acc in pool.accounts),
      [acc.proxy_slot for acc in pool.accounts])
handler._route_accounts_set_all({"enabled": True})
check("set-all enable plans everyone again",
      all(acc.proxy_slot for acc in pool.accounts),
      [acc.proxy_slot for acc in pool.accounts])

handler._route_accounts_delete({"uid": "r0"})
check("deleting an account keeps the rest bound",
      all(pool.get(uid).proxy_slot for uid in ("r1", "r2", "r3")),
      [pool.get(uid).proxy_slot for uid in ("r1", "r2", "r3")])
check("the deleted account is gone", pool.get("r0") is None)

print()
print("%d passed, %d failed" % (PASS, FAIL))
sys.exit(1 if FAIL else 0)
