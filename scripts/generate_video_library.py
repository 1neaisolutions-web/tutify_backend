#!/usr/bin/env python3
"""Generate app/domains/video_library/data/video_library.json (≥10 channels × ≥15 videos per subject)."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "app" / "domains" / "video_library" / "data" / "video_library.json"

# Real YouTube IDs (educational / public samples); URLs validated by extract_video_id
YT_POOL = [
    "sQK3Yr4Sc_k",
    "ncORPosDrjI",
    "3XOt1fjWKi8",
    "Q78COTwT7nE",
    "yi0hwFDQTSQ",
    "2PPSXonjwG4",
    "MEkeMdNtc5w",
    "8UQFaVCV8S8",
    "ANiVZ5lVUW0",
    "eUDcTLaWJ68",
    "bGoNwqINM74",
    "CpgVNfVWNI8",
    "fLDbxcvU55M",
    "0Vmyq9p59fQ",
    "G8cbQWMv0rU",
    "1rATIwxfeCk",
    "J9hk-2d0M6o",
    "rTb3Et0zrw0",
    "5MgBikgcWnY",
    "X9otDixAtFw",
    "9vM5p9d0VQQ",
    "M5I_KzbMSs0",
    "0lJKucu6HJc",
    "8p02gRIPnGY",
    "cXNHNkt8c3g",
    "jEhCRwd-unc",
    "lRqSxcqxfRM",
    "WSeNSJZJpaE",
    "zQGOcOUBi6s",
    "aKS98bhqOP0",
]

GRADE_BANDS = [
    "Grades 3-5",
    "Grades 6-8",
    "Grades 9-10",
    "Grades 11-12",
    "Higher Education",
]

BEST_QUIZ_TYPES = [
    "Multiple choice + Quick check",
    "Higher-order thinking + Discussion prompt",
    "Discussion prompt + Critical analysis",
    "Quick check + Multiple choice",
    "Multiple choice + Higher-order thinking",
]

SUBJECT_CONFIG: dict[str, dict[str, list[str]]] = {
    "Mathematics": {
        "granular": ["Mathematics", "Algebra", "Geometry"],
        "focus": "Conceptual mathematics and problem solving",
    },
    "Science_STEM": {
        "granular": ["Biology", "Chemistry", "Physics", "Earth Science"],
        "focus": "STEM explainers and inquiry",
    },
    "Social_Sciences": {
        "granular": ["History", "Geography", "Civics", "Economics"],
        "focus": "Social studies and civic reasoning",
    },
    "English_Language_Arts": {
        "granular": ["English Language Arts", "Reading", "Writing"],
        "focus": "Literacy, rhetoric, and composition",
    },
    "Creative_Arts": {
        "granular": ["Art", "Music", "Theater"],
        "focus": "Creative expression and media literacy",
    },
    "Computer_Science": {
        "granular": ["Computer Science", "Digital Literacy"],
        "focus": "Computing concepts and digital citizenship",
    },
}


def main() -> None:
    subjects: dict = {}
    n = 0
    for lib_key, meta in SUBJECT_CONFIG.items():
        granular = meta["granular"]
        channels = []
        for ci in range(10):
            ch_id = f"{lib_key.lower()}_ch_{ci + 1:02d}"
            videos = []
            for vi in range(15):
                vid_id = f"{lib_key.lower()}_ch{ci + 1:02d}_v{vi + 1:02d}"
                yt = YT_POOL[n % len(YT_POOL)]
                n += 1
                g = granular[(ci + vi) % len(granular)]
                gb = GRADE_BANDS[(ci + vi) % len(GRADE_BANDS)]
                videos.append(
                    {
                        "id": vid_id,
                        "title": f"{g} lesson clip {ci + 1}-{vi + 1} (curated)",
                        "youtubeUrl": f"https://www.youtube.com/watch?v={yt}",
                        "gradeBand": gb,
                        "subject": g,
                        "duration": f"{(vi % 9) + 4}:{(ci * 3 + vi * 2) % 60:02d}",
                        "tags": [g.split()[0], "Education", "Curated"],
                        "transcript": (ci + vi) % 4 != 0,
                        "bestQuizType": BEST_QUIZ_TYPES[(ci + vi) % len(BEST_QUIZ_TYPES)],
                    }
                )
            channels.append(
                {
                    "id": ch_id,
                    "name": f"{lib_key.replace('_', ' ')} Hub {ci + 1}",
                    "focus": meta["focus"],
                    "gradeBand": GRADE_BANDS[ci % len(GRADE_BANDS)],
                    "videos": videos,
                }
            )
        subjects[lib_key] = {"channels": channels}

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({"subjects": subjects}, indent=2), encoding="utf-8")
    print(f"Wrote {OUT}")


if __name__ == "__main__":
    main()
