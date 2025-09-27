"""Migrate command implementation."""

import json
import os
import sys
import re
from ..utils.ui import Colors, TableFormatter, StatusIcons, SectionDivider, MigrationTable
from ..core.detector import build_app_registry
from ..core.manager import is_app_running
from ..core.migrator import migrate_manual_apps_to_brew
from ..providers.homebrew import check_brew_equivalent_with_api


def handle_migrate_command(args, apps, brew_cask_names=None, brew_paths=None):
    """Handle the migrate subcommand"""
    from ..providers.homebrew import check_homebrew_installed
    from ..providers.homebrew_api import HomebrewAPI

    if not check_homebrew_installed():
        print(f"{Colors.YELLOW}Homebrew is not installed. Cannot migrate applications.{Colors.RESET}")
        return

    # Initialize Homebrew API once for all operations
    api = HomebrewAPI()
    api.load_data()  # Load data once upfront

    # Use the centralized app registry for efficient classification
    sys.stdout.write(f"{Colors.DIM}Classifying applications by installation type{Colors.RESET}\n")
    sys.stdout.flush()
    registry = build_app_registry(apps, brew_paths, show_progress=True)

    # Determine which apps to include for migration
    migration_candidates = registry.manual_apps[:]  # Copy the list
    migration_app_paths = registry.manual_app_paths.copy()

    # Include App Store apps if requested
    if getattr(args, 'include_appstore', False):
        print(f"{Colors.BLUE}Including App Store apps for migration (--include-appstore flag detected){Colors.RESET}")
        for app_name in registry.appstore_apps:
            migration_candidates.append(app_name)
            # Reconstruct path for App Store apps (they follow the same pattern)
            migration_app_paths[app_name] = os.path.join("/Applications", app_name)

    migration_candidates.sort()

    if not migration_candidates:
        if getattr(args, 'include_appstore', False):
            print(f"{Colors.YELLOW}No manually installed or App Store applications found to migrate.{Colors.RESET}")
        else:
            print(f"{Colors.YELLOW}No manually installed applications found to migrate.{Colors.RESET}")
            print(f"{Colors.BLUE}Tip: Use --include-appstore to also migrate App Store apps to Homebrew{Colors.RESET}")
        return

    # Update variable names for clarity in the rest of the function
    manual_apps_list = migration_candidates
    manual_app_paths = migration_app_paths

    if args.dry_run:
        # Check if we need JSON format
        if args.format == 'json':
            result = {
                'dry_run': True,
                'apps_to_migrate': {},
                'summary': {
                    'total_manual_apps': len(manual_apps_list),
                    'can_migrate': 0,
                    'cannot_migrate': 0,
                    'currently_running': 0
                }
            }

            for app_name in manual_apps_list:
                app_path = manual_app_paths.get(app_name)
                casks = check_brew_equivalent_with_api(app_name, app_path, api)
                is_running = is_app_running(app_name)

                if casks:
                    result['apps_to_migrate'][app_name] = {
                        'can_migrate': True,
                        'homebrew_equivalent': casks[0][0],
                        'is_running': is_running,
                        'status': 'running' if is_running else 'ready'
                    }
                    result['summary']['can_migrate'] += 1
                    if is_running:
                        result['summary']['currently_running'] += 1
                else:
                    result['apps_to_migrate'][app_name] = {
                        'can_migrate': False,
                        'homebrew_equivalent': None,
                        'is_running': is_running,
                        'status': 'no_equivalent'
                    }
                    result['summary']['cannot_migrate'] += 1

            print(json.dumps(result, indent=2))
        else:
            # Progressive table output
            formatter = TableFormatter()

            print(f"\n{Colors.ORANGE}[DRY RUN]{Colors.RESET} Checking apps for Homebrew packages")

            # Calculate initial column widths based on headers
            headers = ['App Name', 'Brew Package', 'Status']

            # Pre-calculate max widths to avoid table jumping
            max_app_name_len = max(len(app) for app in manual_apps_list) if manual_apps_list else 20
            col_widths = [
                max(max_app_name_len, len(headers[0])),
                max(20, len(headers[1])),  # Brew equivalent column
                max(10, len(headers[2]))   # Status column
            ]

            # Build and print the table header
            def format_row(values, widths, use_heavy=False):
                cells = []
                for i, val in enumerate(values):
                    if i < len(widths):
                        # Remove ANSI codes for width calculation
                        clean_val = re.sub(r'\033\[[0-9;]*m', '', str(val))
                        padding = widths[i] - len(clean_val)
                        cells.append(f" {val}{' ' * padding} ")
                border_char = "┃" if use_heavy else "│"
                return border_char + border_char.join(cells) + border_char

            # Print header
            header_row = format_row(headers, col_widths, use_heavy=True)
            border_top = "┏" + "┳".join("━" * (w + 2) for w in col_widths) + "┓"
            border_mid = "┡" + "╇".join("━" * (w + 2) for w in col_widths) + "┩"

            print(border_top)
            print(header_row)
            print(border_mid)

            # Process apps and display progressively
            table_rows = []
            migratable_count = 0
            total_apps = len(manual_apps_list)

            for i, app_name in enumerate(manual_apps_list):
                # Show checking status with proper width calculation
                progress_msg = f"Checking {i+1}/{total_apps}: {app_name[:40]}..."
                # Calculate the exact width of the table row
                row_width = sum(col_widths) + len(col_widths) * 3 + 1  # cells + separators + borders
                # Create a full-width progress message that matches table structure
                inner_width = row_width - 3  # Subtract the two border characters and leading space
                padded_msg = progress_msg[:inner_width].ljust(inner_width)
                sys.stdout.write(f"\r│ {Colors.DIM}{padded_msg}{Colors.RESET}│\r")
                sys.stdout.flush()

                app_path = manual_app_paths.get(app_name)
                casks = check_brew_equivalent_with_api(app_name, app_path, api)

                # Prepare row data
                if casks:
                    cask_name = casks[0][0]  # Use first match
                    if is_app_running(app_name):
                        status = f"{Colors.YELLOW}Running{Colors.RESET}"
                    else:
                        status = f"{Colors.GREEN}Ready{Colors.RESET}"
                    row = (app_name, cask_name, status)
                    migratable_count += 1
                else:
                    row = (
                        app_name,
                        f"{Colors.DIM}No package{Colors.RESET}",
                        f"{Colors.DIM}Skipped{Colors.RESET}"
                    )

                table_rows.append(row)

                # Clear the entire line before printing the row
                sys.stdout.write("\r" + " " * row_width + "\r")
                sys.stdout.flush()
                print(format_row(row, col_widths, use_heavy=False))

            # Close the table
            border_bottom = "└" + "┴".join("─" * (w + 2) for w in col_widths) + "┘"
            print(border_bottom)

            # Show summary as a table
            total_analyzed = len(manual_apps_list)
            no_equivalent_count = total_analyzed - migratable_count
            print(SectionDivider.format_header("Summary", width=40))

            migratable_percentage = (migratable_count / total_analyzed * 100) if total_analyzed > 0 else 0
            no_equivalent_percentage = (no_equivalent_count / total_analyzed * 100) if total_analyzed > 0 else 0

            summary_rows = []
            summary_rows.append((
                f"{StatusIcons.SUCCESS} {Colors.GREEN}Apps that can be migrated{Colors.RESET}",
                f"{migratable_count} ({migratable_percentage:.1f}%)"
            ))
            summary_rows.append((
                f"{StatusIcons.WARNING} {Colors.YELLOW}Apps without Homebrew packages{Colors.RESET}",
                f"{no_equivalent_count} ({no_equivalent_percentage:.1f}%)"
            ))

            if getattr(args, 'include_appstore', False):
                manual_count = len(registry.manual_apps)
                appstore_count = len(registry.appstore_apps)
                summary_rows.append((
                    f"{Colors.DIM}  {StatusIcons.TREE_BRANCH} Manual apps{Colors.RESET}",
                    str(manual_count)
                ))
                summary_rows.append((
                    f"{Colors.DIM}  {StatusIcons.TREE_END} App Store apps{Colors.RESET}",
                    str(appstore_count)
                ))
            else:
                if registry.appstore_apps:
                    summary_rows.append((
                        f"{StatusIcons.INFO} {Colors.BLUE}App Store apps (excluded){Colors.RESET}",
                        str(len(registry.appstore_apps))
                    ))

            summary_table = formatter.format_table(
                headers=['Category', 'Count'],
                rows=summary_rows
            )
            print(summary_table)

            if not getattr(args, 'include_appstore', False) and registry.appstore_apps:
                print(f"\n{StatusIcons.INFO} {Colors.DIM}Tip: Use --include-appstore to also migrate App Store apps{Colors.RESET}")
        return

    # Separate apps with and without Homebrew packages
    migratable_apps = []
    migratable_app_paths = {}
    apps_without_matches = []

    for app_name in manual_apps_list:
        app_path = manual_app_paths.get(app_name)
        casks = check_brew_equivalent_with_api(app_name, app_path, api)
        if casks:  # Has Homebrew equivalent
            migratable_apps.append(app_name)
            migratable_app_paths[app_name] = manual_app_paths[app_name]
        else:
            apps_without_matches.append(app_name)

    if not migratable_apps:
        print(f"{Colors.YELLOW}No manually installed applications found with Homebrew packages to migrate.{Colors.RESET}")
        if apps_without_matches:
            print(f"Apps without matches: {', '.join(sorted(apps_without_matches))} ({len(apps_without_matches)} apps)")
        return

    # Migration UI is now handled entirely in migrator.py with MigrationTable


    # Perform actual migration with the new compact UI
    migrate_manual_apps_to_brew(
        migratable_apps,
        migratable_app_paths,
        auto_approve=args.auto,
        apps_without_matches=apps_without_matches
    )

    # Summary is now handled in migrator.py with the final table display


