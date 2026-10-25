# AlignCV

## Deployment preparation

Deploy with the root `render.yaml` using Render **New > Blueprint** after pushing this folder to your Git provider. The API and static frontend deploy separately; no database is needed.

- Set `GROQ_API_KEY` on the API service.
- Set `FRONTEND_ORIGIN` to the frontend's exact HTTPS origin, without a trailing slash. Multiple origins can be comma-separated.
- Set `VITE_API_URL` to the API's HTTPS origin, without `/api`. Redeploy the frontend after changing it. Production builds validate this setting; HTTP localhost is allowed for local testing.
- Optional artwork requires `CLOUDFLARE_ACCOUNT_ID` and `CLOUDFLARE_API_TOKEN` on the API service. Add these in the Render dashboard only if using artwork.
- Verify `/api/health`, sample resume loading, and one real analysis on the deployed site. Provider calls in the automated tests are mocked; passing tests does not verify deployed credentials or quota.

Keep `frontend/package-lock.json`, backend tests, sample documents, and `.env.example` files in the repository. Local `.env` files, `.venv`, `node_modules`, `dist`, and caches are ignored and must not be uploaded. Render installs dependencies and builds `dist` itself. The optional `requirements-rag.txt` is deliberately excluded from the Render build to avoid loading PyTorch/MiniLM on the lightweight API service.

Local verification (PowerShell, from the project root):

```powershell
Push-Location backend
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe -m pip check
Pop-Location
Push-Location frontend
npm.cmd run build
npm.cmd audit
Pop-Location
```

Use Python 3.11 for parity with the Render configuration. The existing local environment may use another Python version; recreate it with Python 3.11 if SDK compatibility warnings appear.

AlignCV is a responsive resume document analyzer built for the Developer Assessment, Task 2. It accepts PDF/TXT resumes, extracts text, uses retrieval-augmented generation (RAG) with a Groq-hosted LLM, validates structured results, and shows evidence excerpts and review indicators.

## Features mapped to Task 2

| Assessment requirement | AlignCV implementation |
|---|---|
| PDF/text upload and extraction | FastAPI upload endpoint; PyMuPDF extracts PDF text; UTF-8 decoder handles TXT. Files are limited to 5 MB. Empty, unreadable, unsupported, and scanned/image-only PDFs receive clear errors. |
| Sample documents | The supplied software developer PDF is in `backend/samples`; an editable sample JD is available from the job description section. |
| AI summaries and styles | Groq API generates a brief, detailed, or bullet-style summary grounded in retrieved resume text. Key findings and suggestions are included. |
| Structured fields | Name, email, skills, education, and experience are returned as validated Pydantic JSON fields with value, evidence, and status. Missing or unverifiable values are null. |
| Adaptive analysis | Basic/standard/detailed depth and optional focus areas are sent to the analysis prompt. Users can leave focus blank for a complete analysis. |
| Visual insight | Skills are grouped into categories with exact counts and category bars. An optional Cloudflare Workers AI illustration replaces the pie chart. |
| Interactive review | Separate upload, loading, and report screens; expandable evidence; missing/uncertain flags; completeness indicator; optional job-description keyword comparison. |
| Deployment and documentation | Render setup is described below. This README includes stack, environment settings, test flow, and known limitations. |

## Stack

- React + Vite frontend
- Python + FastAPI backend
- PyMuPDF for PDF extraction
- `sentence-transformers/all-MiniLM-L6-v2` embeddings and cosine similarity for semantic retrieval when the optional model package is installed and enabled
- Lexical-overlap retrieval for RAG by default; used as fallback when MiniLM is disabled/unavailable
- Groq API for LLM generation (`openai/gpt-oss-20b` by default; change `GROQ_MODEL` if your Groq account exposes a different supported model)
- Pydantic for output validation
- CSS category bars and optional Cloudflare Workers AI skills artwork

## Run locally on Windows

Install **Python 3.11 or later** and **Node.js 20 or later**. Run these commands in PowerShell from the project root.

### Backend

First-time setup:

```powershell
cd backend
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
if (!(Test-Path .env)) { Copy-Item .env.example .env }
```

Set `GROQ_API_KEY` in `backend/.env` to your Groq API key. Keep this file private.

Start the backend from the `backend` folder:

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

### Frontend

Open a second terminal at the project root:

```powershell
cd frontend
npm install
if (!(Test-Path .env)) { Copy-Item .env.example .env }
npm run dev
```

On subsequent runs, only run the backend start command and `npm run dev` in their respective folders. Install dependencies again when their requirements change.

Open `http://localhost:5173`. The backend health check is at `http://localhost:8000/api/health`. Keep both terminals running; press **Ctrl+C** in each to stop the app.

RAG uses lexical retrieval by default. For optional MiniLM semantic retrieval, run `.\.venv\Scripts\python.exe -m pip install -r requirements-rag.txt` from `backend`, set `ENABLE_MINILM=true` in `backend/.env`, and restart the backend. This installs PyTorch and downloads the embedding model on first use.

## Render deployment

A root `render.yaml` Blueprint defines both services, the API health check, Python 3.11, Node.js 22, and lightweight lexical retrieval. In Render, choose **New > Blueprint** and select your repository. Enter `GROQ_API_KEY`, `FRONTEND_ORIGIN` (the frontend's full HTTPS origin), and `VITE_API_URL` (the API's full HTTPS base URL without `/api`) when prompted. Use the actual URLs assigned by Render; service names may receive a suffix. If those URLs are not yet known, update them in the dashboard after creation and redeploy both services. Changes to `VITE_API_URL` require a new frontend build. No API keys belong in frontend environment variables.

Skill counts and category bars use extracted data and native CSS. Optional skills artwork uses Cloudflare Workers AI and is decorative; exact counts remain visible.

Deploy the frontend and API as separate Render services so the React static site stays light and the Python API can host the processing dependencies.

### Backend web service

1. Push the `aligncv` project to a private or public GitHub repository. Confirm `.env`, `.venv`, `node_modules`, and build output are excluded.
2. In Render, create a **Web Service** from the repository and set its root directory to `backend`.
3. Runtime: **Python**. Build command: `pip install -r requirements.txt`. Start command: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`.
4. Add environment variables: `GROQ_API_KEY` (secret), `GROQ_MODEL` (`openai/gpt-oss-20b`), `FRONTEND_ORIGIN` (the exact public frontend URL), `MAX_UPLOAD_MB` (`5`), and `ENABLE_MINILM`.
5. For a free, low-memory service, use the regular `requirements.txt` and set `ENABLE_MINILM=false`; RAG still works with the built-in lexical retrieval. To use MiniLM, switch the backend build configuration to install `requirements-rag.txt` and set `ENABLE_MINILM=true` only if the selected Render instance has enough memory for PyTorch and the embedding model. The model weights are downloaded on first RAG request, not committed to the repository.
6. Deploy and copy the public API base URL (for example, `https://your-api.onrender.com`). Check `/api/health`.

### Frontend static site

1. In Render, create a **Static Site** from the same repository and set its root directory to `frontend`.
2. Build command: `npm ci && npm run build`. Publish directory: `dist`.
3. Add environment variable `VITE_API_URL` with the backend's public API base URL. Vite uses this value during the build.
4. Deploy the static site. Copy its public URL and update the backend's `FRONTEND_ORIGIN` to that exact URL, then redeploy the backend.
5. Test upload, samples, both retrieval modes, error states, and the complete report flow from the public frontend URL.

Render's free services can sleep when idle, so the first API request after inactivity may be slow. Render builds from the committed source files.

## API

- `GET /api/health` — health check
- `GET /api/samples` — lists sample resumes
- `GET /api/samples/{filename}` — returns a sample PDF/TXT document as base64 with extracted text
- `POST /api/analyze` — multipart upload and analysis options; returns summary, findings, extracted fields/evidence, scores, chart categories, retrieval mode, and optional job match

## Scoring and reliability notes

- **Summary evidence overlap** measures meaningful summary terms found across the combined source-verified field excerpts, excluding common filler words and normalizing simple plurals. The expandable calculation shows sentence-level overlap and up to three matching excerpts. Unlike the previous whole-sentence threshold, it gives partial credit for evidence spread across fields. Zero means no matching terms, not that the whole resume is incorrect. Paraphrases may receive a lower score, and matching words cannot verify meaning or negation. This is a review aid, not factual accuracy or a hiring score. Empty, unmeasurable summaries have no score.
- **Completeness** measures whether five predefined resume fields were extracted. It does not judge resume quality.
- **Job match estimate** assesses JD requirements against full resume evidence across requested skills, experience, projects, education, certifications and responsibilities. Essential requirements weigh 3 and preferred requirements weigh 1; met earns full credit, partial 40%, missing zero. Missing essential requirements cap the overall score at 59%; partial essentials cap it at 79%. Exact JD and resume quotes are checked before scoring. Requirement extraction and semantic assessment use AI and can be incorrect; the score is not an employer ATS score. Existing saved reports must be reanalyzed to receive the new comparison.
- Field evidence quotes are verified against the extracted source text. If a non-null field has no exact verifiable quote, AlignCV drops its value to null and marks it uncertain.
- LLM output is never guaranteed correct. Review evidence and the original resume before acting on the result.

## Test cases

Use the software developer sample PDF and sample JD to test analysis. Also test a blank TXT file, an unsupported file, a corrupted PDF, a scanned image-only PDF, a file over 5 MB, a resume with no email/education/experience, no job description, and a pasted job description. The backend includes focused logic tests in `backend/tests/test_logic.py`.

## Environment variables

| Name | Purpose |
|---|---|
| `GROQ_API_KEY` | Private Groq API credential; required for LLM analysis. |
| `GROQ_MODEL` | Groq model ID. Default: `openai/gpt-oss-20b`. |
| `FRONTEND_ORIGIN` | Allowed frontend origin for CORS; comma-separated origins are supported. |
| `MAX_UPLOAD_MB` | Upload size cap; default `5`. |
| `ENABLE_MINILM` | `true` loads the MiniLM embedding model for semantic RAG; `false` uses lexical retrieval. |
| `VITE_API_URL` | Frontend build-time base URL for the FastAPI service. |

## Known limitations

- Scanned/image-only PDFs need OCR, which is not included.
- This prototype analyzes resumes only and keeps uploads in memory; it does not persist uploaded documents or user history.
- MiniLM and PyTorch require substantially more memory and disk space and have a cold-load cost. The default lexical RAG avoids that deployment weight. On constrained free hosting, use `ENABLE_MINILM=false`.
- Groq account model availability and free-tier rate limits can change. A rate-limit or provider error is returned as a clear retry message.
- Keyword matching and summary evidence overlap are transparent heuristics, not formal ATS/ground-truth metrics.

## License and privacy

This is an assessment prototype. Do not commit API keys or real resumes. Uploaded content is processed in memory and is not written to disk by the API.

## Optional AI skills artwork

Set `CLOUDFLARE_ACCOUNT_ID` and `CLOUDFLARE_API_TOKEN` in `backend/.env`, then restart the backend. The token needs Account > Workers AI > Read permission. Keep it out of frontend environment variables and source control.

Click **Create skills visual** in the report. The backend uses `@cf/black-forest-labs/flux-1-schnell` with four diffusion steps. Only predefined skill-category names are sent, never resume text or personal details. Images are decorative; counts and category bars remain authoritative.

Generation runs separately from resume analysis with a 60-second timeout. A bounded in-memory cache reuses artwork for the same category set, and a generation lock avoids duplicate concurrent provider calls. The browser also caches up to eight images during the session. Errors do not affect the report. No database is required. Live generation needs valid Cloudflare credentials and available quota; free usage is not guaranteed. Before opening this prototype to public traffic, protect the image endpoint with authentication and per-user quotas to control provider spending.
## Browser report history

Completed analyses are saved in localStorage in the current browser (up to 20 reports). History lets you reopen and delete saved reports. Uploaded resumes separately stores original PDF/TXT documents in browser IndexedDB when selected, and supports preview, download and deletion. Deleting a document does not delete its analysis history, or vice versa. Reports remain after refresh and backend restarts; original documents persist separately in IndexedDB. Previously analyzed documents must be uploaded again to create a preview. History does not sync across devices, browser profiles, or site addresses. Clearing site data removes it. If browser storage is blocked or full, the app shows a warning and keeps changes in memory for the current page. No database service is required for the assessment demo.

## ATS readability and simpler skills chart

Skills charts show counts (for example, 3 skills), without percentages. Additional skills are entries outside the predefined categories. Expand a category to see its skills.

The ATS readability report checks extracted text, source-supported name/email, standard section headings and replacement characters. It provides the extracted text for manual reading-order review. It does not validate visual layout, tables, columns or compatibility with a specific employer parser, and provides no ATS score. Older saved reports require a new analysis to receive these checks.

## Completeness validation

A rule-based checklist covers name, email, skills, education and work experience. Each nonempty field with verified source evidence contributes 20% to completeness. Missing fields show an explicit no-data message. Unverifiable fields remain null and are marked Needs review, separately from missing data; they earn no completeness credit. A 100% result means all five fields were found, not that the resume or every extracted claim is correct.

## Screenshots

### Resume upload and job description

Upload a resume and add a target job description before starting the analysis.

![AlignCV resume upload and target job description](docs/screenshots/aligncv%201.png)

### Resume analysis and job comparison

Review summary evidence, resume completeness, and job requirements with expandable supporting evidence. The values shown are specific to the illustrated analysis.

![AlignCV analysis report and job description comparison](docs/screenshots/aligncv%202.png)
