"""Notification providers.

The one rule that matters: a provider reports only what it actually did.
A provider that is not configured returns status "not_configured" and says
plainly that nothing was sent. Nothing in this file ever returns "sent" for
work it did not perform.
"""
from abc import ABC, abstractmethod

from .. import config

SENT = "sent"
CREATED = "created"
NOT_CONFIGURED = "not_configured"
FAILED = "failed"


class NotificationProvider(ABC):
    name = "base"

    @abstractmethod
    def send(self, alert: dict) -> dict: ...

    @abstractmethod
    def configured(self) -> bool: ...


class InAppProvider(NotificationProvider):
    """Produces the alert object the browser/app renders. This one genuinely
    completes its job here, so it reports 'created', not 'sent'."""
    name = "in_app"

    def configured(self) -> bool:
        return True

    def send(self, alert):
        return {"provider": self.name, "status": CREATED, "delivered": False,
                "detail": "Alert created for in-app and browser notification"}


class FCMProvider(NotificationProvider):
    """Firebase Cloud Messaging push."""
    name = "fcm"

    def configured(self) -> bool:
        return config.FCM_CONFIGURED

    def send(self, alert):
        if not self.configured():
            return {"provider": self.name, "status": NOT_CONFIGURED, "delivered": False,
                    "detail": "Firebase Cloud Messaging is not configured. No push was sent."}
        try:
            # Wire the FCM HTTP v1 call here once service-account credentials exist.
            raise NotImplementedError
        except NotImplementedError:
            return {"provider": self.name, "status": NOT_CONFIGURED, "delivered": False,
                    "detail": "Firebase credentials found but push sending is not "
                              "implemented in this prototype. No push was sent."}


class MockSMSProvider(NotificationProvider):
    """Stands in when no SMS gateway is configured.

    It exists so the UI has a provider to display, NOT so a demo can look like
    it sent messages. It always reports that nothing was sent.
    """
    name = "sms"

    def configured(self) -> bool:
        return False

    def send(self, alert):
        return {"provider": self.name, "status": NOT_CONFIGURED, "delivered": False,
                "detail": "SMS provider not configured. No SMS was sent."}


class RealSMSProvider(NotificationProvider):
    """Live SMS gateway. Only selected when real credentials are present."""
    name = "sms"

    def configured(self) -> bool:
        return config.SMS_CONFIGURED

    def send(self, alert):
        try:
            # Wire the gateway HTTP call here, then return SENT with delivered=True
            # only on a confirmed provider acknowledgement.
            raise NotImplementedError
        except NotImplementedError:
            return {"provider": self.name, "status": NOT_CONFIGURED, "delivered": False,
                    "detail": "SMS gateway credentials found but the integration is not "
                              "implemented in this prototype. No SMS was sent."}


def providers() -> list:
    return [
        InAppProvider(),
        FCMProvider(),
        RealSMSProvider() if config.SMS_CONFIGURED else MockSMSProvider(),
    ]


def dispatch(alert: dict) -> list:
    return [p.send(alert) for p in providers()]


def status() -> dict:
    return {p.name: {"configured": p.configured()} for p in providers()}
