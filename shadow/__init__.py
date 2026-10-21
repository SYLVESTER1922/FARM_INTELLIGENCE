"""
Shadow mode (plan sections 13 and 14, step 8). The OLD engine answers the user, exactly as before. With SHADOW_MODE=1 the NEW engine also runs on the
same question, in the background, and its answer goes to the `shadow_log` table only: the user never sees it, and nothing it does can change or delay
the old answer. A person labels the disagreements (shadow/report.py); the "report wrong answer" button (shadow/reports.py) and a sample of the old
engine's `query_log` (shadow/sample.py) feed the cases the written set missed.

Everything is off by default:
    SHADOW_MODE=1            run the new engine beside the old one
    SHADOW_SAMPLE=0.5        fraction of questions to shadow (default 1.0)
    SHADOW_DAILY_LIMIT=200   most shadow runs per day, a ceiling on model cost (default 200)
    SHADOW_MODEL=gpt-4.1     the router model (default: the pinned one)
"""

import os


def enabled(env=None) -> bool:
    return (os.environ if env is None else env).get("SHADOW_MODE") == "1"
