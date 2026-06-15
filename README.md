# MIM Incident Intelligence — Splunk Agentic Ops Demo

MIM Incident Intelligence is an AI-assisted Major Incident Management demo for cyber and application incidents. It normalises incident records into a MIM workflow, recommends operational response steps, allows a responder to approve workflow actions, and writes an auditable workflow trail into Splunk.

## What it demonstrates

- AI-assisted incident classification and response planning.
- Human approval of proposed MIM workflow actions.
- A React dashboard running as the primary frontend container.
- FastAPI workflow APIs for incident workflow creation and approval.
- Splunk HTTP Event Collector integration.
- Searchable workflow audit events in mim_workflow_audit.

## Architecture

React frontend container
  -> FastAPI mim-api container
      -> Workflow service / AI-assisted incident analysis
      -> MongoDB / MongoDB MCP operational memory
      -> Redis normalized incident worker
      -> Splunk HEC
          -> Splunk index: mim_workflow_audit

## Services

- mim-frontend: React dashboard on port 5173
- mim-api: FastAPI workflow API on port 8000
- splunk-enterprise: Splunk Web, HEC, and search API on ports 18000, 8088, and 8089
- mim-mongodb: local MongoDB-compatible store on port 27017
- mim-mongodb-mcp: MongoDB MCP operational-memory service on port 3000
- redis: incident queue on port 6379
- normalized-incident-worker: handles normalized incident events internally

## Setup

Copy the example environment file:

cp .env.example .env

Set SPLUNK_HEC_TOKEN and SPLUNK_PASSWORD in .env.

Start the stack:

docker compose up --build -d

Open the demo services:

- Frontend dashboard: http://localhost:5173
- FastAPI docs: http://localhost:8000/docs
- Splunk Web: http://localhost:18000

Splunk login:

- username: admin
- password: value of SPLUNK_PASSWORD

## Demo flow

1. Open the React dashboard.
2. Create or open a workflow from a normalised cyber incident.
3. Review the AI-assisted classification and proposed response actions.
4. Approve or select a workflow step.
5. Click Send update to Splunk.
6. Open Splunk Web.
7. Search the audit index with:

index="mim_workflow_audit"
| spath
| sort - _time
| table _time incident_id workflow_id workflow_status action step_id ticket_note ai_summary resolver

The expected result is a searchable Splunk event showing the workflow ID, incident ID, approved action, responder note, and AI-generated summary.

## Splunk integration

The dashboard appends workflow audit records to Splunk through HEC. It does not edit original Splunk events. Audit events are linked by incident_id and workflow_id.

## AI usage

The system uses AI-assisted workflow logic to classify incidents, assess similarity to historical incidents, recommend resolver groups, and generate structured response steps for human approval.

## Production direction

This is a hackathon demo stack. In production, the FastAPI service could run on Cloud Run or another container platform, while Splunk would typically be an existing enterprise Splunk deployment. The demo keeps Splunk Enterprise in Docker Compose so reviewers can reproduce the full workflow locally.

## License

MIT License.
