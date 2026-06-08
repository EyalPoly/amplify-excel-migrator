---
name: preparing-excel-for-amplify-migration
description: Use when preparing, cleaning, or fixing an Excel/spreadsheet file to be ingested by the amplify-excel-migrator tool (amplify-migrator migrate) into an AWS Amplify GraphQL backend — covers sheet naming, column headers, foreign keys, types, required/missing fields, and pre-flight checks.
---

# Preparing Excel for Amplify Migration

## Overview

The `amplify-excel-migrator` tool (`amplify-migrator migrate`) reads an Excel workbook and uploads each row as a record to an AWS Amplify Gen 2 GraphQL API. "Ready to migrate" means the workbook's sheets, headers, and cell values map cleanly onto the live schema. This skill encodes the tool's actual ingestion rules — several of which are counter-intuitive.

**Core principle: never guess the schema.** Start by exporting it.

## Step 0 — Get the authoritative schema (do this first)

```bash
amplify-migrator export-schema            # → schema-reference.xlsx (one sheet per model + Enums + Custom Types)
amplify-migrator export-data --model X    # → a real example row in the exact expected format
```

The reference lists every model, field name, type, required (`!`) flag, enum values, custom-type fields, and FK column names. Match against it — do not infer field names from memory.

## The rules that bite (verified against the tool's parser)

**Sheet name = model name.** Exact, case-sensitive, singular PascalCase (`Observation`, not `Observations`/`observation`). A non-matching sheet is silently **skipped**, not errored.

**Headers auto-convert** snake_case / kebab-case / "space separated" / camelCase → camelCase. So pick a header that converts to the *real field name*. Trap: `Species Name` → `speciesName`, which is **not** the field `species`. When unsure, name the header exactly as the schema field.

**Foreign keys — this is the most common mistake:**
- Column name is the relationship name **without** the `Id` suffix: `reporter`, not `reporterId` (both are accepted, but no-`Id` is preferred and is what `export-schema` emits).
- The cell value is the related record's **primary/identifying field value** (e.g. `reporter_1`), **NOT** the Amplify UUID. The tool resolves it via a lookup cache.
- The referenced record **must already exist in the backend** (the tool pre-fetches FK lookups from Amplify, not from sibling sheets). Migrate/seed parent models first, or place parent sheets before child sheets in the workbook.
- Missing/unknown FK value → row fails, unless `default_fk_values` is configured (see below).

**Remove auto-generated columns:** `id`, `createdAt`, `updatedAt`, `owner`. Including them causes errors or noise.

**Types** (full table: `docs/EXCEL_FORMAT_SPECIFICATION.md`):
- Booleans accept `true/false`, `1/0`, `yes/no`, `y/n`, `v/x` (case-insensitive). No need to normalize to lowercase `true`.
- Dates accept ISO `2023-06-15`, `15/06/2023` (DD/MM/YYYY), or `15-06-2023` (DD-MM-YYYY).
- Lists accept JSON `["a","b"]`, semicolon, comma, or space separated. **Pipe `|` does NOT work.** Empty elements are dropped.
- Enums auto-uppercase with underscores (`in progress` → `IN_PROGRESS`). Value must exist in the schema's enum.
- Custom types: one column per sub-field via dot notation (`address.city`); for a *list* of custom types use ` - ` dash-separated values per column.

**Number gotcha:** a dash in a numeric cell is parsed as arithmetic — `2-2` becomes `4`. Avoid hyphens/ranges in Int/Float fields.

## Required & missing data

Fields marked `!` in the schema must have a value in every row, else the row fails. For genuinely incomplete data, configure (via `amplify-migrator config`) instead of dropping rows:
- `fill_unknown: true` — substitutes typed placeholders for missing required non-FK fields (`String`→`"UNKNOWN"`, `Int`→`0`, `Boolean`→`false`, `AWSDate`→`"1970-01-01"`, …).
- `default_fk_values` — fallback Amplify record ID per model for missing required FKs (create an "Unknown" placeholder record first).

Leave *optional* missing fields as **empty cells** — never `"N/A"`, `"-"`, or `"null"` (those fail type validation).

**Duplicate detection:** the tool skips a row whose primary/index field already exists. If that value legitimately repeats across groups (e.g. `sequentialId` per country), set `composite_unique_fields` (e.g. `{"Observation": ["country"]}`) so it only counts as a duplicate when the discriminator also matches.

## Pre-flight checklist

- [ ] Ran `export-schema`; have the model/field/type reference open
- [ ] Each sheet renamed to exact, singular, case-correct model name
- [ ] `id`, `createdAt`, `updatedAt`, `owner` columns removed
- [ ] Every header converts to a real schema field (watch `Species Name`→`speciesName`)
- [ ] FK columns named without `Id`; values are the parent's identifying value, not UUIDs
- [ ] FK parent records exist in backend (or parent sheets ordered first)
- [ ] Required (`!`) fields non-blank, or `fill_unknown`/`default_fk_values` configured
- [ ] Dates, booleans, lists, enums in an accepted format; no `|` in lists, no dashes in numbers
- [ ] Migrate a small subset first to confirm mapping before the full file

After migrating, `amplify-migrator export-data` plus the failed-records workbook let you fix and re-upload rejected rows.