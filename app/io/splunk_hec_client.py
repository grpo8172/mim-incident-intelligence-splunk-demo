from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any

import requests


class SplunkHecClient:
    def __init__(self) -> None:
        self.url = os.getenv("SPLUNK_HEC_URL", "").strip()
        self.token = os.getenv("SPLUNK_HEC_TOKEN", "").strip()
        self.index = os.getenv("SPLUNK_AUDIT_INDEX", "mim_workflow_audit").strip()
        self.verify_ssl = os.getenv("SPLUNK_VERIFY_SSL", "false").lower() == "true"

    @property
    def enabled(self) -> bool:
        return bool(self.url and self.token)

    def send_workflow_event(
        self,
        *,
        incident_id: str,
        workflow_id: str,
        workflow_status: str,
        action: str,
        step_id: str | None = None,
        step_title: str | None = None,
        ai_summary: str | None = None,
        resolver: str | None = None,
        resolution_summary: str | None = None,
        extra: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if not self.enabled:
            return {
                "sent": False,
                "reason": "Splunk HEC is not configured. Set SPLUNK_HEC_URL and SPLUNK_HEC_TOKEN.",
            }

        event: dict[str, Any] = {
            "incident_id": incident_id,
            "workflow_id": workflow_id,
            "workflow_status": workflow_status,
            "action": action,
            "step_id": step_id,
            "step_title": step_title,
            "ai_summary": ai_summary,
            "resolver": resolver,
            "resolution_summary": resolution_summary,
            "sent_at": datetime.now(timezone.utc).isoformat(),
        }

        if extra:
            event.update(extra)

        # Keep Splunk events clean by removing empty fields.
        event = {
            key: value
            for key, value in event.items()
            if value is not None and value != ""
        }

        payload = {
            "time": datetime.now(timezone.utc).timestamp(),
            "host": "mim-api",
            "source": "mim-dashboard",
            "sourcetype": "mim:workflow:audit",
            "index": self.index,
            "event": event,
        }

        response = requests.post(
            self.url,
            headers={
                "Authorization": f"Splunk {self.token}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=10,
            verify=self.verify_ssl,
        )

        response.raise_for_status()

        try:
            splunk_response = response.json()
        except ValueError:
            splunk_response = {"raw_response": response.text}

        return {
            "sent": True,
            "splunk_response": splunk_response,
            "event": event,
        }
