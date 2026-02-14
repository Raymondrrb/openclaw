# DaVinci Resolve Automation Guide -- Rayviews Lab

Compiled from web research (Feb 2026). Cross-referenced with existing `resolve_editing_rules.md` and `resolve_schema.py`.

---

## Python Scripting API Setup (macOS)

```bash
export RESOLVE_SCRIPT_API="/Library/Application Support/Blackmagic Design/DaVinci Resolve/Developer/Scripting"
export RESOLVE_SCRIPT_LIB="/Applications/DaVinci Resolve/DaVinci Resolve.app/Contents/Libraries/Fusion/fusionscript.so"
export PYTHONPATH="$PYTHONPATH:$RESOLVE_SCRIPT_API/Modules/"
```

**Prerequisite:** Resolve Studio must be running. Enable: Preferences > General > External Scripting Using > **Local**.

```python
import DaVinciResolveScript as dvr_script
resolve = dvr_script.scriptapp("Resolve")
projectManager = resolve.GetProjectManager()
```

---

## Automated Workflow (Maps to Pipeline Manifest)

### Step 1: Create Project
```python
project = projectManager.CreateProject(f"rayviews_{video_id}")
```

### Step 2: Import Media
```python
mediaPool = project.GetMediaPool()
clips = mediaPool.ImportMedia([
    "/path/to/audio/voice/chunks/01.mp3",
    "/path/to/assets/dzine/products/05_hero.png",
    # ... all media files
])
```

### Step 3: Create Timeline + Add Clips
```python
timeline = mediaPool.CreateEmptyTimeline(f"{video_id}_edit")

# Append audio chunks to A1
for chunk_clip in voice_chunks:
    mediaPool.AppendToTimeline([{
        "mediaPoolItem": chunk_clip,
        "mediaType": 2,  # 2 = Audio only
    }])

# Append product images to V1
for image_clip in product_images:
    mediaPool.AppendToTimeline([{
        "mediaPoolItem": image_clip,
        "mediaType": 1,  # 1 = Video only
        "startFrame": 0,
        "endFrame": 120,  # 4 seconds at 30fps
    }])
```

### Step 4: Set Clip Properties
```python
items = timeline.GetItemListInTrack("video", 1)
for item in items:
    item.SetProperty("ZoomX", 1.05)
    item.SetProperty("ZoomY", 1.05)
    item.SetProperty("DynamicZoomEase", 3)  # Ease In and Out
```

### Step 5: Add Timeline Markers
```python
# frameId is in frames (seconds * fps)
timeline.AddMarker(0, "Blue", "Hook", "Strong opening", 30)
timeline.AddMarker(240, "Green", "Avatar Intro", "3-5s clip", 30)
timeline.AddMarker(390, "Yellow", "Product #5", "234 words 90.6s", 30)
```

### Step 6: Render
```python
project.SetRenderSettings({
    "TargetDir": f"/path/to/exports",
    "CustomName": f"{video_id}_final",
    "FormatWidth": 1920,
    "FormatHeight": 1080,
    "FrameRate": "29.97",
    "ExportVideo": True,
    "ExportAudio": True,
})
project.SetCurrentRenderFormatAndCodec("mp4", "H264")
jobId = project.AddRenderJob()
project.StartRendering(jobId)

while project.IsRenderingInProgress():
    status = project.GetRenderJobStatus(jobId)
```

### Headless Mode
```bash
"/Applications/DaVinci Resolve/DaVinci Resolve.app/Contents/MacOS/Resolve" -nogui
```

---

## API Limitations

| Limitation | Workaround |
|-----------|------------|
| No keyframe creation via API | Use `DynamicZoomEase` + static zoom; or Fusion comps |
| AppendToTimeline adds to Track 1 only | Place all on V1, manually arrange; or multiple passes |
| No Dynamic Zoom rectangle control | Use `ZoomX/ZoomY/Pan/Tilt` for static transforms |
| Fusion comp manipulation limited | Use `ImportFusionComp(path)` for pre-built .comp files |
| No track targeting for append | Use markers to guide manual placement |

---

## Dynamic Zoom / Ken Burns

### Property Constants
```python
DYNAMIC_ZOOM_EASE_LINEAR = 0
DYNAMIC_ZOOM_EASE_IN = 1
DYNAMIC_ZOOM_EASE_OUT = 2
DYNAMIC_ZOOM_EASE_IN_AND_OUT = 3
```

### Static Properties
```python
item.SetProperty("ZoomX", 1.05)
item.SetProperty("ZoomY", 1.05)
item.SetProperty("Pan", 0.02)   # range -4.0*width to 4.0*width
item.SetProperty("Tilt", 0.0)
```

### Batch Application (UI Method)
1. Set Dynamic Zoom on one image
2. `Cmd+C` to copy
3. Select all other images
4. Right-click > **Paste Attribute** (`Alt+V`), check only **Dynamic Zoom**

### Zoom Levels for Pipeline

| Motion Type | Zoom Range | Use Case |
|------------|-----------|----------|
| zoom_in | 1.00 to 1.03-1.05 | Standard product shots |
| zoom_out | 1.05-1.07 to 1.00 | Hero shots |
| ken_burns | Zoom + lateral pan | Variety / retention |
| snap_zoom | 1.00 to 1.10-1.15 over 6 frames | Pattern interrupts only |

---

## YouTube Export Settings

| Setting | Value |
|---------|-------|
| Format | MP4 |
| Codec | H.264 |
| Encoder | Hardware (Apple/AMD/NVIDIA) |
| Resolution | 1920x1080 |
| Frame Rate | 29.97 fps |
| Rate Control | CBR |
| Bitrate | 20 Mbps |
| Profile | High |
| Audio Codec | AAC |
| Audio Bitrate | 320 kbps |
| Audio Sample Rate | 48,000 Hz |
| Network Optimization | On |
| Color Space Tag | Rec.709 or Rec.709-A |

Expected file size for 10-min video: ~150-300 MB.

Optional 4K upscale trick: Export at 3840x2160 from 1080p source. YouTube applies higher quality VP9/AV1 compression for 4K content. Use Super Scale (2x) in Resolve Studio.

---

## Fusion Template Architecture

### Templates Needed

| Template | Parameterized Controls | Track |
|----------|----------------------|-------|
| Rank Badge | rank number, accent color | V3 |
| Benefit Callout | text (max 6 words), icon path | V3 |
| Product Name Lower Third | product name | V3 |
| Disclosure | (fixed text) | V3 |

### Template Save Location (macOS)
```
~/Library/Application Support/Blackmagic Design/DaVinci Resolve/Support/Fusion/Templates/Edit/Titles/Rayviews/
```

### Creating Templates
1. Build node tree in Fusion: Text+ > Background > Merge > MediaOut
2. Select all > right-click > Macro > Create Macro
3. Expose adjustable controls (text, colors)
4. Save to templates folder
5. Use from Edit page: Effects Library > Titles > Rayviews

### Fusion Comp Import via API
```python
item = timeline.GetItemListInTrack("video", 1)[0]
comp = item.ImportFusionComp("/path/to/product_card.comp")
```

---

## Marker Colors (Pipeline Convention)

| Color | Meaning |
|-------|---------|
| Blue | Hook start |
| Green | Avatar intro |
| Yellow | Products #5-#2 |
| Red | Product #1 (winner) |
| Cyan | Retention reset |
| Purple | Outro / Disclosure |
| Sky | B-roll insertion points |
| Mint | Benefit overlay cues |
| Lavender | Signature moments |
| Cream | Global overlays |

---

## What Can Be Automated vs Manual

### Automatable via Python
- Project creation with correct settings
- Media import into organized bins
- Timeline creation
- Voiceover chunk placement on A1 (sequential append)
- Timeline marker placement
- Static zoom/pan values on clips
- Render settings and headless rendering

### Requires Manual Work
- Dynamic Zoom rectangle positioning
- Multi-track arrangement (V1-V4)
- Fusion template application for overlays
- B-roll placement and color matching
- Audio ducking configuration
- SFX placement and timing
- Final QC pass

---

## Sources

- [Unofficial Resolve Scripting Docs](https://deric.github.io/DaVinciResolve-API-Docs/)
- [Resolve Scripting API v20.3](https://gist.github.com/X-Raym/2f2bf453fc481b9cca624d7ca0e19de8)
- [X-Raym Resolve Scripting](https://extremraym.com/cloud/resolve-scripting-doc/)
- [ResolveDevDoc API](https://resolvedevdoc.readthedocs.io/en/latest/API_basic.html)
- [Batch Ken Burns](https://www.vidio.ai/blog/article/how-do-i-batch-apply-ken-burns-pan-zoom-to-hundreds-of-wedding-photos-in-davinci-resolve)
- [YouTube Export Settings](https://creativevideotips.com/tutorials/best-resolve-to-youtube-export-settings)
- [Configurable Fusion Templates](https://www.sabbirz.com/blog-3d/create-and-use-configurable-fusion-templates-in-davinci-resolve)
- [CSV to Resolve Markers](https://editingtools.io/guides/convert-csv-to-resolve-marker)
