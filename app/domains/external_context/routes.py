"""
Metadata and user profile (teaching context) API routes.
"""
from fastapi import APIRouter, Depends, HTTPException, status, Query

from app.domains.external_context.metadata_data import (
    COUNTRIES,
    get_regions_for_country,
    SUBJECTS,
    CURRICULUM_FRAMEWORKS,
    GRADE_BANDS,
    US_GRADES,
    SCHOOL_TYPES,
    LANGUAGES,
    YEARS_EXPERIENCE,
)

router = APIRouter(prefix="/api/v1", tags=["metadata"])


@router.get("/metadata/countries")
async def get_countries():
    """Return list of countries for dropdown. Static list for now."""
    return COUNTRIES


@router.get("/metadata/regions")
async def get_regions(country: str = Query(..., description="Country code")):
    """Return regions/states for the given country."""
    regions = get_regions_for_country(country.strip())
    return regions


@router.get("/metadata/subjects")
async def get_subjects():
    """Return list of subjects for multi-select."""
    return SUBJECTS


@router.get("/metadata/curriculums")
async def get_curriculums():
    """Return curriculum framework options."""
    return CURRICULUM_FRAMEWORKS


@router.get("/metadata/grade-bands")
async def get_grade_bands():
    """Return grade band options."""
    return GRADE_BANDS


@router.get("/metadata/grades")
async def get_grades():
    """Return US K-12 individual grade options (Kindergarten, Grade 1–12)."""
    return US_GRADES


@router.get("/metadata/school-types")
async def get_school_types():
    """Return school type options."""
    return SCHOOL_TYPES


@router.get("/metadata/languages")
async def get_languages():
    """Return preferred teaching language options."""
    return LANGUAGES


@router.get("/metadata/years-experience")
async def get_years_experience():
    """Return years of experience options."""
    return YEARS_EXPERIENCE
