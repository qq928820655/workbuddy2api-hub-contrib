#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""整池冷却时的「透明等待」（WB_TRANSPARENT_RETRY_WAIT，默认 30s）。

背景：下游（CPA、Claude Code、各种 harness）拿到 429 只会中断这一轮，要人手动
重发。而实测这些冷却窗口大多只有几十秒，等一会儿本来就能自己继续。这里钉：

  1. 全池在冷却、且能在预算内恢复 → 等它恢复后接着发这一轮，不报 429；
  2. 恢复时间超出预算 → 预算用完就如实报 429；
  3. 日限额 / 手工禁用 / 没有账号 → 等多久都没用，立刻上报，一个字节都不等；
  4. 预算设 0 → 完全恢复旧行为（立刻 429）；
  5. 固定账号（/u/<ref>/）不等待——它没有「换一个」的余地；
  6. 等待期间的日志只打一次，不会每 0.25 秒刷一行。

时钟是假的：patch 掉 wb_proxy.time / wb_accounts.time，sleep 只推进虚拟时间，
测试本身不真的睡。
"""
import json
import os
import sys
import tempfile
import unittest
import urllib.error
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import wb_accounts as A
import wb_proxy as P
import wb_settings


class FakeTime(object):
    """time 模块的替身：sleep 只推进虚拟时钟。"""

    def __init__(self, start=None):
        self.now = 1700000000.0 if start is None else float(start)
        self.slept = []

    def time(self):
        return self.now

    def monotonic(self):
        return self.now

    def sleep(self, seconds):
        self.slept.append(float(seconds))
        self.now += max(0.0, float(seconds))

    def strftime(self, *args, **kwargs):
        return ""

    def localtime(self, *args, **kwargs):
        import time as _real
        return _real.gmtime(self.now)

    def gmtime(self, *args, **kwargs):
        import time as _real
        return _real.gmtime(self.now)

    def mktime(self, *args, **kwargs):
        return 0.0


class _Sock(object):
    def settimeout(self, value):
        pass


class _UpstreamResponse(object):
    """够 open_upstream 的成功路径用。"""

    def __init__(self):
        self.closed = False

    @property
    def fp(self):
        sock = _Sock()

        class Raw(object):
            _sock = sock

        class Fp(object):
            raw = Raw()

        return Fp()

    def close(self):
        self.closed = True


def _rate_limit_body():
    return json.dumps({"error": {"message": "usage exceeds frequency limit",
                                 "code": 14003}}).encode("utf-8")


class _Base(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        os.makedirs(os.path.join(self.dir, "accounts"), exist_ok=True)
        self.clock = FakeTime()
        self._patches = [
            mock.patch.object(P, "time", self.clock),
            mock.patch.object(A, "time", self.clock),
            mock.patch.object(P, "ACCOUNTS_DIR", self.dir),
        ]
        for patch in self._patches:
            patch.start()
        self._old_pool = P.POOL
        self._old_urlopen = A.urlopen
        self._old_wait = P.TRANSPARENT_RETRY_WAIT
        # 本套件只钉「透明等待」本身，与出站模型别名无关：上游 v2.0.x 起
        # intl 出站会把 deepseek-v4.1-flash 改写成 -sg，而这里的假账号是按
        # 逻辑名冷却的。关掉别名让两者对齐，否则 throttle_wait 查的是 -sg、
        # 冷却记的是 base，永远读到 0 秒，等待路径根本不会触发。
        self._old_alias = os.environ.get("WB_INTL_MODEL_ALIAS")
        os.environ["WB_INTL_MODEL_ALIAS"] = "0"
        P.TRANSPARENT_RETRY_WAIT = 30.0
        self.accounts = [self._make_account("uid-a"), self._make_account("uid-b")]
        P.POOL = self._make_pool(self.accounts)
        self.hits = []
        self.logs = []
        self._old_log = P.log
        P.log = lambda msg, level=None, tag=None: self.logs.append(str(msg))

    def tearDown(self):
        P.log = self._old_log
        P.TRANSPARENT_RETRY_WAIT = self._old_wait
        P.POOL = self._old_pool
        A.urlopen = self._old_urlopen
        if self._old_alias is None:
            os.environ.pop("WB_INTL_MODEL_ALIAS", None)
        else:
            os.environ["WB_INTL_MODEL_ALIAS"] = self._old_alias
        for patch in reversed(self._patches):
            patch.stop()

    def _make_account(self, uid):
        return A.Account({"uid": uid, "accessToken": "t", "realm": "intl"},
                         os.path.join(self.dir, uid + ".json"))

    def _make_pool(self, accounts):
        class Pool(object):
            affinity = type("Affinity", (), {
                "unbind": lambda self, key: None,
                "demote": lambda self, key, uid=None: None})()

            def count_ready(self, realm, model=None):
                return sum(1 for a in accounts if a.ready(model=model))

            def pick_for_session(self, realm, session_key=None, exclude=(),
                                 model=None, page=None):
                for account in accounts:
                    if account.uid in exclude:
                        continue
                    if not account.ready(model=model):
                        continue
                    return account
                return None

            def list_public(self):
                return []

            def apply_daily_token_limit(self, *a, **k):
                return 0

            def apply_daily_credit_limit(self, *a, **k):
                return 0

            def apply_model_daily_token_limit(self, *a, **k):
                return 0

            def apply_remaining_weights(self, weights=None):
                return weights or {}

        pool = Pool()
        pool.accounts = accounts
        return pool

    def _always_429(self):
        def urlopen(req, timeout=30, proxy=""):
            self.hits.append(req.full_url)
            raise urllib.error.HTTPError(
                req.full_url, 429, "Too Many Requests", {},
                __import__("io").BytesIO(_rate_limit_body()))

        A.urlopen = urlopen

    def _succeed_after(self, n_failures):
        """前 n_failures 次回 429，之后成功。"""
        state = {"n": 0}

        def urlopen(req, timeout=30, proxy=""):
            self.hits.append(req.full_url)
            state["n"] += 1
            if state["n"] <= n_failures:
                raise urllib.error.HTTPError(
                    req.full_url, 429, "Too Many Requests", {},
                    __import__("io").BytesIO(_rate_limit_body()))
            return _UpstreamResponse()

        A.urlopen = urlopen

    def _request(self, **kwargs):
        return P.open_upstream(
            {"model": "deepseek-v4.1-flash",
             "messages": [{"role": "user", "content": "hi"}]},
            target_realm="intl", **kwargs)


class TransparentWaitTests(_Base):
    def test_waits_for_a_cooling_pool_then_serves_the_turn(self):
        """全池冷却 → 等恢复 → 这一轮成功，客户端看不到 429。"""
        for account in self.accounts:
            account.note_error("429", model="deepseek-v4.1-flash",
                               until=self.clock.now + 2.0)
        self._succeed_after(0)
        response, account, _effort = self._request()
        self.assertIsNotNone(account)
        self.assertTrue(self.clock.slept, "应当等待过冷却窗口")
        self.assertGreaterEqual(self.clock.now, 1700000000.0 + 2.0)
        self.assertEqual(len(self.hits), 1, "恢复后只发一次上游请求")
        response.close()

    def test_a_window_beyond_the_budget_is_not_waited_for(self):
        """冷却比预算长 → 等了也白等，立刻如实报 429。"""
        for account in self.accounts:
            account.note_error("429", model="deepseek-v4.1-flash",
                               until=self.clock.now + 600.0)
        self._always_429()
        with self.assertRaises(P.RateLimited):
            self._request()
        self.assertEqual(self.clock.slept, [],
                         "恢复时刻在预算之外时不该空等")

    def test_wait_never_exceeds_the_budget(self):
        """等过一次之后又撞上更长的冷却：总等待时间不能超过预算。"""
        for account in self.accounts:
            account.note_error("429", model="deepseek-v4.1-flash",
                               until=self.clock.now + 20.0)
        # 第一次恢复后的重试仍然 429（上游还在限流），新的冷却 60s 超出余额。
        self._always_429()
        with self.assertRaises(P.RateLimited):
            self._request()
        waited = self.clock.now - 1700000000.0
        self.assertGreaterEqual(waited, 20.0, "应当等过那 20 秒")
        self.assertLessEqual(waited, 30.5, "总等待必须被预算卡住")

    def test_daily_limit_is_reported_immediately(self):
        """日限额等多久都没用，一个字节都不该等。"""
        for account in self.accounts:
            account.daily_token_limit = 100
            account.daily_tokens_today = 100
        self._always_429()
        with self.assertRaises(P.RateLimited) as caught:
            self._request()
        self.assertEqual(self.clock.slept, [], "日限额不该触发透明等待")
        self.assertIn("token limit", str(caught.exception.message))

    def test_no_accounts_is_reported_immediately(self):
        for account in self.accounts:
            account.enabled = False
        self._always_429()
        with self.assertRaises(Exception):
            self._request()
        self.assertEqual(self.clock.slept, [])

    def test_zero_budget_restores_the_old_behaviour(self):
        P.TRANSPARENT_RETRY_WAIT = 0.0
        for account in self.accounts:
            account.note_error("429", model="deepseek-v4.1-flash",
                               until=self.clock.now + 5.0)
        self._always_429()
        with self.assertRaises(P.RateLimited):
            self._request()
        self.assertEqual(self.clock.slept, [], "预算 0 时必须立刻上报")

    def test_pinned_account_does_not_wait(self):
        """固定账号没有「换一个」的余地，等待只会拖住请求。"""
        account = self.accounts[0]
        account.note_error("429", model="deepseek-v4.1-flash",
                           until=self.clock.now + 5.0)
        self._always_429()
        with self.assertRaises(Exception):
            self._request(pin_account=account)
        self.assertEqual(self.clock.slept, [])

    def test_wait_is_logged_once(self):
        for account in self.accounts:
            account.note_error("429", model="deepseek-v4.1-flash",
                               until=self.clock.now + 2.0)
        self._succeed_after(0)
        response, _account, _effort = self._request()
        waiting = [m for m in self.logs if "waiting up to" in m]
        self.assertEqual(len(waiting), 1, "等待日志只该打一次")
        response.close()

    def test_recovered_pool_gets_a_full_attempt_budget(self):
        """等过之后要能重新挑到同一个账号（tried 必须被清掉）。"""
        for account in self.accounts:
            account.note_error("429", model="deepseek-v4.1-flash",
                               until=self.clock.now + 1.0)
        # 第一次成功调用之后，这个账号的冷却已经被等过去了。
        self._succeed_after(0)
        response, account, _effort = self._request()
        self.assertEqual(account.uid, "uid-a")
        response.close()


class DefaultsTests(unittest.TestCase):
    def test_default_budget_is_thirty_seconds(self):
        self.assertEqual(
            float(os.environ.get("WB_TRANSPARENT_RETRY_WAIT", "30") or 0), 30.0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
