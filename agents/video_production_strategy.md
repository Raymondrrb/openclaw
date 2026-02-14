# Video Production Strategy — Rayviews Lab

## Audience Profile
- **Target**: 40+ / 50+ Amazon shoppers
- Values clarity over style
- Prefers practical demonstration
- Distrusts flashy or over-edited content
- Needs to SEE how the product works
- Responds to calm, informative tone
- Prefers realistic environments

## Do NOT
- Generate influencer-style hype content
- Generate fast-cut TikTok-style edits
- Exaggerate claims visually
- Use dramatic shadows, lens flares, stylized color grading
- Use exaggerated motion blur or artificial glow
- Burn credits on large variations

## Video Structure (per product, 3-4 clips)

### 1. Product Clarity Shot (3-4 seconds)
- Static or subtle push-in
- Clean lighting
- Neutral background
- Emphasize real shape and details

### 2. Human Usage Demo (3-4 seconds)
- Simple hand interaction
- Slow, natural movement
- Clear scale reference
- Realistic home environment

### 3. Benefit in Action (3-4 seconds)
- Show outcome
- No dramatic transformation
- Practical result

### 4. Clean Closing Shot (2-3 seconds)
- Product resting on surface
- Calm framing
- Clear visibility

## Model Selection

**Primary**: Minimax Hailuo 2.3 (56-98 credits)
- Best cost-to-output ratio
- Short clips (max 4 seconds)
- Minimal camera motion
- One action per clip
- Use 4-6 strong product reference images
- Avoid complex environments

**If product fidelity drifts**:
- Reduce motion
- Shorten clip
- Tighten framing
- Regenerate only that clip (not entire batch)

## Style Guidelines

- Realistic lighting only
- Environments: kitchen, living room, office desk, garage, bathroom
- Natural and believable
- No extreme close-ups that hide scale
- No unrealistic perfection

## Conversion Principles

**Show**: ease of use, scale relative to hands, key features clearly, real-life practicality, stability and durability

**Avoid**: flashy transitions, fast motion, extreme close-ups that hide scale, unrealistic perfection

## Output Requirements

- 3-4 short clips per product only
- No batch overproduction
- Validate fidelity before proceeding
- Keep cost efficiency in mind

Optimize for **trust and clarity** — not visual spectacle.

---

## Camera Movement Automation

### Allowed Movements (priority order)

**Default (product scenes):**
1. **Static Shot** (highest priority, always safe)
2. **Push In** (subtle only, for product detail)
3. **Very light Zoom In** (if Push In not available)

**Secondary (human usage scenes only):**
4. Pan Left or Pan Right (slow)
5. Tracking Shot (very slow, only if necessary)

### Strictly Forbidden
- Shake
- Truck Left / Right (distortion risk)
- Pedestal Up / Down (unnatural for product demo)
- Tilt Up / Down (unless subtle product reveal)
- More than 2 movement combinations
- Push In + Zoom In combined
- Tracking + Pan combined
- Any 3-combination stack

### Automation Logic

```python
# Step 1: Click "Free Selection" tab
# Step 2: Deselect any forbidden active movements
# Step 3: Select based on scene type:

if scene_type == "product_clarity":
    select("Static Shot")
elif scene_type == "product_detail":
    select("Push In")
elif scene_type == "human_usage":
    select("Static Shot")
    select("Pan Left")  # optional, slow
elif scene_type == "closing":
    select("Static Shot")

# Safety: verify <= 2 movements selected
# If uncertain: always "Static Shot" only
```

### UI Interaction Rules
- Click button by visible text label
- Confirm button visual state change (active highlight)
- Wait 300-500ms between UI actions
- Log selected camera configuration
- If already active, do not re-click
