"""User interface utilities for brewhaul."""

import sys
import time
import threading
import re
import signal
import atexit

# Terminal colors for better output
class Colors:
    BOLD = "\033[1m"
    RESET = "\033[0m"
    GREEN = "\033[32m"
    YELLOW = "\033[33m"
    ORANGE = "\033[38;5;208m"
    BLUE = "\033[34m"
    CYAN = "\033[36m"
    DIM = "\033[2m"

class ProgressIndicator:
    """Simple progress indicator with spinner or progress bar with thread safety"""

    # Class-level registry to track active progress indicators for cleanup
    _active_indicators = set()
    _registry_lock = threading.Lock()

    def __init__(self, message, total=None):
        self.message = message
        self.total = total
        self.current = 0
        self.spinner_chars = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"
        self.spinner_index = 0
        self.running = False
        self.thread = None
        self._lock = threading.Lock()  # Thread safety for shared state
        self._cursor_hidden = False  # Track cursor state for cleanup

        # Register signal handlers for graceful shutdown
        self._setup_signal_handlers()

    def _setup_signal_handlers(self):
        """Setup signal handlers for graceful shutdown"""
        # Register this indicator for cleanup
        with ProgressIndicator._registry_lock:
            ProgressIndicator._active_indicators.add(self)

        # Setup signal handlers (only once)
        if not hasattr(ProgressIndicator, '_handlers_setup'):
            def cleanup_all_indicators(signum=None, frame=None):
                """Cleanup all active progress indicators"""
                with ProgressIndicator._registry_lock:
                    indicators_to_cleanup = list(ProgressIndicator._active_indicators)

                for indicator in indicators_to_cleanup:
                    try:
                        indicator._emergency_cleanup()
                    except Exception:
                        pass  # Ignore errors during emergency cleanup

            # Register signal handlers
            try:
                signal.signal(signal.SIGINT, cleanup_all_indicators)
                signal.signal(signal.SIGTERM, cleanup_all_indicators)
                atexit.register(cleanup_all_indicators)
                ProgressIndicator._handlers_setup = True
            except (ValueError, OSError):
                # Signal handling might not be available in all contexts
                pass

    def _emergency_cleanup(self):
        """Emergency cleanup of progress indicator"""
        try:
            with self._lock:
                self.running = False
                if self._cursor_hidden:
                    sys.stdout.write("\033[?25h")  # Restore cursor
                    sys.stdout.flush()
                    self._cursor_hidden = False
        except Exception:
            pass  # Ignore all errors during emergency cleanup

    def start(self):
        """Start the progress indicator"""
        with self._lock:
            if self.running:
                return  # Already running
            self.running = True
            # Hide cursor for cleaner display
            try:
                sys.stdout.write("\033[?25l")
                sys.stdout.flush()
                self._cursor_hidden = True
            except (OSError, IOError):
                # Handle cases where stdout isn't a terminal
                pass

        self.thread = threading.Thread(target=self._animate)
        self.thread.daemon = True
        self.thread.start()

    def update(self, current=None, message=None):
        """Update progress (thread-safe)"""
        with self._lock:
            if current is not None:
                self.current = current
            if message is not None:
                self.message = message

    def stop(self, final_message=None):
        """Stop the progress indicator (thread-safe)"""
        with self._lock:
            if not self.running:
                return  # Already stopped
            self.running = False

        if self.thread:
            self.thread.join()

        with self._lock:
            try:
                # Clear the line completely using ANSI escape codes and show final message
                sys.stdout.write("\033[2K\033[0G")  # Clear line and move to beginning
                if final_message:
                    sys.stdout.write(f"{Colors.GREEN}[OK]{Colors.RESET} {final_message}\n")
                else:
                    sys.stdout.write(f"{Colors.GREEN}[OK]{Colors.RESET} {self.message}\n")
                sys.stdout.flush()
                # Restore cursor
                if self._cursor_hidden:
                    sys.stdout.write("\033[?25h")
                    self._cursor_hidden = False
                    sys.stdout.flush()
            except (OSError, IOError):
                # Handle cases where stdout isn't a terminal
                pass

        # Unregister from active indicators
        try:
            with ProgressIndicator._registry_lock:
                ProgressIndicator._active_indicators.discard(self)
        except Exception:
            pass  # Ignore errors during cleanup

    def _animate(self):
        """Animation loop (thread-safe)"""
        last_output_length = 0

        while True:
            # Check running status in a thread-safe way
            with self._lock:
                if not self.running:
                    break
                current_message = self.message
                current_total = self.total
                current_current = self.current

            # Build the output string
            if current_total is not None:
                # Progress bar mode - bar first for stability
                percentage = (current_current / current_total) * 100 if current_total > 0 else 0
                bar_length = 20
                filled_length = int(bar_length * current_current // current_total) if current_total > 0 else 0
                bar = "█" * filled_length + "░" * (bar_length - filled_length)
                output = f"[{bar}] {percentage:.0f}% ({current_current}/{current_total}) {current_message}"
            else:
                # Spinner mode
                spinner = self.spinner_chars[self.spinner_index % len(self.spinner_chars)]
                output = f"{Colors.CYAN}{spinner}{Colors.RESET} {current_message}"
                self.spinner_index += 1

            try:
                # Clear the previous line completely and write new output
                # Calculate display length (excluding ANSI color codes)
                display_length = len(re.sub(r'\x1b\[[0-9;]*m', '', output))
                clear_length = max(last_output_length, display_length, 100)  # Ensure sufficient clearing

                # Use ANSI escape codes for better terminal compatibility
                # \033[2K clears the entire line, \033[0G moves cursor to beginning of line
                sys.stdout.write(f"\033[2K\033[0G{output}")
                sys.stdout.flush()
                last_output_length = display_length
            except (OSError, IOError):
                # Handle cases where stdout isn't a terminal
                break

            time.sleep(0.2)  # Slower animation to reduce flicker

    def __enter__(self):
        """Context manager entry - start progress indicator"""
        self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit - stop progress indicator"""
        if exc_type is not None:
            # Exception occurred, show error message
            self.stop(f"Error: {str(exc_val)}")
        else:
            # Normal completion
            self.stop()
        # Don't suppress exceptions
        return False

def progress_wrapper(message, func, *args, **kwargs):
    """Wrapper to run a function with a progress indicator"""
    progress = ProgressIndicator(message)
    progress.start()
    try:
        result = func(*args, **kwargs)
        progress.stop(f"{message}")
        return result
    except Exception as e:
        progress.stop(f"{message} - Error: {str(e)}")
        raise


class PerformanceTimer:
    """Performance timing utility for measuring optimization improvements."""

    def __init__(self, description: str, show_logs: bool = True):
        """Initialize the timer.

        Args:
            description: Description of what is being timed
            show_logs: Whether to print timing logs
        """
        self.description = description
        self.show_logs = show_logs
        self.start_time = None
        self.end_time = None

    def __enter__(self):
        """Start timing when entering context."""
        self.start_time = time.time()
        if self.show_logs:
            print(f"{Colors.DIM}[..] Starting: {self.description}{Colors.RESET}")
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Stop timing when exiting context."""
        self.end_time = time.time()
        duration = self.end_time - self.start_time

        if self.show_logs:
            if duration < 1.0:
                print(f"{Colors.GREEN}[OK] Completed: {self.description} ({duration:.2f}s){Colors.RESET}")
            else:
                print(f"{Colors.GREEN}[OK] Completed: {self.description} ({duration:.1f}s){Colors.RESET}")

    def get_duration(self) -> float:
        """Get the measured duration in seconds.

        Returns:
            Duration in seconds, or None if timing not completed
        """
        if self.start_time is None:
            return None
        end = self.end_time if self.end_time is not None else time.time()
        return end - self.start_time


# Global subprocess call counter for performance monitoring
class SubprocessCounter:
    """Counter to track subprocess calls for performance optimization monitoring."""

    def __init__(self):
        self._count = 0
        self._lock = threading.Lock()

    def increment(self, command_name: str = "subprocess"):
        """Increment the counter for a subprocess call."""
        with self._lock:
            self._count += 1

    def get_count(self) -> int:
        """Get the current count of subprocess calls."""
        with self._lock:
            return self._count

    def reset(self):
        """Reset the counter to zero."""
        with self._lock:
            self._count = 0

    def report(self, prefix: str = "") -> str:
        """Generate a report of subprocess calls.

        Args:
            prefix: Optional prefix for the report

        Returns:
            Formatted string with subprocess call count
        """
        count = self.get_count()
        return f"{prefix}Subprocess calls: {count}"


# Global instance for tracking subprocess calls
subprocess_counter = SubprocessCounter()


class StatusIcons:
    """Status icons for consistent visual feedback across the application"""
    SUCCESS = "✓"
    FAILED = "✗"
    WARNING = "⚠"
    INFO = "ℹ"
    PROCESSING = "⟳"
    ARROW = "→"
    CHECKBOX_EMPTY = "□"
    CHECKBOX_CHECKED = "☑"
    BULLET = "•"
    TREE_BRANCH = "├─"
    TREE_END = "└─"


class SectionDivider:
    """Format section headers and dividers for consistent UI"""

    @staticmethod
    def format_header(title, width=60, color=None):
        """Format a main section header

        Args:
            title: The title text
            width: Total width of the header line
            color: Optional color code from Colors class

        Returns:
            Formatted header string
        """
        if color:
            return f"\n{color}{title}{Colors.RESET}\n{'─' * width}"
        return f"\n{Colors.BOLD}{title}{Colors.RESET}\n{'─' * width}"

    @staticmethod
    def format_subheader(title, prefix=""):
        """Format a subsection header

        Args:
            title: The title text
            prefix: Optional prefix like status icons

        Returns:
            Formatted subheader string
        """
        if prefix:
            return f"{prefix} {Colors.BOLD}{title}{Colors.RESET}"
        return f"{Colors.BOLD}{title}{Colors.RESET}"


class BoxChars:
    """Unicode box drawing characters for tables"""
    # Heavy borders (for header)
    TOP_LEFT = '┏'
    TOP_RIGHT = '┓'
    TOP_SEP = '┳'
    HEAVY_HORIZONTAL = '━'
    HEAVY_VERTICAL = '┃'

    # Mixed borders (header/content separator)
    HEADER_LEFT = '┡'
    HEADER_RIGHT = '┩'
    HEADER_SEP = '╇'

    # Light borders (for content)
    BOTTOM_LEFT = '└'
    BOTTOM_RIGHT = '┘'
    BOTTOM_SEP = '┴'
    HORIZONTAL = '─'
    VERTICAL = '│'

    # Fallback ASCII characters
    ASCII_HORIZONTAL = '-'
    ASCII_VERTICAL = '|'
    ASCII_CORNER = '+'
    ASCII_SEP = '+'


class TableFormatter:
    """Format data as a nicely bordered table"""

    def __init__(self, use_unicode=True):
        """Initialize table formatter

        Args:
            use_unicode: Whether to use Unicode box drawing characters
        """
        self.box = BoxChars() if use_unicode else None
        self.use_unicode = use_unicode

    def format_table(self, headers, rows, column_colors=None):
        """Format data as a bordered table

        Args:
            headers: List of column headers
            rows: List of row tuples/lists
            column_colors: Optional dict mapping column indices to color codes

        Returns:
            Formatted table string
        """
        if not headers or not rows:
            return ""

        # Calculate column widths
        widths = [len(h) for h in headers]
        for row in rows:
            for i, cell in enumerate(row):
                if i < len(widths):
                    # Remove ANSI codes for width calculation
                    clean_cell = re.sub(r'\x1b\[[0-9;]*m', '', str(cell))
                    widths[i] = max(widths[i], len(clean_cell))

        # Add padding
        widths = [w + 2 for w in widths]

        lines = []

        # Top border
        if self.use_unicode:
            segments = [self.box.HEAVY_HORIZONTAL * w for w in widths]
            lines.append(self.box.TOP_LEFT + self.box.TOP_SEP.join(segments) + self.box.TOP_RIGHT)
        else:
            segments = [self.ASCII_HORIZONTAL * w for w in widths]
            lines.append(self.ASCII_CORNER + self.ASCII_SEP.join(segments) + self.ASCII_CORNER)

        # Header row
        header_cells = []
        for i, header in enumerate(headers):
            cell = f" {header.ljust(widths[i] - 2)} "
            header_cells.append(cell)

        if self.use_unicode:
            lines.append(self.box.HEAVY_VERTICAL + self.box.HEAVY_VERTICAL.join(header_cells) + self.box.HEAVY_VERTICAL)
        else:
            lines.append(self.ASCII_VERTICAL + self.ASCII_VERTICAL.join(header_cells) + self.ASCII_VERTICAL)

        # Header separator
        if self.use_unicode:
            segments = [self.box.HEAVY_HORIZONTAL * w for w in widths]
            lines.append(self.box.HEADER_LEFT + self.box.HEADER_SEP.join(segments) + self.box.HEADER_RIGHT)
        else:
            segments = [self.ASCII_HORIZONTAL * w for w in widths]
            lines.append(self.ASCII_CORNER + self.ASCII_SEP.join(segments) + self.ASCII_CORNER)

        # Data rows
        for row in rows:
            row_cells = []
            for i, cell in enumerate(row):
                if i >= len(widths):
                    break
                # Handle colored cells
                cell_str = str(cell)
                # Remove ANSI codes for padding calculation
                clean_cell = re.sub(r'\x1b\[[0-9;]*m', '', cell_str)
                padding = widths[i] - 2 - len(clean_cell)
                padded_cell = f" {cell_str}{' ' * padding} "
                row_cells.append(padded_cell)

            if self.use_unicode:
                lines.append(self.box.VERTICAL + self.box.VERTICAL.join(row_cells) + self.box.VERTICAL)
            else:
                lines.append(self.ASCII_VERTICAL + self.ASCII_VERTICAL.join(row_cells) + self.ASCII_VERTICAL)

        # Bottom border
        if self.use_unicode:
            segments = [self.box.HORIZONTAL * w for w in widths]
            lines.append(self.box.BOTTOM_LEFT + self.box.BOTTOM_SEP.join(segments) + self.box.BOTTOM_RIGHT)
        else:
            segments = [self.ASCII_HORIZONTAL * w for w in widths]
            lines.append(self.ASCII_CORNER + self.ASCII_SEP.join(segments) + self.ASCII_CORNER)

        return '\n'.join(lines)


class ProgressTable:
    """Dynamic table that updates rows in place during operations"""

    def __init__(self, headers, use_unicode=True):
        """Initialize progress table

        Args:
            headers: List of column headers
            use_unicode: Whether to use Unicode box drawing characters
        """
        self.headers = headers
        self.rows = {}  # Dictionary mapping row_id to row data
        self.row_order = []  # Track order of rows
        self.formatter = TableFormatter(use_unicode)
        self.use_unicode = use_unicode
        self._last_output_lines = 0
        self._table_drawn = False

    def add_row(self, row_id, *cells):
        """Add a new row to the table

        Args:
            row_id: Unique identifier for the row
            cells: Cell values for the row
        """
        self.rows[row_id] = list(cells)
        if row_id not in self.row_order:
            self.row_order.append(row_id)

    def update_row(self, row_id, column_index=None, value=None, cells=None):
        """Update a specific cell or entire row

        Args:
            row_id: Row identifier to update
            column_index: Index of column to update (optional)
            value: New value for the cell (optional)
            cells: Complete new row data (optional)
        """
        if row_id not in self.rows:
            return

        if cells is not None:
            self.rows[row_id] = list(cells)
        elif column_index is not None and value is not None:
            if column_index < len(self.rows[row_id]):
                self.rows[row_id][column_index] = value

    def render(self, clear_previous=True):
        """Render the current state of the table

        Args:
            clear_previous: Whether to clear previous output
        """
        # Build rows list in order
        ordered_rows = []
        for row_id in self.row_order:
            if row_id in self.rows:
                ordered_rows.append(self.rows[row_id])

        # Format table
        table_output = self.formatter.format_table(self.headers, ordered_rows)
        lines = table_output.split('\n')

        if clear_previous and self._table_drawn:
            # Clear previous output
            for _ in range(self._last_output_lines):
                sys.stdout.write("\033[A\033[2K")  # Move up and clear line

        # Output new table
        for line in lines:
            print(line)

        self._last_output_lines = len(lines)
        self._table_drawn = True
        sys.stdout.flush()

    def finalize(self):
        """Finalize the table (no more updates)"""
        # Just ensure final render
        self.render(clear_previous=True)


class MigrationTable:
    """Specialized table for migration UI with checkbox selection and status tracking"""

    def __init__(self, apps_with_matches, apps_without_matches=None):
        """Initialize migration table

        Args:
            apps_with_matches: List of tuples (app_name, cask_name) that have Homebrew matches
            apps_without_matches: List of app names without Homebrew matches
        """
        self.apps_with_matches = sorted(apps_with_matches, key=lambda x: x[0].lower())
        self.apps_without_matches = sorted(apps_without_matches or [], key=lambda x: x.lower())

        # Track checkbox states and status for each app
        self.checkboxes = {}  # app_name -> bool (selected)
        self.statuses = {}    # app_name -> status string
        self.targets = {}     # app_name -> target package name

        # Initialize states
        for app_name, cask_name in self.apps_with_matches:
            self.checkboxes[app_name] = False
            self.statuses[app_name] = "Ready"
            self.targets[app_name] = cask_name

        self._last_output_lines = 0
        self._header_printed = False
        self._saved_cursor_pos = False

    def select_apps(self, indices, update_display=True):
        """Mark apps as selected based on indices

        Args:
            indices: List of 1-based indices to select
            update_display: Whether to update the display immediately
        """
        # Clear all checkboxes first
        for app_name in self.checkboxes:
            self.checkboxes[app_name] = False

        # Set selected indices
        for idx in indices:
            if 1 <= idx <= len(self.apps_with_matches):
                app_name = self.apps_with_matches[idx - 1][0]
                self.checkboxes[app_name] = True

        # Update display if requested
        if update_display and self._last_output_lines > 0:
            self.render(clear_previous=True)

    def update_status(self, app_name, status):
        """Update the status of an app

        Args:
            app_name: Name of the app
            status: New status string (e.g., "Queue", "Removing", "45%", "Done")
        """
        if app_name in self.statuses:
            self.statuses[app_name] = status

    def render(self, title="", show_selection_prompt=False, clear_previous=True):
        """Render the migration table

        Args:
            title: Optional title above the table
            show_selection_prompt: Whether to show selection numbers
            clear_previous: Whether to clear previous output
        """
        # Build table rows
        table_rows = []
        for i, (app_name, cask_name) in enumerate(self.apps_with_matches, 1):
            # Checkbox column
            if show_selection_prompt:
                checkbox = f"{StatusIcons.CHECKBOX_EMPTY} {i}"
            else:
                checkbox = f"{StatusIcons.CHECKBOX_CHECKED if self.checkboxes[app_name] else StatusIcons.CHECKBOX_EMPTY} {i}"

            # Status with colors
            status = self.statuses[app_name]
            if status == "Ready":
                status_colored = status
            elif status == "Queue" or "⏸" in status:
                status_colored = f"{Colors.YELLOW}{status}{Colors.RESET}"
            elif status == "Removing":
                status_colored = f"{Colors.YELLOW}{status}{Colors.RESET}"
            elif "%" in status or "⟳" in status:
                status_colored = f"{Colors.CYAN}{status}{Colors.RESET}"
            elif "✓" in status or "Done" in status:
                status_colored = f"{Colors.GREEN}{status}{Colors.RESET}"
            elif "✗" in status or "Failed" in status:
                status_colored = f"{Colors.YELLOW}{status}{Colors.RESET}"
            elif status == "-":
                status_colored = f"{Colors.DIM}{status}{Colors.RESET}"
            else:
                status_colored = status

            # Build row - show dash for unchecked items in selection mode
            if not self.checkboxes[app_name] and not show_selection_prompt:
                table_rows.append([
                    f"  {Colors.DIM}-{Colors.RESET}",
                    app_name,
                    f"{Colors.DIM}-{Colors.RESET}",
                    status_colored
                ])
            else:
                table_rows.append([
                    checkbox,
                    app_name,
                    cask_name,
                    status_colored
                ])

        # Save cursor position on first render
        if self._last_output_lines == 0:
            sys.stdout.write("\033[s")  # Save cursor position
            sys.stdout.flush()
            self._saved_cursor_pos = True

        # Clear previous output if requested and table was already drawn
        if clear_previous and self._last_output_lines > 0 and self._saved_cursor_pos:
            # Restore to saved cursor position and clear from there
            sys.stdout.write("\033[u")  # Restore cursor position
            sys.stdout.write("\033[J")  # Clear from cursor to end of screen
            sys.stdout.flush()

        # Build the output lines
        lines = []

        # Add title if provided
        if title:
            lines.append(title)

        # Format table
        formatter = TableFormatter()
        table = formatter.format_table(
            headers=["#", "App", "Target", "Status"],
            rows=table_rows
        )

        for line in table.split('\n'):
            lines.append(line)

        # Add "No matches" line if there are any
        if self.apps_without_matches:
            no_match_names = ", ".join(self.apps_without_matches)
            if len(no_match_names) > 50:  # Truncate if too long
                no_match_names = no_match_names[:47] + "..."
            lines.append("")
            lines.append(f"{Colors.DIM}No matches: {no_match_names} ({len(self.apps_without_matches)} apps){Colors.RESET}")

        # Print all lines
        for line in lines:
            print(line)

        self._last_output_lines = len(lines)
        sys.stdout.flush()

    def get_selected_apps(self):
        """Get list of selected app names

        Returns:
            List of (app_name, cask_name) tuples for selected apps
        """
        selected = []
        for app_name, cask_name in self.apps_with_matches:
            if self.checkboxes.get(app_name, False):
                selected.append((app_name, cask_name))
        return selected

    def render_for_selection(self):
        """Render table in selection mode"""
        self.render(
            title="Checking apps for Homebrew packages",
            show_selection_prompt=True
        )

    def render_progress(self, title="[MIGRATION] Processing packages..."):
        """Render table showing migration progress"""
        self.render(title=title, show_selection_prompt=False)


class StatusLine:
    """Single-line status display for showing detailed operation progress"""

    def __init__(self):
        """Initialize the status line"""
        self._last_message_length = 0
        self._visible = False

    def update(self, action, details="", status_type="info"):
        """Update the status line with a new message

        Args:
            action: The action being performed (e.g., "Checking", "Downloading")
            details: Additional details (e.g., "karabiner-elements 45%")
            status_type: Type of status ("info", "success", "error", "warning")
        """
        # Build the status message
        if details:
            message = f"{action}: {details}"
        else:
            message = action

        # Add color based on status type
        if status_type == "success":
            colored_message = f"{Colors.GREEN}{message}{Colors.RESET}"
        elif status_type == "error":
            colored_message = f"{Colors.YELLOW}{message}{Colors.RESET}"
        elif status_type == "warning":
            colored_message = f"{Colors.ORANGE}{message}{Colors.RESET}"
        else:
            colored_message = message

        # Clear previous message and write new one
        clear_length = max(self._last_message_length, len(message), 100)
        sys.stdout.write(f"\r{' ' * clear_length}\r{colored_message}")
        sys.stdout.flush()

        self._last_message_length = len(message)
        self._visible = True

    def clear(self):
        """Clear the status line"""
        if self._visible:
            sys.stdout.write(f"\r{' ' * max(self._last_message_length, 100)}\r")
            sys.stdout.flush()
            self._last_message_length = 0
            self._visible = False

    def finish(self):
        """Clear the status line and move to next line"""
        self.clear()
        if self._visible:
            sys.stdout.write("\n")
            sys.stdout.flush()
            self._visible = False