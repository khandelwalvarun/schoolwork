"""Class → Drive file-id mapping for 2026-27 syllabus PDFs.

Extracted from `/pages/Syllabus-2026-27` on the parent portal, 2026-04-23. See
docs/SITE_MAP.md §6. Refresh via `scripts/refresh_syllabus_links.py` (TODO) when
the school posts new documents.
"""

from __future__ import annotations

# Keys: human-readable class names as they appear on the portal page.
SYLLABUS_DRIVE_IDS: dict[str, str] = {
    "Foundation": "1gbw4bQyzUofa8G9YBD-DFk7L5tYcBNyu",
    "Nursery": "1lIvOnjmpVrE3shCE7xUs32LFzZ_DLhmY",
    "Class 1": "1xRAoosTBKQEnmZ8CFVwD-crfKV2ebrjK",
    "Class 2": "1fllIbiQsEeN240N7mGgdOMulqamS16dY",
    "Class 3": "1LwkYk5bFEtHk19QsZwFSsWeVF8vM9w9j",
    "Class 4": "12ZbNa2c-r2_BSKknABHhCJDFqrC8tQNt",
    "Class 5": "1PcSast7uOGbOdPbU1PtWK1pIHHGWkMr8",
    "Class 6": "1OeDNkUvJ528brGGSW1gowDwe40yua4ZN",
    "Class 7": "18yItDyLgt_DN7XG2V98XmmjJ3kkDYDS3",
    "Class 8": "1eNgOWcalcBe9UunMKkQjj0TJiEsMS8sP",
    "Class 8 IGCSE": "1otEGlPNt1ElB3bEVO0byMBR-O9KiYChR",
    "Class 9": "1YHaIWJ1VJx8mjoR714Y0Zy96gO1fJ3yx",
    "Class 9 IGCSE": "1147PDDAkeHx-NtwumDeB6-q02apVy4kf",
    "Class 10": "1kQCuAJICZAfeJ_wfaspKqEnOlgPYdleG",
    "Class 10 IGCSE": "1UjkY7aQGLTaClkiCbt36vxC93pnzvEVd",
    "Class 11": "1BXXaFo3pS2MBJ6f5hTiEnvexxjvpUlwJ",
    "Class 11 - A Level": "1E1tNmKCs2TXmUIDK3pOlOi9iRlIPMZYn",
    "Class 12": "1n2KAC-blhJ3zZNMB09TETp_xYJ7WSznP",
    "Class 12 - AS Level": "1hKobMTeqqkSYYpL_KwxU3NWvOSDbet_0",
}

BOOK_LIST_DRIVE_IDS: dict[str, str] = {
    "Class 6": "1MWQkt32vhZ-OlzpL7_oJ0LHKjTDN0yh0",
    "Class 7": "1UbW4bmYNfttE6A8zX2tPyhrklETpxZmN",
    "Class 8": "1cOXaTEYYd-G16kQ36UtvKco272Is0Lvh",
}


def syllabus_drive_id(class_level: int) -> str | None:
    """Map class_level (1..12) → Drive file-id for the 2026-27 syllabus PDF."""
    return SYLLABUS_DRIVE_IDS.get(f"Class {class_level}")


def drive_download_url(file_id: str) -> str:
    return f"https://drive.google.com/uc?export=download&id={file_id}"
