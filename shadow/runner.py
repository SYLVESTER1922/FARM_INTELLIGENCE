"""
Run the new engine beside the old one and log what it said. Never raises, never blocks the caller (submit() returns at once; the work happens on a
small background pool), and writes only to shadow_log. Bounded: a sampling fraction and a daily ceiling cap the number of model calls.
"""

import concurrent.futures as cf
import dataclasses
import datetime as dt
import json
import logging
import os
import random

import psycopg

from shadow import compare, enabled

log = logging.getLogger("shadow")
_POOL = cf.ThreadPoolExecutor(max_workers=2, thread_name_prefix="shadow")
_PENDING = []


def _limits(env=None):
    env = os.environ if env is None else env
    return float(env.get("SHADOW_SAMPLE", "1.0")), int(env.get("SHADOW_DAILY_LIMIT", "200"))


def _make_llm(env=None):
    from router.llm import PINNED_MODEL, make_client
    return make_client((os.environ if env is None else env).get("SHADOW_MODEL", PINNED_MODEL))


def _scope_json(scope):
    if scope is None:
        return None
    return json.dumps({k: (str(v) if isinstance(v, (dt.date, dt.datetime)) else (list(v) if isinstance(v, tuple) else v))
                       for k, v in dataclasses.asdict(scope).items() if v not in (None, ())}, default=str)


def ran_today(conn, farm_code):
    return conn.execute("SELECT COUNT(*) FROM shadow_log WHERE farm_code = %s AND logged_at >= date_trunc('day', now())", (farm_code,)).fetchone()[0]


def run_shadow(dsn, farm_code, question, old, *, date_from=None, date_to=None, llm=None, today=None, week_start=0, env=None, rng=None, conn=None):
    """Answer `question` with the new engine and log it next to the old engine's answer `old` (an old-engine Answer, or anything with its attributes
    and a .text). Returns the shadow_log id, or None when it was skipped or failed. `conn`: a connection to use instead of opening one (tests)."""
    own = conn is None
    try:
        rate, daily = _limits(env)
        if (rng or random).random() >= rate:
            log.info("shadow skipped (SHADOW_SAMPLE=%s)", rate)
            return None
        conn = conn or psycopg.connect(dsn, autocommit=True, prepare_threshold=None)
        if conn.execute("SELECT to_regclass('shadow_log')").fetchone()[0] is None:
            log.error("shadow_log missing: run registry.migrations.migrate")
            return None
        if ran_today(conn, farm_code) >= daily:
            log.warning("shadow skipped: today's ceiling of %s runs (SHADOW_DAILY_LIMIT) is reached", daily)
            return None
        from router import answer_question_v2
        from router.prompt import PROMPT_VERSION
        from registry.settings import get_settings, week_start_index
        try:
            week_start = week_start_index(get_settings(conn, farm_code))
        except Exception:
            pass
        flt = (date_from, date_to) if date_from and date_to else None
        new_kind = new_code = new_metric = new_text = new_error = scope = None
        model = llm_s = cost = total = None
        try:
            llm = llm or _make_llm(env)
            ans = answer_question_v2(question, conn, llm, farm_code=farm_code, today=today, dashboard_filter=flt, week_start=week_start)
            new_kind, new_code, new_metric, new_text = ans.kind, ans.code, ans.metric_id, ans.text
            scope = _scope_json(ans.scope)
            total = ans.seconds
            if ans.llm:
                model, llm_s, cost = ans.llm.model, ans.llm.latency_s, ans.llm.cost_usd
        except Exception as e:                                          # the new engine failing is itself a finding
            new_kind, new_error = "error", f"{type(e).__name__}: {e}"[:300]
        old_kind, old_reason = compare.old_outcome(old)
        old_text = getattr(old, "text", "") or ""
        cls = compare.classify(old_kind, old_text, new_kind, new_text, new_error)
        new_id = conn.execute(
            """INSERT INTO shadow_log (farm_code, question, filter_from, filter_to, old_kind, old_intent_source, old_reason, old_text, new_kind, new_code,
                                       new_metric, new_scope, new_text, new_error, model, prompt_version, llm_seconds, total_seconds, cost_usd,
                                       classification, needs_label)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
            (farm_code, question, date_from, date_to, old_kind, getattr(old, "intent_source", None), old_reason, old_text, new_kind, new_code, new_metric,
             scope, new_text, new_error, model, PROMPT_VERSION, llm_s, total, cost, cls, compare.needs_label(cls))).fetchone()[0]
        log.info("shadow row %s logged: %s (new engine: %s)", new_id, cls, new_kind)
        return new_id
    except Exception as e:                                               # shadow mode must never be able to hurt the real answer
        # Type, message and traceback, never the question or the DSN (a psycopg error message does not carry the password).
        log.error("shadow run failed: %s: %s", type(e).__name__, str(e)[:300], exc_info=True)
        return None
    finally:
        if own and conn is not None:
            try:
                conn.close()
            except Exception:
                pass


def submit(dsn, farm_code, question, old, **kw):
    """Fire and forget: schedule run_shadow on the background pool and return immediately. Does nothing unless SHADOW_MODE=1."""
    if not enabled(kw.get("env")):
        return None
    log.info("shadow run scheduled")
    fut = _POOL.submit(run_shadow, dsn, farm_code, question, old, **kw)
    _PENDING.append(fut)
    del _PENDING[:-50]
    return fut


def wait(timeout=30):
    """For tests and shutdown: wait for scheduled runs."""
    cf.wait(list(_PENDING), timeout=timeout)
