"""Mac App Store operations."""

import subprocess
import logging

# Set up logging for this module
logger = logging.getLogger(__name__)


def check_mas_installed():
    """Check if mas (Mac App Store CLI) is installed with improved error reporting"""
    try:
        result = subprocess.run(["which", "mas"], check=True, capture_output=True, text=True)
        logger.debug(f"mas CLI found at: {result.stdout.strip()}")
        return True
    except subprocess.CalledProcessError:
        logger.info("mas CLI is not installed or not in PATH")
        return False
    except FileNotFoundError:
        logger.error("'which' command not found - unable to check for mas CLI")
        return False
    except Exception as e:
        logger.error(f"Unexpected error checking for mas CLI: {e}")
        return False


def is_mas_app_by_search(app_name):
    """Check if an app is available in Mac App Store using mas search with improved error handling"""
    if not check_mas_installed():
        logger.debug("mas CLI not available for App Store search")
        return False

    # Security fix: Validate input to prevent command injection
    if not app_name or not isinstance(app_name, str):
        logger.warning(f"Invalid app name provided to is_mas_app_by_search: {app_name}")
        return False

    clean_name = app_name.replace(".app", "")

    # Additional input validation
    if len(clean_name) > 100 or not clean_name.strip():
        logger.warning(f"App name too long or empty after cleaning: '{clean_name}'")
        return False

    try:
        # Security fix: Using array form which is already safe, but added validation
        result = subprocess.run(["mas", "search", clean_name],
                              capture_output=True, text=True, timeout=10)

        if result.returncode != 0:
            logger.debug(f"mas search failed for '{clean_name}': {result.stderr}")
            return False

        if result.stdout.strip():
            # Check if exact match exists in results
            lines = result.stdout.strip().split('\n')
            for line in lines:
                if clean_name.lower() in line.lower():
                    logger.debug(f"Found Mac App Store match for '{clean_name}': {line}")
                    return True
            logger.debug(f"No exact match found in App Store search results for '{clean_name}'")
        else:
            logger.debug(f"No search results from App Store for '{clean_name}'")

        return False
    except subprocess.TimeoutExpired:
        logger.warning(f"Timeout during mas search for '{clean_name}'")
        return False
    except subprocess.SubprocessError as e:
        logger.error(f"Subprocess error during mas search for '{clean_name}': {e}")
        return False
    except Exception as e:
        logger.error(f"Unexpected error during mas search for '{clean_name}': {e}")
        return False