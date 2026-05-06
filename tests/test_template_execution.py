"""
Tests for template execution persistence.
"""
import uuid
from datetime import datetime

import pytest
from sqlalchemy.orm import Session

from app.models.template import Template, TemplateCategory
from app.models.template_version import TemplateVersion, TemplateVersionStatus
from app.models.template_execution import TemplateExecution
from app.services.execution_service import ExecutionService


@pytest.fixture
def template_with_version(db: Session) -> tuple[Template, TemplateVersion]:
    """Create a template with published version for execution tests."""
    template = Template(
        slug="execution_test_template",
        name="Execution Test Template",
        description="Template for testing execution",
        category=TemplateCategory.LESSON_DESIGN,
        is_system_template=True,
        is_active=True,
    )
    db.add(template)
    db.flush()
    
    version = TemplateVersion(
        template_id=template.id,
        version=1,
        status=TemplateVersionStatus.PUBLISHED,
        input_schema={
            "type": "object",
            "properties": {
                "subject": {"type": "string"},
                "grade": {"type": "integer"},
                "topic": {"type": "string"},
            },
            "required": ["subject", "grade", "topic"]
        },
        output_schema={},
        prompt_definition={"description": "Test"},
        model_config={"provider": "openai", "model": "gpt-4o-mini"},
        published_at=datetime.utcnow(),
    )
    db.add(version)
    db.commit()
    db.refresh(template)
    db.refresh(version)
    return template, version


@pytest.mark.asyncio
async def test_execution_creates_template_execution_record(db: Session, template_with_version):
    """Test that executing a template creates a TemplateExecution record."""
    template, version = template_with_version
    
    input_data = {
        "subject": "science",
        "grade": 5,
        "topic": "Test Topic",
    }
    
    # Count executions before
    count_before = db.query(TemplateExecution).filter(
        TemplateExecution.template_id == template.id
    ).count()
    
    # Execute
    execution, output = await ExecutionService.execute(
        db,
        template=template,
        template_version=version,
        input_data=input_data,
        user_id=None,
        tenant_id=None,
        is_demo=False,
    )
    
    # Verify execution was created
    assert execution is not None
    assert execution.id is not None
    assert execution.template_id == template.id
    assert execution.template_version_id == version.id
    assert execution.input_data == input_data
    assert execution.output_data is not None
    
    # Verify it's persisted
    db.refresh(execution)
    persisted = db.query(TemplateExecution).filter(
        TemplateExecution.id == execution.id
    ).first()
    assert persisted is not None
    assert persisted.template_id == template.id
    
    # Count executions after
    count_after = db.query(TemplateExecution).filter(
        TemplateExecution.template_id == template.id
    ).count()
    assert count_after == count_before + 1


@pytest.mark.asyncio
async def test_execution_persists_metadata(db: Session, template_with_version):
    """Test that TemplateExecution includes model, provider, token usage, etc."""
    template, version = template_with_version
    
    execution, output = await ExecutionService.execute(
        db,
        template=template,
        template_version=version,
        input_data={"subject": "math", "grade": 4, "topic": "Fractions"},
        user_id=None,
        tenant_id=None,
        is_demo=False,
    )
    
    # Verify metadata fields
    assert execution.model_used is not None
    assert execution.provider_used is not None
    assert execution.token_usage is not None
    assert isinstance(execution.token_usage, dict)
    assert "total" in execution.token_usage or execution.token_usage == {}
    assert execution.latency_ms is not None
    assert execution.cache_hit is not None


@pytest.mark.asyncio
async def test_execution_with_user_and_tenant(db: Session, template_with_version):
    """Test that execution stores user_id and tenant_id when provided."""
    template, version = template_with_version
    
    user_id = uuid.uuid4()
    tenant_id = uuid.uuid4()
    
    execution, output = await ExecutionService.execute(
        db,
        template=template,
        template_version=version,
        input_data={"subject": "english", "grade": 6, "topic": "Writing"},
        user_id=user_id,
        tenant_id=tenant_id,
        is_demo=False,
    )
    
    assert execution.user_id == user_id
    assert execution.tenant_id == tenant_id

