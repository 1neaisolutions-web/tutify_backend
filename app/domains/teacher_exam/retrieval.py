"""Exam retrieval — delegates to shared quiz retrieval implementation."""
from app.domains.teacher_quiz.retrieval import QuizRetrievalService as ExamRetrievalService
from app.domains.teacher_quiz.retrieval import RetrievalResult

__all__ = ["ExamRetrievalService", "RetrievalResult"]
