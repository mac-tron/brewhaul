"""Application migration orchestration."""

import subprocess
import shlex
import time
from ..utils.ui import Colors, StatusIcons, SectionDivider, MigrationTable, ProgressIndicator, StatusLine
from .manager import is_app_running, kill_app, move_to_trash


def _perform_migration(app_name, app_path, cask_name, migration_table=None, status_line=None):
    """Perform the actual migration from manual installation to Homebrew

    Args:
        app_name: Name of the app
        app_path: Path to the app
        cask_name: Homebrew cask name
        migration_table: Optional MigrationTable for status updates
        status_line: Optional StatusLine for detailed progress
    """
    try:
        # Step 1: Move the application to trash
        if migration_table:
            migration_table.update_status(app_name, "Removing")
            migration_table.render_progress()

        if status_line:
            status_line.update("Moving", f"{app_name} to Trash")

        if not move_to_trash(app_path):
            if migration_table:
                migration_table.update_status(app_name, f"{StatusIcons.FAILED} Failed")
                migration_table.render_progress()
            return False

        # Step 2: Install the Homebrew cask

        # Run brew install with output shown to user in real-time
        # Security fix: Validate cask_name to prevent command injection
        if not cask_name or not isinstance(cask_name, str) or len(cask_name) > 100:
            print(f"{Colors.YELLOW}Invalid cask name. Migration cancelled.{Colors.RESET}")
            return False

        # Track installation progress
        if status_line:
            status_line.update("Fetching", f"{cask_name} from Homebrew")

        process = subprocess.Popen(['brew', 'install', '--cask', cask_name],
                                  stdout=subprocess.PIPE,
                                  stderr=subprocess.STDOUT,
                                  universal_newlines=True)

        output_lines = []
        progress_pct = 0
        for line in process.stdout:
            output_lines.append(line.strip())

            # Update status line with detailed progress
            if status_line:
                if "Downloading" in line:
                    # Try to extract download progress if available
                    if "%" in line:
                        import re
                        pct_match = re.search(r'(\d+)%', line)
                        if pct_match:
                            status_line.update("Downloading", f"{cask_name} {pct_match.group(1)}%")
                    else:
                        status_line.update("Downloading", cask_name)
                elif "Verifying" in line or "checksum" in line.lower():
                    status_line.update("Verifying", "Package signature")
                elif "Extracting" in line or "extract" in line.lower():
                    status_line.update("Extracting", f"{cask_name}.app")
                elif "Installing" in line:
                    status_line.update("Installing", f"/Applications/{app_name}")
                elif "Moving" in line:
                    status_line.update("Installing", f"Moving to /Applications")
                elif "Linking" in line:
                    status_line.update("Linking", "Creating symlinks")

            # Update progress in table
            if migration_table:
                if "Downloading" in line:
                    progress_pct = min(progress_pct + 10, 50)
                elif "Installing" in line:
                    progress_pct = min(progress_pct + 25, 90)
                migration_table.update_status(app_name, f"{StatusIcons.PROCESSING} {progress_pct}%")
                migration_table.render_progress()

        return_code = process.wait()

        if return_code != 0:
            if migration_table:
                migration_table.update_status(app_name, f"{StatusIcons.FAILED} Failed")
                migration_table.render_progress()
            return False

        if migration_table:
            migration_table.update_status(app_name, f"{StatusIcons.SUCCESS} Done")
            migration_table.render_progress()

        if status_line:
            status_line.update("Installed", f"{cask_name} via Homebrew", "success")

        return True

    except Exception as e:
        if migration_table:
            migration_table.update_status(app_name, f"{StatusIcons.FAILED} Error")
            migration_table.render_progress()
        return False


def select_migration_mode(manual_apps_list, manual_app_paths, apps_without_matches=None):
    """Present migration modes to the user and return the selected apps for migration

    Args:
        manual_apps_list: List of app names with Homebrew matches
        manual_app_paths: Dict mapping app names to paths
        apps_without_matches: List of app names without Homebrew matches

    Returns:
        Tuple of (selected_apps, auto_approve, migration_table)
    """
    from ..providers.homebrew import check_brew_equivalent
    import sys

    print(f"\n{Colors.ORANGE}[MIGRATION]{Colors.RESET} Checking apps for Homebrew packages")

    # Build list of apps with their targets - progressively
    apps_with_targets = []
    sorted_apps = sorted(manual_apps_list)
    total_apps = len(sorted_apps)

    for i, app_name in enumerate(sorted_apps):
        # Show progress message
        progress_msg = f"Checking {i+1}/{total_apps}: {app_name[:40]}..."
        sys.stdout.write(f"\r{Colors.DIM}{progress_msg}{Colors.RESET}")
        sys.stdout.flush()

        app_path = manual_app_paths.get(app_name)
        casks = check_brew_equivalent(app_name, app_path)
        if casks:
            cask_name = casks[0][0]  # Use first match
            apps_with_targets.append((app_name, cask_name))

    # Clear the progress line
    sys.stdout.write("\r" + " " * 80 + "\r")
    sys.stdout.flush()

    # Create migration table
    migration_table = MigrationTable(apps_with_targets, apps_without_matches)

    # Render the table first so users can see what's available
    migration_table.render_for_selection()

    # Show menu options after the table
    print()  # Empty line for spacing
    print(f"How would you like to proceed?")
    print(f"1. Review and approve each app individually {Colors.DIM}(recommended){Colors.RESET}")
    print(f"2. Select specific apps from the list")
    print(f"3. Migrate all apps automatically")

    while True:
        choice = input(f"\nYour choice [1-3, Enter=1]: ").strip()

        # Default to option 1 if empty input
        if not choice:
            choice = "1"

        if choice == "3":
            # Migrate all apps
            # Clear the menu options and input line (7 lines total)
            # 1 empty line, 4 menu lines, 1 empty line before input, 1 input line
            for _ in range(7):
                sys.stdout.write("\033[A\033[2K")  # Move up and clear line
            sys.stdout.flush()

            # Select all apps (update_display=True will handle the rendering)
            all_indices = list(range(1, len(apps_with_targets) + 1))
            migration_table.select_apps(all_indices, update_display=True)

            confirm = input(f"\nMigrate all {len(apps_with_targets)} apps? [y/N]: ").lower()

            if confirm == 'y':
                return [app for app, _ in apps_with_targets], True, migration_table
            else:
                print(f"{Colors.YELLOW}Migration cancelled.{Colors.RESET}")
                return [], False, None

        elif choice == "2":
            # Select specific apps
            # Clear the menu options and input line (7 lines total)
            # 1 empty line, 4 menu lines, 1 empty line before input, 1 input line
            for _ in range(7):
                sys.stdout.write("\033[A\033[2K")  # Move up and clear line
            sys.stdout.flush()

            selections = input(f"Select apps [1-{len(apps_with_targets)}, all, none]: ").strip()

            if selections.lower() == 'none' or not selections:
                print(f"{Colors.YELLOW}No apps selected. Migration cancelled.{Colors.RESET}")
                return [], False, None
            elif selections.lower() == 'all':
                selected_indices = list(range(1, len(apps_with_targets) + 1))
            else:
                try:
                    # Parse selection
                    selected_indices = []
                    for part in selections.split(','):
                        idx = int(part.strip())
                        if 1 <= idx <= len(apps_with_targets):
                            selected_indices.append(idx)
                        else:
                            print(f"{Colors.YELLOW}Index {idx} out of range. Skipping.{Colors.RESET}")
                except ValueError:
                    print(f"{Colors.YELLOW}Invalid input. Please enter numbers like 1,3,5{Colors.RESET}")
                    continue

            if not selected_indices:
                print(f"{Colors.YELLOW}No valid apps selected. Migration cancelled.{Colors.RESET}")
                return [], False, None

            # Update table with selection (cursor save/restore will handle the update)
            migration_table.select_apps(selected_indices, update_display=True)

            selected_apps = [app for app, _ in migration_table.get_selected_apps()]
            print(f"\nSelected {len(selected_apps)} app{'s' if len(selected_apps) != 1 else ''}: {', '.join(selected_apps)}")
            confirm = input(f"Proceed with migration? [y/N]: ").lower()

            if confirm == 'y':
                return selected_apps, True, migration_table
            else:
                print(f"{Colors.YELLOW}Migration cancelled.{Colors.RESET}")
                return [], False, None

        elif choice == "1":
            # Manual approval for each app
            # Clear the menu options and input line (7 lines total)
            # 1 empty line, 4 menu lines, 1 empty line before input, 1 input line
            for _ in range(7):
                sys.stdout.write("\033[A\033[2K")  # Move up and clear line
            sys.stdout.flush()

            print(f"Selected: Approve each app manually")
            return [app for app, _ in apps_with_targets], False, migration_table

        else:
            print(f"{Colors.YELLOW}Invalid choice. Please enter 1, 2, or 3.{Colors.RESET}")


def migrate_manual_apps_to_brew(manual_apps_list, manual_app_paths, auto_approve=False, apps_without_matches=None):
    """Improved migration routine with different approval modes

    Args:
        manual_apps_list: List of app names with Homebrew matches
        manual_app_paths: Dict mapping app names to paths
        auto_approve: Whether to skip individual confirmations
        apps_without_matches: List of app names without Homebrew matches
    """

    if not manual_apps_list:
        print(f"{Colors.YELLOW}No manually installed applications found to migrate.{Colors.RESET}")
        return 0

    # Get user's preferred migration mode (unless auto_approve is already set)
    if auto_approve:
        from ..providers.homebrew import check_brew_equivalent
        import sys

        print(f"\n{Colors.ORANGE}[MIGRATION]{Colors.RESET} Checking apps for Homebrew packages")

        # Build list for auto mode - progressively
        apps_with_targets = []
        sorted_apps = sorted(manual_apps_list)
        total_apps = len(sorted_apps)

        for i, app_name in enumerate(sorted_apps):
            # Show progress message
            progress_msg = f"Checking {i+1}/{total_apps}: {app_name[:40]}..."
            sys.stdout.write(f"\r{Colors.DIM}{progress_msg}{Colors.RESET}")
            sys.stdout.flush()

            app_path = manual_app_paths.get(app_name)
            casks = check_brew_equivalent(app_name, app_path)
            if casks:
                apps_with_targets.append((app_name, casks[0][0]))

        # Clear the progress line
        sys.stdout.write("\r" + " " * 80 + "\r")
        sys.stdout.flush()

        migration_table = MigrationTable(apps_with_targets, apps_without_matches)
        # Select all for auto mode
        migration_table.select_apps(list(range(1, len(apps_with_targets) + 1)))
        selected_apps = manual_apps_list
        print(f"Auto-approval mode: Migrating all {len(manual_apps_list)} apps")
    else:
        selected_apps, auto_approve, migration_table = select_migration_mode(
            manual_apps_list, manual_app_paths, apps_without_matches
        )

    if not selected_apps or migration_table is None:
        return 0  # User cancelled or no apps selected

    migrated_count = 0
    failed_apps = []

    # Create status line for detailed progress
    status_line = StatusLine()

    # Set all selected apps to Queue status initially
    for app_name in selected_apps:
        migration_table.update_status(app_name, f"{StatusIcons.WARNING}⏸ Queue")
    migration_table.render_progress()

    for app_name in selected_apps:
        app_path = manual_app_paths[app_name]

        # Update status to processing
        migration_table.update_status(app_name, "Removing")
        migration_table.render_progress()

        # Get available brew casks for this app
        from ..providers.homebrew import check_brew_equivalent
        casks = check_brew_equivalent(app_name, app_path)

        if not casks:
            migration_table.update_status(app_name, f"{StatusIcons.WARNING} No match")
            migration_table.render_progress()
            continue

        # Check if the app is currently running
        status_line.update("Checking", f"{app_name} running state")
        app_running = is_app_running(app_name)

        if app_running:
            status_line.clear()
            if auto_approve:
                status_line.update("Stopping", app_name)
                if not kill_app(app_name):
                    status_line.update("Failed", f"Could not stop {app_name}", "error")
                    migration_table.update_status(app_name, f"{StatusIcons.FAILED} Failed")
                    migration_table.render_progress()
                    failed_apps.append(app_name)
                    continue
            else:
                # Show prompt below table
                print(f"\n{StatusIcons.WARNING} {app_name} is running")
                kill_confirm = input(f"Quit app before migrating? [y/N]: ").lower()

                if kill_confirm == 'y':
                    status_line.update("Stopping", app_name)
                    if not kill_app(app_name):
                        status_line.update("Failed", f"Could not stop {app_name}", "error")
                        migration_table.update_status(app_name, f"{StatusIcons.FAILED} Failed")
                        migration_table.render_progress()
                        failed_apps.append(app_name)
                        continue
                else:
                    migration_table.update_status(app_name, "Skipped")
                    migration_table.render_progress()
                    status_line.clear()  # Clear after skipping
                    continue

        # If there's only one cask available
        if len(casks) == 1:
            cask_name, description = casks[0]

            if not auto_approve:
                status_line.clear()  # Clear status before user prompt
                print(f"\nMigrate {app_name} to {cask_name}? [y/N]: ", end='')
                confirm = input().lower()
                if confirm != 'y':
                    migration_table.update_status(app_name, "Skipped")
                    migration_table.render_progress()
                    status_line.clear()  # Clear after skipping
                    continue

            # Perform migration with table updates and status line
            if _perform_migration(app_name, app_path, cask_name, migration_table, status_line):
                migrated_count += 1
            else:
                failed_apps.append(app_name)

        # If there are multiple casks available
        else:
            status_line.clear()  # Clear status before showing options
            print(f"Multiple matches for {app_name}:")
            for i, (cask_name, description) in enumerate(casks[:3], 1):  # Show max 3 options
                print(f"  {i}. {cask_name}")

            # Auto-select first cask if auto_approve is True
            if auto_approve:
                selected_cask = casks[0][0]
                print(f"Auto-selecting: {selected_cask}")
                if _perform_migration(app_name, app_path, selected_cask, migration_table, status_line):
                    migrated_count += 1
            else:
                # Ask user to select a cask
                while True:
                    try:
                        choice = input(f"Select [1-{min(len(casks), 3)}, or skip]: ")

                        if choice.lower() in ['s', 'skip', '']:
                            print(f"{Colors.YELLOW}Skipping {app_name}{Colors.RESET}")
                            break

                        choice_index = int(choice) - 1
                        # Security fix: Enhanced bounds checking
                        if 0 <= choice_index < len(casks) and choice_index < 100:  # Prevent array access beyond reasonable bounds
                            selected_cask = casks[choice_index][0]

                            if _perform_migration(app_name, app_path, selected_cask, migration_table, status_line):
                                migrated_count += 1
                            break
                        else:
                            print(f"{Colors.YELLOW}Invalid choice. Please enter a number between 1 and {len(casks)}.{Colors.RESET}")
                    except ValueError:
                        print(f"{Colors.YELLOW}Invalid input. Please enter a number or 'c'.{Colors.RESET}")

    # Clear status line before final summary
    status_line.clear()

    # Final summary
    if migration_table:
        migration_table.render(title="[MIGRATION] Complete", clear_previous=True)
        total_selected = len(selected_apps)
        if failed_apps:
            print(f"\nResult: {migrated_count}/{total_selected} successful, {len(failed_apps)} failed")
            if failed_apps:
                print(f"Failed apps remain in trash and can be restored")
        else:
            print(f"\nResult: {migrated_count}/{total_selected} successful")

    return migrated_count