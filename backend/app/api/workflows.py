from fastapi import APIRouter, HTTPException
from typing import List, Dict
from datetime import datetime
import uuid
import json
import aiosqlite
import logging

from ..models import (
    WorkflowDefinition,
    WorkflowCreate,
    WorkflowUpdate,
)

router = APIRouter()
logger = logging.getLogger(__name__)

DATABASE_PATH = "workflows.db"


async def init_db():
    """Initialize the SQLite database. Includes idempotent migration to add
    session_id column to existing pre-E3 databases (the column links a saved
    workflow to the trial session that produced it)."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS workflows (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                data TEXT NOT NULL,
                session_id TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
        """)

        # Idempotent migration: add session_id to legacy schemas that pre-date E3.
        async with db.execute("PRAGMA table_info(workflows)") as cursor:
            existing_cols = [row[1] async for row in cursor]
        if "session_id" not in existing_cols:
            logger.info("[init_db] migrating: adding session_id column to workflows")
            await db.execute("ALTER TABLE workflows ADD COLUMN session_id TEXT")

        await db.commit()
    logger.info("Database initialized")


async def get_db():
    """Get database connection."""
    return await aiosqlite.connect(DATABASE_PATH)


@router.get("/", response_model=List[WorkflowDefinition])
async def list_workflows():
    """List all workflows."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM workflows ORDER BY updated_at DESC") as cursor:
            rows = await cursor.fetchall()

    workflows = []
    for row in rows:
        data = json.loads(row["data"])
        workflows.append(WorkflowDefinition(
            id=row["id"],
            name=row["name"],
            agents=data.get("agents", []),
            topologies=data.get("topologies", []),
            connections=data.get("connections", []),
            nodes=data.get("nodes", []),
            session_id=row["session_id"] if "session_id" in row.keys() else None,
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
        ))

    return workflows


@router.get("/{workflow_id}", response_model=WorkflowDefinition)
async def get_workflow(workflow_id: str):
    """Get a specific workflow by ID."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM workflows WHERE id = ?", (workflow_id,)
        ) as cursor:
            row = await cursor.fetchone()

    if not row:
        raise HTTPException(status_code=404, detail="Workflow not found")

    data = json.loads(row["data"])
    return WorkflowDefinition(
        id=row["id"],
        name=row["name"],
        agents=data.get("agents", []),
        topologies=data.get("topologies", []),
        connections=data.get("connections", []),
        nodes=data.get("nodes", []),
        session_id=row["session_id"] if "session_id" in row.keys() else None,
        created_at=datetime.fromisoformat(row["created_at"]),
        updated_at=datetime.fromisoformat(row["updated_at"]),
    )


@router.post("/", response_model=WorkflowDefinition)
async def create_workflow(workflow: WorkflowCreate):
    """Create a new workflow."""
    workflow_id = f"workflow-{uuid.uuid4().hex[:8]}"
    now = datetime.utcnow()

    data = {
        "agents": [a.model_dump() for a in workflow.agents],
        "topologies": [t.model_dump() for t in workflow.topologies],
        "connections": [c.model_dump() for c in workflow.connections],
        "nodes": [n.model_dump() for n in workflow.nodes],
    }

    logger.info(f"[create_workflow] id={workflow_id} session_id={workflow.session_id}")

    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute(
            """
            INSERT INTO workflows (id, name, data, session_id, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (workflow_id, workflow.name, json.dumps(data), workflow.session_id, now.isoformat(), now.isoformat())
        )
        await db.commit()

    logger.info(f"Created workflow: {workflow_id}")

    return WorkflowDefinition(
        id=workflow_id,
        name=workflow.name,
        agents=workflow.agents,
        topologies=workflow.topologies,
        connections=workflow.connections,
        nodes=workflow.nodes,
        session_id=workflow.session_id,
        created_at=now,
        updated_at=now,
    )


@router.put("/{workflow_id}", response_model=WorkflowDefinition)
async def update_workflow(workflow_id: str, workflow: WorkflowUpdate):
    """Update an existing workflow."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM workflows WHERE id = ?", (workflow_id,)
        ) as cursor:
            row = await cursor.fetchone()

    if not row:
        raise HTTPException(status_code=404, detail="Workflow not found")

    existing_data = json.loads(row["data"])
    existing_session_id = row["session_id"] if "session_id" in row.keys() else None
    now = datetime.utcnow()

    # Update fields if provided
    name = workflow.name if workflow.name is not None else row["name"]
    agents = [a.model_dump() for a in workflow.agents] if workflow.agents is not None else existing_data.get("agents", [])
    topologies = [t.model_dump() for t in workflow.topologies] if workflow.topologies is not None else existing_data.get("topologies", [])
    connections = [c.model_dump() for c in workflow.connections] if workflow.connections is not None else existing_data.get("connections", [])
    nodes = [n.model_dump() for n in workflow.nodes] if workflow.nodes is not None else existing_data.get("nodes", [])
    # Only overwrite session_id if the request explicitly provided one. This
    # preserves the original trial owner across mid-trial saves where the
    # client may not re-send sessionId.
    session_id = workflow.session_id if workflow.session_id is not None else existing_session_id

    data = {
        "agents": agents,
        "topologies": topologies,
        "connections": connections,
        "nodes": nodes,
    }

    logger.info(f"[update_workflow] id={workflow_id} session_id={session_id}")

    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute(
            """
            UPDATE workflows
            SET name = ?, data = ?, session_id = ?, updated_at = ?
            WHERE id = ?
            """,
            (name, json.dumps(data), session_id, now.isoformat(), workflow_id)
        )
        await db.commit()

    logger.info(f"Updated workflow: {workflow_id}")

    return WorkflowDefinition(
        id=workflow_id,
        name=name,
        agents=workflow.agents if workflow.agents is not None else [],
        topologies=workflow.topologies if workflow.topologies is not None else [],
        connections=workflow.connections if workflow.connections is not None else [],
        nodes=workflow.nodes if workflow.nodes is not None else [],
        session_id=session_id,
        created_at=datetime.fromisoformat(row["created_at"]),
        updated_at=now,
    )


@router.delete("/{workflow_id}")
async def delete_workflow(workflow_id: str):
    """Delete a workflow."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        async with db.execute(
            "SELECT id FROM workflows WHERE id = ?", (workflow_id,)
        ) as cursor:
            row = await cursor.fetchone()

        if not row:
            raise HTTPException(status_code=404, detail="Workflow not found")

        await db.execute("DELETE FROM workflows WHERE id = ?", (workflow_id,))
        await db.commit()

    logger.info(f"Deleted workflow: {workflow_id}")

    return {"message": f"Workflow {workflow_id} deleted"}
