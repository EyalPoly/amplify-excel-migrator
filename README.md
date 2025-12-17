# Amplify Excel Migrator

[![PyPI version](https://badge.fury.io/py/amplify-excel-migrator.svg)](https://badge.fury.io/py/amplify-excel-migrator)
[![Python versions](https://img.shields.io/pypi/pyversions/amplify-excel-migrator.svg)](https://pypi.org/project/amplify-excel-migrator/)
[![Downloads](https://pepy.tech/badge/amplify-excel-migrator)](https://pepy.tech/project/amplify-excel-migrator)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

A CLI tool to migrate data from Excel files to AWS Amplify GraphQL API.
Developed for the MECO project - https://github.com/sworgkh/meco-observations-amplify

## Installation

### From PyPI (Recommended)

Install the latest stable version from PyPI:

```bash
pip install amplify-excel-migrator
```

### From Source

Clone the repository and install:

```bash
git clone https://github.com/EyalPoly/amplify-excel-migrator.git
cd amplify-excel-migrator
pip install .
```

## Usage

The tool has four subcommands:

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

Configuration is saved to `~/.amplify-migrator/config.json`

### 2. Show Configuration

View your current saved configuration:

```bash
amplify-migrator show
```

### 3. Export Schema

Export your GraphQL schema to a markdown reference document:

```bash
# Export all models
amplify-migrator export-schema

# Export to a specific file
amplify-migrator export-schema --output my-schema.md

# Export specific models only
amplify-migrator export-schema --models User Post Comment
```

This generates a comprehensive markdown document with:
- All model fields with types and requirements
- Enum definitions
- Custom type structures
- Foreign key relationships
- Excel formatting guidelines

Perfect for sharing with team members who need to prepare Excel files for migration.

💡 The exported schema reference can help you prepare your Excel file. For detailed formatting guidelines, see the [Excel Format Specification](docs/EXCEL_FORMAT_SPECIFICATION.md).

### 4. Run Migration

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

# Export schema documentation (share with team)
amplify-migrator export-schema

# Run migration (uses saved config)
amplify-migrator migrate

# View help
amplify-migrator --help
```

📋 For detailed Excel format requirements, see the [Excel Format Specification](docs/EXCEL_FORMAT_SPECIFICATION.md).

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

### Data Processing & Conversion
- **Automatic type parsing** - Smart field type detection for all GraphQL types including scalars, enums, and custom types
- **Custom types and enums** - Full support for Amplify custom types with automatic conversion
- **Duplicate detection** - Automatically skips existing records to prevent duplicates
- **Foreign key resolution** - Automatic relationship handling with pre-fetching for performance

### AWS Integration
- **Configuration caching** - Save your setup, reuse it for multiple migrations
- **MFA support** - Works with multi-factor authentication
- **Admin group validation** - Ensures proper authorization before migration

### Performance
- **Async uploads** - Fast parallel uploads with configurable batch size
- **Connection pooling** - Efficient HTTP connection reuse for better performance
- **Pagination support** - Handles large datasets efficiently

### User Experience
- **Interactive prompts** - Easy step-by-step configuration
- **Progress reporting** - Real-time feedback on migration status
- **Detailed error messages** - Clear context for troubleshooting failures
- **Schema export** - Generate markdown documentation of your GraphQL schema to share with team members

## Excel Format Requirements

Your Excel file must follow specific formatting guidelines for sheet names, column headers, data types, and special field handling. For comprehensive format requirements, examples, and troubleshooting, see:

📋 **[Excel Format Specification Guide](docs/EXCEL_FORMAT_SPECIFICATION.md)**

## Advanced Features

- **Foreign Key Resolution** - Automatically resolves relationships between models with pre-fetching for optimal performance
- **Schema Introspection** - Dynamically queries your GraphQL schema to understand model structures and field types
- **Configurable Batch Processing** - Tune upload performance with adjustable batch sizes (default: 20 records per batch)
- **Progress Reporting** - Real-time batch progress with per-sheet confirmation prompts before upload

## Error Handling & Recovery

When records fail to upload, the tool provides a robust recovery mechanism to help you identify and fix issues without starting over.

### How It Works

1. **Automatic Error Capture** - Each failed record is logged with detailed error messages explaining what went wrong
2. **Failed Records Export** - After migration completes, you'll be prompted to export failed records to a new Excel file with a timestamp (e.g., `data_failed_records_20251201_143022.xlsx`)
3. **Easy Retry** - Fix the issues in the exported file and run the migration again using only the failed records
4. **Progress Visibility** - Detailed summary shows success/failure counts, percentages, and specific error reasons for each failed record

The tool tracks which records succeeded and failed, providing row-level context to help you quickly identify and resolve issues. Simply export the failed records, fix the errors in the Excel file, and re-run the migration with the corrected file.

## Troubleshooting

### Authentication & AWS Configuration

**Authentication Errors:**
- Verify your Cognito User Pool ID and Client ID are correct
- Ensure your username and password are valid
- Check that your user is in the ADMINS group

**MFA Issues:**
- Enable MFA in your Cognito User Pool settings if required
- Ensure your user has MFA set up (SMS or software token)

**AWS Credentials:**
- Set up AWS credentials in `~/.aws/credentials`
- Or set environment variables: `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_DEFAULT_REGION`
- Or use `aws configure` to set up your default profile

**Permission Errors:**
- Add your user to the ADMINS group in Cognito User Pool
- Contact your AWS administrator if you don't have permission

### Excel Format & Validation Issues

For errors related to Excel file format, data types, sheet naming, required fields, or foreign keys, see the comprehensive troubleshooting guide:

📋 **[Common Issues and Solutions](docs/EXCEL_FORMAT_SPECIFICATION.md#common-issues-and-solutions)**

## License

MIT