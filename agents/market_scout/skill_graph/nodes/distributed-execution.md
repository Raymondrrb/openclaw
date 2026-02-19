---
id: distributed-execution
title: Distributed Execution (Mac Controller + Windows Worker)
description: Dispatches headless jobs to worker nodes with capability checks and local fallback behavior.
tags: [cluster, tailscale, worker, controller]
links: ["[[observability-receipts]]", "[[cost-tiering]]"]
---

# Distributed Execution

Controller routes jobs by capability and risk.

## Allocation Rule

- Keep DaVinci final render on Mac.
- Send headless audio/probe/postcheck jobs to Windows worker.
- If worker health fails, fallback locally and log fallback reason.

Use stable run_id and job_id contracts to keep retries idempotent.
