"""Application lifecycle management functionality."""

import subprocess
import time
import shlex


def is_app_running(app_name):
    """Check if an application is currently running"""
    try:
        # Use Apple's System Events to check if app is running
        # Security fix: Use shlex.quote to prevent shell injection
        clean_app_name = app_name.replace(".app", "")
        script = f'tell application "System Events" to count (every process whose name is {shlex.quote(clean_app_name)})'
        result = subprocess.run([
            'osascript',
            '-e',
            script
        ], capture_output=True, text=True)

        # Parse the output - if greater than 0, app is running
        count = int(result.stdout.strip())
        return count > 0
    except (ValueError, subprocess.SubprocessError):
        # If there's an error, assume app is not running
        return False


def kill_app(app_name):
    """Attempt to quit an application gracefully"""
    try:
        # First try to quit the app gracefully
        # Security fix: Use shlex.quote to prevent shell injection
        clean_app_name = app_name.replace(".app", "")
        script = f'tell application {shlex.quote(clean_app_name)} to quit'
        subprocess.run([
            'osascript',
            '-e',
            script
        ], capture_output=True)

        # Wait a moment for the app to quit
        time.sleep(1)

        # Check if the app is still running
        if is_app_running(app_name):
            # If still running, force quit
            # Security fix: Use shlex.quote to prevent shell injection
            clean_app_name = app_name.replace(".app", "")
            subprocess.run([
                'pkill',
                '-f',
                shlex.quote(clean_app_name)
            ])

            # Wait again to ensure it's terminated
            time.sleep(1)

        return not is_app_running(app_name)
    except subprocess.SubprocessError:
        return False


def move_to_trash(app_path):
    """Move an application to trash using Finder"""
    try:
        # Security fix: Validate input to prevent shell injection
        if not app_path or not isinstance(app_path, str):
            return False

        # Additional validation to ensure it's a valid path
        if not app_path.startswith('/') or '..' in app_path:
            return False

        # Escape any double quotes in the path itself, then wrap in double quotes for AppleScript
        escaped_path = app_path.replace('"', '\\"')
        script = f'tell application "Finder" to move POSIX file "{escaped_path}" to trash'
        result = subprocess.run(
            ['osascript', '-e', script],
            capture_output=True, text=True
        )
        return result.returncode == 0
    except subprocess.SubprocessError:
        return False