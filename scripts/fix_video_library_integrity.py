#!/usr/bin/env python3
"""
One-shot data integrity fixer for app/domains/video_library/data/video_library.json.

Hard constraints:
- Data correction only (subject bucket placement + youtubeUrl cleanup)
- Preserve schema shape: subjects -> channels[] -> videos[]
- No changes to backend/frontend logic or mapping modules

Pipeline (single-run, no recursive loops):
load once -> index once -> oEmbed validate unique URLs once -> mutate once -> validate invariants -> write once
"""

from __future__ import annotations

import json
import re
import sys
import urllib.parse
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

import requests


ROOT = Path(__file__).resolve().parents[1]
DATA_PATH = ROOT / "app" / "domains" / "video_library" / "data" / "video_library.json"

CANON_RE = re.compile(r"^https://www\.youtube\.com/watch\?v=([A-Za-z0-9_-]{11})$")
EXTRACT_ID_RE = re.compile(r"[?&]v=([A-Za-z0-9_-]{11})")

MAX_WORKERS = 25
TIMEOUT_S = 10

LIB_KEYS = (
    "Mathematics",
    "Science_STEM",
    "Social_Sciences",
    "English_Language_Arts",
    "Creative_Arts",
    "Computer_Science",
)


def _norm_tokenize(text: str) -> set[str]:
    s = (text or "").lower()
    s = re.sub(r"[^a-z0-9]+", " ", s)
    toks = {t for t in s.split() if len(t) >= 3}
    return toks


def _parse_duration_to_seconds(d: str) -> Optional[int]:
    # Accepts "m:ss" or "mm:ss" or "h:mm:ss" (rare).
    raw = (d or "").strip()
    if not raw:
        return None
    parts = raw.split(":")
    if not all(p.isdigit() for p in parts):
        return None
    nums = [int(p) for p in parts]
    if len(nums) == 2:
        m, s = nums
        return m * 60 + s
    if len(nums) == 3:
        h, m, s = nums
        return h * 3600 + m * 60 + s
    return None


def extract_video_id(url: str) -> Optional[str]:
    if not url:
        return None
    m = CANON_RE.match(url.strip())
    if m:
        return m.group(1)
    m2 = EXTRACT_ID_RE.search(url)
    if m2:
        return m2.group(1)
    return None


def canonical_url(video_id: str) -> str:
    return f"https://www.youtube.com/watch?v={video_id}"


def oembed_url_for(video_url: str) -> str:
    return "https://www.youtube.com/oembed?format=json&url=" + urllib.parse.quote(video_url, safe="")


def oembed_fetch(video_url: str, session: requests.Session) -> tuple[bool, dict[str, Any] | None]:
    r = session.get(oembed_url_for(video_url), timeout=TIMEOUT_S)
    if r.status_code != 200:
        return False, None
    try:
        return True, r.json()
    except Exception:
        return True, None


def classify_from_oembed(title: str, author: str) -> tuple[str, str]:
    """
    URL-truth classification using oEmbed (title + author_name).
    Returns: (top_level_bucket_key, granular_subject_value)

    Granular values are restricted to those in app/domains/video_library/mapping.py.
    """
    bag = _norm_tokenize(f"{title or ''} {author or ''}")

    def has_any(words: set[str]) -> bool:
        return bool(bag & words)

    # Creative Arts
    if has_any(
        {
            "music",
            "guitar",
            "piano",
            "rhythm",
            "melody",
            "harmony",
            "chord",
            "chords",
            "song",
            "songs",
            "theory",
            "art",
            "drawing",
            "painting",
            "design",
            "theater",
            "theatre",
            "dance",
        }
    ):
        if has_any({"theater", "theatre"}):
            return "Creative_Arts", "Theater"
        if has_any({"music", "guitar", "piano", "rhythm", "melody", "harmony", "chord", "chords", "theory", "song"}):
            return "Creative_Arts", "Music"
        return "Creative_Arts", "Art"

    # English Language Arts
    if has_any(
        {
            "grammar",
            "writing",
            "reading",
            "literature",
            "essay",
            "poetry",
            "novel",
            "sentence",
            "paragraph",
            "comprehension",
            "phonics",
            "spelling",
        }
    ):
        if has_any({"writing", "essay", "paragraph"}):
            return "English_Language_Arts", "Writing"
        if has_any({"reading", "comprehension", "phonics"}):
            return "English_Language_Arts", "Reading"
        return "English_Language_Arts", "English Language Arts"

    # Social Sciences
    if has_any(
        {
            "history",
            "geography",
            "civics",
            "economics",
            "government",
            "constitution",
            "democracy",
            "map",
            "maps",
            "trade",
            "market",
            "supply",
            "demand",
        }
    ):
        if has_any({"economics", "market", "trade", "supply", "demand"}):
            return "Social_Sciences", "Economics"
        if has_any({"geography", "map", "maps"}):
            return "Social_Sciences", "Geography"
        if has_any({"civics", "government", "constitution", "democracy"}):
            return "Social_Sciences", "Civics"
        return "Social_Sciences", "History"

    # Computer Science
    if has_any(
        {
            "programming",
            "coding",
            "algorithm",
            "algorithms",
            "computer",
            "software",
            "python",
            "javascript",
            "java",
            "html",
            "css",
            "internet",
            "digital",
            "cyber",
        }
    ):
        if has_any({"internet", "digital", "cyber"}):
            return "Computer_Science", "Digital Literacy"
        return "Computer_Science", "Computer Science"

    # Science & STEM
    if has_any(
        {
            "biology",
            "chemistry",
            "physics",
            "photosynthesis",
            "cell",
            "cells",
            "earth",
            "geology",
            "ecology",
            "atom",
            "atoms",
            "molecule",
            "molecules",
            "planet",
            "planets",
            "solar",
            "system",
            "volcano",
            "weather",
        }
    ):
        if has_any({"biology", "cell", "cells", "photosynthesis", "ecology"}):
            return "Science_STEM", "Biology"
        if has_any({"chemistry", "atom", "atoms", "molecule", "molecules"}):
            return "Science_STEM", "Chemistry"
        if has_any({"physics"}):
            return "Science_STEM", "Physics"
        return "Science_STEM", "Earth Science"

    # Mathematics (only when strongly indicated)
    if has_any(
        {
            "math",
            "mathematics",
            "algebra",
            "geometry",
            "calculus",
            "equation",
            "equations",
            "fraction",
            "fractions",
            "decimal",
            "decimals",
            "ratio",
            "proportion",
            "percent",
            "percentage",
        }
    ):
        if has_any({"algebra", "equation", "equations"}):
            return "Mathematics", "Algebra"
        if has_any({"geometry"}):
            return "Mathematics", "Geometry"
        return "Mathematics", "Mathematics"

    # Conservative fallback
    return "Science_STEM", "Earth Science"


@dataclass(frozen=True)
class VideoRef:
    bucket: str
    ch_idx: int
    v_idx: int


def main() -> int:
    if not DATA_PATH.is_file():
        print(f"ERROR: Missing {DATA_PATH}", file=sys.stderr)
        return 2

    raw = DATA_PATH.read_text(encoding="utf-8")
    data: Dict[str, Any] = json.loads(raw)
    subjects = data.get("subjects")
    if not isinstance(subjects, dict):
        raise ValueError("Invalid schema: expected top-level 'subjects' object")

    # ---- 2) Index once (read-only) ----
    noncanonical: List[VideoRef] = []
    no_video_id: List[VideoRef] = []
    canonical_to_refs: Dict[str, List[VideoRef]] = defaultdict(list)
    ref_to_canonical: Dict[VideoRef, Optional[str]] = {}

    total_videos = 0
    for bucket_key, bucket in subjects.items():
        if not isinstance(bucket, dict) or "channels" not in bucket:
            raise ValueError(f"Invalid bucket shape at {bucket_key}")
        channels = bucket.get("channels") or []
        for ch_idx, ch in enumerate(channels):
            videos = ch.get("videos") or []
            for v_idx, v in enumerate(videos):
                total_videos += 1
                ref = VideoRef(bucket=bucket_key, ch_idx=ch_idx, v_idx=v_idx)

                yt_raw = str(v.get("youtubeUrl") or "")
                vid = extract_video_id(yt_raw)
                if not vid:
                    ref_to_canonical[ref] = None
                    no_video_id.append(ref)
                    continue
                canon = canonical_url(vid)
                ref_to_canonical[ref] = canon
                canonical_to_refs[canon].append(ref)
                if yt_raw.strip() != canon:
                    noncanonical.append(ref)

    # Mark duplicates based on canonical mapping
    duplicate_urls = {u: refs for u, refs in canonical_to_refs.items() if len(refs) > 1}

    print(
        json.dumps(
            {
                "videos_total": total_videos,
                "urls_noncanonical": len(noncanonical),
                "urls_no_video_id": len(no_video_id),
                "unique_canonical_urls": len(canonical_to_refs),
                "duplicate_url_groups": len(duplicate_urls),
            },
            indent=2,
        )
    )

    # ---- 3) oEmbed validate unique canonical urls once ----
    # Note: URLs with no video id are handled as invalid and will be replaced.
    session = requests.Session()
    oembed_status: Dict[str, bool] = {}
    oembed_meta: Dict[str, dict[str, Any]] = {}
    canon_urls = list(canonical_to_refs.keys())

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        futs = {ex.submit(oembed_fetch, url, session): url for url in canon_urls}
        for fut in as_completed(futs):
            url = futs[fut]
            ok = False
            meta: dict[str, Any] | None = None
            try:
                ok, meta = fut.result()
            except Exception:
                ok = False
                meta = None
            oembed_status[url] = ok
            if ok and isinstance(meta, dict):
                oembed_meta[url] = meta

    bad_urls = [u for u, ok in oembed_status.items() if not ok]
    print(
        json.dumps(
            {
                "oembed_bad_unique_urls": len(bad_urls),
                "oembed_ok_unique_urls": sum(1 for u in canon_urls if oembed_status.get(u, False)),
            },
            indent=2,
        )
    )

    # ---- 4) Mutate once (canonicalize -> move -> replace -> resolve duplicates) ----

    def get_video(ref: VideoRef) -> Dict[str, Any]:
        return subjects[ref.bucket]["channels"][ref.ch_idx]["videos"][ref.v_idx]

    def get_channel(bucket_key: str, ch_idx: int) -> Dict[str, Any]:
        return subjects[bucket_key]["channels"][ch_idx]

    # 4A) Canonicalize URLs in place where possible
    for ref, canon in ref_to_canonical.items():
        if canon:
            get_video(ref)["youtubeUrl"] = canon

    # Helper: find/create channel in target bucket by id/name
    def upsert_target_channel(target_bucket: str, source_channel: Dict[str, Any]) -> int:
        t_channels = subjects[target_bucket]["channels"]
        src_id = str(source_channel.get("id") or "")
        src_name = str(source_channel.get("name") or "")
        for i, ch in enumerate(t_channels):
            if src_id and str(ch.get("id") or "") == src_id:
                return i
        for i, ch in enumerate(t_channels):
            if src_name and str(ch.get("name") or "") == src_name:
                return i
        # Create new channel with copied metadata; videos will be appended.
        new_ch = {
            "id": src_id or f"{target_bucket.lower()}_ch_new",
            "name": src_name or "Unknown Channel",
            "focus": str(source_channel.get("focus") or ""),
            "gradeBand": str(source_channel.get("gradeBand") or ""),
            "videos": [],
        }
        t_channels.append(new_ch)
        return len(t_channels) - 1

    # 4B) Move videos based on URL-truth oEmbed classification.
    # Important: Remove in descending index order per (bucket, ch_idx) to keep indices stable.
    moves_by_source: Dict[Tuple[str, int], List[Tuple[int, str, str]]] = defaultdict(list)
    for ref, canon in ref_to_canonical.items():
        if not canon or not oembed_status.get(canon, False):
            continue
        meta = oembed_meta.get(canon) or {}
        otitle = str(meta.get("title") or "")
        oauthor = str(meta.get("author_name") or "")
        target_bucket, granular = classify_from_oembed(otitle, oauthor)
        if target_bucket != ref.bucket:
            moves_by_source[(ref.bucket, ref.ch_idx)].append((ref.v_idx, target_bucket, granular))

    moved_count = 0
    for (src_bucket, ch_idx), entries in moves_by_source.items():
        entries.sort(key=lambda t: t[0], reverse=True)
        src_channel = get_channel(src_bucket, ch_idx)
        src_videos = src_channel.get("videos") or []
        for v_idx, target_bucket, granular in entries:
            video_obj = src_videos.pop(v_idx)
            video_obj["subject"] = granular
            target_ch_idx = upsert_target_channel(target_bucket, src_channel)
            subjects[target_bucket]["channels"][target_ch_idx]["videos"].append(video_obj)
            moved_count += 1

    print(json.dumps({"moved_videos_by_oembed": moved_count}, indent=2))

    # Build a pool of known-good donor videos (by oEmbed) after moves (in-dataset only).
    # Pool keyed by (bucket, channel_id) and by bucket.
    def video_canon_from_obj(v: Dict[str, Any]) -> Optional[str]:
        vid = extract_video_id(str(v.get("youtubeUrl") or ""))
        return canonical_url(vid) if vid else None

    donors_by_bucket_channel: Dict[Tuple[str, str], List[Dict[str, Any]]] = defaultdict(list)
    donors_by_bucket: Dict[str, List[Dict[str, Any]]] = defaultdict(list)

    for bucket_key, bucket in subjects.items():
        for ch in bucket.get("channels") or []:
            ch_id = str(ch.get("id") or "")
            for v in ch.get("videos") or []:
                cu = video_canon_from_obj(v)
                if cu and oembed_status.get(cu, False):
                    donors_by_bucket_channel[(bucket_key, ch_id)].append(v)
                    donors_by_bucket[bucket_key].append(v)

    used_urls: set[str] = set()
    # Track currently used canonical URLs
    for bucket_key, bucket in subjects.items():
        for ch in bucket.get("channels") or []:
            for v in ch.get("videos") or []:
                cu = video_canon_from_obj(v)
                if cu:
                    used_urls.add(cu)

    def score_donor(target: Dict[str, Any], donor: Dict[str, Any]) -> Tuple[int, int]:
        # higher is better: (token_overlap, -duration_diff)
        tbag = _norm_tokenize(str(target.get("title") or ""))
        for t in target.get("tags") or []:
            tbag |= _norm_tokenize(str(t))
        dbag = _norm_tokenize(str(donor.get("title") or ""))
        for t in donor.get("tags") or []:
            dbag |= _norm_tokenize(str(t))
        overlap = len(tbag & dbag)
        td = _parse_duration_to_seconds(str(target.get("duration") or ""))
        dd = _parse_duration_to_seconds(str(donor.get("duration") or ""))
        diff = 10**9
        if td is not None and dd is not None:
            diff = abs(td - dd)
        return (overlap, -diff)

    def choose_replacement(bucket_key: str, channel_id: str, target_video: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        candidates: List[Dict[str, Any]] = []
        candidates.extend(donors_by_bucket_channel.get((bucket_key, channel_id), []))
        if not candidates:
            candidates.extend(donors_by_bucket.get(bucket_key, []))

        best: Optional[Dict[str, Any]] = None
        best_score: Optional[Tuple[int, int]] = None
        for d in candidates:
            cu = video_canon_from_obj(d)
            if not cu or cu in used_urls:
                continue
            sc = score_donor(target_video, d)
            if best is None or (best_score is not None and sc > best_score):
                best = d
                best_score = sc
        return best

    replaced_broken = 0
    # 4C) Replace broken/unavailable URLs and no-video-id cases
    for bucket_key, bucket in subjects.items():
        for ch in bucket.get("channels") or []:
            ch_id = str(ch.get("id") or "")
            for v in ch.get("videos") or []:
                cu = video_canon_from_obj(v)
                is_bad = (cu is None) or (cu in oembed_status and not oembed_status[cu])
                if not is_bad:
                    continue
                donor = choose_replacement(bucket_key, ch_id, v)
                if donor is None:
                    continue
                donor_cu = video_canon_from_obj(donor)
                if not donor_cu:
                    continue
                # Keep id stable; replace the rest coherently.
                keep_id = v.get("id")
                v.clear()
                v.update(donor)
                v["id"] = keep_id
                used_urls.add(donor_cu)
                replaced_broken += 1

    print(json.dumps({"replaced_broken_or_unparseable": replaced_broken}, indent=2))

    # 4C2) Align metadata with URL truth (oEmbed) for all oEmbed-ok URLs
    aligned_meta = 0
    for bucket_key, bucket in subjects.items():
        for ch in bucket.get("channels") or []:
            for v in ch.get("videos") or []:
                cu = video_canon_from_obj(v)
                if not cu or not oembed_status.get(cu, False):
                    continue
                meta = oembed_meta.get(cu) or {}
                otitle = str(meta.get("title") or "").strip()
                oauthor = str(meta.get("author_name") or "").strip()
                actual_bucket, granular = classify_from_oembed(otitle, oauthor)
                # bucket_key should already match after moves, but keep granular consistent.
                v["subject"] = granular
                if otitle:
                    v["title"] = otitle
                # Minimal tag repair: ensure bucket + granular are present
                tags = v.get("tags")
                if not isinstance(tags, list):
                    tags = []
                tagset = {str(t) for t in tags}
                if bucket_key not in tagset:
                    tags.append(bucket_key)
                if granular not in tagset:
                    tags.append(granular)
                v["tags"] = tags
                aligned_meta += 1

    print(json.dumps({"aligned_oembed_metadata": aligned_meta}, indent=2))

    # 4D) Resolve duplicates by replacing all but one occurrence
    # Recompute canonical usage map after replacements.
    canon_to_video_objs: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for bucket_key, bucket in subjects.items():
        for ch in bucket.get("channels") or []:
            for v in ch.get("videos") or []:
                cu = video_canon_from_obj(v)
                if cu:
                    canon_to_video_objs[cu].append(v)
    dup_groups = {cu: vids for cu, vids in canon_to_video_objs.items() if len(vids) > 1}

    replaced_dupes = 0
    if dup_groups:
        for cu, vids in dup_groups.items():
            # keep first, replace rest
            for victim in vids[1:]:
                # Need bucket/channel context: do a targeted search (bounded small dataset).
                found_bucket = None
                found_ch_id = None
                for bk, bucket in subjects.items():
                    for ch in bucket.get("channels") or []:
                        if victim in (ch.get("videos") or []):
                            found_bucket = bk
                            found_ch_id = str(ch.get("id") or "")
                            break
                    if found_bucket:
                        break
                if not found_bucket:
                    continue
                donor = choose_replacement(found_bucket, found_ch_id or "", victim)
                if donor is None:
                    continue
                donor_cu = video_canon_from_obj(donor)
                if not donor_cu:
                    continue
                keep_id = victim.get("id")
                victim.clear()
                victim.update(donor)
                victim["id"] = keep_id
                used_urls.add(donor_cu)
                replaced_dupes += 1

    print(json.dumps({"duplicate_groups_remaining_prevalidate": len(dup_groups), "replaced_dupes": replaced_dupes}, indent=2))

    # ---- 5) Final invariants ----
    # Structure and key constraints
    assert isinstance(data.get("subjects"), dict)
    for k in LIB_KEYS:
        assert k in subjects, f"Missing subject bucket: {k}"

    # Subject integrity: bucket must match URL-truth oEmbed classification for oEmbed-ok URLs.
    remaining_mismatches = 0
    # URL format + uniqueness
    all_cu: List[str] = []
    invalid_format = 0
    for bucket_key, bucket in subjects.items():
        for ch in bucket.get("channels") or []:
            for v in ch.get("videos") or []:
                url = str(v.get("youtubeUrl") or "")
                m = CANON_RE.match(url)
                if not m:
                    invalid_format += 1
                    continue
                all_cu.append(url)
                if oembed_status.get(url, False):
                    meta = oembed_meta.get(url) or {}
                    otitle = str(meta.get("title") or "")
                    oauthor = str(meta.get("author_name") or "")
                    actual_bucket, _ = classify_from_oembed(otitle, oauthor)
                    if actual_bucket != bucket_key:
                        remaining_mismatches += 1

    dupe_count = len(all_cu) - len(set(all_cu))
    print(
        json.dumps(
            {
                "final_remaining_mismatches": remaining_mismatches,
                "final_invalid_url_format": invalid_format,
                "final_duplicate_urls": dupe_count,
            },
            indent=2,
        )
    )

    if remaining_mismatches or invalid_format or dupe_count:
        print("ERROR: Final invariants failed; refusing to write.", file=sys.stderr)
        return 1

    # oEmbed validity for final set: must be ok or absent from map (should not happen).
    final_bad = 0
    for u in set(all_cu):
        if u in oembed_status and not oembed_status[u]:
            final_bad += 1
    if final_bad:
        print(f"ERROR: {final_bad} final URLs are oEmbed-bad; refusing to write.", file=sys.stderr)
        return 1

    # ---- 6) Write once ----
    DATA_PATH.write_text(json.dumps(data, indent=4, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Wrote: {DATA_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

