from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

WorkflowStatus = Literal[
    "created",
    "incident_analysed",
    "context_retrieved",
    "action_plan_created",
    "awaiting_approval",
    "approved",
    "executed",
    "validated",
    "closed",
    "failed",
]


class WorkflowIncident(BaseModel):
    incident_id: str | None = None
    service: str | None = None
    short_description: str | None = None
    description: str | None = None
    severity: str | None = None
    priority: str | None = None
    symptoms: list[str] = Field(default_factory=list)
    raw: dict[str, Any] = Field(default_factory=dict)


class WorkflowAnalysis(BaseModel):
    mim_classification: str | None = None
    mim_confidence: float = 0.0
    seen_before_status: str | None = None
    recommended_kba_id: str | None = None
    recommended_resolver_group: str | None = None
    recommended_resolution_steps: list[str] = Field(default_factory=list)
    recommended_validation_steps: list[str] = Field(default_factory=list)
    decision_reasons: list[str] = Field(default_factory=list)


class WorkflowContext(BaseModel):
    matched_kbas: list[dict[str, Any]] = Field(default_factory=list)
    matched_dips: list[dict[str, Any]] = Field(default_factory=list)
    matched_change_records: list[dict[str, Any]] = Field(default_factory=list)
    matched_validation_plans: list[dict[str, Any]] = Field(default_factory=list)


class WorkflowExecution(BaseModel):
    environment: str = "uat"
    approved_action_ids: list[str] = Field(default_factory=list)
    results: list[dict[str, Any]] = Field(default_factory=list)


class WorkflowValidation(BaseModel):
    checks: list[str] = Field(default_factory=list)
    status: str = "not_started"
    evidence: list[str] = Field(default_factory=list)


class WorkflowState(BaseModel):
    workflow_id: str
    status: WorkflowStatus = "created"
    incident: WorkflowIncident
    analysis: WorkflowAnalysis = Field(default_factory=WorkflowAnalysis)
    context: WorkflowContext = Field(default_factory=WorkflowContext)
    action_plan: dict[str, Any] | None = None
    execution: WorkflowExecution = Field(default_factory=WorkflowExecution)
    validation: WorkflowValidation = Field(default_factory=WorkflowValidation)
    notes: list[str] = Field(default_factory=list)

