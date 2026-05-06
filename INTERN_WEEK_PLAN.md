# Intern Week Plan — Next Week

**Tobba:** Templates domain (later: add/update/change template output format as needed)  
**Gazia:** Chatbot domain

---

## Monday — Setup and domain map

**Tobba**
- Clone repo, set `.env` (use provided `DATABASE_URL`).
- Run `alembic upgrade head`, then `python -m app.seed.cli --auth`, `python -m app.seed.cli --create-admin --interactive`, and `python -m app.seed.cli --templates` if needed.
- Start app with `uvicorn app.main:app --reload`; open `/health` and `/docs`.
- Read PROJECT_GUIDE.md and DATABASE_GUIDE.md.
- Map templates: list files in `app/models/template*.py`, `app/api/v1/routes_templates.py`, `app/services/execution_service.py`, `app/llm/prompt_builder.py`, `app/schemas/template*.py`.
- Write a short “Templates map” (bullet list): entry points, where templates are stored, where execution runs, where output is saved.

**Gazia**
- Clone repo, set `.env` (use provided `DATABASE_URL`).
- Run `alembic upgrade head`, then `python -m app.seed.cli --auth`, `python -m app.seed.cli --create-admin --interactive`.
- Start app; open `/health` and `/docs`.
- Read PROJECT_GUIDE.md and DATABASE_GUIDE.md.
- Map chatbots: list files in `app/domains/chatbots/` (routes, models, schemas, services).
- Write a short “Chatbot map” (bullet list): routes, where conversations/messages live, where LLM is called.

---

## Tuesday — First hands-on change

**Tobba**
- Trace one template flow end-to-end (e.g. list templates) from `routes_templates.py` → DB.
- Add one optional query parameter to an existing templates endpoint (e.g. `limit` or `category` if not already there), or add a short comment in code documenting the flow.
- Test in `/docs`.

**Gazia**
- Trace one chatbot flow (e.g. list chatbots or get conversation) from `routes.py` → service → DB.
- Add one optional query parameter to an existing chatbot endpoint (e.g. `limit`), or add a short comment documenting the flow.
- Test in `/docs`.

---

## Wednesday — Deeper domain task

**Tobba**
- Pick one template (from DB or seed) and trace full execution: route → ExecutionService → prompt builder → LLM → `TemplateExecution.output_data`.
- Add or adjust one field in a template/execution response (e.g. simple metadata or `generated_at`), or improve one validation message in templates.
- Use Cursor with @-mentions to relevant files; run app and test one execution.

**Gazia**
- Trace “Send message” flow: route → MessageService → conversation history → LLM → save message.
- Add one small improvement: e.g. optional request field (e.g. `include_metadata`) or a short docstring on how context is built (last N messages).
- Test in `/docs`: list chatbots → get or create conversation → send message.

---

## Thursday — Documentation

**Tobba**
- Write a short “Templates – How to” guide (3–5 bullets): e.g. how to add a new template field, how execution output is stored, where to change prompt for templates.
- Add 1–2 “Cursor prompts that worked” for template-related changes.
- Save as one page or section (e.g. “Templates – intern notes Week 1”).

**Gazia**
- Write a short “Chatbot – How to” guide: e.g. how to add a new chatbot endpoint, how conversation context is built, where LLM is called for messages.
- Add 1–2 “Cursor prompts that worked” for chatbot-related changes.
- Save as one page or section (e.g. “Chatbot – intern notes Week 1”).

---

## Friday — Consolidation and demo prep

**Tobba**
- Prepare a 3–5 minute demo: how templates work in this project and what was changed this week.
- Update “Templates map” if needed after the week’s work.

**Gazia**
- Prepare a 3–5 minute demo: how the chatbot flow works and what was changed this week.
- Update “Chatbot map” if needed after the week’s work.

---

## Reference

- PROJECT_GUIDE.md  
- DATABASE_GUIDE.md  
- SETUP.md  
