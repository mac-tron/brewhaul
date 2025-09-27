# Brewhaul

A macOS CLI tool that helps you analyse and migrate applications based on their installation source to brew.

## Overview

Brewhaul is a command-line tool designed to help macOS users understand and manage their installed applications. It categorises applications by their installation method (Homebrew, App Store, or Manual installation) and provides powerful migration capabilities to consolidate package management under Homebrew.

## Features

- **Application Classification**: Automatically detects and categorises all applications in `/Applications` by their installation source
- **Smart Migration**: Migrate manually installed applications to Homebrew with intelligent package matching
- **App Store Consolidation**: Optionally migrate App Store applications to Homebrew for unified package management
- **Performance Optimised**: Uses efficient caching and parallel processing for fast analysis
- **Rich CLI Interface**: Beautiful terminal output with progress indicators, tables, and color-coded information
- **Dry Run Support**: Preview migration candidates before making any changes

## Installation

### Prerequisites

- macOS (10.15 or later recommended)
- Python 3.8 or later
- Homebrew (optional but recommended for full functionality)

### Quick Install

```bash
# Clone the repository
git clone https://github.com/yourusername/brewhaul.git
cd brewhaul

# Run directly (no installation needed)
./brewhaul list
```

### Installation Options

#### Option 1: Run from Repository (Recommended)
The simplest way - just clone and run:
```bash
./brewhaul [command]
```

#### Option 2: Install to PATH
Add to your system PATH for global access:
```bash
# Copy to local bin (create if doesn't exist)
mkdir -p ~/.local/bin
cp brewhaul ~/.local/bin/

# Add to PATH in your shell profile (.zshrc or .bash_profile)
echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.zshrc
source ~/.zshrc

# Now run from anywhere
brewhaul list
```

#### Option 3: Create Alias
Add an alias to your shell configuration:
```bash
echo "alias brewhaul='python3 /path/to/brewhaul/brewhaul'" >> ~/.zshrc
source ~/.zshrc
```

## Usage

### List Applications

View all applications organised by installation source:

```bash
# List all applications
brewhaul list

# Filter by specific type
brewhaul list --type manual
brewhaul list --type homebrew
brewhaul list --type appstore

# Multiple types
brewhaul list --type manual,homebrew

# JSON output for scripting
brewhaul list --format json
```

### Migrate Applications

Migrate manually installed applications to Homebrew:

```bash
# Preview what can be migrated (dry run)
brewhaul migrate --dry-run

# Perform migration interactively
brewhaul migrate

# Auto-approve all migrations
brewhaul migrate --auto

# Include App Store apps in migration
brewhaul migrate --include-appstore

# Dry run with JSON output
brewhaul migrate --dry-run --format json
```

## How It Works

### Application Detection

Brewhaul uses multiple detection methods to accurately classify applications:

1. **Homebrew Detection**:

   - Checks Homebrew's installation records
   - Verifies against Homebrew API for cask information
   - Examines application bundle identifiers

2. **App Store Detection**:

   - Looks for Mac App Store receipt files
   - Validates with `mas` tool if available
   - Checks application signatures

3. **Manual Installation**:
   - Applications not installed via Homebrew or App Store
   - Includes direct downloads, third-party installers, etc.

### Migration Process

The migration feature:

1. Scans all manually installed applications
2. Searches Homebrew's cask database for equivalent packages
3. Shows migration candidates with their Homebrew equivalents
4. Backs up applications before removal
5. Installs via Homebrew and verifies installation
6. Safely removes old versions after confirmation

## Architecture

```
brewhaul/
├── __main__.py          # Entry point
├── cli.py               # Command-line interface
├── core/
│   ├── detector.py      # Application detection logic
│   ├── manager.py       # Application management utilities
│   └── migrator.py      # Migration orchestration
├── providers/
│   ├── homebrew.py      # Homebrew integration
│   ├── homebrew_api.py  # Homebrew API client
│   ├── appstore.py      # App Store detection
│   └── brew_cache.py    # Caching layer
├── commands/
│   ├── list.py          # List command implementation
│   └── migrate.py       # Migrate command implementation
└── utils/
    ├── ui.py            # Terminal UI components
    └── app_metadata.py  # Application metadata extraction
```

## Performance

Brewhaul is optimised for speed:

- Caches Homebrew data to avoid repeated API calls
- Minimal subprocess calls through smart batching

## Limitations

- Requires `/Applications` directory access
- Some applications may not have Homebrew equivalents

## License

MIT License - see LICENSE file for details

## Author

mac-tron

## Acknowledgments

- Homebrew team
- `mas` project for App Store CLI integration
