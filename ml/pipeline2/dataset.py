from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List

import pandas as pd

from ml.common.validation import validate_required_columns


REQUIRED_COLUMNS: List[str] = [
    "Subject",
    "Grade_Level",
    "Years_Exp",
    "Skills",
    "School_SES_Rating",
    "Student_Teacher_Ratio",
    "Regional_Priority_Skills",
    "Region",
]


@dataclass
class DatasetConfig:
    path: Path


def teacher_to_text(row: pd.Series) -> str:
    """
    Deterministically convert a teacher row into a textual profile.
    """
    economic_label = (
        "low income school" if float(row["School_SES_Rating"]) < 0.5 else "moderate income school"
    )

    class_label = (
        "small class size"
        if float(row["Student_Teacher_Ratio"]) < 25
        else "large class size"
    )

    return (
        f"Teaches {row['Subject']} to {row['Grade_Level']} grade. "
        f"Has {row['Years_Exp']} years of experience. "
        f"Expert in {row['Skills']}. "
        f"Works in a {economic_label} with {class_label}. "
        f"Regional Priority skills are :{row['Regional_Priority_Skills']}. "
        f"Region: {row['Region']}."
    )


def validate_required_columns_for_profile(df: pd.DataFrame) -> None:
    """
    Validate that the dataframe has all columns required to construct Teacher_profile.
    """
    validate_required_columns(df, REQUIRED_COLUMNS)


def generate_teacher_profile(df: pd.DataFrame) -> pd.DataFrame:
    """
    Ensure the dataframe has a Teacher_profile column.

    If Teacher_profile already exists, it is left untouched.
    If it is missing, it is generated deterministically from the required columns.
    """
    if "Teacher_profile" in df.columns:
        return df

    validate_required_columns_for_profile(df)

    # Generate Teacher_profile without mutating the original object passed in.
    df = df.copy()
    df["Teacher_profile"] = df.apply(teacher_to_text, axis=1)
    return df


def load_dataset(path: str | Path) -> pd.DataFrame:
    """
    Load the CSV dataset and ensure Teacher_profile is available in memory.

    The input CSV is never modified on disk by default.
    """
    csv_path = Path(path)
    df = pd.read_csv(csv_path)
    df = generate_teacher_profile(df)
    return df

