"""Pydantic models for video library file and API responses."""

from __future__ import annotations

from typing import List

from pydantic import BaseModel, Field


class LibraryVideo(BaseModel):
    id: str
    title: str
    youtubeUrl: str
    gradeBand: str
    subject: str
    duration: str
    tags: List[str]
    transcript: bool
    bestQuizType: str


class LibraryChannel(BaseModel):
    id: str
    name: str
    focus: str
    gradeBand: str
    videos: List[LibraryVideo] = Field(default_factory=list)


class LibrarySubjectBucket(BaseModel):
    channels: List[LibraryChannel] = Field(default_factory=list)


class VideoLibraryFile(BaseModel):
    """Root shape of data/video_library.json."""

    subjects: dict[str, LibrarySubjectBucket]


class RecommendationVideo(BaseModel):
    id: str
    title: str
    youtubeUrl: str
    gradeBand: str
    subject: str
    duration: str
    tags: List[str]
    transcript: bool
    bestQuizType: str


class RecommendationChannel(BaseModel):
    id: str
    name: str
    focus: str
    gradeBand: str
    videos: List[RecommendationVideo] = Field(default_factory=list)


class RecommendationsResponse(BaseModel):
    channels: List[RecommendationChannel]


class VideoDetailResponse(BaseModel):
    id: str
    title: str
    youtubeUrl: str
    gradeBand: str
    subject: str
    duration: str
    tags: List[str]
    transcript: bool
    bestQuizType: str
    channelId: str
    channelName: str
    librarySubjectKey: str
