from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Body
from pydantic import BaseModel, Field

from app.agents.execution_agent import ExecutionAgent
from app.agents.validation_agent import ValidationAgent
from app.agents.workflow_coordinator import WorkflowCoordinatorAgent
from app.api.execution import router as execution_router
from app.models.workflow_state import WorkflowState
from app.services.workflow_service import process_workflow
from fastapi.middleware.cors import CORSMiddleware
from app.io.splunk_hec_client import SplunkHecClient


class SplunkWorkflowUpdateRequest(BaseModel):
    workflow_id: str
    workflow_status: str
    action: str
    step_id: str | None = None
    step_title: str | None = None
    ticket_note: str | None = None
    ai_summary: str | None = None
    resolver: str | None = None
    resolution_summary: str | None = None


app = FastAPI(
    title="MIM Incident Intelligence API",
    description="API wrapper for payload analysis, KBA/DIP retrieval, approval, execution, and validation.",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

WORKFLOW_STORE: dict[str, WorkflowState] = {}
WORKFLOW_OUTPUT_DIR = Path("data/output/api_workflows")

app.include_router(execution_router)

PAYLOAD_OPTIONS = {
    "salesforce_sso": "fixtures/payloads/incoming-incident-salesforce-sso.json",
    "vault_key": "fixtures/payloads/incoming-incident-vault-key.json",
    "pipeline_failure": "fixtures/payloads/incoming-incident-pipeline-failure.json",
    "cyber_app_exploit": "fixtures/payloads/incoming-cyber-app-exploit.json",
}


DATASET_OPTIONS = {
    "it_mim": "data/generated/cyber_mim_incidents.csv",
    "cyber_mim": "data/generated/cyber_mim_incidents.csv",
}


class CreateWorkflowRequest(BaseModel):
    payload_key: str | None = Field(
        default=None,
        description="Known payload fixture key, such as salesforce_sso or cyber_app_exploit.",
    )
    payload_path: str | None = Field(
        default=None,
        description="Direct path to an incoming payload JSON file.",
    )
    payload: dict[str, Any] | None = Field(
        default=None,
        description="Inline incident payload. Takes precedence over payload_key/path.",
    )
    dataset_key: str | None = Field(
        default="it_mim",
        description="Known historical dataset key, such as it_mim or cyber_mim.",
    )
    dataset_path: str | None = Field(
        default=None,
        description="Direct path to canonical historical incidents CSV.",
    )


class ApproveWorkflowRequest(BaseModel):
    action_id: str = Field(description="Action ID to approve and execute.")


class RollbackWorkflowActionRequest(BaseModel):
    action_id: str


def load_json(path: str) -> dict[str, Any]:
    file_path = Path(path)

    if not file_path.exists():
        raise HTTPException(status_code=404, detail=f"File not found: {path}")

    return json.loads(file_path.read_text(encoding="utf-8"))


def resolve_payload(request: CreateWorkflowRequest) -> dict[str, Any]:
    if request.payload is not None:
        return request.payload

    if request.payload_path:
        return load_json(request.payload_path)

    if request.payload_key:
        path = PAYLOAD_OPTIONS.get(request.payload_key)
        if not path:
            raise HTTPException(
                status_code=400,
                detail=f"Unknown payload_key: {request.payload_key}",
            )
        return load_json(path)

    raise HTTPException(
        status_code=400,
        detail="Provide payload, payload_path, or payload_key.",
    )


def resolve_dataset_path(request: CreateWorkflowRequest) -> str:
    if request.dataset_path:
        path = request.dataset_path
    else:
        dataset_key = request.dataset_key or "it_mim"
        path = DATASET_OPTIONS.get(dataset_key)
        if not path:
            raise HTTPException(
                status_code=400,
                detail=f"Unknown dataset_key: {dataset_key}",
            )

    if not Path(path).exists():
        raise HTTPException(
            status_code=404,
            detail=f"Historical incidents dataset not found: {path}",
        )

    return path


def write_workflow_state(state: WorkflowState) -> None:
    output_dir = Path("data/output/api_workflows")
    output_dir.mkdir(parents=True, exist_ok=True)

    path = output_dir / f"{state.workflow_id}.json"
    path.write_text(state.model_dump_json(indent=2), encoding="utf-8")


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/options")
def options() -> dict[str, Any]:
    return {
        "payloads": PAYLOAD_OPTIONS,
        "datasets": DATASET_OPTIONS,
        "execution_mode": "real"
        if __import__("os").getenv("REAL_EXECUTION", "false").lower() == "true"
        else "simulated",
    }


@app.post("/api/workflows")
def create_workflow(request: CreateWorkflowRequest) -> dict[str, Any]:
    payload = resolve_payload(request)
    dataset_path = resolve_dataset_path(request)

    state = process_workflow(
        payload=payload,
        dataset_path=dataset_path,
    )

    WORKFLOW_STORE[state.workflow_id] = state

    return state.model_dump()


@app.get("/api/workflows")
def list_mim_review_workflows() -> list[dict[str, Any]]:
    WORKFLOW_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    review_items: list[dict[str, Any]] = []

    for path in sorted(
        WORKFLOW_OUTPUT_DIR.glob("*.json"),
        key=lambda item: item.stat().st_mtime,
        reverse=True,
    ):
        workflow = json.loads(path.read_text(encoding="utf-8"))

        incident = workflow.get("incident", {})
        analysis = workflow.get("analysis", {})
        action_plan = workflow.get("action_plan") or {}

        priority = incident.get("priority")
        classification = analysis.get("mim_classification")
        workflow_status = workflow.get("status")

        requires_mim_review = priority in {"P1", "P2"} or classification in {
            "major_mim",
            "global_major_mim",
        }

        is_open = workflow_status not in {
            "validated",
            "failed",
            "completed",
        }

        if requires_mim_review and is_open:
            review_items.append(workflow)

    return review_items


@app.get("/api/workflows/{workflow_id}")
def get_workflow(workflow_id: str) -> dict[str, Any]:
    state = WORKFLOW_STORE.get(workflow_id)

    if state:
        return state.model_dump()

    path = WORKFLOW_OUTPUT_DIR / f"{workflow_id}.json"

    if not path.exists():
        raise HTTPException(
            status_code=404,
            detail=f"Workflow not found: {workflow_id}",
        )

    return json.loads(path.read_text(encoding="utf-8"))


@app.post("/api/workflows/{workflow_id}/approve")
def approve_and_execute(
    workflow_id: str,
    request: ApproveWorkflowRequest,
) -> dict[str, Any]:
    state = WORKFLOW_STORE.get(workflow_id)

    if not state:
        path = Path("data/output/api_workflows") / f"{workflow_id}.json"
        if path.exists():
            state = WorkflowState.model_validate_json(path.read_text(encoding="utf-8"))
        else:
            raise HTTPException(status_code=404, detail=f"Workflow not found: {workflow_id}")

    coordinator = WorkflowCoordinatorAgent()
    state = coordinator.approve_action(state, request.action_id)
    state = ExecutionAgent().execute_approved_actions(state)
    state = ValidationAgent().validate(state)

    WORKFLOW_STORE[state.workflow_id] = state
    write_workflow_state(state)

    return state.model_dump()


@app.post("/api/workflows/{workflow_id}/rollback")
def prepare_workflow_rollback(
    workflow_id: str,
    request: RollbackWorkflowActionRequest,
) -> dict[str, Any]:
    state = WORKFLOW_STORE.get(workflow_id)

    if not state:
        path = Path("data/output/api_workflows") / f"{workflow_id}.json"

        if path.exists():
            state = WorkflowState.model_validate_json(path.read_text(encoding="utf-8"))
        else:
            raise HTTPException(
                status_code=404,
                detail=f"Workflow not found: {workflow_id}",
            )

    coordinator = WorkflowCoordinatorAgent()

    state = coordinator.create_rollback_action_plan(
        state=state,
        action_id=request.action_id,
    )

    WORKFLOW_STORE[state.workflow_id] = state
    write_workflow_state(state)

    rollback_action_id = f"rollback-{request.action_id}"

    return {
        "status": state.status,
        "workflow_id": workflow_id,
        "rollback_action_id": rollback_action_id,
        "message": (
            f"Rollback action {rollback_action_id} has been created. "
            "Explicit human approval is required before execution."
        ),
        "action_plan": state.action_plan,
    }


@app.get("/api/workflows/{workflow_id}/logs/{action_id}")
def get_workflow_action_log(
    workflow_id: str,
    action_id: str,
) -> dict[str, Any]:
    state = WORKFLOW_STORE.get(workflow_id)

    if not state:
        path = Path("data/output/api_workflows") / f"{workflow_id}.json"

        if path.exists():
            state = WorkflowState.model_validate_json(
                path.read_text(encoding="utf-8")
            )
        else:
            raise HTTPException(
                status_code=404,
                detail=f"Workflow not found: {workflow_id}",
            )

    matching_results = [
        result
        for result in state.execution.results
        if result.get("action_id") == action_id
    ]

    if not matching_results:
        raise HTTPException(
            status_code=404,
            detail=f"No execution result found for action: {action_id}",
        )

    latest_result = matching_results[-1]

    log_path_value = latest_result.get("log_path")

    if not log_path_value:
        return {
            "workflow_id": workflow_id,
            "action_id": action_id,
            "status": latest_result.get("status"),
            "message": latest_result.get("message"),
            "log_available": False,
        }

    allowed_log_dir = Path(
        "data/output/execution_logs"
    ).resolve()

    log_path = Path(log_path_value).resolve()

    if allowed_log_dir not in log_path.parents:
        raise HTTPException(
            status_code=403,
            detail="Log path is outside the approved log directory.",
        )

    if not log_path.exists():
        raise HTTPException(
            status_code=404,
            detail=f"Log file not found for action: {action_id}",
        )

    return {
        "workflow_id": workflow_id,
        "action_id": action_id,
        "status": latest_result.get("status"),
        "message": latest_result.get("message"),
        "log_available": True,
        "log_content": log_path.read_text(
            encoding="utf-8",
            errors="replace",
        ),
    }


@app.post("/api/splunk/incidents/{incident_id}/workflow-update")
def send_splunk_workflow_update(
    incident_id: str,
    payload: dict[str, Any] = Body(...),
) -> dict[str, Any]:
    update_request = SplunkWorkflowUpdateRequest.model_validate(payload)

    client = SplunkHecClient()

    extra: dict[str, Any] = {}
    if update_request.ticket_note:
        extra["ticket_note"] = update_request.ticket_note

    return client.send_workflow_event(
        incident_id=incident_id,
        workflow_id=update_request.workflow_id,
        workflow_status=update_request.workflow_status,
        action=update_request.action,
        step_id=update_request.step_id,
        step_title=update_request.step_title,
        ai_summary=update_request.ai_summary,
        resolver=update_request.resolver,
        resolution_summary=update_request.resolution_summary,
        extra=extra,
    )