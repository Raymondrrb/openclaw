# Workflow: Refinement Loop (Multi-Agent)

Goal: Iterate scripts with structured feedback until QA passes.

Files:

- Draft v1: content/<slug>/draft_v1.md
- SEO notes: content/<slug>/seo_notes.md
- Editor notes: content/<slug>/edit_notes.md
- Reviewer notes: content/<slug>/review_notes.md
- Draft v2: content/<slug>/draft_v2.md

Loop:

1. Scriptwriter creates draft_v1.md
2. SEO writes seo_notes.md
3. Editor writes edit_notes.md
4. Reviewer writes review_notes.md
5. Lead merges into draft_v2.md
6. Run QA checklist
7. If critical issues remain, repeat once and stop
