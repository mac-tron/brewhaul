"""BrewCache singleton class for caching Homebrew operations.

This module provides a thread-safe singleton cache for expensive Homebrew operations
like fetching installed casks, to significantly reduce subprocess calls and improve
performance across the application.
"""

import subprocess
import threading
import time
from typing import Set, Optional


class BrewCache:
    """Singleton cache for Homebrew operations with TTL (time-to-live).

    This class implements the singleton pattern to ensure only one cache instance
    exists throughout the application lifecycle. It provides thread-safe caching
    for expensive Homebrew operations.

    Features:
    - Singleton pattern ensures single cache instance
    - Thread-safe operations using locks
    - TTL-based cache invalidation (default: 5 minutes)
    - Automatic refresh when cache expires
    - Force refresh capability for when fresh data is needed
    """

    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        """Implement singleton pattern with thread safety."""
        if cls._instance is None:
            with cls._lock:
                # Double-check locking pattern
                if cls._instance is None:
                    cls._instance = super(BrewCache, cls).__new__(cls)
        return cls._instance

    def __init__(self):
        """Initialize the cache if not already initialized."""
        # Only initialize once
        if hasattr(self, '_initialized'):
            return

        self._initialized = True
        self._cache_lock = threading.Lock()

        # Cache settings
        self._ttl = 300  # 5 minutes TTL

        # Installed casks cache
        self._installed_casks: Optional[Set[str]] = None
        self._installed_casks_timestamp: float = 0.0

        # Cask names cache (for brew list --cask)
        self._cask_names: Optional[list] = None
        self._cask_names_timestamp: float = 0.0

    def is_cache_valid(self, timestamp: float) -> bool:
        """Check if cache timestamp is still valid based on TTL.

        Args:
            timestamp: The timestamp when cache was last updated

        Returns:
            True if cache is still valid, False if expired
        """
        return (time.time() - timestamp) < self._ttl

    def get_installed_casks(self, force_refresh: bool = False) -> Set[str]:
        """Get installed Homebrew casks with caching.

        This method caches the result of 'brew list --cask' to avoid repeated
        subprocess calls. The cache expires after TTL seconds.

        Args:
            force_refresh: If True, bypass cache and fetch fresh data

        Returns:
            Set of installed cask token names
        """
        with self._cache_lock:
            # Check if we need to refresh the cache
            if (force_refresh or
                self._installed_casks is None or
                not self.is_cache_valid(self._installed_casks_timestamp)):

                self._installed_casks = self._fetch_installed_casks()
                self._installed_casks_timestamp = time.time()

            return self._installed_casks.copy() if self._installed_casks else set()

    def get_cask_names(self, force_refresh: bool = False) -> list:
        """Get list of installed cask names with caching.

        This is similar to get_installed_casks but returns a sorted list
        instead of a set, for backward compatibility with existing code.

        Args:
            force_refresh: If True, bypass cache and fetch fresh data

        Returns:
            Sorted list of installed cask names
        """
        with self._cache_lock:
            # Check if we need to refresh the cache
            if (force_refresh or
                self._cask_names is None or
                not self.is_cache_valid(self._cask_names_timestamp)):

                casks_set = self._fetch_installed_casks()
                self._cask_names = sorted(list(casks_set)) if casks_set else []
                self._cask_names_timestamp = time.time()

            return self._cask_names.copy() if self._cask_names else []

    def _fetch_installed_casks(self) -> Set[str]:
        """Fetch installed casks from Homebrew.

        This is the actual subprocess call to 'brew list --cask'.
        It's private to ensure caching is always used.

        Returns:
            Set of installed cask tokens
        """
        # Import here to avoid circular imports
        from ..utils.ui import subprocess_counter

        try:
            # Track subprocess calls for performance monitoring
            subprocess_counter.increment("brew list --cask")

            result = subprocess.run(
                ['brew', 'list', '--cask'],
                capture_output=True,
                text=True,
                timeout=10
            )

            if result.returncode == 0 and result.stdout:
                casks = result.stdout.strip().split('\n')
                return set(cask.strip() for cask in casks if cask.strip())
        except (subprocess.TimeoutExpired, subprocess.SubprocessError):
            pass

        return set()

    def refresh_cache(self):
        """Force refresh all cached data.

        This method clears all caches and forces fresh data to be fetched
        on the next access. Useful when you know Homebrew state has changed.
        """
        with self._cache_lock:
            self._installed_casks = None
            self._installed_casks_timestamp = 0.0
            self._cask_names = None
            self._cask_names_timestamp = 0.0

    def is_cask_installed(self, cask_token: str) -> bool:
        """Check if a specific cask is installed using cached data.

        Args:
            cask_token: The cask token to check

        Returns:
            True if the cask is installed
        """
        installed_casks = self.get_installed_casks()
        return cask_token in installed_casks

    def get_cache_stats(self) -> dict:
        """Get cache statistics for debugging/monitoring.

        Returns:
            Dictionary with cache statistics including:
            - installed_casks_cached: Whether installed casks are cached
            - installed_casks_age: Age of installed casks cache in seconds
            - cask_names_cached: Whether cask names are cached
            - cask_names_age: Age of cask names cache in seconds
            - ttl: Cache TTL in seconds
        """
        with self._cache_lock:
            current_time = time.time()

            return {
                'installed_casks_cached': self._installed_casks is not None,
                'installed_casks_age': (current_time - self._installed_casks_timestamp)
                                     if self._installed_casks is not None else None,
                'cask_names_cached': self._cask_names is not None,
                'cask_names_age': (current_time - self._cask_names_timestamp)
                                if self._cask_names is not None else None,
                'ttl': self._ttl
            }


# Convenience function to get the singleton instance
def get_brew_cache() -> BrewCache:
    """Get the BrewCache singleton instance.

    Returns:
        The singleton BrewCache instance
    """
    return BrewCache()