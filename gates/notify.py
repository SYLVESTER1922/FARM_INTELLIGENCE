"""Email on a block (plan section 9: during the pilot every block notifies Sylvester). Reuses the ALERT_* settings of router/alerts.py; failure is
recorded, never raised."""

from router.alerts import smtp_notifier


def block_email(farm_code, blocks, outcome="blocked"):
    lines = [f"- {f.message}" for f in blocks[:20]]
    more = f"\n(and {len(blocks) - 20} more)" if len(blocks) > 20 else ""
    subject = f"[Farm Intelligence] Upload {'blocked' if outcome == 'blocked' else 'failed'} for {farm_code}"
    body = (f"The latest upload for {farm_code} {'did not pass the data gates' if outcome == 'blocked' else 'could not be loaded'}. The app keeps serving the last "
            f"verified data, with the banner \"Data last verified <date>. A newer upload is being reviewed.\"\n\n" + "\n".join(lines) + more +
            "\n\nEvery firing is in the gate_firings table. A block clears when a later upload passes.\n")
    return subject, body


def notify_block(farm_code, blocks, notifier=None, outcome="blocked"):
    """Returns (sent, error). `notifier` is a function (subject, body); default is SMTP from the environment."""
    send = notifier if notifier is not None else smtp_notifier()
    if send is None:
        return False, "email not configured (ALERT_SMTP_HOST / ALERT_EMAIL_TO)"
    try:
        send(*block_email(farm_code, blocks, outcome))
        return True, None
    except Exception as e:
        return False, f"{type(e).__name__}: {e}"[:300]
