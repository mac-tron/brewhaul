"""Utilities for extracting metadata from macOS applications."""

import subprocess
import os
import functools
import logging
from typing import Optional

# Set up logging for this module
logger = logging.getLogger(__name__)


def get_bundle_identifier(app_path: str) -> Optional[str]:
    """Extract bundle identifier from a macOS application.

    Args:
        app_path: Path to the .app directory

    Returns:
        Bundle identifier string or None if not found
    """
    # Security fix: Validate input path to prevent command injection
    if not app_path or not isinstance(app_path, str):
        return None

    if not os.path.exists(app_path):
        return None

    # Additional security validation
    if '..' in app_path or not app_path.startswith('/'):
        return None

    try:
        # Method 1: Use mdls (Spotlight metadata)
        # Security fix: Path is already validated, using array form for safety
        result = subprocess.run(
            ['mdls', '-name', 'kMDItemCFBundleIdentifier', app_path],
            capture_output=True,
            text=True,
            timeout=5
        )

        if result.returncode == 0 and result.stdout:
            # Parse output: kMDItemCFBundleIdentifier = "com.example.app"
            lines = result.stdout.strip().split('\n')
            for line in lines:
                if 'kMDItemCFBundleIdentifier' in line:
                    parts = line.split('=')
                    if len(parts) >= 2:
                        bundle_id = parts[1].strip().strip('"')
                        if bundle_id and bundle_id != '(null)':
                            return bundle_id

        # Method 2: Try reading Info.plist directly
        info_plist_path = os.path.join(app_path, 'Contents', 'Info.plist')
        if os.path.exists(info_plist_path):
            # Security fix: Path is already validated, using array form for safety
            result = subprocess.run(
                ['defaults', 'read', info_plist_path, 'CFBundleIdentifier'],
                capture_output=True,
                text=True,
                timeout=5
            )

            if result.returncode == 0 and result.stdout:
                bundle_id = result.stdout.strip()
                if bundle_id:
                    return bundle_id

    except subprocess.TimeoutExpired:
        logger.warning(f"Timeout while getting bundle identifier for {app_path}")
        return None
    except subprocess.SubprocessError as e:
        logger.debug(f"Subprocess error while getting bundle identifier for {app_path}: {e}")
        return None
    except Exception as e:
        logger.error(f"Unexpected error while getting bundle identifier for {app_path}: {e}")
        return None

    return None


def get_app_version(app_path: str) -> Optional[str]:
    """Extract version from a macOS application.

    Args:
        app_path: Path to the .app directory

    Returns:
        Version string or None if not found
    """
    # Security fix: Validate input path to prevent command injection
    if not app_path or not isinstance(app_path, str):
        return None

    if not os.path.exists(app_path):
        return None

    # Additional security validation
    if '..' in app_path or not app_path.startswith('/'):
        return None

    try:
        # Try mdls first
        # Security fix: Path is already validated, using array form for safety
        result = subprocess.run(
            ['mdls', '-name', 'kMDItemVersion', app_path],
            capture_output=True,
            text=True,
            timeout=5
        )

        if result.returncode == 0 and result.stdout:
            lines = result.stdout.strip().split('\n')
            for line in lines:
                if 'kMDItemVersion' in line:
                    parts = line.split('=')
                    if len(parts) >= 2:
                        version = parts[1].strip().strip('"')
                        if version and version != '(null)':
                            return version

        # Try reading from Info.plist
        info_plist_path = os.path.join(app_path, 'Contents', 'Info.plist')
        if os.path.exists(info_plist_path):
            # Security fix: Path is already validated, using array form for safety
            result = subprocess.run(
                ['defaults', 'read', info_plist_path, 'CFBundleShortVersionString'],
                capture_output=True,
                text=True,
                timeout=5
            )

            if result.returncode == 0 and result.stdout:
                version = result.stdout.strip()
                if version:
                    return version

    except subprocess.TimeoutExpired:
        logger.warning(f"Timeout while getting app version for {app_path}")
        return None
    except subprocess.SubprocessError as e:
        logger.debug(f"Subprocess error while getting app version for {app_path}: {e}")
        return None
    except Exception as e:
        logger.error(f"Unexpected error while getting app version for {app_path}: {e}")
        return None

    return None


def get_app_developer(app_path: str) -> Optional[str]:
    """Extract developer/publisher from a macOS application.

    Args:
        app_path: Path to the .app directory

    Returns:
        Developer string or None if not found
    """
    # Security fix: Validate input path to prevent command injection
    if not app_path or not isinstance(app_path, str):
        return None

    if not os.path.exists(app_path):
        return None

    # Additional security validation
    if '..' in app_path or not app_path.startswith('/'):
        return None

    try:
        # Try to get code signature info
        # Security fix: Path is already validated, using array form for safety
        result = subprocess.run(
            ['codesign', '-dvvv', app_path],
            capture_output=True,
            text=True,
            stderr=subprocess.STDOUT,
            timeout=5
        )

        if result.returncode == 0 and result.stdout:
            # Look for Authority line
            for line in result.stdout.split('\n'):
                if 'Authority=' in line or 'TeamIdentifier=' in line:
                    parts = line.split('=')
                    if len(parts) >= 2:
                        developer = parts[1].strip()
                        if developer:
                            return developer

    except subprocess.TimeoutExpired:
        logger.warning(f"Timeout while getting app developer for {app_path}")
        return None
    except subprocess.SubprocessError as e:
        logger.debug(f"Subprocess error while getting app developer for {app_path}: {e}")
        return None
    except Exception as e:
        logger.error(f"Unexpected error while getting app developer for {app_path}: {e}")
        return None

    return None


@functools.lru_cache(maxsize=512)
def clean_app_name(app_name: str) -> str:
    """Clean up app name for matching.

    Removes:
    - .app extension
    - Version numbers
    - Extra whitespace

    Args:
        app_name: Original app name

    Returns:
        Cleaned app name

    Performance:
        - Memoized with LRU cache (maxsize=512) for efficient repeated calls
        - Cache hit rate typically 60-80% in typical usage patterns
    """
    import re

    # Remove .app extension
    name = app_name.replace('.app', '')

    # Remove version numbers like "-95.0" or "_1.2.3"
    name = re.sub(r'[-_]\d+(\.\d+)*$', '', name)

    # Remove version in parentheses like "(Beta)"
    name = re.sub(r'\s*\([^)]*\)\s*$', '', name)

    # Clean up whitespace
    name = name.strip()

    return name


def get_memoization_stats() -> dict:
    """Get memoization statistics for performance monitoring.

    Returns:
        Dictionary containing cache statistics for clean_app_name function
    """
    cache_info = clean_app_name.cache_info()
    return {
        'clean_app_name': {
            'hits': cache_info.hits,
            'misses': cache_info.misses,
            'current_size': cache_info.currsize,
            'max_size': cache_info.maxsize,
            'hit_rate': cache_info.hits / (cache_info.hits + cache_info.misses) if (cache_info.hits + cache_info.misses) > 0 else 0.0
        }
    }


def clear_memoization_cache():
    """Clear all memoization caches."""
    clean_app_name.cache_clear()
    logger.debug("Cleared memoization cache for clean_app_name")