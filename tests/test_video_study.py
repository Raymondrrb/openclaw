"""Integration tests for video_study.py — the CLI orchestrator."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tools.lib.video_study_schema import InsightItem, ToolMention
from tools.video_study import run_study, cmd_list, cmd_show, EXIT_OK, EXIT_ERROR, EXIT_ACTION_REQUIRED


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _mock_analysis_response():
    """Return a valid knowledge dict for mocked analysis."""
    return {
        "relevance": "Relevant for editing",
        "summary": "Covers editing techniques for video production.",
        "key_insights": [
            {
                "category": "editing",
                "insight": "Use AI Audio Assistant",
                "details": "One-click professional audio mix",
                "actionable": True,
            }
        ],
        "tools_mentioned": [
            {"name": "DaVinci Resolve", "category": "editing", "url": "", "note": "NLE"}
        ],
        "action_items": [
            {"priority": "high", "action": "Test AI Audio", "timeline": "this week"}
        ],
        "integration_plan": [],
        "transcript_highlights": [],
        "sources": [],
    }


# Module paths for patching (these are imported lazily inside run_study)
_DL = "tools.lib.video_study_download"
_EX = "tools.lib.video_study_extract"
_AN = "tools.lib.video_study_analyze"
_KN = "tools.lib.video_study_knowledge"


# ---------------------------------------------------------------------------
# run_study: full pipeline (all I/O mocked)
# ---------------------------------------------------------------------------

def test_run_study_full_pipeline(tmp_path):
    """Test the full pipeline with all external I/O mocked."""
    from tools.lib.video_study_download import DownloadResult
    from tools.lib.video_study_extract import ExtractionResult, TranscriptSegment
    from tools.lib.video_study_schema import KnowledgeOutput

    mock_dl = DownloadResult(
        success=True,
        job_dir=tmp_path / "job",
        video_path=tmp_path / "job" / "video.mp4",
        video_id="test_vid",
        title="Test Video",
        channel="TestChannel",
        description="A test video",
        duration_s=300,
    )

    mock_extract = ExtractionResult(
        success=True,
        frames=[tmp_path / "frame_0001.jpg"],
        transcript=[TranscriptSegment(0, 5, "Hello world")],
        transcript_text="[0:00] Hello world",
    )

    mock_knowledge = KnowledgeOutput.from_dict({
        "video_id": "test_vid",
        "title": "Test Video",
        "channel": "TestChannel",
        "url": "https://youtube.com/watch?v=test_vid",
        "study_date": "2026-02-13",
        **_mock_analysis_response(),
    })
    mock_meta = {"model": "claude-sonnet-4-5-20250929", "input_tokens": 5000, "output_tokens": 800, "duration_s": 12.0, "frame_count": 1}

    (tmp_path / "job").mkdir(parents=True, exist_ok=True)
    (tmp_path / "job" / "video.mp4").write_bytes(b"fake")

    with patch(f"{_DL}.check_ytdlp", return_value="/usr/bin/yt-dlp"), \
         patch(f"{_DL}.check_ffmpeg", return_value="/usr/bin/ffmpeg"), \
         patch(f"{_DL}.create_job_dir", return_value=tmp_path / "job"), \
         patch(f"{_DL}.download_video", return_value=mock_dl), \
         patch(f"{_EX}.extract_all", return_value=mock_extract), \
         patch(f"{_EX}.sample_frames", return_value=[tmp_path / "frame_0001.jpg"]), \
         patch(f"{_AN}.analyze_video", return_value=(mock_knowledge, mock_meta)), \
         patch(f"{_KN}.save_knowledge", return_value=(tmp_path / "k.json", tmp_path / "k.md")), \
         patch(f"{_KN}.save_to_supabase", return_value=False), \
         patch(f"{_DL}.cleanup_job_dir") as mock_cleanup:

        exit_code = run_study(url="https://youtube.com/watch?v=test_vid")

    assert exit_code == EXIT_OK
    mock_cleanup.assert_called_once()


def test_run_study_no_url_no_file():
    exit_code = run_study()
    assert exit_code == EXIT_ERROR


def test_run_study_missing_ytdlp():
    with patch(f"{_DL}.check_ytdlp", return_value=None):
        exit_code = run_study(url="https://youtube.com/watch?v=test")
    assert exit_code == EXIT_ACTION_REQUIRED


def test_run_study_missing_ffmpeg():
    with patch(f"{_DL}.check_ytdlp", return_value="/usr/bin/yt-dlp"), \
         patch(f"{_DL}.check_ffmpeg", return_value=None):
        exit_code = run_study(url="https://youtube.com/watch?v=test")
    assert exit_code == EXIT_ACTION_REQUIRED


def test_run_study_download_failure(tmp_path):
    from tools.lib.video_study_download import DownloadResult

    mock_dl = DownloadResult(success=False, error="Network error", job_dir=tmp_path)

    with patch(f"{_DL}.check_ytdlp", return_value="/usr/bin/yt-dlp"), \
         patch(f"{_DL}.check_ffmpeg", return_value="/usr/bin/ffmpeg"), \
         patch(f"{_DL}.create_job_dir", return_value=tmp_path), \
         patch(f"{_DL}.download_video", return_value=mock_dl), \
         patch(f"{_DL}.cleanup_job_dir"):

        exit_code = run_study(url="https://youtube.com/watch?v=fail")

    assert exit_code == EXIT_ERROR


# ---------------------------------------------------------------------------
# cmd_list / cmd_show
# ---------------------------------------------------------------------------

def test_cmd_list(tmp_path):
    with patch(f"{_KN}.agents_dir", return_value=tmp_path):
        data = {"video_id": "abc", "title": "Vid", "channel": "Ch", "study_date": "2026-02-13"}
        (tmp_path / "video_study_abc.json").write_text(json.dumps(data))
        exit_code = cmd_list()
    assert exit_code == EXIT_OK


def test_cmd_show_found():
    from tools.lib.video_study_schema import KnowledgeOutput, InsightItem
    k = KnowledgeOutput(
        video_id="abc", title="Test", channel="Ch", url="", study_date="2026-02-13",
        relevance="Rel", summary="Sum",
        key_insights=[InsightItem(category="editing", insight="X")],
    )
    with patch(f"{_KN}.load_study", return_value=k):
        exit_code = cmd_show("abc")
    assert exit_code == EXIT_OK


def test_cmd_show_not_found():
    with patch(f"{_KN}.load_study", return_value=None):
        exit_code = cmd_show("missing")
    assert exit_code == EXIT_ERROR


def test_cmd_show_json():
    from tools.lib.video_study_schema import KnowledgeOutput, InsightItem
    k = KnowledgeOutput(
        video_id="abc", title="Test", channel="Ch", url="", study_date="2026-02-13",
        relevance="Rel", summary="Sum",
        key_insights=[InsightItem(category="editing", insight="X")],
    )
    with patch(f"{_KN}.load_study", return_value=k):
        exit_code = cmd_show("abc", as_json=True)
    assert exit_code == EXIT_OK
