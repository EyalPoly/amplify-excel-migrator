# Amplify Excel Migrator

A CLI tool to migrate data from Excel files to AWS Amplify GraphQL API.
Developed for the MECO project - https://github.com/sworgkh/meco-observations-amplify

## Installation

### From PyPI (Recommended)

Install the latest stable version from PyPI:

```bash
pip install amplify-excel-migrator
```

### From GitHub

Install directly from GitHub:

```bash
pip install git+https://github.com/EyalPoly/amplify-excel-migrator.git
```

### From Source

Clone the repository and install:

```bash
git clone https://github.com/EyalPoly/amplify-excel-migrator.git
cd amplify-excel-migrator
pip install .
```

### For Development

Install with development dependencies:

```bash
pip install -e ".[dev]"
```

This installs the package in editable mode with pytest and other development tools.

## Usage

The tool has three subcommands:

### 1. Configure (First Time Setup)

Save your AWS Amplify configuration:

```bash
amplify-migrator config
```

This will prompt you for:
- Excel file path
- AWS Amplify API endpoint
- AWS Region
- Cognito User Pool ID
- Cognito Client ID
- Admin username

Configuration is saved to `~/.amplify-migrator/config.json` (passwords are never saved).

### 2. Show Configuration

View your current saved configuration:

```bash
amplify-migrator show
```

### 3. Run Migration

Run the migration using your saved configuration:

```bash
amplify-migrator migrate
```

You'll only be prompted for your password (for security, passwords are never cached).

### Quick Start

```bash
# First time: configure the tool
amplify-migrator config

# View current configuration
amplify-migrator show

# Run migration (uses saved config)
amplify-migrator migrate

# View help
amplify-migrator --help
```

### Example: Configuration

```
╔════════════════════════════════════════════════════╗
║        Amplify Migrator - Configuration Setup      ║
╚════════════════════════════════════════════════════╝

📋 Configuration Setup:
------------------------------------------------------
Excel file path [data.xlsx]: my-data.xlsx
AWS Amplify API endpoint: https://xxx.appsync-api.us-east-1.amazonaws.com/graphql
AWS Region [us-east-1]:
Cognito User Pool ID: us-east-1_xxxxx
Cognito Client ID: your-client-id
Admin Username: admin@example.com

✅ Configuration saved successfully!
💡 You can now run 'amplify-migrator migrate' to start the migration.
```

### Example: Migration

```
╔════════════════════════════════════════════════════╗
║             Migrator Tool for Amplify              ║
╠════════════════════════════════════════════════════╣
║   This tool requires admin privileges to execute   ║
╚════════════════════════════════════════════════════╝

🔐 Authentication:
------------------------------------------------------
Admin Password: ********
```

## Requirements

- Python 3.8+
- AWS Amplify GraphQL API
- AWS Cognito User Pool
- Admin access to the Cognito User Pool

## Features

- **Configuration caching** - Save your setup, reuse it for multiple migrations
- **Interactive prompts** - Easy step-by-step configuration
- **Custom types and enums** - Full support for Amplify custom types
- **Duplicate detection** - Automatically skips existing records
- **Async uploads** - Fast parallel uploads for better performance
- **MFA support** - Works with multi-factor authentication
- **Automatic type parsing** - Smart field type detection and conversion

## Excel File Format

The Excel file should have:
- One sheet per Amplify model (sheet name must match model name)
- Column names matching the model field names
- First row as headers

### Example Excel Structure

**Sheet: User**
| name | email | age |
|------|-------|-----|
| John | john@example.com | 30 |
| Jane | jane@example.com | 25 |

**Sheet: Post**
| title | content | userId |
|-------|---------|--------|
| First Post | Hello World | john@example.com |

## License

MIT