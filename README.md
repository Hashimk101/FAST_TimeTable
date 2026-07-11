# FAST Timetable Generator

A full-stack application that dynamically parses, cleans, and generates personalized weekly timetables from FAST NUCES's highly unstructured schedule spreadsheets.

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
4. **Interactive Frontend:** A premium, responsive web interface allows users to select their batch, course, section, and specific subjects to instantly generate a personalized weekly timetable grid.

## Architecture

- **Backend:** Python, Flask, SQLite3, Google Sheets API
- **Frontend:** Vanilla HTML, CSS (Custom Dark/Light Themes), JavaScript
- **Deployment:** Ready for Vercel (via Serverless Functions using the included `vercel.json`)

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
5. Start the local server:
   ```bash
   python app.py
   ```
6. Open `http://127.0.0.1:5000` in your browser.
