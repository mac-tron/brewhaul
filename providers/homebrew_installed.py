"""Get installed Homebrew casks efficiently with caching."""

from typing import Set
from .brew_cache import get_brew_cache


def get_installed_cask_tokens(force_refresh: bool = False) -> Set[str]:
    """Get a set of installed Homebrew cask tokens with caching.

    This function now uses the BrewCache singleton to cache results,
    significantly reducing subprocess calls when called repeatedly.

    Args:
        force_refresh: If True, bypass cache and fetch fresh data

    Returns:
        Set of installed cask tokens
    """
    cache = get_brew_cache()
    return cache.get_installed_casks(force_refresh=force_refresh)


def is_cask_installed(cask_token: str) -> bool:
    """Check if a specific cask is installed using cached data.

    Args:
        cask_token: The cask token to check

    Returns:
        True if the cask is installed
    """
    cache = get_brew_cache()
    return cache.is_cask_installed(cask_token)