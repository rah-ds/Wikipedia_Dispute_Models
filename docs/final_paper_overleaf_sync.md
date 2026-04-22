# Final paper / Overleaf sync

This branch keeps the paper itself in `final_paper/` so GitHub collaborators can browse and review the LaTeX sources directly.

The Overleaf project already exists, and Overleaf's native GitHub synchronization cannot connect an existing Overleaf project to an existing GitHub repository. Git remotes are also local-only configuration, so simply adding an `overleaf` remote would not be visible to collaborators on GitHub.

To bridge that gap, this branch adds a committed sync helper that copies the contents of `final_paper/` to and from the existing Overleaf Git project.

## Commands

```bash
make paper-overleaf-status
make paper-overleaf-diff
make paper-overleaf-pull
make paper-overleaf-push
```

All four commands accept these optional overrides:

```bash
OVERLEAF_FINAL_PAPER_URL=...
OVERLEAF_FINAL_PAPER_BRANCH=master
```

The default URL in the Makefile targets the current Overleaf project for this branch.

## Recommended workflow

1. Start by pulling the latest Overleaf changes into `final_paper/`:

   ```bash
   make paper-overleaf-pull
   ```

2. Review the resulting Git diff, then commit and push those updates to GitHub.

3. Make paper edits in `final_paper/` on `RH_4_6/final_paper`, commit them, and push the branch to GitHub so collaborators can review them.

4. Push the committed `final_paper/` state back to Overleaf:

   ```bash
   make paper-overleaf-push
   ```

The push command requires `final_paper/` to be clean in Git so that the GitHub branch stays the collaborator-visible source of truth.

## Why this workflow

- `final_paper/` stays as ordinary tracked files in this repository, so GitHub always shows the actual TeX and figures.
- The sync script works with an existing Overleaf project and does not rely on shared Git history.
- The script assumes a single Overleaf branch (default `master`), which matches Overleaf's Git limitations.
