# Data Directory

This directory contains all data for the project.

## Structure

- `raw/` - Original, immutable data dump. Never edit these files.
- `processed/` - Cleaned and transformed data ready for analysis.
- `external/` - Data from third-party sources.

## Note

Large data files should NOT be committed to git. Add them to `.gitignore` if they exceed 50MB.
Consider using DVC (Data Version Control) or storing data externally (Google Drive, AWS S3, etc.).
