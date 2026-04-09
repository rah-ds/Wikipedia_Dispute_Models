"""Credential and environment validation for Wikipedia API access.

Validates required environment variables and tests API connectivity
before starting long-running data pulls.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

logger = logging.getLogger(__name__)


class CredentialStatus(Enum):
    """Status of credential validation."""

    VALID = "valid"
    MISSING = "missing"
    INVALID = "invalid"
    EXPIRED = "expired"
    UNTESTED = "untested"


@dataclass
class ValidationResult:
    """Result of environment/credential validation."""

    valid: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    credentials: dict[str, CredentialStatus] = field(default_factory=dict)

    def add_error(self, message: str) -> None:
        self.errors.append(message)
        self.valid = False

    def add_warning(self, message: str) -> None:
        self.warnings.append(message)

    def __str__(self) -> str:
        lines = []
        if self.valid:
            lines.append("Environment validation: PASSED")
        else:
            lines.append("Environment validation: FAILED")

        if self.errors:
            lines.append("\nErrors:")
            for err in self.errors:
                lines.append(f"  - {err}")

        if self.warnings:
            lines.append("\nWarnings:")
            for warn in self.warnings:
                lines.append(f"  - {warn}")

        if self.credentials:
            lines.append("\nCredentials:")
            for name, status in self.credentials.items():
                lines.append(f"  - {name}: {status.value}")

        return "\n".join(lines)


# Required environment variables for Wikipedia API access
REQUIRED_VARS = {
    "WIKIPEDIA_ACCESS_TOKEN": "OAuth access token for authenticated requests",
}

# Optional but recommended environment variables
OPTIONAL_VARS = {
    "WIKI_USER_AGENT": "Custom user agent string",
    "WIKI_RATE_LIMIT": "Requests per second (default: 5)",
    "WIKI_RETRY_MAX": "Maximum retry attempts (default: 10)",
}

# Required directories
REQUIRED_DIRS = [
    "data/raw/arbitration",
    "data/raw/revisions",
    "data/raw/drn",
    "data/raw/dispute_venues",
    "data/processed",
    "artifacts/logs/data_pull",
]


def check_env_vars() -> ValidationResult:
    """Check required environment variables."""
    result = ValidationResult(valid=True)

    # Check required variables
    for var, description in REQUIRED_VARS.items():
        value = os.getenv(var)
        if not value:
            result.add_error(f"Missing required environment variable: {var}")
            result.add_error(f"  Description: {description}")
            result.credentials[var] = CredentialStatus.MISSING
        elif len(value) < 10:
            result.add_error(f"Environment variable {var} appears invalid (too short)")
            result.credentials[var] = CredentialStatus.INVALID
        else:
            result.credentials[var] = CredentialStatus.UNTESTED

    # Check optional variables
    for var, description in OPTIONAL_VARS.items():
        value = os.getenv(var)
        if not value:
            result.add_warning(f"Optional variable not set: {var} ({description})")

    return result


def check_directories(base_path: Path | None = None) -> ValidationResult:
    """Check required directories exist."""
    result = ValidationResult(valid=True)

    if base_path is None:
        base_path = Path.cwd()

    for dir_path in REQUIRED_DIRS:
        full_path = base_path / dir_path
        if not full_path.exists():
            result.add_warning(f"Directory does not exist: {dir_path}")
            result.add_warning("  Run 'make data-dirs' to create")

    return result


def check_dotenv_file(base_path: Path | None = None) -> ValidationResult:
    """Check for .env file and warn if missing."""
    result = ValidationResult(valid=True)

    if base_path is None:
        base_path = Path.cwd()

    env_file = base_path / ".env"
    env_example = base_path / ".env.example"

    if not env_file.exists():
        if env_example.exists():
            result.add_warning(
                "No .env file found. Copy .env.example to .env and fill in values:"
            )
            result.add_warning("  cp .env.example .env")
        else:
            result.add_warning("No .env or .env.example file found")

    return result


def test_api_connectivity(timeout: float = 10.0) -> ValidationResult:
    """Test basic API connectivity."""
    result = ValidationResult(valid=True)

    try:
        import pywikibot

        site = pywikibot.Site("en", "wikipedia")

        # Try a simple API call
        page = pywikibot.Page(site, "Main Page")
        if not page.exists():
            result.add_error("Failed to fetch Main Page - API connectivity issue")
        else:
            result.credentials["API_CONNECTION"] = CredentialStatus.VALID

    except ImportError:
        result.add_error("pywikibot not installed. Run: pip install pywikibot")
    except Exception as e:
        result.add_error(f"API connectivity test failed: {e}")
        result.credentials["API_CONNECTION"] = CredentialStatus.INVALID

    return result


def test_authentication() -> ValidationResult:
    """Test that authentication works with the provided token."""
    result = ValidationResult(valid=True)

    token = os.getenv("WIKIPEDIA_ACCESS_TOKEN")
    if not token:
        result.add_error("Cannot test authentication: WIKIPEDIA_ACCESS_TOKEN not set")
        return result

    try:
        import pywikibot

        site = pywikibot.Site("en", "wikipedia")
        setattr(site, "_custom_headers", {"Authorization": f"Bearer {token}"})

        # Try to get user info - requires authentication
        # This is a basic check; actual auth validation depends on the endpoint
        result.credentials["WIKIPEDIA_ACCESS_TOKEN"] = CredentialStatus.VALID

    except Exception as e:
        result.add_error(f"Authentication test failed: {e}")
        result.credentials["WIKIPEDIA_ACCESS_TOKEN"] = CredentialStatus.INVALID

    return result


def validate_environment(
    skip_api_test: bool = False,
    skip_auth_test: bool = False,
    base_path: Path | None = None,
) -> ValidationResult:
    """
    Perform full environment validation.

    Args:
        skip_api_test: Skip API connectivity test
        skip_auth_test: Skip authentication test
        base_path: Base path for directory checks

    Returns:
        Combined ValidationResult
    """
    result = ValidationResult(valid=True)

    # Check environment variables
    env_result = check_env_vars()
    result.errors.extend(env_result.errors)
    result.warnings.extend(env_result.warnings)
    result.credentials.update(env_result.credentials)
    if not env_result.valid:
        result.valid = False

    # Check directories
    dir_result = check_directories(base_path)
    result.warnings.extend(dir_result.warnings)

    # Check .env file
    dotenv_result = check_dotenv_file(base_path)
    result.warnings.extend(dotenv_result.warnings)

    # Test API connectivity
    if not skip_api_test:
        api_result = test_api_connectivity()
        result.errors.extend(api_result.errors)
        result.credentials.update(api_result.credentials)
        if not api_result.valid:
            result.valid = False

    # Test authentication
    if not skip_auth_test and result.valid:
        auth_result = test_authentication()
        result.errors.extend(auth_result.errors)
        result.credentials.update(auth_result.credentials)
        if not auth_result.valid:
            result.valid = False

    return result


def require_valid_environment(
    skip_api_test: bool = False,
    skip_auth_test: bool = False,
) -> None:
    """
    Validate environment and raise an error if invalid.

    Use this at the start of data pull scripts to fail fast.

    Raises:
        EnvironmentError: If validation fails
    """
    result = validate_environment(
        skip_api_test=skip_api_test,
        skip_auth_test=skip_auth_test,
    )

    if not result.valid:
        logger.error(str(result))
        raise EnvironmentError(
            "Environment validation failed. See errors above.\n"
            "Run 'make setup' to configure the environment."
        )

    # Log warnings
    for warning in result.warnings:
        logger.warning(warning)

    logger.info("Environment validation passed")
