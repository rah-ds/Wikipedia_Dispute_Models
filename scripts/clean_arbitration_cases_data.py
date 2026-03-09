import json
import re
import os
import mwparserfromhell

HEADERS = [
    "Case Opened",
    "Case Closed",
    "Involved Parties",
    "Confirmation that all parties are aware of the request",
    "Confirmation that other steps",
    "Requests for comment",
    "Statement by",
    "Preliminary decisions",
    "Final decision",
    "Findings of Fact",
    "Remedies",
    "Enforcement",
]


def clean_wiki_text(text):
    """Remove wiki markup and templates, returning clean text."""
    wikicode = mwparserfromhell.parse(text)
    return wikicode.strip_code().strip()


def extract_subsections_remedies(remedies_text):
    """
    Extract 'note' before first subheader and all subsections under '===Subheader==='
    until the marker '=Proposed enforcement=' (any level of '=' surrounding),
    or end of text.

    Returns dict:
    {
      "note": "text before first subheader",
      "subsections": {
          "Subheader1": "text...",
          "Subheader2": "text...",
          ...
      }
    }
    """
    # Find '=Proposed enforcement=' header line (any number of =)
    enforcement_match = re.search(
        r"\n=+ *Proposed enforcement *={1,}\n", remedies_text, flags=re.IGNORECASE
    )
    if enforcement_match:
        remedies_text = remedies_text[: enforcement_match.start()]

    # Split text by subheaders '=== Subheader ==='
    parts = re.split(r"(===\s*[^=]+?\s*===)", remedies_text)

    note = ""
    subsections = {}

    if len(parts) == 1:
        # No subheaders found: all text is note
        note = clean_wiki_text(parts[0])
    else:
        note = clean_wiki_text(parts[0])
        # Subsequent pairs are header-content
        for i in range(1, len(parts), 2):
            header_raw = parts[i].strip("= \n")
            content_raw = parts[i + 1] if i + 1 < len(parts) else ""
            subsections[header_raw] = clean_wiki_text(content_raw)

    return {"note": note, "subsections": subsections}


def extract_sections(text, headers=HEADERS):
    # Build regex for headers: match header value anywhere in the line, after any markup, HTML, template, or at line start, with optional bold/italic, and allow trailing text
    header_patterns = [rf"(?:^|\n).*?{re.escape(h)}[^\n]*" for h in headers]
    header_regex = re.compile("|".join(header_patterns), re.IGNORECASE)

    matches = []
    for match in header_regex.finditer(text):
        for idx, h in enumerate(headers):
            if re.search(rf"{re.escape(h)}", match.group(0), re.IGNORECASE):
                matches.append((match.start(), idx, match.group(0)))
                break
    matches.sort()
    matches.append((len(text), None, None))

    result = {h: None for h in headers}
    for i, (start, idx, _) in enumerate(matches[:-1]):
        end = matches[i + 1][0]
        section_start = text.find("\n", start)
        if section_start == -1 or section_start > end:
            section_start = start
        else:
            section_start += 1
        value = text[section_start:end].strip()
        header = headers[idx]
        result[header] = value if value else None
    return result


def list_raw_files(folder="data/raw/arbitration"):
    files = [
        f
        for f in os.listdir(folder)
        if f.startswith("arbitration_cases_") and f.endswith(".json")
    ]
    files.sort()
    return files


def process_file(input_path, output_path):
    with open(input_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    results = []
    for case in data:
        title = case.get("title", "no_title").replace("/", "_").replace(" ", "_")
        url = case.get("url", "")
        for rev in case.get("revisions", []):
            timestamp = rev.get("timestamp", "").replace(":", "-")
            text = rev.get("text", "")
            sections = extract_sections(text)
            results.append(
                {
                    "title": title,
                    "url": url,
                    "timestamp": timestamp,
                    "full_text": text,
                    "sections": sections,
                }
            )
    with open(output_path, "w", encoding="utf-8") as out_f:
        json.dump(results, out_f, indent=2, ensure_ascii=False)
    print(f"Saved cleaned data to {output_path}")


if __name__ == "__main__":
    raw_folder = "data/raw/arbitration"
    processed_folder = "data/processed"
    os.makedirs(processed_folder, exist_ok=True)

    files = list_raw_files(raw_folder)
    if not files:
        print(f"No files found in {raw_folder}")
        exit()

    print("Select a file to process:")
    for i, f in enumerate(files, 1):
        print(f"{i}. {f}")

    choice = input(f"Enter a number (1-{len(files)}): ").strip()
    if not choice.isdigit() or not (1 <= int(choice) <= len(files)):
        print("Invalid choice.")
        exit()

    selected_file = files[int(choice) - 1]
    print(f"Processing file: {selected_file}")

    m = re.search(r"arbitration_cases_(\d{8}_\d{6})\.json", selected_file)
    datepart = m.group(1) if m else "unknown_date"

    input_path = os.path.join(raw_folder, selected_file)
    output_filename = f"clean_arbitration_cases_{datepart}.json"
    output_path = os.path.join(processed_folder, output_filename)

    process_file(input_path, output_path)
