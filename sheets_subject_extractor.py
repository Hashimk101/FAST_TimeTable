import re
from collections import OrderedDict
from databaseHandler import get_sheets_service, days_of_week

SPREADSHEET_ID = "1ZQJqdArlwCS965uw4sbJrB6j8rEPfZerMT7X8qkXSzY"

def normalize_color(color_dict: dict) -> tuple:
    """Converts Google Sheets API backgroundColor float dict (0.0-1.0) to RGB tuple (0-255)."""
    if not color_dict:
        return (255, 255, 255)
    r = int(round(color_dict.get('red', 0.0) * 255))
    g = int(round(color_dict.get('green', 0.0) * 255))
    b = int(round(color_dict.get('blue', 0.0) * 255))
    return (r, g, b)

def rgb_to_hex(rgb: tuple) -> str:
    return f"#{rgb[0]:02X}{rgb[1]:02X}{rgb[2]:02X}"

def generate_short_name(full_name: str) -> str:
    """Generates an auto-acronym for a subject name (e.g. 'Object Oriented Programming' -> 'OOP')."""
    name = full_name.strip()
    if not name:
        return ""
    
    is_lab = False
    if re.search(r'(?i)\s*-?\s*lab$', name):
        is_lab = True
        name = re.sub(r'(?i)\s*-?\s*lab$', '', name).strip()

    stop_words = {"and", "of", "to", "in", "for", "the", "with", "on"}
    words = [w for w in re.split(r'[\s\-_]+', name) if w]

    if not words:
        acronym = full_name[:4].upper()
    elif len(words) == 1:
        acronym = words[0]
    else:
        meaningful_words = [w for w in words if w.lower() not in stop_words]
        if not meaningful_words:
            meaningful_words = words
        acronym = "".join(w[0].upper() for w in meaningful_words)

    if is_lab and not acronym.lower().endswith("lab"):
        acronym += " Lab"

    return acronym

def is_color_similar(c1: tuple, c2: tuple, tolerance: int = 15) -> bool:
    """Checks if two RGB tuples are within a tolerance threshold."""
    return abs(c1[0] - c2[0]) <= tolerance and abs(c1[1] - c2[1]) <= tolerance and abs(c1[2] - c2[2]) <= tolerance

def extract_subjects_and_batches_from_api(spreadsheet_id: str = SPREADSHEET_ID):
    """
    Reads grid data from Google Sheets API, extracts legend batch colors from rows 1-4,
    gathers all scheduled subjects using an O(n) hashmap method (splitting before '('),
    and maps each subject to its offering batch(es) based on cell color matching.
    """
    service = get_sheets_service()
    print("Fetching grid data from Google Sheets API with includeGridData=True...")
    
    # Request grid data for all day sheets
    response = service.spreadsheets().get(
        spreadsheetId=spreadsheet_id,
        ranges=days_of_week,
        includeGridData=True
    ).execute()

    sheets = response.get('sheets', [])

    # Step 1: Extract Legend Batch Colors from rows 1-4 of the first sheet (e.g. Monday)
    # Legend structure: (Batch Name, RGB Tuple, Hex String)
    legend_batches = [] # List of dicts to preserve legend order
    legend_color_map = {} # RGB -> Batch Name

    if sheets:
        monday_data = sheets[0]['data'][0].get('rowData', [])
        # Rows 1 to 4 (index 0 to 3)
        for row_idx in range(min(4, len(monday_data))):
            row_cells = monday_data[row_idx].get('values', [])
            for cell in row_cells:
                val = cell.get('formattedValue', '').strip()
                if not val or val == "Room" or val == "Lab" or "TimeTable" in val or "FSC" in val:
                    continue
                
                # Filter out pure timeslot header strings if any
                if re.match(r'^\d{2}:\d{2}', val):
                    continue

                effective_format = cell.get('effectiveFormat', {})
                bg_color_dict = effective_format.get('backgroundColor', {})
                rgb = normalize_color(bg_color_dict)

                # Skip white/unfilled background
                if is_color_similar(rgb, (255, 255, 255), tolerance=5):
                    continue

                hex_code = rgb_to_hex(rgb)
                
                # Check if batch is already in list
                if not any(b['name'] == val for b in legend_batches):
                    legend_batches.append({
                        'name': val,
                        'rgb': rgb,
                        'hex': hex_code
                    })
                    legend_color_map[rgb] = val

    print(f"Extracted {len(legend_batches)} batch categories from top 4 rows legend:")
    for b in legend_batches:
        print(f"  - {b['name']}: RGB{b['rgb']} / {b['hex']}")

    # Step 2: Gather all unique subjects and match them with batches in O(n) pass
    unique_subjects = OrderedDict() # subject_name -> short_name
    batch_subject_links = set() # (batch_name, subject_name) tuples

    # Ignore list for schedule cell parsing
    ignore_keywords = {"room", "lab", "nil", "day", "monday", "tuesday", "wednesday", "thursday", "friday", "timetable"}

    for sheet in sheets:
        sheet_title = sheet['properties']['title']
        grid = sheet['data'][0].get('rowData', [])

        # Process grid rows starting after the header (row index 4 onwards)
        for r_idx in range(4, len(grid)):
            row_cells = grid[r_idx].get('values', [])
            for cell in row_cells:
                raw_val = cell.get('formattedValue', '').strip()
                if not raw_val or raw_val.lower() in ignore_keywords:
                    continue
                
                # Ignore timeslot headers
                if re.match(r'^\d{2}:\d{2}', raw_val):
                    continue
                
                # Ignore section-only or room-only labels
                if raw_val.startswith("Room") or raw_val.startswith("Lab"):
                    continue

                # O(n) Hashmap extraction: Split before '(' opening brace
                parts = raw_val.split('(', 1)
                subject_name = parts[0].strip()
                
                # Additional cleanup for multiline text or garbage
                if '\n' in subject_name:
                    subject_name = subject_name.split('\n')[0].strip()

                if not subject_name or subject_name.lower() in ignore_keywords or len(subject_name) < 2:
                    continue

                # Store in unique subjects hashmap
                if subject_name not in unique_subjects:
                    short = generate_short_name(subject_name)
                    unique_subjects[subject_name] = short

                # Step 3: Cell Color Matching against Batch Legend
                effective_format = cell.get('effectiveFormat', {})
                bg_color_dict = effective_format.get('backgroundColor', {})
                cell_rgb = normalize_color(bg_color_dict)

                # Skip white/unfilled cells
                if is_color_similar(cell_rgb, (255, 255, 255), tolerance=5):
                    continue

                # Find matching batch by color
                matched_batch = None
                for legend_b in legend_batches:
                    if is_color_similar(cell_rgb, legend_b['rgb'], tolerance=25):
                        matched_batch = legend_b['name']
                        break

                if matched_batch:
                    batch_subject_links.add((matched_batch, subject_name))

    print(f"\nExtracted {len(unique_subjects)} unique subjects across all day sheets using O(n) hashmap.")
    print(f"Extracted {len(batch_subject_links)} batch-subject links.")

    return legend_batches, unique_subjects, list(batch_subject_links)

if __name__ == "__main__":
    batches, subjects, links = extract_subjects_and_batches_from_api()
    print("\nSample Subjects & Short Names:")
    for name, short in list(subjects.items())[:10]:
        print(f"  - {name} -> {short}")
