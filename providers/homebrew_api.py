"""Homebrew API client for accurate cask matching."""

import os
import json
import time
import urllib.request
import urllib.error
import logging
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# Set up logging for this module
logger = logging.getLogger(__name__)


class HomebrewAPI:
    """Client for Homebrew's public API with caching."""

    API_URL = "https://formulae.brew.sh/api/cask.json"
    CACHE_DIR = Path.home() / ".cache" / "brewhaul"
    CACHE_FILE = CACHE_DIR / "homebrew-casks.json"
    CACHE_EXPIRY_HOURS = 24
    # Critical operations cache age threshold (hours)
    CRITICAL_CACHE_AGE_HOURS = 48

    def __init__(self):
        self.cache_dir = self.CACHE_DIR
        self.cache_file = self.CACHE_FILE
        self._data = None
        self._app_name_to_cask = {}
        self._bundle_id_to_cask = {}
        self._cask_to_info = {}
        self._last_refresh_check = 0
        self._refresh_check_interval = 300  # Check refresh every 5 minutes

    def _ensure_cache_dir(self):
        """Create cache directory if it doesn't exist."""
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def _is_cache_valid(self) -> bool:
        """Check if cache exists and is not stale."""
        if not self.cache_file.exists():
            return False

        # Check age of cache file
        cache_age_seconds = time.time() - self.cache_file.stat().st_mtime
        cache_age_hours = cache_age_seconds / 3600
        return cache_age_hours < self.CACHE_EXPIRY_HOURS

    def _get_cache_age_hours(self) -> Optional[float]:
        """Get the age of the cache file in hours."""
        if not self.cache_file.exists():
            return None

        cache_age_seconds = time.time() - self.cache_file.stat().st_mtime
        return cache_age_seconds / 3600

    def _should_check_for_refresh(self, critical_operation: bool = False) -> bool:
        """Check if we should attempt a cache refresh.

        Args:
            critical_operation: If True, use stricter cache age limits

        Returns:
            True if we should attempt a refresh
        """
        # Rate limit refresh checks
        current_time = time.time()
        if current_time - self._last_refresh_check < self._refresh_check_interval:
            return False

        self._last_refresh_check = current_time

        cache_age = self._get_cache_age_hours()
        if cache_age is None:
            # No cache, definitely refresh
            return True

        if critical_operation:
            # For critical operations, refresh if cache is older than threshold
            return cache_age > self.CRITICAL_CACHE_AGE_HOURS
        else:
            # Normal operations, refresh if cache is older than normal expiry
            return cache_age > self.CACHE_EXPIRY_HOURS

    def _fetch_from_api(self) -> List[Dict]:
        """Fetch cask data from Homebrew API."""
        try:
            logger.info("Fetching Homebrew cask data from API...")
            with urllib.request.urlopen(self.API_URL, timeout=30) as response:
                data = json.loads(response.read().decode('utf-8'))
                logger.info(f"Successfully fetched {len(data)} casks from API")
                return data
        except urllib.error.URLError as e:
            logger.error(f"Network error fetching Homebrew API data: {e}")
            return []
        except json.JSONDecodeError as e:
            logger.error(f"JSON decode error for Homebrew API data: {e}")
            return []
        except Exception as e:
            logger.error(f"Unexpected error fetching Homebrew API data: {e}")
            return []

    def _load_cache(self) -> Optional[List[Dict]]:
        """Load cached data if available and valid."""
        if not self._is_cache_valid():
            return None

        try:
            with open(self.cache_file, 'r') as f:
                data = json.load(f)
                logger.debug(f"Loaded {len(data)} casks from cache")
                return data
        except json.JSONDecodeError as e:
            logger.warning(f"Invalid JSON in cache file: {e}")
            return None
        except IOError as e:
            logger.warning(f"Could not read cache file: {e}")
            return None

    def _save_cache(self, data: List[Dict]):
        """Save data to cache file."""
        self._ensure_cache_dir()
        try:
            with open(self.cache_file, 'w') as f:
                json.dump(data, f, indent=2)
            logger.debug(f"Saved {len(data)} casks to cache")
        except IOError as e:
            logger.warning(f"Could not save cache: {e}")

    def _build_lookup_tables(self, data: List[Dict]):
        """Build lookup tables for fast matching."""
        self._app_name_to_cask = {}  # Will store name -> list of cask tokens
        self._bundle_id_to_cask = {}  # Will store bundle_id -> list of cask tokens
        self._cask_to_info.clear()

        for cask in data:
            token = cask.get('token', '')
            if not token:
                continue

            # Store cask info
            self._cask_to_info[token] = {
                'token': token,
                'names': cask.get('name', []),
                'desc': cask.get('desc', ''),
                'homepage': cask.get('homepage', ''),
            }

            # Build app name lookup (store as list to handle multiple casks per app)
            names = cask.get('name', [])
            for name in names:
                if name:
                    # Store exact name
                    if name not in self._app_name_to_cask:
                        self._app_name_to_cask[name] = []
                    self._app_name_to_cask[name].append(token)

                    # Store lowercase version for case-insensitive matching
                    lower_name = name.lower()
                    if lower_name not in self._app_name_to_cask:
                        self._app_name_to_cask[lower_name] = []
                    if token not in self._app_name_to_cask[lower_name]:
                        self._app_name_to_cask[lower_name].append(token)

            # Extract bundle IDs from artifacts if available
            artifacts = cask.get('artifacts', [])
            for artifact in artifacts:
                if isinstance(artifact, dict):
                    # Check for uninstall quit field which often contains bundle ID
                    uninstall = artifact.get('uninstall', [])
                    if isinstance(uninstall, list):
                        for item in uninstall:
                            if isinstance(item, dict) and 'quit' in item:
                                bundle_id = item['quit']
                                if isinstance(bundle_id, str):
                                    if bundle_id not in self._bundle_id_to_cask:
                                        self._bundle_id_to_cask[bundle_id] = []
                                    self._bundle_id_to_cask[bundle_id].append(token)
                                elif isinstance(bundle_id, list):
                                    for bid in bundle_id:
                                        if isinstance(bid, str):
                                            if bid not in self._bundle_id_to_cask:
                                                self._bundle_id_to_cask[bid] = []
                                            self._bundle_id_to_cask[bid].append(token)

    def load_data(self, force_refresh: bool = False, critical_operation: bool = False) -> bool:
        """Load cask data from cache or API with intelligent refresh.

        Args:
            force_refresh: Force refresh from API regardless of cache status
            critical_operation: If True, use stricter cache age limits for refresh

        Returns:
            True if data loaded successfully, False otherwise
        """
        # Check if we should attempt a refresh based on cache age and operation type
        should_refresh = force_refresh or self._should_check_for_refresh(critical_operation)

        # Try to load from cache first if not forcing refresh
        if not force_refresh and not should_refresh:
            cached_data = self._load_cache()
            if cached_data:
                self._data = cached_data
                self._build_lookup_tables(cached_data)
                return True

        # Try background refresh for critical operations
        if should_refresh:
            cache_age = self._get_cache_age_hours()
            if cache_age is not None:
                logger.info(f"Cache is {cache_age:.1f} hours old, attempting refresh...")

            # Fetch from API
            api_data = self._fetch_from_api()
            if api_data:
                self._data = api_data
                self._save_cache(api_data)
                self._build_lookup_tables(api_data)
                return True
            else:
                logger.warning("API fetch failed, falling back to cache if available")

        # Fall back to existing cache (even if stale) if API fails
        if not force_refresh:
            try:
                with open(self.cache_file, 'r') as f:
                    cached_data = json.load(f)
                    if cached_data:
                        cache_age = self._get_cache_age_hours()
                        if cache_age is not None:
                            logger.info(f"Using cache that is {cache_age:.1f} hours old")
                        self._data = cached_data
                        self._build_lookup_tables(cached_data)
                        return True
            except (json.JSONDecodeError, IOError) as e:
                logger.error(f"Could not load fallback cache: {e}")

        return False

    def find_cask_for_app(self, app_name: str) -> Optional[Tuple[str, Dict]]:
        """Find the best matching cask for an app name.

        Returns:
            Tuple of (cask_token, cask_info) or None if no match found
        """
        if not self._data:
            if not self.load_data():
                return None

        # Clean the app name
        clean_name = app_name.replace('.app', '').strip()

        # Collect all potential matches
        candidates = []

        # Try exact match first
        if clean_name in self._app_name_to_cask:
            tokens = self._app_name_to_cask[clean_name]
            candidates.extend(tokens)

        # Try lowercase match
        if clean_name.lower() in self._app_name_to_cask:
            tokens = self._app_name_to_cask[clean_name.lower()]
            for token in tokens:
                if token not in candidates:
                    candidates.append(token)

        # If we have multiple candidates, prefer stable versions
        if len(candidates) > 1:
            # Sort candidates to prefer stable versions
            def sort_key(token):
                # Penalize variants
                if '@beta' in token or '@nightly' in token or '@dev' in token or '@insiders' in token:
                    return 1
                elif '@' in token:
                    return 2
                else:
                    return 0

            candidates.sort(key=sort_key)

        if candidates:
            token = candidates[0]
            return (token, self._cask_to_info[token])

        return None

    def find_cask_by_bundle_id(self, bundle_id: str) -> Optional[Tuple[str, Dict]]:
        """Find cask by bundle identifier.

        Returns:
            Tuple of (cask_token, cask_info) or None if no match found
        """
        if not self._data:
            if not self.load_data():
                return None

        if bundle_id in self._bundle_id_to_cask:
            tokens = self._bundle_id_to_cask[bundle_id]

            # If multiple tokens, prefer stable version
            if len(tokens) > 1:
                def sort_key(token):
                    if '@beta' in token or '@nightly' in token or '@dev' in token or '@insiders' in token:
                        return 1
                    elif '@' in token:
                        return 2
                    else:
                        return 0
                tokens = sorted(tokens, key=sort_key)

            token = tokens[0]
            return (token, self._cask_to_info[token])

        return None

    def get_all_cask_tokens(self) -> List[str]:
        """Get all available cask tokens."""
        if not self._data:
            if not self.load_data():
                return []
        return list(self._cask_to_info.keys())

    def invalidate_cache_on_homebrew_operation(self):
        """Invalidate cache when Homebrew operations are performed.

        This ensures fresh data is fetched after cask installations/removals.
        """
        if self.cache_file.exists():
            try:
                # Set cache modification time to very old to force refresh
                old_time = time.time() - (self.CACHE_EXPIRY_HOURS + 1) * 3600
                os.utime(self.cache_file, (old_time, old_time))
                logger.info("Cache invalidated due to Homebrew operation")
                # Reset refresh check timer to allow immediate refresh
                self._last_refresh_check = 0
            except OSError as e:
                logger.warning(f"Could not invalidate cache: {e}")

    def get_cache_status(self) -> dict:
        """Get cache status information for monitoring and debugging.

        Returns:
            Dictionary with cache status information
        """
        cache_age = self._get_cache_age_hours()
        return {
            'cache_file_exists': self.cache_file.exists(),
            'cache_age_hours': cache_age,
            'cache_valid': self._is_cache_valid(),
            'data_loaded': self._data is not None,
            'cask_count': len(self._cask_to_info) if self._data else 0,
            'last_refresh_check': self._last_refresh_check,
            'cache_file_path': str(self.cache_file)
        }

    def clear_cache(self):
        """Clear the cache file."""
        if self.cache_file.exists():
            self.cache_file.unlink()
            logger.info("Cache cleared")
            self._data = None
            self._app_name_to_cask.clear()
            self._bundle_id_to_cask.clear()
            self._cask_to_info.clear()

    def find_casks_batch(self, app_names: List[str]) -> Dict[str, Optional[Tuple[str, Dict]]]:
        """Find casks for multiple app names in a single batch operation.

        This is more efficient than calling find_cask_for_app multiple times
        as it only loads the data once and processes all apps together.

        Args:
            app_names: List of app names to look up

        Returns:
            Dictionary mapping app names to their cask results
        """
        # Ensure data is loaded once for the entire batch
        if not self._data:
            if not self.load_data():
                return {app_name: None for app_name in app_names}

        results = {}

        # Process all apps in batch
        for app_name in app_names:
            try:
                result = self.find_cask_for_app(app_name)
                results[app_name] = result
            except Exception as e:
                logger.error(f"Error finding cask for {app_name} in batch: {e}")
                results[app_name] = None

        logger.debug(f"Batch processed {len(app_names)} app lookups")
        return results

    def find_casks_by_bundle_ids_batch(self, bundle_ids: List[str]) -> Dict[str, Optional[Tuple[str, Dict]]]:
        """Find casks for multiple bundle IDs in a single batch operation.

        Args:
            bundle_ids: List of bundle IDs to look up

        Returns:
            Dictionary mapping bundle IDs to their cask results
        """
        # Ensure data is loaded once for the entire batch
        if not self._data:
            if not self.load_data():
                return {bundle_id: None for bundle_id in bundle_ids}

        results = {}

        # Process all bundle IDs in batch
        for bundle_id in bundle_ids:
            try:
                result = self.find_cask_by_bundle_id(bundle_id)
                results[bundle_id] = result
            except Exception as e:
                logger.error(f"Error finding cask for bundle ID {bundle_id} in batch: {e}")
                results[bundle_id] = None

        logger.debug(f"Batch processed {len(bundle_ids)} bundle ID lookups")
        return results