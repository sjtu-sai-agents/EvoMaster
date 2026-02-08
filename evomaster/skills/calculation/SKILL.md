---
name: calculation
description: "When using Mat MCP tools (mat_sg_*, mat_dpa_*, mat_doc_*): (1) Use the URL returned by a previous tool (e.g. structure_paths) as input to the next tool—do not pass only a filename when the previous step returned an https URL. (2) For long-running DPA tasks use submit_* first, then query_job_status, then get_job_results when Done—do not use synchronous tools which may timeout. (3) When polling job status, wait 30–60 seconds between queries; call get_job_results once status is Done/Success."
license: null
---

Full guide: **job_submit.md**. Reserved: **matmaster/** for more materials-calculation content.
