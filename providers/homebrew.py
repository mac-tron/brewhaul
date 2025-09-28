"""Homebrew package manager operations."""

import os
import subprocess
import re
import shlex
import logging
from utils.ui import Colors, progress_wrapper

# Set up logging for this module
logger = logging.getLogger(__name__)


def check_homebrew_installed():
    """Check if Homebrew is installed with improved error reporting"""
    try:
        result = subprocess.run(["which", "brew"], check=True, capture_output=True, text=True)
        logger.debug(f"Homebrew found at: {result.stdout.strip()}")
        return True
    except subprocess.CalledProcessError:
        logger.info("Homebrew is not installed or not in PATH")
        return False
    except FileNotFoundError:
        logger.error("'which' command not found - unable to check for Homebrew")
        return False
    except Exception as e:
        logger.error(f"Unexpected error checking for Homebrew: {e}")
        return False


def get_brew_apps(force_refresh: bool = False):
    """Get list of apps installed via Homebrew with progress and caching"""
    from utils.ui import ProgressIndicator
    from .brew_cache import get_brew_cache

    # Use cache for better performance
    cache = get_brew_cache()

    # Check if we have cached data and don't need to show progress
    if not force_refresh:
        cached_apps = cache.get_cask_names()
        if cached_apps:
            return cached_apps

    # Only show progress if we're actually fetching fresh data
    progress = ProgressIndicator("Querying Homebrew for installed casks...")
    progress.start()

    try:
        # Update message to show we're running the command
        progress.update(message="Running brew list --cask (this may take a few seconds)...")

        # Force refresh to get latest data and update cache
        apps = cache.get_cask_names(force_refresh=True)

        progress.update(message=f"Processing {len(apps)} installed casks...")
        progress.stop(f"Getting Homebrew cask list - Complete ({len(apps)} casks)")
        return apps
    except subprocess.CalledProcessError as e:
        error_msg = f"Homebrew command failed: {e}"
        logger.error(error_msg)
        progress.stop(f"Getting Homebrew cask list - Error: Homebrew command failed")
        return []
    except Exception as e:
        error_msg = f"Unexpected error getting Homebrew apps: {e}"
        logger.error(error_msg)
        progress.stop(f"Getting Homebrew cask list - Error: {str(e)}")
        return []


def get_brew_app_paths():
    """Get paths of all Homebrew cask installed applications using API data with batch optimization"""
    from .homebrew_api import HomebrewAPI
    from utils.app_metadata import get_bundle_identifier
    import glob

    brew_app_paths = []
    api = HomebrewAPI()

    # Load API data
    if not api.load_data():
        logger.warning("Could not load Homebrew API data for path detection")
        return brew_app_paths

    # Get all installed apps from /Applications
    app_files = glob.glob("/Applications/*.app")

    if not app_files:
        return brew_app_paths

    # Batch processing: collect all app names and bundle IDs first
    app_names = [os.path.basename(app_path).replace('.app', '') for app_path in app_files]

    # Batch lookup by app names
    name_results = api.find_casks_batch(app_names)

    # Track which apps were found by name
    found_by_name = set()
    for i, app_path in enumerate(app_files):
        app_name = app_names[i]
        if name_results.get(app_name):
            brew_app_paths.append(app_path)
            found_by_name.add(app_path)

    # For remaining apps, try bundle ID matching in batch
    remaining_apps = [app_path for app_path in app_files if app_path not in found_by_name]
    if remaining_apps:
        bundle_ids = []
        app_path_to_bundle_id = {}

        for app_path in remaining_apps:
            bundle_id = get_bundle_identifier(app_path)
            if bundle_id:
                bundle_ids.append(bundle_id)
                app_path_to_bundle_id[bundle_id] = app_path

        if bundle_ids:
            # Batch lookup by bundle IDs
            bundle_results = api.find_casks_by_bundle_ids_batch(bundle_ids)

            for bundle_id, result in bundle_results.items():
                if result:
                    app_path = app_path_to_bundle_id[bundle_id]
                    brew_app_paths.append(app_path)

    logger.info(f"Found {len(brew_app_paths)} Homebrew-managed apps via batch processing")
    return brew_app_paths


def filter_cask_results(casks, app_name, exclude_fonts=True, exclude_dev_tools=True):
    """Filter cask results to remove irrelevant matches"""
    if not casks:
        return casks

    filtered_casks = []
    app_base = app_name.replace(".app", "").lower()

    for cask_name, description in casks:
        cask_lower = cask_name.lower()
        desc_lower = description.lower()

        # Skip fonts if requested
        if exclude_fonts and ('font-' in cask_lower or 'font' in desc_lower):
            continue

        # Skip development tools that don't match closely
        if exclude_dev_tools and app_base not in cask_lower:
            dev_keywords = ['sdk', 'api', 'cli', 'command', 'library', 'framework']
            if any(keyword in desc_lower for keyword in dev_keywords):
                continue

        # Prioritize exact matches
        if app_base == cask_lower or app_base in cask_lower:
            filtered_casks.insert(0, (cask_name, description))
        else:
            filtered_casks.append((cask_name, description))

    return filtered_casks


def check_brew_equivalent_with_api(app_name, app_path, api, exclude_fonts=True, exclude_dev_tools=True):
    """Enhanced check for Homebrew packages using provided API instance"""
    from utils.app_metadata import get_bundle_identifier, clean_app_name

    # Clean the app name
    clean_name = clean_app_name(app_name)

    # Try exact name match via API
    result = api.find_cask_for_app(clean_name)
    if result:
        token, info = result
        desc = info.get('desc', '')

        # Check for deprecation status
        is_deprecated, deprecation_msg = api.is_cask_deprecated(token)
        if is_deprecated:
            desc = f"{desc} [{deprecation_msg}]"

        return [(token, desc)]

    # Try bundle identifier match if app path is provided
    if app_path:
        bundle_id = get_bundle_identifier(app_path)
        if bundle_id:
            result = api.find_cask_by_bundle_id(bundle_id)
            if result:
                token, info = result
                desc = info.get('desc', '')

                # Check for deprecation status
                is_deprecated, deprecation_msg = api.is_cask_deprecated(token)
                if is_deprecated:
                    desc = f"{desc} [{deprecation_msg}]"

                return [(token, desc)]

    # Fall back to brew search for cases not in API
    return _fallback_brew_search(app_name, exclude_fonts, exclude_dev_tools)


def check_brew_equivalent(app_name, app_path=None, exclude_fonts=True, exclude_dev_tools=True):
    """Enhanced check for Homebrew packages using API-based matching with fallback to brew search"""
    from .homebrew_api import HomebrewAPI

    # Try API-based matching first
    api = HomebrewAPI()
    return check_brew_equivalent_with_api(app_name, app_path, api, exclude_fonts, exclude_dev_tools)


def _fallback_brew_search(app_name, exclude_fonts=True, exclude_dev_tools=True):
    """Fall back to brew search for cases not in API"""
    # (but with much simpler logic since API should handle most cases)
    clean_name_for_search = app_name.replace(".app", "")
    casks = []

    try:
        # Remove version numbers from app names (e.g., "MKVToolNix-95.0" -> "MKVToolNix")
        base_name = re.sub(r'[-_]\d+(\.\d+)*$', '', clean_name_for_search)

        # Try a simple search with the base name
        name_variations = [
            base_name.lower().replace(" ", "-"),  # Most common format
        ]

        # Remove duplicates while preserving order
        name_variations = list(dict.fromkeys(name_variations))

        found_casks = []

        # Simple fallback search - only if API didn't find a match
        # Try a basic brew search with the cleaned name
        for variation in name_variations[:1]:  # Only try the most likely format
            # Security fix: Validate input to prevent command injection
            if not variation or not isinstance(variation, str) or len(variation) > 100:
                continue

            try:
                # Use array form to prevent shell injection (already safe, but added validation)
                search_result = subprocess.run(
                    ["brew", "search", "--cask", variation],
                    capture_output=True, text=True, timeout=15
                )

                if search_result.returncode != 0:
                    logger.debug(f"Brew search failed for '{variation}': {search_result.stderr}")
                    continue

                if search_result.stdout.strip():
                    # Found matches
                    cask_names = search_result.stdout.strip().split('\n')
                    for cask_name in cask_names:
                        if cask_name and not cask_name.startswith("==>") and not cask_name.startswith("Error:"):
                            # Only include exact matches of the base name
                            cask_base = cask_name.lower().replace("-", "").replace("_", "")
                            search_base = variation.lower().replace("-", "").replace("_", "").replace(" ", "")
                            # Stricter matching: require exact match only
                            if search_base == cask_base:
                                # Get description using brew info
                                # Security fix: Validate cask_name to prevent command injection
                                if not cask_name or not isinstance(cask_name, str) or len(cask_name) > 100:
                                    continue

                                try:
                                    # Use array form to prevent shell injection (already safe, but added validation)
                                    info_result = subprocess.run(
                                        ["brew", "info", "--cask", cask_name],
                                        capture_output=True, text=True, timeout=10
                                    )
                                    if info_result.returncode == 0:
                                        lines = info_result.stdout.strip().split('\n')
                                        if lines:
                                            first_line = lines[0]
                                            if ':' in first_line:
                                                parts = first_line.split(':', 1)
                                                if len(parts) >= 2:
                                                    description = parts[1].strip()
                                                    if '(' in description:
                                                        description = description.split('(')[0].strip()
                                                    found_casks.append((cask_name, description))
                                                else:
                                                    found_casks.append((cask_name, ""))
                                            else:
                                                found_casks.append((cask_name, ""))
                                    else:
                                        logger.debug(f"Brew info failed for cask '{cask_name}': {info_result.stderr}")
                                except subprocess.TimeoutExpired:
                                    logger.warning(f"Timeout getting info for cask '{cask_name}'")
                                except subprocess.SubprocessError as e:
                                    logger.debug(f"Subprocess error getting info for cask '{cask_name}': {e}")

                    if found_casks:
                        break

            except subprocess.TimeoutExpired:
                logger.warning(f"Timeout during brew search for '{variation}'")
                continue
            except subprocess.SubprocessError as e:
                logger.debug(f"Subprocess error during brew search for '{variation}': {e}")
                continue

        # Apply filtering to results
        casks = filter_cask_results(found_casks, app_name, exclude_fonts, exclude_dev_tools)

        # Limit to top 5 results to avoid overwhelming output
        return casks[:5]

    except subprocess.SubprocessError as e:
        logger.error(f"Subprocess error in check_brew_equivalent: {e}")
        return []
    except Exception as e:
        logger.error(f"Unexpected error in check_brew_equivalent: {e}")
        return []
