# Content Factory — Deliverable Report

## 1. Files Created

### Domain root
- `app/domains/content_factory/__init__.py`
- `app/domains/content_factory/enums.py` — ContentGenerationStrategy, JobStatus
- `app/domains/content_factory/models.py` — ContentGenerationJob
- `app/domains/content_factory/schemas.py` — Request/Response, agent output shapes
- `app/domains/content_factory/routes.py` — POST /generate/micro-course, GET /jobs, GET /jobs/{id}

### Services
- `app/domains/content_factory/services/__init__.py`
- `app/domains/content_factory/services/validation_service.py` — validate_micro_course, validate_and_raise
- `app/domains/content_factory/services/publishing_service.py` — publish_micro_course (ContentRegistryService)
- `app/domains/content_factory/services/generation_orchestrator_service.py` — run_micro_course_job
- `app/domains/content_factory/services/content_factory_service.py` — create_job, list_jobs, get_job, generate_micro_course

### Agents (stateless; ModelRouter only)
- `app/domains/content_factory/agents/__init__.py`
- `app/domains/content_factory/agents/_utils.py` — parse_json_from_llm
- `app/domains/content_factory/agents/curriculum_agent.py` — run_curriculum_agent
- `app/domains/content_factory/agents/pedagogy_agent.py` — run_pedagogy_agent
- `app/domains/content_factory/agents/structure_agent.py` — run_structure_agent
- `app/domains/content_factory/agents/assessment_agent.py` — run_assessment_agent
- `app/domains/content_factory/agents/review_agent.py` — run_review_agent
- `app/domains/content_factory/agents/quality_agent.py` — run_quality_agent

### Workflows
- `app/domains/content_factory/workflows/__init__.py`
- `app/domains/content_factory/workflows/micro_course_workflow.py` — run_micro_course_pipeline

### Migration
- `alembic/versions/h9i0j1k2l3m4_create_content_generation_jobs_table.py`

### Modified
- `app/db/base.py` — import ContentGenerationJob
- `app/api/v1/__init__.py` — include content_factory router

---

## 2. Models Added

- **ContentGenerationJob** (table `content_generation_jobs`): id, requested_by_user_id (FK users.id), content_type, generation_strategy, topic, subject, grade_band, difficulty, locale, status, current_step, retry_count, quality_score, result_content_id, error_message, step_outputs (JSONB), created_at, started_at, completed_at, updated_at. Indexes: id, requested_by_user_id, content_type, status, created_at.

---

## 3. Routes Added

| Method | Path | Auth | Purpose |
|--------|------|------|--------|
| POST | `/api/v1/content-factory/generate/micro-course` | Admin (super_admin, org_admin) | Request new micro-course; runs workflow to completion, returns job |
| GET | `/api/v1/content-factory/jobs` | Authenticated | List jobs (query: status, content_type, skip, limit) |
| GET | `/api/v1/content-factory/jobs/{id}` | Authenticated | Job details |

---

## 4. Service Methods

- **ContentFactoryService:** create_job, get_job, list_jobs, generate_micro_course (async, runs orchestrator).
- **GenerationOrchestratorService:** run_micro_course_job (async): running → pipeline → validation → reviewing → quality check → publishing → completed (or failed).
- **ValidationService:** validate_micro_course (returns list of errors), validate_and_raise.
- **PublishingService:** publish_micro_course (builds ContentRegistryCreate, create_item, publish_item; returns content_id).

---

## 5. Agents Implemented

| Agent | Purpose | Output keys |
|-------|--------|-------------|
| Curriculum | topic → curriculum plan | learning_objectives, key_concepts, prerequisites, target_skills |
| Pedagogy | curriculum → teaching approach | instructional_flow, examples, teaching_strategies, teacher_reflections |
| Structure | curriculum + pedagogy → structure | modules, lessons, steps, activities |
| Assessment | structure → assessment | practice_tasks, reflection_prompts, mini_quizzes, rubrics |
| Review | full content → coherence | review_status, issues_found, improvement_notes |
| Quality | full content → score | quality_score, quality_feedback, clarity, pedagogical_depth, teacher_usefulness, structure_quality |

All use `ModelRouter.generate()` with temperature 0.2–0.3, max_tokens 800–2000, fallback_chain Anthropic Haiku. No direct provider calls.

---

## 6. Workflow Steps

1. curriculum_agent  
2. pedagogy_agent  
3. structure_agent  
4. assessment_agent  
5. validation_service.validate_and_raise  
6. status = reviewing  
7. review_agent (inside pipeline)  
8. quality_agent (inside pipeline)  
9. If quality_score < 0.5: retry (max 1) or fail  
10. status = publishing  
11. publishing_service.publish_micro_course  
12. status = completed, result_content_id set  

---

## 7. Job Lifecycle

pending → running → (pipeline) → reviewing → (quality check) → publishing → completed  
On validation failure or exception: failed (error_message set).  
On quality below threshold and retries exhausted: failed.

---

## 8. LLM Router Usage

- Every agent calls `from app.llm.router import ModelRouter` and `await router.generate(system_message, prompt, model_config)`.
- model_config: temperature, max_tokens, fallback_chain (e.g. anthropic/claude-3-haiku).
- No OpenAI/Anthropic/Google SDK calls outside the router.

---

## 9. Publishing Integration

- **PublishingService** uses **ContentRegistryService** (create_item, publish_item).
- content_type = micro_course, schema_version = 1.0, source_type = content_factory, source_ref = job id.
- json_blob = full_content (curriculum, pedagogy, structure, assessment, review, quality).
- content_id = factory-{job_id.hex[:8]}-{slug(topic)}.

---

## 10. Schema Validation

- **ValidationService** checks: presence of curriculum, pedagogy, structure, assessment; at least one module and one lesson; assessment has practice_tasks or reflection_prompts.
- Raises **ValidationServiceError** with message list if invalid.

---

## 11. Migration Details

- **Revision:** h9i0j1k2l3m4, **down_revision:** g8h9i0j1k2l3.
- Creates table **content_generation_jobs** with all columns and FK to users.id (SET NULL). Indexes on id, requested_by_user_id, content_type, status, created_at.
- Apply with: `alembic upgrade head` (after ensuring content_registry migration g8h9i0j1k2l3 is applied).

---

## 12. Observability

- Logs: agent step start/finish, provider/model, token usage, workflow status changes, quality score, result_content_id, validation/orchestration failures.

---

## 13. Result Flow

Teacher need / ML gap → Content Generation Job → Agentic Workflow → Quality Validation → Content Registry → Learning Hub Recommendation.

The platform can expand by generating new professional learning resources via the content factory and publishing them into the canonical registry for recommendation mapping.
