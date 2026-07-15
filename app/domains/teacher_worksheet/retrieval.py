"""Worksheet retrieval — delegates to shared quiz retrieval implementation."""
from app.domains.teacher_quiz.retrieval import QuizRetrievalService as WorksheetRetrievalService
from app.domains.teacher_quiz.retrieval import RetrievalResult as WorksheetRetrievalResult

__all__ = ["WorksheetRetrievalService", "WorksheetRetrievalResult"]
