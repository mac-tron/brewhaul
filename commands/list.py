"""List command implementation."""

import json
from utils.ui import Colors, TableFormatter
from core.detector import build_app_registry


def handle_list_command(args, apps, brew_cask_names, brew_paths):
    """Handle the list subcommand"""
    # Use centralized app registry for efficient classification
    print(f"{Colors.DIM}Classifying applications by installation type{Colors.RESET}")
    registry = build_app_registry(apps, brew_paths, show_progress=True)

    # Extract data for backward compatibility
    brew_apps_list = registry.homebrew_apps
    appstore_apps_list = registry.appstore_apps
    manual_apps_list = registry.manual_apps
    brew_count = registry.homebrew_count
    appstore_count = registry.appstore_count
    manual_count = registry.manual_count

    # Use args.types if available (comma-separated support), otherwise fall back to args.type
    types_to_show = getattr(args, 'types', [args.type] if args.type != 'all' else ['manual', 'homebrew', 'appstore'])

    if args.format == 'json':
        result = {
            'homebrew': brew_apps_list if 'homebrew' in types_to_show else [],
            'appstore': appstore_apps_list if 'appstore' in types_to_show else [],
            'manual': manual_apps_list if 'manual' in types_to_show else [],
            'summary': {
                'homebrew_count': brew_count,
                'appstore_count': appstore_count,
                'manual_count': manual_count,
                'total': brew_count + appstore_count + manual_count
            }
        }
        print(json.dumps(result, indent=2))
        return

    # Table format output
    formatter = TableFormatter()

    # Prepare table data
    table_rows = []

    if 'homebrew' in types_to_show:
        for app_name in brew_apps_list:
            table_rows.append((app_name, f"{Colors.GREEN}Homebrew{Colors.RESET}"))

    if 'appstore' in types_to_show:
        for app_name in appstore_apps_list:
            table_rows.append((app_name, f"{Colors.BLUE}App Store{Colors.RESET}"))

    if 'manual' in types_to_show:
        for app_name in manual_apps_list:
            table_rows.append((app_name, f"{Colors.YELLOW}Manual{Colors.RESET}"))

    # Sort all apps alphabetically
    table_rows.sort(key=lambda x: x[0].lower())

    # Print the table
    print(f"\n{Colors.BOLD}Applications by Installation Type:{Colors.RESET}")
    table = formatter.format_table(
        headers=['Application', 'Source'],
        rows=table_rows
    )
    print(table)

    # Print summary as a table
    total_count = brew_count + appstore_count + manual_count
    print(f"\n{Colors.BOLD}Summary:{Colors.RESET}")

    summary_rows = []
    if 'homebrew' in types_to_show:
        percentage = (brew_count / total_count * 100) if total_count > 0 else 0
        summary_rows.append((
            f"{Colors.GREEN}Homebrew Applications{Colors.RESET}",
            str(brew_count),
            f"{percentage:.1f}%"
        ))
    if 'appstore' in types_to_show:
        percentage = (appstore_count / total_count * 100) if total_count > 0 else 0
        summary_rows.append((
            f"{Colors.BLUE}App Store Applications{Colors.RESET}",
            str(appstore_count),
            f"{percentage:.1f}%"
        ))
    if 'manual' in types_to_show:
        percentage = (manual_count / total_count * 100) if total_count > 0 else 0
        summary_rows.append((
            f"{Colors.YELLOW}Manually Installed Applications{Colors.RESET}",
            str(manual_count),
            f"{percentage:.1f}%"
        ))

    # Show total if displaying all types or multiple types
    if len(types_to_show) > 1:
        summary_rows.append((
            f"{Colors.BOLD}Total Applications Analyzed{Colors.RESET}",
            str(total_count),
            "100.0%"
        ))

    summary_table = formatter.format_table(
        headers=['Type', 'Count', 'Percentage'],
        rows=summary_rows
    )
    print(summary_table)