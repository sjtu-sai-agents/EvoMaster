# Calculation job submit and tool usage

Rules for calling Mat MCP calculation tools (mat_sg, mat_dpa, mat_doc) to avoid common errors and pointless polling.

## 1. Use URLs from previous tool output as downstream input

- If the previous tool returned an **https URL** (e.g. `structure_paths`, `job_link`, file URL), the next tool that needs that file **must use that URL** as input. Do not pass only a filename (e.g. `Fe_bcc.cif`).
- Example: `mat_sg_build_bulk_structure_by_template` returns `structure_paths: "https://bohrium.oss-.../Fe_bcc.cif"`; then `mat_dpa_optimize_structure`'s `input_structure` must be that **full URL**, not `Fe_bcc.cif`.
- Use a local path only when the file is actually in the local workspace and must be uploaded (and OSS env vars are configured).

## 2. Long-running DPA tasks: always use submit → poll status → get results

- **Do not** use the synchronous tools: `mat_dpa_optimize_structure`, `mat_dpa_calculate_phonon`, `mat_dpa_run_molecular_dynamics`, etc., as they may timeout.
- **Do** use the corresponding **submit_** tool to submit the job, then `mat_dpa_query_job_status` to check status, and when status is Done/Success call `mat_dpa_get_job_results` to fetch results.
- Flow: `mat_dpa_submit_optimize_structure` → get `job_id` → loop `mat_dpa_query_job_status(job_id)` until not Running → `mat_dpa_get_job_results(job_id)`.

## 3. How to poll job status

- Wait at least **30–60 seconds** between two `query_job_status` calls; avoid high-frequency polling.
- When status is **Running**, keep waiting and query again later, or do other steps and then check again.
- When status is **Done / Success**, call **get_job_results** immediately to get the result and continue; do not keep querying status without fetching results.

## 4. Chaining with Structure Generator

- URLs returned by `mat_sg_*` for structure files can be used directly as `input_structure` (and similar) for `mat_dpa_*`.
- For "structure generation then DPA calculation", prefer using the URL from the previous step rather than downloading to local and passing a local path (unless you explicitly need local upload and have OSS configured).
