"""
Capability service for executing chatbot capabilities.
"""
import json
import re
from typing import Optional, Dict, Any, List
from uuid import UUID
from datetime import datetime, timezone

from sqlalchemy import and_, desc
from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.llm.router import ModelRouter
from app.llm.cache import ResponseCache
from app.llm.rate_limiter import RateLimiter
from app.llm.cost_tracker import CostTracker
from app.llm.config import llm_settings
from app.llm.schemas import LLMResponse
from app.llm.toon_handler import TOONHandler
from app.domains.chatbots.models import (
    Chatbot,
    ChatbotCapability,
    ChatbotConversation,
    ChatbotMessage,
    ChatbotModelUsage,
    UserCapabilityProgress,
)
from app.domains.chatbots.services.model_service import ChatbotModelService
from app.domains.subscriptions.services.credit_service import CreditService
from app.domains.subscriptions.exceptions import InsufficientCreditsError
from app.domains.subscriptions.feature_keys import CHATBOT_CAPABILITY

logger = get_logger(__name__)


class CapabilityService:
    """Service for executing chatbot capabilities."""

    def __init__(self, db: Session):
        self.db = db
        self.model_service = ChatbotModelService(db)
        
        # Initialize LLM infrastructure (reuse existing components)
        self.cache = ResponseCache(
            ttl_seconds=llm_settings.CACHE_TTL_SECONDS,
            redis_url=llm_settings.REDIS_URL
        ) if llm_settings.CACHE_ENABLED else None
        
        self.rate_limiter = RateLimiter(llm_settings) if llm_settings.RATE_LIMIT_ENABLED else None
        self.cost_tracker = CostTracker() if llm_settings.COST_TRACKING_ENABLED else None
        
        self.model_router = ModelRouter(
            config=llm_settings,
            cache=self.cache,
            rate_limiter=self.rate_limiter,
            cost_tracker=self.cost_tracker,
        )
        self.credit_service = CreditService(db)

        # Initialize TOON handler for efficient structured parsing
        self.toon_handler = TOONHandler()

    async def execute_capability(
        self,
        chatbot_id: UUID,
        capability_key: str,
        user_id: UUID,
        input_data: str,
        parameters: Optional[Dict[str, Any]] = None,
        save_result: bool = True,
        conversation_id: Optional[UUID] = None,
    ) -> Dict[str, Any]:
        """Execute a capability (e.g., text complexity analysis)."""
        # 1. Get chatbot
        chatbot = self.db.query(Chatbot).filter(Chatbot.id == chatbot_id).first()
        if not chatbot:
            raise ValueError("Chatbot not found")

        # 2. Get capability config
        capability = self.db.query(ChatbotCapability).filter(
            ChatbotCapability.chatbot_id == chatbot_id,
            ChatbotCapability.capability_key == capability_key,
            ChatbotCapability.is_active == True,
        ).first()

        if not capability:
            raise ValueError(f"Capability '{capability_key}' not found")

        # 3. Build system prompt from capability template
        system_prompt = capability.system_prompt_template
        if not system_prompt:
            system_prompt = f"You are an expert assistant. Execute the capability: {capability.capability_name}"

        # 4. Build user prompt with TOON-encoded input and parameters (for token efficiency)
        input_payload = {
            "input": input_data,
            "parameters": parameters or {},
        }
        
        # Try TOON encoding for token efficiency (70% reduction)
        try:
            toon_input = self.toon_handler.encode_input(input_payload)
            user_prompt = f"INPUT (TOON format):\n{toon_input}\n\nExecute the capability and return result in JSON format."
        except Exception as e:
            logger.warning(f"TOON encoding failed, using plain text: {e}")
            # Fallback to plain text
            user_prompt = input_data
            if parameters:
                params_str = ", ".join([f"{k}: {v}" for k, v in parameters.items()])
                user_prompt = f"{user_prompt}\n\nParameters: {params_str}"

        # 5. Get chatbot's model config
        model_config = self.model_service.get_model_config_for_chatbot(chatbot_id)
        if not model_config:
            raise ValueError("No models assigned to chatbot")

        credit_check = self.credit_service.check_balance(user_id)
        cost = self.credit_service.get_feature_cost(CHATBOT_CAPABILITY)
        if not credit_check.allowed or credit_check.balance < cost:
            raise InsufficientCreditsError(
                credit_check,
                cost,
                "You don't have enough credits to use this tool.",
            )

        # 6. Generate response using ModelRouter
        try:
            llm_response: LLMResponse = await self.model_router.generate(
                system_message=system_prompt,
                prompt=user_prompt,
                model_config=model_config,
            )

            # 7. Parse response using TOON with fallback to JSON and regex-based parsing
            result = self._parse_capability_response(
                llm_response.content, 
                capability.output_schema,
                capability_key=capability_key,  # Pass capability_key for type-specific parsing
                input_data=input_data  # Pass input_data for calculating word/sentence counts
            )

            # 8. Log model usage
            usage_log = ChatbotModelUsage(
                chatbot_id=chatbot_id,
                provider=llm_response.provider,
                model_name=llm_response.model_used,
                tokens_used=llm_response.token_usage.total if llm_response.token_usage else 0,
                cost_estimate=llm_response.cost_estimate,
                latency_ms=llm_response.latency_ms,
                success=True,
            )
            self.db.add(usage_log)

            # 9. Persist a traceable history item (chatbot_conversation) when requested.
            # Many specialized chatbot pages use capabilities (not chat streaming), but users still
            # expect these generations to show up in /history with a preview.
            persisted_conversation_id: Optional[UUID] = None
            if save_result:
                title = capability.capability_name or f"Capability · {capability_key}"
                meta_patch = {
                    "chatbot_slug": chatbot.slug,
                    "capability_key": capability_key,
                    "capability_name": capability.capability_name,
                    "parameters": parameters or {},
                }

                if conversation_id:
                    conv = (
                        self.db.query(ChatbotConversation)
                        .filter(
                            and_(
                                ChatbotConversation.id == conversation_id,
                                ChatbotConversation.user_id == user_id,
                                ChatbotConversation.chatbot_id == chatbot_id,
                            )
                        )
                        .first()
                    )
                    if not conv:
                        raise ValueError("Conversation not found")

                    conv.title = title
                    existing_meta = conv.conversation_metadata or {}
                    conv.conversation_metadata = {**existing_meta, **meta_patch}
                    conv.updated_at = datetime.now(timezone.utc)
                    usage_log.conversation_id = conv.id
                    persisted_conversation_id = conv.id

                    user_msg = (
                        self.db.query(ChatbotMessage)
                        .filter(
                            ChatbotMessage.conversation_id == conv.id,
                            ChatbotMessage.role == "user",
                        )
                        .order_by(desc(ChatbotMessage.created_at), desc(ChatbotMessage.id))
                        .first()
                    )
                    msg_meta = {"capability_key": capability_key}
                    if user_msg:
                        user_msg.content = input_data
                        user_msg.message_metadata = msg_meta
                    else:
                        self.db.add(
                            ChatbotMessage(
                                conversation_id=conv.id,
                                role="user",
                                content=input_data,
                                message_metadata=msg_meta,
                            )
                        )

                    assistant_msg = (
                        self.db.query(ChatbotMessage)
                        .filter(
                            ChatbotMessage.conversation_id == conv.id,
                            ChatbotMessage.role == "assistant",
                        )
                        .order_by(desc(ChatbotMessage.created_at), desc(ChatbotMessage.id))
                        .first()
                    )
                    assistant_content = json.dumps(result, indent=2, ensure_ascii=False)
                    if assistant_msg:
                        assistant_msg.content = assistant_content
                        assistant_msg.message_metadata = msg_meta
                    else:
                        self.db.add(
                            ChatbotMessage(
                                conversation_id=conv.id,
                                role="assistant",
                                content=assistant_content,
                                message_metadata=msg_meta,
                            )
                        )
                else:
                    conv = ChatbotConversation(
                        chatbot_id=chatbot_id,
                        user_id=user_id,
                        tenant_id=None,
                        title=title,
                        conversation_metadata=meta_patch,
                    )
                    self.db.add(conv)
                    self.db.flush()  # get conv.id without committing

                    usage_log.conversation_id = conv.id
                    persisted_conversation_id = conv.id

                    self.db.add(
                        ChatbotMessage(
                            conversation_id=conv.id,
                            role="user",
                            content=input_data,
                            message_metadata={"capability_key": capability_key},
                        )
                    )
                    self.db.add(
                        ChatbotMessage(
                            conversation_id=conv.id,
                            role="assistant",
                            content=json.dumps(result, indent=2, ensure_ascii=False),
                            message_metadata={"capability_key": capability_key},
                        )
                    )

            # 10. Update user progress if save_result
            if save_result:
                self._update_user_progress(user_id, capability.id)

            self.db.commit()

            self.credit_service.charge(
                user_id=user_id,
                feature_key=CHATBOT_CAPABILITY,
                llm_response=llm_response,
                description=f"Capability · {capability_key}",
            )

            out: Dict[str, Any] = {
                "result": result,
                "metadata": {
                    "processing_time_ms": llm_response.latency_ms,
                    "tokens_used": llm_response.token_usage.total if llm_response.token_usage else 0,
                    "model_used": llm_response.model_used,
                    "capability_version": "1.0",
                },
                "usage_id": usage_log.id,
                "progress_update": self._get_progress_update(user_id, capability.id),
            }
            if save_result and persisted_conversation_id is not None:
                out["conversation_id"] = persisted_conversation_id
            return out

        except InsufficientCreditsError:
            raise
        except Exception as e:
            logger.error(f"Error executing capability: {e}", exc_info=True)
            # Log failure
            usage_log = ChatbotModelUsage(
                chatbot_id=chatbot_id,
                success=False,
                error_message=str(e),
            )
            self.db.add(usage_log)
            self.db.commit()
            raise

    def _parse_capability_response(
        self,
        content: str,
        output_schema: Optional[Dict[str, Any]],
        capability_key: Optional[str] = None,
        input_data: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Parse capability response using TOON with JSON fallback and type-specific parsing."""
        logger.info(f"Parsing capability response for key: {capability_key}, content length: {len(content)}")
        
        # Try TOON parsing first (more efficient, 70% token reduction)
        try:
            parsed = self.toon_handler.parse_output(content, schema=str(output_schema) if output_schema else None)
            if parsed and isinstance(parsed, dict):
                logger.info(f"TOON parsing succeeded. Keys: {list(parsed.keys())}")
                # Transform TOON parsed response as well
                if capability_key == "text_complexity":
                    return self._transform_text_complexity_response(parsed, input_data)
                elif capability_key == "guided_reading":
                    return self._transform_guided_reading_response(parsed)
                elif capability_key == "writing_feedback":
                    return self._transform_writing_feedback_response(parsed)
                return parsed
        except Exception as toon_error:
            logger.debug(f"TOON parsing failed, trying JSON: {toon_error}")
        
        # Try JSON parsing
        try:
            # Clean markdown fences if present
            cleaned = content.strip()
            if cleaned.startswith("```"):
                lines = cleaned.split("\n")
                if lines[0].startswith("```"):
                    lines = lines[1:]
                if lines and lines[-1].strip() == "```":
                    lines = lines[:-1]
                cleaned = "\n".join(lines).strip()
            
            # Try to parse the entire cleaned string as JSON first
            try:
                parsed = json.loads(cleaned)
                if isinstance(parsed, dict):
                    logger.info(f"JSON parsing succeeded (full string). Keys: {list(parsed.keys())}")
                    # Transform parsed JSON to frontend-expected format based on capability type
                    if capability_key == "text_complexity":
                        transformed = self._transform_text_complexity_response(parsed, input_data)
                        logger.info(f"Transformed text_complexity response. Final keys: {list(transformed.keys())}")
                        return transformed
                    elif capability_key == "guided_reading":
                        return self._transform_guided_reading_response(parsed)
                    elif capability_key == "writing_feedback":
                        return self._transform_writing_feedback_response(parsed)
                    return parsed
            except json.JSONDecodeError:
                # If full string parse fails, try to extract JSON with regex
                pass
            
            # Extract JSON if wrapped (fallback for text with JSON embedded)
            json_match = re.search(r'\{.*\}', cleaned, re.DOTALL)
            if json_match:
                try:
                    parsed = json.loads(json_match.group())
                    if isinstance(parsed, dict):
                        logger.info(f"JSON parsing succeeded (regex extract). Keys: {list(parsed.keys())}")
                        # Transform parsed JSON to frontend-expected format based on capability type
                        if capability_key == "text_complexity":
                            transformed = self._transform_text_complexity_response(parsed, input_data)
                            logger.info(f"Transformed text_complexity response. Final keys: {list(transformed.keys())}")
                            return transformed
                        elif capability_key == "guided_reading":
                            return self._transform_guided_reading_response(parsed)
                        elif capability_key == "writing_feedback":
                            return self._transform_writing_feedback_response(parsed)
                        return parsed
                except json.JSONDecodeError:
                    pass
        except Exception as json_error:
            logger.warning(f"JSON parsing failed: {json_error}")
        
        # Fallback: type-specific regex parsing
        if capability_key == "text_complexity":
            logger.info("Using fallback regex parsing for text_complexity")
            return self._parse_text_complexity_response(content, input_data)
        elif capability_key == "guided_reading":
            return self._parse_guided_reading_response(content)
        elif capability_key == "writing_feedback":
            return self._parse_writing_feedback_response(content)
        
        # Default: return as content
        logger.warning(f"No parsing method worked, returning content as dict")
        return {"content": content}

    def _update_user_progress(self, user_id: UUID, capability_id: UUID):
        """Update user's progress for a capability."""
        progress = self.db.query(UserCapabilityProgress).filter(
            UserCapabilityProgress.user_id == user_id,
            UserCapabilityProgress.capability_id == capability_id,
        ).first()

        if not progress:
            progress = UserCapabilityProgress(
                user_id=user_id,
                capability_id=capability_id,
                times_used=0,
            )
            self.db.add(progress)

        progress.times_used += 1
        progress.last_used_at = datetime.now(timezone.utc)

        # Update mastery level based on usage
        if progress.times_used < 5:
            progress.mastery_level = "beginner"
        elif progress.times_used < 20:
            progress.mastery_level = "intermediate"
        else:
            progress.mastery_level = "advanced"

    def _get_progress_update(self, user_id: UUID, capability_id: UUID) -> Dict[str, Any]:
        """Get progress update for user capability."""
        progress = self.db.query(UserCapabilityProgress).filter(
            UserCapabilityProgress.user_id == user_id,
            UserCapabilityProgress.capability_id == capability_id,
        ).first()

        if not progress:
            return {
                "times_used": 0,
                "mastery_level": None,
            }

        return {
            "times_used": progress.times_used,
            "mastery_level": progress.mastery_level,
        }

    # Transformation methods - convert LLM response format to frontend-expected format
    def _transform_text_complexity_response(self, llm_response: Dict[str, Any], input_data: Optional[str] = None) -> Dict[str, Any]:
        """Transform LLM response to frontend-expected format for text complexity."""
        # Check if already in expected format
        if "readingLevel" in llm_response and "complexity" in llm_response and "wordCount" in llm_response:
            logger.debug("Response already in expected format, returning as-is")
            return llm_response
        
        logger.info(f"Transforming text complexity response. Keys: {list(llm_response.keys())}")
        
        # Extract from LLM's actual response structure
        readability_scores = llm_response.get("readability_scores", {})
        complexity_factors = llm_response.get("complexity_factors", {})
        recommended_grade = llm_response.get("recommended_grade_instructional_level", "")
        
        logger.debug(f"Readability scores: {readability_scores}, Recommended grade: {recommended_grade}")
        
        # Extract readability score (use Flesch-Kincaid Reading Ease if available)
        readability_score = readability_scores.get("Flesch_Kincaid_Reading_Ease", 75)
        if not isinstance(readability_score, (int, float)):
            readability_score = 75
        
        # Extract grade level from recommended_grade_instructional_level - handle ranges like "Grade 1-2"
        grade_level = "5"
        if recommended_grade:
            # Try to extract from "Grade 1-2" format (take first number)
            grade_range_match = re.search(r'Grade\s*(\d+)[\s-]*(\d+)?', str(recommended_grade), re.IGNORECASE)
            if grade_range_match:
                grade_level = grade_range_match.group(1)  # Take the first number
            else:
                # Fallback: try to extract any number
                num_match = re.search(r'(\d+)', str(recommended_grade))
                if num_match:
                    grade_level = num_match.group(1)
        
        # Use Flesch-Kincaid Grade Level if available for more accurate grade level
        fk_grade = readability_scores.get("Flesch_Kincaid_Grade_Level")
        if fk_grade and isinstance(fk_grade, (int, float)):
            # Round to nearest whole number
            grade_level = str(int(round(float(fk_grade))))
            logger.debug(f"Using Flesch-Kincaid grade level: {grade_level}")
        
        # Determine reading level from grade
        grade_num = int(grade_level) if grade_level.isdigit() else 5
        if grade_num <= 2:
            reading_level = "Beginner"
        elif grade_num <= 6:
            reading_level = "Intermediate"
        else:
            reading_level = "Advanced"
        
        # Determine complexity from vocabulary description
        vocab_text = str(complexity_factors.get("vocabulary", "")).lower()
        if "simple" in vocab_text or "basic" in vocab_text:
            complexity = "Simple"
        elif "complex" in vocab_text or "advanced" in vocab_text or "sophisticated" in vocab_text:
            complexity = "Complex"
        else:
            complexity = "Moderate"
        
        # Extract vocabulary level (use recommended_grade directly if it's already in correct format)
        vocabulary_level = recommended_grade if recommended_grade else f"Grade {max(1, grade_num - 2)}-{grade_num + 2}"
        
        # Calculate word and sentence counts from input text if available
        word_count = 0
        sentence_count = 0
        avg_words_per_sentence = 0
        if input_data:
            words = re.findall(r'\b\w+\b', input_data)
            word_count = len(words)
            sentences = re.findall(r'[.!?]+', input_data)
            sentence_count = len(sentences) if sentences else 1
            # If no sentence punctuation found, treat entire text as one sentence
            if sentence_count == 0:
                sentence_count = 1
            avg_words_per_sentence = round(word_count / sentence_count) if sentence_count > 0 else word_count
            logger.debug(f"Calculated from input: wordCount={word_count}, sentenceCount={sentence_count}")
        
        result = {
            "readingLevel": reading_level,
            "complexity": complexity,
            "wordCount": word_count,
            "sentenceCount": sentence_count,
            "avgWordsPerSentence": avg_words_per_sentence,
            "vocabularyLevel": vocabulary_level,
            "gradeLevel": grade_level,
            "readabilityScore": int(readability_score),
        }
        
        logger.info(f"Transformed result: {result}")
        return result
    
    def _transform_guided_reading_response(self, llm_response: Dict[str, Any]) -> Dict[str, Any]:
        """Transform LLM response to frontend-expected format for guided reading."""
        # Check if already in expected format
        if "beforeReading" in llm_response and "duringReading" in llm_response:
            return llm_response
        
        # Transform from LLM structure if different
        return {
            "beforeReading": llm_response.get("beforeReading", []),
            "duringReading": llm_response.get("duringReading", []),
            "afterReading": llm_response.get("afterReading", []),
            "vocabulary": llm_response.get("vocabulary", []),
            "comprehensionQuestions": llm_response.get("comprehensionQuestions", {
                "literal": [],
                "inferential": [],
                "evaluative": [],
            }),
        }
    
    def _transform_writing_feedback_response(self, llm_response: Dict[str, Any]) -> Dict[str, Any]:
        """Transform LLM response to frontend-expected format for writing feedback."""
        # Check if already in expected format
        if "strengths" in llm_response and "rubricScore" in llm_response:
            return llm_response
        
        # Transform from LLM structure if different
        return {
            "strengths": llm_response.get("strengths", []),
            "areasForImprovement": llm_response.get("areasForImprovement", []),
            "suggestions": llm_response.get("suggestions", []),
            "rubricScore": llm_response.get("rubricScore", {
                "content": 3,
                "organization": 3,
                "language": 3,
                "conventions": 3,
            }),
        }
    
    # Type-specific parsing methods
    def _parse_text_complexity_response(self, content: str, input_data: Optional[str] = None) -> Dict[str, Any]:
        """Parse text complexity analysis response."""
        # Try to extract JSON from response
        json_match = re.search(r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}', content, re.DOTALL)
        if json_match:
            try:
                return json.loads(json_match.group())
            except:
                pass
        
        # Parse from text if JSON not found - use input_data if available for word/sentence counts
        text_to_analyze = input_data if input_data else content
        words = re.findall(r'\b\w+\b', text_to_analyze)
        word_count = len(words)
        sentences = len(re.findall(r'[.!?]+', text_to_analyze))
        
        # Extract readability score
        readability_match = re.search(r'(\d+(?:\.\d+)?)/?\s*100', content)
        readability_score = int(float(readability_match.group(1))) if readability_match else 75
        
        # Extract grade level
        grade_match = re.search(r'grade\s*(\d+)', content, re.IGNORECASE)
        grade_level = grade_match.group(1) if grade_match else "5"
        
        return {
            "readingLevel": self._extract_reading_level(content),
            "complexity": self._extract_complexity(content),
            "wordCount": word_count,
            "sentenceCount": sentences if sentences > 0 else 1,
            "avgWordsPerSentence": round(word_count / sentences) if sentences > 0 else word_count,
            "vocabularyLevel": self._extract_vocabulary_level(content),
            "gradeLevel": grade_level,
            "readabilityScore": readability_score,
        }

    def _extract_reading_level(self, text: str) -> str:
        """Extract reading level from text."""
        text_lower = text.lower()
        if "beginner" in text_lower or "elementary" in text_lower:
            return "Beginner"
        elif "advanced" in text_lower or "expert" in text_lower:
            return "Advanced"
        return "Intermediate"

    def _extract_complexity(self, text: str) -> str:
        """Extract complexity from text."""
        text_lower = text.lower()
        if "simple" in text_lower or "low" in text_lower or "easy" in text_lower:
            return "Simple"
        elif "complex" in text_lower or "high" in text_lower or "difficult" in text_lower:
            return "Complex"
        return "Moderate"

    def _extract_vocabulary_level(self, text: str) -> str:
        """Extract vocabulary level."""
        match = re.search(r'grade\s*(\d+)[\s-]*(\d+)?', text, re.IGNORECASE)
        if match:
            grade1 = match.group(1)
            grade2 = match.group(2) or str(int(grade1) + 2)
            return f"Grade {grade1}-{grade2}"
        return "Grade 4-6"

    def _parse_guided_reading_response(self, content: str) -> Dict[str, Any]:
        """Parse guided reading strategies response."""
        return {
            "beforeReading": self._extract_list_items(content, ["before", "pre-reading", "prereading"]),
            "duringReading": self._extract_list_items(content, ["during", "while reading"]),
            "afterReading": self._extract_list_items(content, ["after", "post-reading", "postreading"]),
            "vocabulary": self._extract_list_items(content, ["vocabulary", "vocab", "words"]),
            "comprehensionQuestions": {
                "literal": self._extract_questions(content, ["literal", "factual"]),
                "inferential": self._extract_questions(content, ["inferential", "inference", "imply"]),
                "evaluative": self._extract_questions(content, ["evaluative", "evaluation", "judge"]),
            },
        }

    def _extract_list_items(self, text: str, keywords: List[str]) -> List[str]:
        """Extract list items near keywords."""
        items = []
        text_lower = text.lower()
        
        for keyword in keywords:
            # Find section with keyword
            pattern = rf'{keyword}.*?:(.*?)(?=\n\s*[A-Z][a-z]+:|$)'
            match = re.search(pattern, text, re.IGNORECASE | re.DOTALL)
            if match:
                section = match.group(1)
                # Extract bullet points
                bullets = re.findall(r'[-•*]\s*(.+?)(?=\n|$)', section)
                items.extend([b.strip() for b in bullets if b.strip()])
        
        # Remove duplicates and limit
        seen = set()
        unique_items = []
        for item in items:
            if item not in seen and len(item) > 5:  # Minimum length
                seen.add(item)
                unique_items.append(item)
        
        return unique_items[:10]  # Max 10 items

    def _extract_questions(self, text: str, keywords: List[str]) -> List[str]:
        """Extract questions of specific type."""
        all_questions = re.findall(r'([^.!?]+\?)', text)
        
        # Filter by keywords in context (simplified)
        filtered = []
        for q in all_questions:
            q_lower = q.lower()
            if any(kw in q_lower for kw in keywords):
                filtered.append(q.strip())
        
        return filtered[:5] if filtered else all_questions[:5]

    def _parse_writing_feedback_response(self, content: str) -> Dict[str, Any]:
        """Parse writing feedback response."""
        return {
            "strengths": self._extract_list_items(content, ["strength", "strong", "good"]),
            "areasForImprovement": self._extract_list_items(content, ["improvement", "weakness", "weak", "area for", "need"]),
            "suggestions": self._extract_list_items(content, ["suggestion", "recommend", "should", "could"]),
            "rubricScore": {
                "content": self._extract_rubric_score(content, ["content", "ideas"]),
                "organization": self._extract_rubric_score(content, ["organization", "structure"]),
                "language": self._extract_rubric_score(content, ["language", "word choice", "vocabulary"]),
                "conventions": self._extract_rubric_score(content, ["convention", "grammar", "spelling", "punctuation"]),
            },
        }

    def _extract_rubric_score(self, text: str, keywords: List[str]) -> int:
        """Extract rubric score for category."""
        for keyword in keywords:
            pattern = rf'{keyword}.*?(\d+(?:\.\d+)?)/?\s*5'
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                score = int(float(match.group(1)))
                return min(max(score, 1), 5)  # Clamp between 1-5
        
        # Default: try to find any score
        score_match = re.search(r'(\d+(?:\.\d+)?)/?\s*5', text, re.IGNORECASE)
        if score_match:
            return min(max(int(float(score_match.group(1))), 1), 5)
        
        return 3  # Default score
