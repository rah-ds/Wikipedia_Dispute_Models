# Zotero Citation Manager

We should probably use this to keep track of information.

Zotero [zoh-TAIR-oh] is a free reference manager for collecting, organizing, citing, and sharing research sources.

---

## Installation

1. Download Zotero from <https://www.zotero.org/download>
2. Install the **Zotero Connector** browser extension (Chrome, Firefox, Edge, or Safari)
3. Create a free account at <https://www.zotero.org/user/register> for syncing

---

## Adding References

### From Web Browser (Recommended)

The Zotero Connector automatically detects bibliographic data on webpages:

| Icon | Source Type |
| ---- | ----------- |
| 📄 | Journal article |
| 📕 | Book |
| 📁 | Multiple items (select which to save) |
| 🌐 | Generic webpage |

Click the icon in your browser toolbar to save the reference and download the PDF if available.

### By Identifier

Click the "Add Item by Identifier" button (magic wand icon) and enter:

- **DOI** — `10.1000/xyz123`
- **ISBN** — `978-0-123456-78-9`
- **PubMed ID** — `12345678`
- **arXiv ID** — `arXiv:1234.5678`

Zotero retrieves metadata automatically from CrossRef, Library of Congress, PubMed, and arXiv.

### Drag and Drop PDFs

Drag a PDF into Zotero. It will attempt to extract metadata automatically. If unsuccessful:

1. Right-click the PDF → **Create Parent Item**
2. Enter a DOI or ISBN, or select **Manual Entry**

---

## Organizing Your Library

### Collections

Create folders (collections) for projects or topics. Items can belong to multiple collections—they're aliases, not copies.

- Right-click **My Library** → **New Collection**
- Drag items into collections

### Tags

Assign tags for flexible categorization:

- Add via the **Tags** tab in the right pane
- Assign colors to up to 6 tags for quick visual identification
- Use number keys (1-6) to quickly toggle colored tags

### Search

- **Quick search**: Type in the search bar (searches metadata, tags, full text)
- **Advanced search**: Click the magnifying glass for complex queries
- **Saved searches**: Save searches as dynamic collections that auto-update

---

## Citing in Documents

### Word Processor Plugins

Zotero integrates with:

- Microsoft Word
- LibreOffice
- Google Docs

**Insert citation**:

1. Place cursor where you want the citation
2. Click **Add/Edit Citation** in the Zotero toolbar
3. Search for and select the reference

**Insert bibliography**:

1. Place cursor at end of document
2. Click **Add/Edit Bibliography**

### Citation Styles

Zotero supports 10,000+ citation styles (CSL):

- Chicago, MLA, APA, Vancouver, IEEE, etc.
- Journal-specific styles

Change styles: **Document Preferences** → Select style

### Quick Copy (Manual)

For any text field:

1. Select items in Zotero
2. Press `Ctrl+Shift+C` (Windows) or `Cmd+Shift+C` (Mac)
3. Paste the formatted citation/bibliography

Or drag items directly into any text field.

---

## Exporting References

### Export Formats

Right-click items → **Export Items**:

| Format | Use Case |
| ------ | -------- |
| BibTeX | LaTeX documents |
| RIS | Import to other managers |
| CSL JSON | Programmatic use |
| Zotero RDF | Full backup with attachments |

### Better BibTeX Plugin

For LaTeX users, install [Better BibTeX](https://retorque.re/zotero-better-bibtex/):

- Generates stable citation keys
- Auto-exports `.bib` files on changes
- Integrates with Overleaf

**Installation**:

1. Download from <https://retorque.re/zotero-better-bibtex/installation/>
2. In Zotero: **Tools** → **Add-ons** → **Install Add-on From File**

**Auto-export to `.bib` file**:

1. Right-click a collection → **Export Collection**
2. Select **Better BibTeX** format
3. Check **Keep updated** → Choose save location
4. The `.bib` file auto-updates when you add/edit references

**In your LaTeX document**:

```latex
\documentclass{article}
\usepackage[backend=biber]{biblatex}
\addbibresource{references.bib}  % your exported file

\begin{document}
According to \cite{smith2024}, Wikipedia disputes follow...

\printbibliography
\end{document}
```

**Citation keys**: Better BibTeX generates keys like `smith2024` or `smith_wikipedia_2024`. Customize the format in **Zotero Preferences** → **Better BibTeX** → **Citation keys**.

---

## Syncing and Collaboration

### Sync Settings

**Edit** → **Preferences** → **Sync**:

- Library metadata syncs free (unlimited)
- File syncing: 300 MB free, or use WebDAV

### Group Libraries

Create shared libraries for team research:

1. Go to <https://www.zotero.org/groups>
2. Create group → Invite members
3. Group appears in Zotero's left pane

---

## Best Practices

1. **Save from source pages** — Import from publisher/database pages, not Google Scholar, for better metadata
2. **Verify metadata** — Always check imported data for accuracy
3. **Use sentence case for titles** — Zotero can convert to title case; the reverse is unreliable
4. **Store abbreviations with periods** — e.g., "J. Am. Chem. Soc." (Zotero strips periods when needed)
5. **Organize early** — Create collections and tags as you collect, not after

---

## Sources

1. Zotero. "Quick Start Guide." <https://www.zotero.org/support/quick_start_guide>
2. Zotero. "Adding Items to Zotero." <https://www.zotero.org/support/getting_stuff_into_your_library>
3. Zotero. "Word Processor Integration." <https://www.zotero.org/support/word_processor_integration>
4. Zotero. "Citation Styles." <https://www.zotero.org/styles>
