# Data Directory

Store all project data in this directory.

## Structure

- `raw/` - Store original, immutable data. Never modify files in this directory.
- `processed/` - Store cleaned and transformed data ready for analysis.
- `external/` - Store data from third-party sources.

## Guidelines

Do not commit large data files (>50MB) to git. Use DVC (Data Version Control) or external storage (Google Drive, AWS S3) for large datasets.
