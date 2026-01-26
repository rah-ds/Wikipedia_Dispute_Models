# Contributing Guidelines

Thank you for contributing to the Wikipedia Dispute Models project!

## Development Workflow

### Branch Strategy

- `main` - Production-ready code
- `develop` - Integration branch for features
- `feature/<name>` - Individual feature branches
- Use descriptive branch names: `feature/data-preprocessing`, `fix/model-bug`

### Making Changes

1. **Create a new branch** from `develop`:
   ```bash
   git checkout develop
   git pull origin develop
   git checkout -b feature/your-feature-name
   ```

2. **Make your changes** following the project structure and coding standards

3. **Test your changes**:
   ```bash
   pytest tests/
   ```

4. **Commit your changes** with clear, descriptive messages:
   ```bash
   git add .
   git commit -m "Add feature: brief description"
   ```

5. **Push your branch** and create a Pull Request:
   ```bash
   git push origin feature/your-feature-name
   ```

### Commit Message Guidelines

- Use present tense ("Add feature" not "Added feature")
- Be descriptive but concise
- Reference issues when applicable: "Fix #123: Description"

Examples:
- `Add data preprocessing pipeline`
- `Update model evaluation metrics`
- `Fix: Resolve data loading bug`

## Code Standards

### Python Code

- Follow PEP 8 style guide
- Use meaningful variable and function names
- Add docstrings to functions and classes
- Keep functions focused and modular

### Jupyter Notebooks

- Clear all outputs before committing: `Restart & Clear Output`
- Use markdown cells to explain your analysis
- Follow the naming convention in `notebooks/README.md`
- Keep notebooks focused on a single task or analysis

### Data Management

- **Never commit large data files** (>50MB) to git
- Document data sources and acquisition steps
- Store raw data in `data/raw/` (immutable)
- Store processed data in `data/processed/`

## Communication

- Use GitHub Issues for bugs, features, and tasks
- Tag relevant team members using @mentions
- Update project board/milestones regularly
- Have regular sync meetings (weekly recommended)

## Code Review

- All changes require at least one review before merging
- Be constructive and respectful in reviews
- Address review comments promptly
- Use "Request Changes" only for critical issues

## Project Organization

### Notebook Naming

Include your initials and a sequence number:
- `01_jd_initial_exploration.ipynb`
- `02_as_feature_engineering.ipynb`

### Function/Module Organization

- Keep reusable code in `src/` modules
- Import from `src/` in notebooks: `from src.utils import load_data`
- Write unit tests for `src/` code in `tests/`

## Questions?

If you're unsure about anything, don't hesitate to ask the team!
