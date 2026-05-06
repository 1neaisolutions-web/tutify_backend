"""
Tests for template API endpoints.
"""
import uuid
from datetime import datetime

import pytest
from sqlalchemy.orm import Session

from app.models.template import Template, TemplateCategory
from app.models.template_version import TemplateVersion, TemplateVersionStatus


@pytest.fixture
def sample_template(db: Session) -> Template:
    """Create a sample template for testing."""
    template = Template(
        slug="test_lesson_planner",
        name="Test Lesson Planner",
        description="A test lesson planner template",
        category=TemplateCategory.LESSON_DESIGN,
        subject_default=None,
        grade_bands_supported=["3-5", "6-8"],
        is_system_template=True,
        is_active=True,
    )
    db.add(template)
    db.flush()
    
    # Create a published version
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
                "learning_objective": {"type": "string"},
                "time_duration": {"type": "string"},
                "bloom_level": {"type": "string"},
            },
            "required": ["subject", "grade", "topic", "learning_objective", "time_duration", "bloom_level"]
        },
        output_schema={},
        prompt_definition={"description": "Test prompt"},
        model_config={"provider": "openai", "model": "gpt-4o-mini"},
        published_at=datetime.utcnow(),
    )
    db.add(version)
    db.commit()
    db.refresh(template)
    return template


def test_list_templates_empty(client):
    """Test listing templates when none exist."""
    response = client.get("/api/v1/templates")
    assert response.status_code == 200
    assert response.json() == []


def test_list_templates_with_data(client, sample_template):
    """Test listing templates returns active templates with published versions."""
    response = client.get("/api/v1/templates")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["slug"] == "test_lesson_planner"
    assert data[0]["name"] == "Test Lesson Planner"
    assert data[0]["is_active"] is True


def test_list_templates_with_filters(client, sample_template, db: Session):
    """Test listing templates with query filters."""
    # Test category filter
    response = client.get("/api/v1/templates?category=lesson_design")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    
    # Test non-matching category
    response = client.get("/api/v1/templates?category=assessment")
    assert response.status_code == 200
    assert len(response.json()) == 0


def test_get_template_detail_success(client, sample_template):
    """Test getting template detail by slug."""
    response = client.get("/api/v1/templates/test_lesson_planner")
    assert response.status_code == 200
    data = response.json()
    assert data["slug"] == "test_lesson_planner"
    assert data["name"] == "Test Lesson Planner"
    assert "latest_version" in data
    assert data["latest_version"] is not None


def test_get_template_detail_not_found(client):
    """Test getting template detail for non-existent slug returns 404."""
    response = client.get("/api/v1/templates/nonexistent")
    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()


def test_get_template_detail_no_published_version(client, db: Session):
    """Test getting template detail when no published version exists returns 404."""
    template = Template(
        slug="no_version_template",
        name="No Version Template",
        description="Template without published version",
        category=TemplateCategory.LESSON_DESIGN,
        is_system_template=True,
        is_active=True,
    )
    db.add(template)
    db.commit()
    
    response = client.get("/api/v1/templates/no_version_template")
    assert response.status_code == 404
    assert "published version" in response.json()["detail"].lower()


def test_execute_template_success(client, sample_template):
    """Test executing a template with valid input."""
    payload = {
        "data": {
            "subject": "science",
            "grade": 5,
            "topic": "Earth's Rotation",
            "learning_objective": "Students will understand how Earth's rotation causes day and night.",
            "time_duration": "45 min",
            "bloom_level": "Understand",
        }
    }
    response = client.post("/api/v1/templates/test_lesson_planner/execute", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert "execution_id" in data
    assert "output" in data
    assert data["template_slug"] == "test_lesson_planner" or data.get("template_id") is not None


def test_execute_template_invalid_input(client, sample_template):
    """Test executing a template with invalid/missing required fields returns 422."""
    # Missing required fields
    payload = {
        "data": {
            "subject": "science",
            # Missing grade, topic, etc.
        }
    }
    response = client.post("/api/v1/templates/test_lesson_planner/execute", json=payload)
    assert response.status_code == 422
    assert "missing" in response.json()["detail"].lower() or "required" in response.json()["detail"].lower()


def test_execute_template_not_found(client):
    """Test executing a non-existent template returns 404."""
    payload = {"data": {"subject": "science", "grade": 5, "topic": "test"}}
    response = client.post("/api/v1/templates/nonexistent/execute", json=payload)
    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()


def test_execute_template_no_published_version(client, db: Session):
    """Test executing template with no published version returns 404."""
    template = Template(
        slug="draft_template",
        name="Draft Template",
        description="Template with only draft version",
        category=TemplateCategory.LESSON_DESIGN,
        is_system_template=True,
        is_active=True,
    )
    db.add(template)
    db.flush()
    
    # Create only a draft version
    version = TemplateVersion(
        template_id=template.id,
        version=1,
        status=TemplateVersionStatus.DRAFT,
        input_schema={"type": "object", "properties": {}, "required": []},
        published_at=None,
    )
    db.add(version)
    db.commit()
    
    payload = {"data": {"subject": "science", "grade": 5, "topic": "test"}}
    response = client.post("/api/v1/templates/draft_template/execute", json=payload)
    assert response.status_code == 404
    assert "published version" in response.json()["detail"].lower()

