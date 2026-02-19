#!/usr/bin/env python3
"""
DaVinci Resolve smoke test:
- connect to Resolve API
- create project/timeline
- import test clip
- attempt short render
- write report json
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

from lib.common import now_iso

BASE_DIR = Path(os.environ.get("PROJECT_ROOT", Path(__file__).resolve().parent.parent))
TMP_DIR = BASE_DIR / 'tmp' / 'davinci_smoke'
REPORT_PATH = TMP_DIR / 'smoke_report.json'
TEST_MEDIA = TMP_DIR / 'smoke_clip.mp4'
OUTPUT_DIR = TMP_DIR / 'render_out'


def ensure_dirs() -> None:
    TMP_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def run_ffmpeg_test_clip() -> None:
    cmd = [
        '/opt/homebrew/bin/ffmpeg',
        '-y',
        '-f',
        'lavfi',
        '-i',
        'color=c=black:s=1920x1080:d=2:r=30',
        '-f',
        'lavfi',
        '-i',
        'sine=frequency=880:duration=2',
        '-c:v',
        'libx264',
        '-pix_fmt',
        'yuv420p',
        '-c:a',
        'aac',
        '-shortest',
        str(TEST_MEDIA),
    ]
    subprocess.run(cmd, check=True, capture_output=True, text=True)


def open_resolve_app() -> None:
    # Resolve is installed as a folder containing the .app bundle.
    app_bundle = '/Applications/DaVinci Resolve/DaVinci Resolve.app'
    subprocess.run(['open', app_bundle], check=False)


def import_resolve_module() -> Any:
    script_api = '/Library/Application Support/Blackmagic Design/DaVinci Resolve/Developer/Scripting'
    script_mod = script_api + '/Modules'
    os.environ.setdefault('RESOLVE_SCRIPT_API', script_api)
    os.environ.setdefault('PYTHONPATH', script_mod)
    if script_mod not in sys.path:
        sys.path.append(script_mod)
    import DaVinciResolveScript  # type: ignore

    return DaVinciResolveScript


def connect_resolve(max_wait_sec: int = 120) -> Any:
    drv = import_resolve_module()
    deadline = time.time() + max_wait_sec
    last_err = None
    while time.time() < deadline:
        try:
            resolve = drv.scriptapp('Resolve')
            if resolve:
                return resolve
        except Exception as e:  # noqa: BLE001
            last_err = str(e)
        time.sleep(2)
    raise RuntimeError(f'Failed to connect to Resolve within {max_wait_sec}s. Last error: {last_err}')


def is_resolve_process_running() -> bool:
    try:
        p = subprocess.run(
            ['ps', 'aux'],
            capture_output=True,
            text=True,
            check=False,
        )
        txt = (p.stdout or '').lower()
        return ('davinci resolve.app/contents/macos/resolve' in txt) or ('/resolve' in txt and 'davinci resolve' in txt)
    except Exception:
        return False


def get_project_manager(resolve: Any) -> Any:
    pm = resolve.GetProjectManager()
    if not pm:
        raise RuntimeError('GetProjectManager returned None')
    return pm


def ensure_database_ready(pm: Any) -> None:
    current_db = None
    current_folder = None
    try:
        if hasattr(pm, 'GetCurrentDatabase'):
            current_db = pm.GetCurrentDatabase()
    except Exception:
        current_db = None
    if not current_db:
        raise RuntimeError(
            'No active project database/library in Resolve. Open Project Manager and select/create a Local Library first.'
        )

    # Some Resolve setups return empty string for root folder. Treat root as valid.
    try:
        if hasattr(pm, 'GotoRootFolder'):
            pm.GotoRootFolder()
    except Exception:
        pass

    try:
        if hasattr(pm, 'GetCurrentFolder'):
            current_folder = pm.GetCurrentFolder()
    except Exception:
        current_folder = None

    if current_folder is None:
        raise RuntimeError(
            'No active project folder context in Resolve. Open Project Manager, enter your Local Library, and retry.'
        )


def ensure_project(pm: Any, project_name: str) -> Any:
    project = pm.LoadProject(project_name)
    if not project:
        project = pm.CreateProject(project_name)
    if not project:
        raise RuntimeError(f'Could not load/create project: {project_name}')
    return project


def create_timeline_with_media(project: Any, timeline_name: str, media_path: Path) -> Any:
    mp = project.GetMediaPool()
    if not mp:
        raise RuntimeError('GetMediaPool returned None')

    imported = mp.ImportMedia([str(media_path)])
    if not imported:
        raise RuntimeError(f'ImportMedia failed for: {media_path}')

    timeline = None
    if hasattr(mp, 'CreateTimelineFromClips'):
        try:
            timeline = mp.CreateTimelineFromClips(timeline_name, imported)
        except Exception:
            timeline = None

    if not timeline and hasattr(mp, 'CreateEmptyTimeline'):
        timeline = mp.CreateEmptyTimeline(timeline_name)
        if timeline and hasattr(mp, 'AppendToTimeline'):
            mp.AppendToTimeline(imported)

    if not timeline:
        raise RuntimeError('Failed to create timeline from imported media')

    if hasattr(project, 'SetCurrentTimeline'):
        project.SetCurrentTimeline(timeline)

    return timeline


def try_render(project: Any, resolve: Any, render_name: str) -> Dict[str, Any]:
    result: Dict[str, Any] = {
        'attempted': True,
        'addRenderJob': False,
        'startRendering': False,
        'isRenderingInProgress': None,
        'renderFiles': [],
        'notes': [],
    }

    try:
        if hasattr(resolve, 'OpenPage'):
            resolve.OpenPage('deliver')
    except Exception as e:  # noqa: BLE001
        result['notes'].append(f'OpenPage(deliver) failed: {e}')

    try:
        loaded = False
        for preset in ['H.264 Master', 'YouTube', 'YouTube 1080p']:
            try:
                if hasattr(project, 'LoadRenderPreset') and project.LoadRenderPreset(preset):
                    loaded = True
                    result['notes'].append(f'Loaded preset: {preset}')
                    break
            except Exception:
                continue
        if not loaded:
            result['notes'].append('No known preset loaded; using direct settings only')
    except Exception as e:  # noqa: BLE001
        result['notes'].append(f'LoadRenderPreset failed: {e}')

    try:
        if hasattr(project, 'SetRenderSettings'):
            project.SetRenderSettings({
                'SelectAllFrames': 1,
                'TargetDir': str(OUTPUT_DIR),
                'CustomName': render_name,
                'FormatWidth': 1920,
                'FormatHeight': 1080,
                'FrameRate': 30,
            })
    except Exception as e:  # noqa: BLE001
        result['notes'].append(f'SetRenderSettings failed: {e}')

    try:
        if hasattr(project, 'AddRenderJob'):
            job = project.AddRenderJob()
            result['addRenderJob'] = bool(job)
            result['notes'].append(f'AddRenderJob returned: {job}')
    except Exception as e:  # noqa: BLE001
        result['notes'].append(f'AddRenderJob failed: {e}')

    try:
        if hasattr(project, 'StartRendering'):
            started = project.StartRendering()
            result['startRendering'] = bool(started)
            result['notes'].append(f'StartRendering returned: {started}')
    except Exception as e:  # noqa: BLE001
        result['notes'].append(f'StartRendering failed: {e}')

    # Wait briefly for render to finish/progress
    for _ in range(30):
        try:
            if hasattr(project, 'IsRenderingInProgress'):
                in_progress = bool(project.IsRenderingInProgress())
                result['isRenderingInProgress'] = in_progress
                if not in_progress:
                    break
        except Exception:
            break
        time.sleep(1)

    files = sorted(str(p) for p in OUTPUT_DIR.glob(f'{render_name}*'))
    result['renderFiles'] = files
    return result


def main() -> int:
    ensure_dirs()
    run_ffmpeg_test_clip()
    open_resolve_app()

    start = time.time()
    report: Dict[str, Any] = {
        'timestamp': now_iso(),
        'ok': False,
        'steps': {},
        'errors': [],
    }

    try:
        resolve = connect_resolve(max_wait_sec=120)
        report['steps']['connectResolve'] = True

        pm = get_project_manager(resolve)
        report['steps']['projectManager'] = True
        ensure_database_ready(pm)
        report['steps']['databaseReady'] = True

        suffix = datetime.now().strftime('%Y%m%d_%H%M%S')
        project_name = f'OpenClaw_Smoke_{suffix}'
        timeline_name = f'SmokeTL_{suffix}'
        render_name = f'smoke_render_{suffix}'

        project = ensure_project(pm, project_name)
        report['steps']['projectName'] = project_name

        _timeline = create_timeline_with_media(project, timeline_name, TEST_MEDIA)
        report['steps']['timelineName'] = timeline_name

        render_info = try_render(project, resolve, render_name)
        report['steps']['render'] = render_info

        report['ok'] = True
    except Exception as e:  # noqa: BLE001
        report['errors'].append(str(e))
        if not report['steps'].get('connectResolve') and is_resolve_process_running():
            report['errors'].append(
                'Resolve process is running but API is unavailable. '
                'Likely cause: Preferences > System > General > External scripting using is not set to Local/Network.'
            )
        report['ok'] = False

    report['elapsedSec'] = round(time.time() - start, 2)
    _tmp = REPORT_PATH.with_suffix(".tmp")
    _payload = json.dumps(report, indent=2).encode("utf-8")
    _fd = os.open(str(_tmp), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o644)
    try:
        os.write(_fd, _payload)
        os.fsync(_fd)
    finally:
        os.close(_fd)
    os.replace(str(_tmp), str(REPORT_PATH))
    print(json.dumps(report, indent=2))
    print(f'REPORT: {REPORT_PATH}')
    return 0 if report['ok'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
