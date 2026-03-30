#!/usr/bin/env python3
"""
XNAT session lookup for MRQART HTML email.
Provides clickable links to XNAT sessions for nonconforming sequences.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Dict, Optional, Tuple

try:
    from pyxnat import Interface

    _HAS_PYXNAT = True
except ImportError:
    _HAS_PYXNAT = False

BASE_DIR = Path(__file__).resolve().parent.parent
DEFAULT_XNAT_CFG = BASE_DIR / "config" / "mrrc-xnat.cfg"

XNAT_SESSION_URL = (
    "{server}/app/action/DisplayItemAction"
    "?search_value={session_id}"
    "&search_element=xnat:mrSessionData"
    "&search_field=xnat:mrSessionData.ID"
)


def get_xnat_interface(cfg_path: Path = DEFAULT_XNAT_CFG) -> Optional["Interface"]:
    """Return a pyxnat Interface or None if unavailable."""
    if not _HAS_PYXNAT:
        logging.warning("pyxnat not installed — XNAT links unavailable")
        return None
    if not cfg_path.exists():
        logging.warning(
            "XNAT config not found at %s — XNAT links unavailable", cfg_path
        )
        return None
    try:
        return Interface(config=str(cfg_path))
    except Exception as e:
        logging.warning("XNAT connection failed: %s", e)
        return None


def lookup_session_urls(
    project_subid_pairs: list[Tuple[str, str]],
    xnat: Optional["Interface"] = None,
) -> Dict[Tuple[str, str], str]:
    """
    Look up XNAT session URLs for a list of (project, subid) pairs.
    Returns a dict mapping (project, subid) -> URL string.
    Missing sessions map to empty string.

    :param project_subid_pairs: list of (project, subid) tuples
    :param xnat: pyxnat Interface (will create one if None)
    """
    if not project_subid_pairs:
        return {}

    if xnat is None:
        xnat = get_xnat_interface()
    if xnat is None:
        return {}

    results: Dict[Tuple[str, str], str] = {}

    for project, subid in project_subid_pairs:
        proj_short = (project.split("^", 1)[-1] if "^" in project else project).upper()
        try:
            cols = [
                "xnat:mrSessionData/LABEL",
                "xnat:mrSessionData/SESSION_ID",
                "xnat:mrSessionData/SUBJECT_LABEL",
            ]
            rows = xnat.select("xnat:mrSessionData", columns=cols).where(
                [
                    ("xnat:mrSessionData/PROJECT", "=", proj_short),
                    ("xnat:mrSessionData/SUBJECT_LABEL", "=", subid),
                    "AND",
                ]
            )
            session_id = ""
            for r in rows:
                session_id = r["session_id"]
                break
            if session_id:
                results[(project, subid)] = XNAT_SESSION_URL.format(
                    server=xnat._server,
                    session_id=session_id,
                )
            else:
                results[(project, subid)] = ""
        except Exception as e:
            logging.warning("XNAT lookup failed for %s/%s: %s", proj_short, subid, e)
            results[(project, subid)] = ""

    return results
