"""
Maps API surfaces to feature_credit_costs.feature_key (seeded in alembic).

Chat stream / sync — chatbot_message (+ chatbot_message_search for web search).
Templates — template_generate.
Chatbot capabilities — chatbot_capability.
PixGen — pixgen_image.
YouTube quiz — quiz_generate.
Teacher tools — quiz_generate, assignment_generate, worksheet_generate, exam_generate
  and partial regenerate keys (quiz_regenerate_question, etc.).
Content factory gap-fill — content_gap_fill.
"""

# Re-export string constants for call sites
CHATBOT_MESSAGE = "chatbot_message"
CHATBOT_MESSAGE_SEARCH = "chatbot_message_search"
TEMPLATE_GENERATE = "template_generate"
CHATBOT_CAPABILITY = "chatbot_capability"
PIXGEN_IMAGE = "pixgen_image"
QUIZ_GENERATE = "quiz_generate"
ASSIGNMENT_GENERATE = "assignment_generate"
WORKSHEET_GENERATE = "worksheet_generate"
EXAM_GENERATE = "exam_generate"
CONTENT_GAP_FILL = "content_gap_fill"

QUIZ_REGENERATE_QUESTION = "quiz_regenerate_question"
ASSIGNMENT_REGENERATE_TOPIC = "assignment_regenerate_topic"
ASSIGNMENT_REGENERATE_LINE = "assignment_regenerate_line"
WORKSHEET_REGENERATE_BLOCK = "worksheet_regenerate_block"
EXAM_REGENERATE_MCQ = "exam_regenerate_mcq"
EXAM_REGENERATE_SHORT = "exam_regenerate_short"
EXAM_REGENERATE_LONG = "exam_regenerate_long"
