"""Application detection and classification functionality."""

import os
import subprocess
import logging
from typing import Dict, List, Tuple, NamedTuple, Optional

from utils.ui import progress_wrapper, ProgressIndicator

# Set up logging for this module
logger = logging.getLogger(__name__)


class AppRegistry(NamedTuple):
    """Structured registry containing categorized applications."""
    homebrew_apps: List[str]
    appstore_apps: List[str]
    manual_apps: List[str]
    manual_app_paths: Dict[str, str]
    homebrew_count: int
    appstore_count: int
    manual_count: int
    total_count: int


def get_all_applications():
    """Get all applications in /Applications directory with progress and error handling"""
    def _scan_applications():
        try:
            if not os.path.exists("/Applications"):
                logger.error("/Applications directory does not exist")
                return []

            apps = []
            for item in os.listdir("/Applications"):
                if item.endswith(".app"):
                    app_path = os.path.join("/Applications", item)
                    # Verify the .app is actually a directory
                    if os.path.isdir(app_path):
                        apps.append(app_path)
                    else:
                        logger.warning(f"Skipping {item} - not a valid application bundle")

            logger.info(f"Found {len(apps)} applications in /Applications")
            return sorted(apps)
        except PermissionError:
            logger.error("Permission denied accessing /Applications directory")
            return []
        except OSError as e:
            logger.error(f"OS error scanning /Applications directory: {e}")
            return []
        except Exception as e:
            logger.error(f"Unexpected error scanning applications: {e}")
            return []

    return progress_wrapper("Scanning /Applications directory", _scan_applications)


def is_appstore_app(app_path):
    """Enhanced check if an app is from the Mac App Store using multiple methods with error handling"""
    try:
        if not app_path or not os.path.exists(app_path):
            logger.warning(f"App path does not exist: {app_path}")
            return False

        app_name = os.path.basename(app_path)

        # Method 1: Check for Mac App Store receipt (most reliable)
        receipt_path = os.path.join(app_path, "Contents", "_MASReceipt")
        if os.path.isdir(receipt_path):
            logger.debug(f"Found MAS receipt for {app_name}")
            return True

        # Method 2: Check using mas search if available (for edge cases)
        from providers.appstore import check_mas_installed, is_mas_app_by_search
        try:
            if check_mas_installed():
                if is_mas_app_by_search(app_name):
                    logger.debug(f"Found {app_name} in App Store search")
                    return True
        except Exception as e:
            logger.debug(f"Error checking App Store for {app_name}: {e}")

        return False
    except Exception as e:
        logger.error(f"Unexpected error checking if {app_path} is App Store app: {e}")
        return False


def is_brew_app(app_path, brew_apps=None, brew_paths=None):
    """
    Check if an app is installed via Homebrew using API-based detection

    Args:
        app_path: Full path to the application
        brew_apps: List of Homebrew cask names (optional, for backward compatibility)
        brew_paths: List of paths to Homebrew installed applications (optional)

    Returns:
        bool: True if app is installed via Homebrew, False otherwise
    """
    # Fast path: Check if the app's path is in the known Homebrew app paths
    if brew_paths and app_path in brew_paths:
        return True

    # Use API-based detection for accurate matching
    from providers.homebrew_api import HomebrewAPI
    from providers.homebrew_installed import is_cask_installed
    from utils.app_metadata import get_bundle_identifier

    app_name = os.path.basename(app_path).replace(".app", "")

    api = HomebrewAPI()

    # Check via API name matching
    result = api.find_cask_for_app(app_name)
    if result:
        # Verify the cask is actually installed
        token, _ = result
        if is_cask_installed(token):
            return True

    # Check via bundle identifier
    bundle_id = get_bundle_identifier(app_path)
    if bundle_id:
        result = api.find_cask_by_bundle_id(bundle_id)
        if result:
            # Verify the cask is actually installed
            token, _ = result
            if is_cask_installed(token):
                return True

    # Fallback: Check if app has Homebrew metadata files
    receipt_paths = [
        os.path.join(app_path, "Contents", ".brew_receipt"),
        os.path.join(app_path, "Contents", "MacOS", ".brew")
    ]

    for receipt_path in receipt_paths:
        if os.path.exists(receipt_path):
            return True

    return False


def build_app_registry(apps: List[str], brew_paths: Optional[List[str]] = None,
                      show_progress: bool = True) -> AppRegistry:
    """
    Build a centralized registry of all applications classified by installation type.

    This function performs a single efficient pass through all applications and
    classifies them as Homebrew, App Store, or manually installed applications.
    It's significantly more efficient than the old classify_apps() function as it
    uses cached Homebrew data and performs O(n) classification.

    Args:
        apps: List of application paths to classify
        brew_paths: Optional list of known Homebrew application paths for fast lookup
        show_progress: Whether to show progress indicator during classification

    Returns:
        AppRegistry: Structured registry with categorized applications and counts

    Performance:
        - Time Complexity: O(n) where n is the number of applications
        - Uses cached Homebrew paths for fast lookup when available
        - Single pass through all applications
        - Minimizes API calls through efficient detection logic
    """
    homebrew_apps = []
    appstore_apps = []
    manual_apps = []
    manual_app_paths = {}

    # Convert brew_paths to set for O(1) lookup if provided
    brew_paths_set = set(brew_paths) if brew_paths else set()

    progress = None
    if show_progress and apps:
        progress = ProgressIndicator("Classifying applications", total=len(apps))
        progress.start()

    try:
        for i, app_path in enumerate(apps):
            try:
                app_name = os.path.basename(app_path)

                if progress:
                    progress.update(current=i, message=f"{app_name}")

                # Validate app path before processing
                if not app_path or not os.path.exists(app_path):
                    logger.warning(f"Skipping invalid app path: {app_path}")
                    continue

                # Fast path: Check if app is in known Homebrew paths
                if brew_paths_set and app_path in brew_paths_set:
                    homebrew_apps.append(app_name)
                    logger.debug(f"Classified {app_name} as Homebrew (fast path)")
                    continue

                # Check App Store first (usually faster than Homebrew API checks)
                try:
                    if is_appstore_app(app_path):
                        appstore_apps.append(app_name)
                        logger.debug(f"Classified {app_name} as App Store")
                        continue
                except Exception as e:
                    logger.warning(f"Error checking App Store status for {app_name}: {e}")

                # Check Homebrew (with brew_paths for efficiency)
                try:
                    if is_brew_app(app_path, brew_paths=list(brew_paths_set) if brew_paths_set else None):
                        homebrew_apps.append(app_name)
                        logger.debug(f"Classified {app_name} as Homebrew")
                        continue
                except Exception as e:
                    logger.warning(f"Error checking Homebrew status for {app_name}: {e}")

                # If not Homebrew or App Store, it's manually installed
                manual_apps.append(app_name)
                manual_app_paths[app_name] = app_path
                logger.debug(f"Classified {app_name} as manual install")

            except Exception as e:
                logger.error(f"Error processing app {app_path}: {e}")
                # Continue with next app instead of failing completely
                continue

        if progress:
            progress.update(current=len(apps))
            progress.stop("Classification complete")

    except Exception as e:
        error_msg = f"Critical error during app classification: {e}"
        logger.error(error_msg)
        if progress:
            progress.stop(f"Classification failed: {str(e)}")
        raise RuntimeError(error_msg) from e

    # Sort all lists alphabetically for consistent output
    homebrew_apps.sort()
    appstore_apps.sort()
    manual_apps.sort()

    # Calculate counts
    homebrew_count = len(homebrew_apps)
    appstore_count = len(appstore_apps)
    manual_count = len(manual_apps)
    total_count = homebrew_count + appstore_count + manual_count

    return AppRegistry(
        homebrew_apps=homebrew_apps,
        appstore_apps=appstore_apps,
        manual_apps=manual_apps,
        manual_app_paths=manual_app_paths,
        homebrew_count=homebrew_count,
        appstore_count=appstore_count,
        manual_count=manual_count,
        total_count=total_count
    )


def classify_apps(apps, brew_cask_names, brew_paths):
    """
    Classify all applications by installation type.

    DEPRECATED: Use build_app_registry() instead for better performance.
    This function is kept for backward compatibility but will be removed in a future version.

    Returns:
        tuple: (brew_apps_list, appstore_apps_list, manual_apps_list, manual_app_paths,
                brew_count, appstore_count, manual_count)
    """
    brew_apps_list = []
    appstore_apps_list = []
    manual_apps_list = []
    manual_app_paths = {}

    brew_count = 0
    appstore_count = 0
    manual_count = 0

    for app in apps:
        app_name = os.path.basename(app)

        if is_brew_app(app, brew_cask_names, brew_paths):
            brew_apps_list.append(app_name)
            brew_count += 1
        elif is_appstore_app(app):
            appstore_apps_list.append(app_name)
            appstore_count += 1
        else:
            manual_apps_list.append(app_name)
            manual_app_paths[app_name] = app
            manual_count += 1

    # Sort all lists alphabetically
    brew_apps_list.sort()
    appstore_apps_list.sort()
    manual_apps_list.sort()

    return (brew_apps_list, appstore_apps_list, manual_apps_list, manual_app_paths,
            brew_count, appstore_count, manual_count)