"""Outbound SMS. No real texts are sent yet.

`get_sms()` returns the provider named by SMS_PROVIDER. Callers only use `send(to, body)` and
record the returned SmsResult in followup_log, so a real provider plugs in here without
touching the routes.
"""
from dataclasses import dataclass

from . import config


@dataclass
class SmsResult:
    simulated: bool
    ok: bool
    provider: str
    detail: str = ""


class SimulatedSms:
    name = "simulated"

    def send(self, to: str, body: str) -> SmsResult:
        if not to:
            return SmsResult(simulated=True, ok=False, provider=self.name, detail="member has no phone number")
        return SmsResult(simulated=True, ok=True, provider=self.name, detail=f"simulated text to {to}")


class TwilioSms:
    """Placeholder. To enable: pip install twilio, implement send() with
    twilio.rest.Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN).messages.create(...), set SMS_PROVIDER=twilio.
    Get member consent for texts before turning this on."""

    name = "twilio"

    def send(self, to: str, body: str) -> SmsResult:
        raise NotImplementedError("Twilio is not wired up yet; set SMS_PROVIDER=simulated")


def get_sms():
    return TwilioSms() if config.SMS_PROVIDER == "twilio" else SimulatedSms()
