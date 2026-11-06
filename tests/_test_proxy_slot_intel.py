"""A proxy slot describes its exit: the IP, the country, and whether that
address is a residential line or a machine room.

The gateway learns an exit's IP by fetching api.ipify.org through the proxy
itself, so the country and the address kind have to come from a public lookup -
nothing in the connection says where it lands. These cases pin the parsing of
that lookup, the naming rule the panel defaults to, the store round trip that
keeps the probed fields, and the routes that hand them to the panel.

No network access: the lookup and the proxy probe are both stubbed.
"""

import json
import os
import sys
import tempfile
import time
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import wb_ipintel as I
import wb_proxy as proxy
import wb_settings as S

PASS = FAIL = 0


def check(label, cond, extra=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print("  [PASS] " + label)
    else:
        FAIL += 1
        print("  [FAIL] " + label + ("  " + str(extra) if extra else ""))


print("[1] a lookup reply becomes the fields a slot stores")

residential = I.classify({
    "status": "success", "country": "美国", "countryCode": "us",
    "isp": "Comcast Cable", "org": "Comcast", "as": "AS7922 Comcast Cable",
    "hosting": False, "proxy": False, "mobile": False,
})
check("a hosting=no address reads as 住宅",
      residential["ip_type"] == I.RESIDENTIAL, residential)
check("its label is 住宅", I.type_label(residential["ip_type"]) == "住宅", residential)
check("the country name is kept as the service wrote it",
      residential["country"] == "美国", residential)
check("the country code is upper-cased", residential["country_code"] == "US", residential)
check("the announcing network is kept for the tooltip",
      residential["asn"].startswith("AS7922"), residential)
check("the isp is kept", residential["isp"] == "Comcast Cable", residential)

datacenter = I.classify({
    "status": "success", "country": "美国", "countryCode": "US",
    "isp": "Google LLC", "as": "AS15169 Google LLC", "hosting": True,
})
check("a hosting=yes address reads as 机房",
      datacenter["ip_type"] == I.DATACENTER, datacenter)
check("its label is 机房", I.type_label(datacenter["ip_type"]) == "机房", datacenter)

partial = I.classify({"status": "success", "country": "日本", "countryCode": "JP"})
check("a reply with no hosting flag still gives the country",
      partial["country"] == "日本", partial)
check("but claims no kind", partial["ip_type"] == "", partial)
check("and an unknown kind has no label", I.type_label(partial["ip_type"]) == "")

print()
print("[2] a lookup that fails is unknown, never a guess")

for label, payload in (
    ("a failed status", {"status": "fail", "message": "reserved range"}),
    ("an empty body", {}),
    ("a body that is not an object", "nope"),
    ("no body at all", None),
):
    got = I.classify(payload)
    check("%s is unknown" % label, got == I.empty(), got)
check("every field of the unknown answer is empty",
      all(value == "" for value in I.empty().values()), I.empty())


class FakeResponse(object):
    def __init__(self, body):
        self._body = body

    def read(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


seen = {}


def answering(request, timeout):
    seen["url"] = request.full_url
    seen["timeout"] = timeout
    return FakeResponse(json.dumps({
        "status": "success", "country": "美国", "countryCode": "US",
        "isp": "Comcast", "as": "AS7922", "hosting": False,
    }).encode("utf-8"))


with mock.patch.object(I, "_open", answering):
    found = I.lookup("1.2.3.4")
check("the lookup asks about the exit ip", "1.2.3.4" in seen.get("url", ""), seen)
check("and asks for the country name the panel shows",
      "lang=zh-CN" in seen.get("url", ""), seen)
check("the parsed country comes back", found["country"] == "美国", found)
check("the parsed kind comes back", found["ip_type"] == I.RESIDENTIAL, found)


def refusing(request, timeout):
    raise OSError("lookup blocked")


with mock.patch.object(I, "_open", refusing):
    blocked = I.lookup("1.2.3.4")
check("a blocked lookup is unknown rather than an exception",
      blocked == I.empty(), blocked)

attempted = []
with mock.patch.object(I, "_open", lambda request, timeout: attempted.append(request)):
    nothing = I.lookup("")
check("an empty ip is never sent anywhere",
      nothing == I.empty() and not attempted, (nothing, attempted))

print()
print("[3] the default name is the exit's country and kind")

check("a machine room is named by country and kind",
      I.slot_name("美国", I.DATACENTER) == "美国 机房", I.slot_name("美国", I.DATACENTER))
check("a residential line says 住宅",
      I.slot_name("美国", I.RESIDENTIAL) == "美国 住宅", I.slot_name("美国", I.RESIDENTIAL))
check("an unknown kind leaves just the country",
      I.slot_name("美国", "") == "美国", I.slot_name("美国", ""))
check("no country means no default name",
      I.slot_name("", I.RESIDENTIAL) == "", I.slot_name("", I.RESIDENTIAL))

print()
print("[4] the slot store keeps the exit fields")

d = tempfile.mkdtemp(prefix="wb-slots-")
S.set_proxy_slots(d, [{
    "id": "slot-1", "name": "美国 住宅", "url": "http://127.0.0.1:17901",
    "ip": "1.2.3.4", "country": "美国", "country_code": "us",
    "ip_type": "residential", "isp": "Comcast", "asn": "AS7922 Comcast",
    "probed_at": 1800000000,
}])
entry = S.proxy_slots(d)[0]
check("the exit ip survives", entry["ip"] == "1.2.3.4", entry)
check("the country survives", entry["country"] == "美国", entry)
check("the country code is normalised on the way in",
      entry["country_code"] == "US", entry)
check("the kind survives", entry["ip_type"] == "residential", entry)
check("the announcing network survives", entry["asn"].startswith("AS7922"), entry)
check("the probe time survives", entry["probed_at"] == 1800000000, entry)

S.save(d, {"proxy_slots": [{"id": "slot-9", "url": "http://127.0.0.1:17909"}]})
legacy = S.proxy_slots(d)[0]
check("a slot saved before this feature loads with no exit info",
      legacy["ip"] == "" and legacy["country"] == "" and legacy["ip_type"] == "",
      legacy)
check("and its name stays empty rather than becoming its id",
      legacy["name"] == "", legacy)

print()
print("[5] a slot is labelled by its name, else its exit, else its id")

check("a named slot uses the operator's name",
      proxy.slot_label({"name": "香港落地", "country": "美国",
                        "ip_type": "residential", "id": "slot-1"}) == "香港落地")
check("an unnamed slot uses its exit",
      proxy.slot_label({"name": "", "country": "美国",
                        "ip_type": "datacenter", "id": "slot-1"}) == "美国 机房")
check("a slot with neither falls back to its id",
      proxy.slot_label({"name": "", "country": "", "ip_type": "",
                        "id": "slot-7"}) == "slot-7")


class FakeRequest(object):
    """Just enough of the handler for the proxy-slot routes."""

    _handle_proxy_slots = proxy.Handler._handle_proxy_slots

    def __init__(self):
        self.answering = []

    def _json(self, status, payload):
        self.answering.append(("json", status, payload))
        return status, payload

    def _error(self, status, message, kind=""):
        self.answering.append(("error", status, message))
        return status, message


PROBE = {
    "ok": True, "exit_ip": "1.2.3.4", "latency_ms": 42, "error": "",
    "intel_ok": True,
    "country": "美国", "country_code": "US", "ip_type": "residential",
    "isp": "Comcast", "asn": "AS7922 Comcast",
}

print()
print("[6] the routes hand the exit info over and remember it")

d2 = tempfile.mkdtemp(prefix="wb-slots-")
S.set_proxy_slots(d2, [{"id": "slot-1", "name": "", "url": "http://127.0.0.1:17901"}])

with mock.patch.multiple(proxy, ACCOUNTS_DIR=d2, POOL=None):
    with mock.patch.object(proxy, "probe_proxy_intel",
                           lambda url, timeout=12: dict(PROBE)):
        status, reply = FakeRequest()._handle_proxy_slots(
            "/proxy/slots/test", {"id": "slot-1"})

    stored = S.proxy_slots(d2)[0]
    check("the test reports the exit ip", reply["exit_ip"] == "1.2.3.4", reply)
    check("and the country and kind",
          reply["country"] == "美国" and reply["ip_type"] == "residential", reply)
    check("the slot remembers the exit ip", stored["ip"] == "1.2.3.4", stored)
    check("and its country and kind",
          stored["country"] == "美国" and stored["ip_type"] == "residential", stored)
    check("and the announcing network", stored["asn"].startswith("AS7922"), stored)
    # An empty name is the store's marker for "label this slot by its exit":
    # slot_label() derives it from the country and kind every time, so the label
    # follows the exit instead of freezing to the one the probe happened to see.
    check("an unnamed slot keeps its blank name", stored["name"] == "", stored)
    check("while its label comes from the exit",
          proxy.slot_label(stored) == "美国 住宅", proxy.slot_label(stored))
    check("the reply carries the stored slot back",
          (reply["slot"] or {}).get("name") == "" and reply["name"] == "", reply)

    failing = dict(PROBE, ok=False, exit_ip="", error="connection refused")
    with mock.patch.object(proxy, "probe_proxy_intel",
                           lambda url, timeout=12: dict(failing)):
        status, reply = FakeRequest()._handle_proxy_slots(
            "/proxy/slots/test", {"id": "slot-1"})

    after = S.proxy_slots(d2)[0]
    check("a failed probe reports the reason",
          reply["ok"] is False and reply["error"] == "connection refused", reply)
    check("and learns nothing, so it changes nothing",
          after["ip"] == "1.2.3.4" and after["country"] == "美国", after)

    # The IP probe answered but the geo lookup did not: the two steps are
    # separate calls, and the exit we already knew must survive the second one.
    no_geo = dict(PROBE, exit_ip="5.6.7.8", intel_ok=False, country="",
                  country_code="", ip_type="", isp="", asn="")
    with mock.patch.object(proxy, "probe_proxy_intel",
                           lambda url, timeout=12: dict(no_geo)):
        status, reply = FakeRequest()._handle_proxy_slots(
            "/proxy/slots/test", {"id": "slot-1"})

    after = S.proxy_slots(d2)[0]
    check("a lookup that answered nothing still updates the ip",
          after["ip"] == "5.6.7.8", after)
    check("but the exit info already stored is kept",
          after["country"] == "美国" and after["country_code"] == "US"
          and after["ip_type"] == "residential"
          and after["asn"].startswith("AS7922"), after)
    check("and the reply says the lookup came back empty",
          reply.get("intel_ok") is False, reply)

    # The exit moved: with the name still blank the label follows the new exit.
    moved = dict(PROBE, exit_ip="9.9.9.9", country="日本", country_code="JP",
                 ip_type="datacenter", isp="IIJ", asn="AS2497 IIJ")
    with mock.patch.object(proxy, "probe_proxy_intel",
                           lambda url, timeout=12: dict(moved)):
        FakeRequest()._handle_proxy_slots("/proxy/slots/test", {"id": "slot-1"})

    moved_entry = S.proxy_slots(d2)[0]
    check("a slot that moved is labelled by the new exit",
          proxy.slot_label(moved_entry) == "日本 机房",
          proxy.slot_label(moved_entry))
    check("and its name is still blank", moved_entry["name"] == "", moved_entry)

    status, saved = FakeRequest()._handle_proxy_slots("/proxy/slots/save", {
        "slots": [{
            "id": "slot-1", "name": "我的美国出口", "url": "http://127.0.0.1:17901",
            "enabled": True, "ip": "1.2.3.4", "country": "美国",
            "country_code": "US", "ip_type": "residential", "isp": "Comcast",
            "asn": "AS7922 Comcast", "probed_at": 1800000000,
        }],
    })
    kept = S.proxy_slots(d2)[0]
    check("a save keeps the exit info the panel echoed back",
          kept["ip"] == "1.2.3.4" and kept["ip_type"] == "residential", kept)
    check("and the probe time", kept["probed_at"] == 1800000000, kept)
    check("a name the operator typed wins over the exit",
          kept["name"] == "我的美国出口", kept)
    check("the view labels the slot by that name",
          saved["slots"][0]["label"] == "我的美国出口", saved["slots"][0])

    os.environ["WB_PROXY_DISCOVER_PORTS"] = "17901"
    try:
        with mock.patch.object(proxy, "probe_proxy_intel",
                               lambda url, timeout=12: dict(PROBE)):
            status, found = FakeRequest()._handle_proxy_slots("/proxy/discover", {})
    finally:
        os.environ.pop("WB_PROXY_DISCOVER_PORTS", None)

    candidates = found["candidates"]
    check("discovery reports one candidate per configured port",
          len(candidates) == 1, candidates)
    check("with the exit ip", candidates[0]["exit_ip"] == "1.2.3.4", candidates[0])
    check("and the country and kind",
          candidates[0]["country"] == "美国"
          and candidates[0]["ip_type"] == "residential", candidates[0])
    check("and reachable mirrors the probe",
          candidates[0]["reachable"] is True, candidates[0])

    # 端口列表可以写多段：共享出口与每节点专属口要一起发现。
    saved = os.environ.get("WB_PROXY_DISCOVER_PORTS")
    try:
        os.environ["WB_PROXY_DISCOVER_PORTS"] = "7890-7892,17901-17903,7892"
        parsed = list(proxy._proxy_port_range())
        check("a comma-separated list of ranges is accepted",
              parsed == [7890, 7891, 7892, 17901, 17902, 17903], parsed)
        os.environ["WB_PROXY_DISCOVER_PORTS"] = "7890,7891"
        check("single ports can be listed too",
              list(proxy._proxy_port_range()) == [7890, 7891])
        os.environ["WB_PROXY_DISCOVER_PORTS"] = "garbage"
        check("an unusable value falls back to the documented default",
              list(proxy._proxy_port_range()) == list(range(17901, 17911)))
        os.environ["WB_PROXY_DISCOVER_PORTS"] = "17901-17904"
        seen = []
        def fake_probe(url, timeout=12):
            seen.append(url)
            return dict(PROBE)
        with mock.patch.object(proxy, "probe_proxy_intel", fake_probe), \
             mock.patch.object(proxy, "proxy_node_map",
                               return_value={17902: "直连-日本"}):
            found_many = proxy.discover_proxy_slots()
        check("every listed port is probed", len(found_many) == 4, found_many)
        check("and the order follows the configured ports",
              [c["url"].rsplit(":", 1)[1] for c in found_many]
              == ["17901", "17902", "17903", "17904"], found_many)
        by_port = {c["url"].rsplit(":", 1)[1]: c for c in found_many}
        check("a discovered port carries the node name the pool reports",
              by_port["17902"]["node"] == "直连-日本", by_port["17902"])
        check("a port with no known node carries an empty name",
              by_port["17901"]["node"] == "", by_port["17901"])
    finally:
        if saved is None:
            os.environ.pop("WB_PROXY_DISCOVER_PORTS", None)
        else:
            os.environ["WB_PROXY_DISCOVER_PORTS"] = saved

print()
print("[7] an update merges under the store lock and never overwrites a name")

d3 = tempfile.mkdtemp(prefix="wb-slots-")
S.set_proxy_slots(d3, [
    {"id": "slot-1", "name": "", "url": "http://127.0.0.1:1"},
    {"id": "slot-2", "name": "已命名", "url": "http://127.0.0.1:2"},
])
merged = S.update_proxy_slot(d3, "slot-1", {"ip": "1.2.3.4", "country": "美国"},
                             defaults={"name": "美国 住宅"})
check("the merge returns the updated slot", merged["ip"] == "1.2.3.4", merged)
check("and fills a default into an empty field",
      merged["name"] == "美国 住宅", merged)
check("the other slot is left alone", S.proxy_slots(d3)[1]["name"] == "已命名",
      S.proxy_slots(d3))

kept = S.update_proxy_slot(d3, "slot-2", {"ip": "5.6.7.8"},
                           defaults={"name": "不该覆盖"})
check("a default never overwrites a value that is already there",
      kept["name"] == "已命名", kept)
check("while the explicit field still lands", kept["ip"] == "5.6.7.8", kept)
check("an unknown slot updates nothing",
      S.update_proxy_slot(d3, "slot-404", {"ip": "9.9.9.9"}) is None)
check("and the stored list is untouched", len(S.proxy_slots(d3)) == 2,
      S.proxy_slots(d3))

print()
print("[8] the slot shows the node behind its port, not just its alias")

# The hub only knows "the proxy at 127.0.0.1:7890". Which node sits behind it
# is chosen in mihomo-pool and moves on rotation, so the view asks the pool and
# keys the answer by local port. Everything here is stubbed: no network.

saved_url = proxy.PROXY_NODE_MAP_URL
try:
    proxy.PROXY_NODE_MAP_URL = ""
    proxy._node_map_cache["at"] = 0.0
    proxy._node_map_cache["ports"] = {}
    check("no pool configured means no node name",
          proxy.proxy_node_map() == {}, proxy.proxy_node_map())
    check("and the slot keeps an empty node field",
          proxy.slot_node_name({"url": "http://127.0.0.1:7890"}) == "")

    d4 = tempfile.mkdtemp()
    S.save(d4, {"proxy_slots": [
        {"id": "slot-1", "name": "mihomo-fixed", "url": "http://127.0.0.1:7890"},
        {"id": "slot-2", "name": "", "url": "http://127.0.0.1:7891",
         "country": "美国", "ip_type": "residential"},
    ]})

    proxy.PROXY_NODE_MAP_URL = "http://pool.test"
    payload = {"ok": True, "exits": [
        {"port": 7890, "group": "HUB-FIXED", "node": "直连-新加坡01"},
        {"port": 7891, "group": "HUB-ROTATE", "node": "pro-香港-01"},
        {"port": 7892, "group": "HUB-ASSIGN", "node": ""},
    ]}

    class FakeResp:
        def __init__(self, data):
            self._data = data
        def read(self):
            return json.dumps(self._data).encode("utf-8")
        def __enter__(self):
            return self
        def __exit__(self, *a):
            return False

    with mock.patch.object(proxy.urllib.request, "urlopen",
                           return_value=FakeResp(payload)):
        mapping = proxy.proxy_node_map(force=True)
    check("the mapping is keyed by local port",
          mapping.get(7890) == "直连-新加坡01" and mapping.get(7891) == "pro-香港-01",
          mapping)
    check("an exit without a node is not stored",
          7892 not in mapping, mapping)

    view = {s["id"]: s for s in proxy.proxy_slots_view.__wrapped__(d4)}         if hasattr(proxy.proxy_slots_view, "__wrapped__") else None

    # proxy_slots_view reads the real ACCOUNTS_DIR, so exercise the two pure
    # helpers it uses instead of swapping global state.
    check("a named slot still reports the node behind its port",
          proxy.slot_node_name({"url": "http://127.0.0.1:7890"}, mapping) == "直连-新加坡01")
    check("an unnamed slot reports its node too",
          proxy.slot_node_name({"url": "http://127.0.0.1:7891"}, mapping) == "pro-香港-01")
    check("a slot on an unmapped port reports nothing",
          proxy.slot_node_name({"url": "http://127.0.0.1:9999"}, mapping) == "")
    check("the alias is still what slot_label returns",
          proxy.slot_label({"name": "mihomo-fixed", "id": "slot-1"}) == "mihomo-fixed")

    # A failed fetch must not keep serving the previous mapping: a stale node
    # name is worse than none, because it claims traffic goes somewhere it does
    # not.
    proxy._node_map_cache["at"] = 0.0
    proxy._node_map_cache["ports"] = {7890: "旧节点"}
    with mock.patch.object(proxy.urllib.request, "urlopen",
                           side_effect=RuntimeError("boom")):
        failed = proxy.proxy_node_map(force=True)
    check("a failed fetch yields no mapping rather than a stale one",
          failed == {}, failed)
    check("and the failure is cached so the next render does not re-probe",
          proxy._node_map_cache["at"] > 0, proxy._node_map_cache)
    check("so an immediate retry returns the cached empty map without calling out",
          proxy.proxy_node_map() == {}, proxy.proxy_node_map())
finally:
    proxy.PROXY_NODE_MAP_URL = saved_url
    proxy._node_map_cache["at"] = 0.0
    proxy._node_map_cache["ports"] = {}

print()
print("[9] the slot editor can pick a port instead of typing one")

# 编辑器把 mihomo 的端口列表画成下拉，选中后写回 http://127.0.0.1:<port>。
# 这里只钉纯函数；DOM 行为由 JS 套件覆盖。

saved_url = proxy.PROXY_NODE_MAP_URL
try:
    proxy.PROXY_NODE_MAP_URL = ""
    proxy._node_map_cache["at"] = 0.0
    proxy._node_map_cache["ports"] = {}
    check("no pool means the picker has nothing to offer",
          proxy.proxy_port_options() == [], proxy.proxy_port_options())

    # 端口选项走的是同一份缓存；给一个非空 URL 才会读缓存而不是直接返回空。
    proxy.PROXY_NODE_MAP_URL = "http://pool.test"
    proxy._node_map_cache["at"] = time.time()
    proxy._node_map_cache["ports"] = {
        7892: "pro-泰国01-2x", 7890: "直连-新加坡01", 17901: "直连-香港03"}
    opts = proxy.proxy_port_options()
    check("every mapped port becomes an option",
          [o["port"] for o in opts] == [7890, 7892, 17901], opts)
    check("and each option carries its node name",
          opts[0]["node"] == "直连-新加坡01" and opts[2]["node"] == "直连-香港03", opts)
    check("options are ordered by port number, shared exits first",
          [o["port"] for o in opts] == sorted(o["port"] for o in opts), opts)
finally:
    proxy.PROXY_NODE_MAP_URL = saved_url
    proxy._node_map_cache["at"] = 0.0
    proxy._node_map_cache["ports"] = {}

print()
print("PASS=%d FAIL=%d" % (PASS, FAIL))
sys.exit(1 if FAIL else 0)
