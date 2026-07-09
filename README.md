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

The tool has five subcommands:

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
- Whether to fill missing required fields with defaults (`fill_unknown`)
- If `fill_unknown` is enabled: FK fallback IDs — enter model name → ID pairs, press Enter on an empty model name to finish

Configuration is saved to `~/.amplify-migrator/config.json`

### 2. Show Configuration

View your current saved configuration:

```bash
amplify-migrator show
```

### 3. Export Schema

Export your GraphQL schema to an Excel reference workbook:

```bash
# Export all models (produces schema-reference.xlsx)
amplify-migrator export-schema

# Export to a specific file
amplify-migrator export-schema --output my-schema.xlsx

# Export as Markdown instead
amplify-migrator export-schema --output my-schema.md

# Export specific models only
amplify-migrator export-schema --models User Post Comment
```

This generates an Excel workbook with:
- One sheet per model, listing all fields with types and requirements
- An **Enums** sheet with all allowed enum values
- A **Custom Types** sheet with nested type definitions
- Foreign key column names and instructions

Open directly in Excel or Google Sheets — no special software needed.

💡 The exported schema reference can help you prepare your Excel file. For detailed formatting guidelines, see the [Excel Format Specification](docs/EXCEL_FORMAT_SPECIFICATION.md).

### 4. Export Data

Export model records from your Amplify backend to an Excel file:

```bash
# Export a single model's records
amplify-migrator export-data --model Reporter

# Export multiple models (each as a separate sheet)
amplify-migrator export-data --model Reporter Article Comment

# Export all models
amplify-migrator export-data --all

# Export to a specific file
amplify-migrator export-data --model Reporter --output reporter_backup.xlsx
amplify-migrator export-data --all --output full_backup.xlsx
```

Records are sorted by primary field and exported with scalar, enum, and ID fields. When exporting multiple models, each model gets its own sheet in the Excel file. This is useful for backing up data, auditing records, or preparing corrections for re-migration.

### 5. Run Migration

Run the migration using your saved configuration:

```bash
amplify-migrator migrate
```

You'll only be prompted for your password (for security, passwords are never cached).

### Programmatic API (advanced)

The migration core is also usable as a library. `MigrationOrchestrator.build_plan()` returns an
inspectable `MigrationPlan` (per-sheet model match, record counts, and rows that failed to parse)
without uploading anything; `execute(plan, selected_sheets=...)` uploads the chosen sheets and
returns a `MigrationResult` with a merged per-sheet `failures` list. This is the seam that lets
non-interactive callers (such as an automated agent) drive a migration. The `amplify-migrator
migrate` CLI is a thin interactive wrapper over this API and behaves exactly as before.

The agent can additionally propose header renames via `propose_column_renames` to reconcile mismatched
column headers with schema field names before migrating; like value edits, every rename passes through
the same human-approval gate and only approved renames are applied. The agent signals completion with an
explicit `finish` tool call rather than by ending a message, so a turn that only narrates its plan never
terminates the session prematurely.

For value problems that repeat across many rows — the same `#REF!`, an enum/casing mismatch, or blank
required cells — the agent proposes bulk fixes at the `(column, value)` level via `propose_value_mappings`
("in column C, map value X to Y") instead of editing thousands of cells one at a time. The grouped
`dry_run` report hands it the exact column and value of each failure group, the human approves each
mapping once, and every matching row is rewritten; mapping from a null `from_value` fills blank cells or
creates and fills a missing required scalar field. Like every other edit, it passes through the
human-approval gate and only approved mappings are applied. For foreign-key values that match no
existing entity, the `dry_run` report also lists the closest existing entities (`closest_existing`, each
with its name and id), so the agent can map a misspelled or variant name to the right record instead of
guessing.

When a required value cannot be determined from the data and has no sensible default — for example a
required foreign key with no column and no plausible candidate — the agent calls `ask_user` to ask the
human a specific free-form question and uses the answer in a follow-up fix. Unlike edits and uploads,
`ask_user` is not gated: it is an ordinary blocking round-trip that returns the human's answer to the
model, and the agent is instructed to use it only as a last resort.

Because a value fix is only as good as the failures it targets, `propose_changes` and
`propose_value_mappings` are blocked until a `dry_run` has run since the last workbook change: the first
value fix with no prior `dry_run` is refused, and any applied edit (including a column rename) invalidates
an earlier `dry_run`, so the agent must re-run it before the next batch. Header renames themselves stay
ungated, since they normally precede the first `dry_run`.

When a proposed value edit is structurally invalid (unknown sheet or column, a missing or
out-of-range `row`), `propose_changes` returns an instructive error naming the exact problem instead
of a terse failure, so the model can self-correct. A malformed `propose_value_mappings` call is just as
legible: a call missing its `summary` or `mappings` array is refused with the expected shape, and a
single mapping missing a required key (for example `to_value`) becomes a per-item `invalid` entry keyed
by its list index while its valid siblings are still applied.

Two loop guards keep a stuck agent from burning every turn. If the model keeps issuing the *same*
failing tool call, the loop escalates once with a corrective message and then aborts. Separately, if a
run of proposals each applies *no* changes — even when their arguments vary every time — the loop
nudges the agent to re-run `dry_run` and, if it still makes no progress, aborts. Any productive step
(an applied edit, or a `dry_run` between attempts) resets the counter.

### Deterministic preparation pipeline (experimental)

Alongside the conversational agent, `PreparationPipeline` runs the migration as a fixed
sequence and calls the LLM only for the decisions no rule can make: mapping messy headers to
schema fields, and resolving foreign-key values that match no existing record. Every proposal
is human-approved; termination is bounded (no agentic loop). Unresolved items — new entities
to create in Amplify, ambiguous FKs, and unmapped headers — are reported for a follow-up.
Measure it with `scripts/eval_pipeline.py` (same flags as `scripts/eval_agent_trajectory.py`).

### Quick Start

```bash
# First time: configure the tool
amplify-migrator config

# View current configuration
amplify-migrator show

# Export schema documentation (share with team)
amplify-migrator export-schema

# Export existing records to Excel
amplify-migrator export-data --model Reporter
amplify-migrator export-data --all

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
- **Schema export** - Generate an Excel workbook documenting your GraphQL schema, viewable without special software
- **Data export** - Export existing model records to Excel for backup, auditing, or correction

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

### Handling Records with Missing Data

Sometimes records are genuinely incomplete — for example, some observations have no known reporter or photographer. Two config options let you migrate these records instead of failing them.

#### Fill unknown (for missing required non-FK fields)

If non-FK required fields are blank, enable `fill_unknown` via `amplify-migrator config` (answer `yes` when prompted) to substitute a type-appropriate placeholder instead of failing the record:

| Field type | Placeholder |
|------------|-------------|
| `String`, `AWSEmail`, `AWSURL`, enum, … | `"UNKNOWN"` |
| `Int`, `AWSTimestamp` | `0` |
| `Float` | `0.0` |
| `Boolean` | `false` |
| `AWSDate` | `"1970-01-01"` |
| `AWSDateTime` | `"1970-01-01T00:00:00.000Z"` |

#### Default FK values (for missing foreign keys)

If a required FK field (e.g. `reporter`, `photographer`) is blank, configure a fallback ID so the record is linked to a placeholder instead of failing. Steps:

1. Create a placeholder record in Amplify for each model (e.g. a Reporter named "Unknown") — you can use the local helper script `scripts/create_placeholders.py` to do this.
2. Run `amplify-migrator config`, answer `yes` to `fill_unknown`, then enter each model name and its placeholder ID when prompted.

Run `amplify-migrator show` to confirm everything was picked up.

Both options are off by default and designed for re-migration runs against the exported failed-records file, not for the initial clean migration.

### Composite duplicate detection

By default a record is considered an existing duplicate if another record shares the model's
primary/secondary-index field. When the same field value can legitimately repeat across groups
(e.g. `sequentialId` reused per country), add discriminator fields so a record only counts as a
duplicate when **all** of them also match.

Configure it interactively with `amplify-migrator config` (answer `yes` to "Configure composite
duplicate-detection keys", then enter the model name and comma-separated fields), or edit
`~/.amplify-migrator/config.json` directly:

```json
{
  "composite_unique_fields": {
    "Observation": ["country"]
  }
}
```

Field names may be given as the relation name (`country`) or the FK column (`countryId`); both
resolve to the stored `countryId`. Run `amplify-migrator show` to confirm. Omit the key (default)
for unchanged single-field behaviour.

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