"""Command-line interface for brewhaul."""

import argparse
from .utils.ui import Colors, PerformanceTimer, subprocess_counter
from .core.detector import get_all_applications
from .providers.homebrew import check_homebrew_installed, get_brew_apps, get_brew_app_paths
from .commands.list import handle_list_command
from .commands.migrate import handle_migrate_command


def parse_arguments():
    """Parse command line arguments"""
    parser = argparse.ArgumentParser(description="Manage macOS applications by installation source")
    subparsers = parser.add_subparsers(dest='command', help='Available commands')

    # List subcommand
    list_parser = subparsers.add_parser('list', help='List applications by installation type')
    list_parser.add_argument('--type',
                           default='all',
                           help='Filter by installation type: manual, homebrew, appstore, all, or comma-separated list (default: all)')
    list_parser.add_argument('--format', choices=['table', 'json'], default='table',
                           help='Output format (default: table)')

    # Migrate subcommand (use --dry-run to preview migratable apps)
    migrate_parser = subparsers.add_parser('migrate', help='Migrate manually installed apps to Homebrew (use --dry-run to check which apps can be migrated)')
    migrate_parser.add_argument('--dry-run', action='store_true',
                              help='Show what would be migrated without making changes')
    migrate_parser.add_argument('--auto', action='store_true',
                              help='Automatically approve all migrations (non-interactive)')
    migrate_parser.add_argument('--format', choices=['table', 'json'], default='table',
                              help='Output format for dry-run (default: table)')
    migrate_parser.add_argument('--include-appstore', action='store_true',
                              help='Include App Store apps for migration to Homebrew (consolidate package management)')

    args = parser.parse_args()

    # If no command is specified, default to list all
    if args.command is None:
        args.command = 'list'
        args.type = 'all'
        args.format = 'table'

    # Process --type argument for list command
    if args.command == 'list' and hasattr(args, 'type'):
        valid_types = {'manual', 'homebrew', 'appstore', 'all'}
        if ',' in args.type:
            # Split comma-separated values and validate
            types = [t.strip() for t in args.type.split(',')]
            invalid_types = [t for t in types if t not in valid_types]
            if invalid_types:
                parser.error(f"Invalid type(s): {', '.join(invalid_types)}. Valid types are: {', '.join(valid_types)}")
            # Store as list for processing
            args.types = types
        else:
            # Single value - validate and convert to list
            if args.type not in valid_types:
                parser.error(f"Invalid type: {args.type}. Valid types are: {', '.join(valid_types)}")
            args.types = [args.type] if args.type != 'all' else ['manual', 'homebrew', 'appstore']

    return args


def main():
    args = parse_arguments()

    # Reset subprocess counter for this run
    subprocess_counter.reset()

    with PerformanceTimer(f"brewhaul {args.command} command", show_logs=False):
        # Display initial processing message
        print()  # Add newline before package manager message
        print(f"{Colors.BOLD}[*] macOS Package Manager{Colors.RESET}")
        print(f"{Colors.DIM}Analyzing your application installations...{Colors.RESET}")

        # Get all applications
        with PerformanceTimer("Scanning applications directory", show_logs=False):
            apps = get_all_applications()

        # Get Homebrew data only for commands that need it
        brew_cask_names = []
        brew_paths = []
        if check_homebrew_installed():
            # Both list and migrate commands benefit from brew_paths for efficient classification
            # List command also needs brew_cask_names
            if args.command in ['list', 'migrate']:
                with PerformanceTimer("Loading Homebrew data", show_logs=False):
                    if args.command == 'list':
                        brew_cask_names = get_brew_apps()
                    brew_paths = get_brew_app_paths()
        else:
            print(f"{Colors.YELLOW}[!] Homebrew not detected - some features unavailable{Colors.RESET}")

        # Dispatch to appropriate handler based on command
        with PerformanceTimer(f"Executing {args.command} command", show_logs=False):
            if args.command == 'list':
                handle_list_command(args, apps, brew_cask_names, brew_paths)
            elif args.command == 'migrate':
                handle_migrate_command(args, apps, brew_cask_names, brew_paths)



if __name__ == "__main__":
    main()