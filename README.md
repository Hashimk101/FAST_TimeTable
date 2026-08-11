# FAST Timetable Generator

A high-performance, edge-cached timetable application that dynamically parses, cleans, and generates personalized weekly timetables from FAST NUCES's highly unstructured schedule spreadsheets.

## The Problem

The university distributes its master timetable as a massive, heavily formatted spreadsheet. Navigating this sheet manually to extract a single student's schedule is incredibly frustrating due to several structural issues:

- **Download Restrictions:** Often, the university restricts the document so it cannot be exported, copied, or downloaded as a standard `.xlsx` file, forcing students to view the massive grid directly in the browser.
- **Irregular Formatting:** The spreadsheet is riddled with merged cells, missing headers, and inconsistent column arrangements.
- **Embedded Time Slots:** Instead of using dedicated time columns uniformly, time slots are frequently and randomly embedded directly within the subject strings (e.g., "Civics (A) 02:00-03:45").
- **Shorthand Inconsistencies:** Subject names frequently switch between full names and obscure shorthands across different cells.

## The Solution

This project bypasses the download restrictions and formatting chaos by programmatically extracting, normalizing, and serving the data.

1. **Direct API Extraction:** Instead of relying on a downloaded file, the application uses the Google Sheets API to authenticate and pull the raw grid data directly from the restricted live document.
2. **Data Normalization:** A Python pipeline parses the raw data, resolving merged cells, stripping out garbage data, mapping shorthands to full names, and using regex to extract embedded time slots from subject strings.
3. **Relational Storage:** The cleaned data is inserted into local SQLite databases (`uni_timetable.db` and `uni_timetable_lab.db`) with a strict schema, allowing for rapid, indexed querying.
4. **Static Edge Delivery:** Pre-generated, obfuscated binary schedule files are served directly from Vercel's Global CDN. All subject filtering happens client-side in the browser, enabling **50,000+ concurrent users** with sub-30ms response times.
5. **Interactive Frontend:** A premium, responsive web interface allows users to select their batch, course, section, and specific subjects to instantly generate a personalized weekly timetable grid.

## Architecture

```
Google Sheet (Read-Only)
    │
    ├── [Every 5 min] Google Apps Script polls for changes
    │       │
    │       └── If changed → Sends webhook to GitHub (repository_dispatch)
    │
    ├── GitHub Actions (triggered by webhook or manual)
    │       │
    │       ├── Pulls fresh data via Google Sheets API
    │       ├── Rebuilds SQLite databases
    │       ├── Generates 178 obfuscated static .bin files
    │       └── Commits & pushes to repo → Vercel auto-deploys
    │
    └── Vercel Global CDN
            │
            └── Students fetch static .bin files (10-30ms, no server compute)
                    │
                    └── Browser decodes & filters schedule locally (<1ms)
```

- **Data Pipeline:** Python, Google Sheets API, SQLite3
- **Frontend:** Vanilla HTML, CSS (Custom Dark/Light Themes), JavaScript
- **Automation:** Google Apps Script (standalone polling), GitHub Actions
- **Deployment:** Vercel (Static CDN, zero serverless functions needed)
- **Data Protection:** Base64 + string-reversal obfuscation on all schedule files

## Performance

| Metric | Old (Flask API) | New (Static CDN) |
|---|---|---|
| Max Concurrent Users | ~50 | **50,000+** |
| Response Time | 500ms - 3,000ms | **10-30ms** |
| Downtime During Updates | ~5-10s | **0 seconds** |
| Monthly Cost | $0 | **$0** |
| Bandwidth Capacity | Limited by serverless | **~740,000 unique students/month** |

## Getting Started

### Prerequisites
- Python 3.x
- A Google Cloud Platform account with the Google Sheets API enabled. You will need an OAuth `credentials.json` file.

### Installation
1. Clone the repository.
2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
3. Place your `credentials.json` in the root directory.
4. (Optional) Run the data extraction scripts if you need to pull fresh data from the Google Sheet and rebuild the SQLite databases.
5. Generate the static data files:
   ```bash
   python generate_static_json.py
   ```
6. Serve the frontend locally:
   ```bash
   python -m http.server 8080 --directory frontend
   ```
7. Open `http://127.0.0.1:8080` in your browser.

## Auto-Sync Setup

The application automatically syncs with the university's Google Sheet using a two-part system:

1. **Google Apps Script (Polling):** A standalone script on `script.google.com` checks the sheet every 5 minutes. If changes are detected, it sends a `repository_dispatch` webhook to GitHub.
2. **GitHub Actions (Build & Deploy):** On receiving the webhook, a GitHub Action rebuilds the databases, regenerates the static files, and pushes them to the repo — triggering an automatic Vercel deployment.

### Required GitHub Secrets
| Secret Name | Value |
|---|---|
| `GOOGLE_CREDENTIALS` | Contents of `credentials.json` |
| `GOOGLE_TOKEN` | Contents of `token.json` |

## Troubleshooting

### ⚠️ GitHub Action failing after a while?

The Google OAuth token stored in `GOOGLE_TOKEN` can expire if:
- You change your Google password
- You revoke app access from your Google account
- The token hasn't been refreshed in ~6 months

**Fix:** Re-run `rebuild_subjects.py` locally to trigger a fresh OAuth login and regenerate `token.json`. Then update the `GOOGLE_TOKEN` secret on GitHub with the new file contents.

```bash
python rebuild_subjects.py
# This will open a browser window to re-authenticate
# After success, copy the new token.json contents to GitHub Secrets
```

### Static data not updating?

1. Check the **Actions** tab on GitHub to see if the workflow ran successfully.
2. If the workflow didn't trigger, go to **Actions > Auto Sync Timetable Static Data > Run workflow** to trigger it manually.
3. Verify the Google Apps Script is still active at [script.google.com](https://script.google.com/).
