# Excel Format Specification

**Amplify Excel Migrator - Input File Format Guide**

This document specifies the exact format requirements for Excel files used with the Amplify Excel Migrator tool. Use this guide to prepare your Excel files for successful migration to AWS Amplify GraphQL.

## Table of Contents

1. [Quick Start Guide](#quick-start-guide)
2. [Sheet Structure Requirements](#sheet-structure-requirements)
3. [Data Type Reference](#data-type-reference)
4. [Special Field Types](#special-field-types)
5. [Data Formatting Rules](#data-formatting-rules)
6. [Required vs Optional Fields](#required-vs-optional-fields)
7. [Validation and Error Handling](#validation-and-error-handling)
8. [Complete Examples](#complete-examples)
9. [Common Issues and Solutions](#common-issues-and-solutions)
10. [Technical Reference](#technical-reference)

---

## Quick Start Guide

### Exporting Existing Data

You can export existing records from your Amplify backend to see the expected format:

```bash
amplify-migrator export-data --model Reporter --output reporter_example.xlsx
```

The exported file serves as a reference for column names, data types, and field ordering.

### Basic Checklist

Before running your migration, ensure:

- [ ] Each sheet name **exactly matches** a model name in your GraphQL schema (case-sensitive)
- [ ] First row of each sheet contains column headers
- [ ] Column names match field names in your schema (or use formats that auto-convert like `first_name`)
- [ ] Required fields have values in every row (no blanks)
- [ ] Foreign key fields end with `Id` (e.g., `authorId`, `reporterId`)
- [ ] Foreign key values exist in the related model's data
- [ ] Data types match your schema (numbers for Int, valid dates for AWSDate, etc.)

## Sheet Structure Requirements

### Sheet Naming

**Rule:** Sheet names must exactly match your GraphQL model names.

| ✅ Correct    | ❌ Incorrect | Reason |
|---------------|-------------|---------|
| `Reporter`    | `reporters` | Case mismatch and plural |
| `Observation` | `observation` | Case mismatch |
| `User`        | `Users` | Wrong plurality |

**Key Points:**
- Sheet names are case-sensitive
- Use PascalCase (first letter capitalized)
- Match your schema exactly - if your model is `Reporter`, your sheet must be `Reporter`
- One sheet per model you want to upload

### Column Headers

**Rule:** First row must contain column headers that match field names in your schema.

The tool automatically converts common naming conventions:

| Excel Header | Converts To | Schema Field |
|-------------|-------------|--------------|
| `first_name` | `firstName` | ✅ Match |
| `first-name` | `firstName` | ✅ Match |
| `first name` | `firstName` | ✅ Match |
| `firstName` | `firstName` | ✅ Match |

**Key Points:**
- Use snake_case, kebab-case, space-separated, or camelCase - all work
- Column order doesn't matter
- You can omit optional fields entirely
- Extra columns not in your schema are ignored

---

## Data Type Reference

### Basic Scalar Types

| Type | Description | Example Values |
|------|-------------|----------------|
| `String` | Text values | `John Doe`, `Hello World` |
| `Int` | Whole numbers | `42`, `100`, `-5` |
| `Float` | Decimal numbers | `3.14`, `99.99`, `-0.5` |
| `Boolean` | True/False values | `true`, `false`, `1`, `0`, `yes`, `no` |

### AWS Scalar Types

| Type | Description | Example Values |
|------|-------------|----------------|
| `AWSDate` | Date values | `2023-06-15`, `15/06/2023` |
| `AWSTime` | Time values | `14:30:00`, `2:30 PM` |
| `AWSDateTime` | Date and time | `2023-06-15T14:30:00Z` |
| `AWSEmail` | Email address | `user@example.com` |
| `AWSJSON` | JSON string | `{"key": "value"}` |
| `AWSURL` | URL string | `https://example.com` |

**Note:** See [Data Formatting Rules](#data-formatting-rules) section below for detailed information on how each type is parsed and validated.
---

## Special Field Types

### Foreign Keys and Relationships

**Rule:** Foreign key columns must end with `Id`.

| Foreign Key Field | Related Model | What It Means |
|------------------|---------------|---------------|
| `authorId` | `Author` | References an Author record |
| `reporterId` | `Reporter` | References a Reporter record |
| `photographerId` | `Photographer` | References a Photographer record |

**Example:**

| localId | reporterId  | photographerId |
|---------|-------------|----------------|
| 6000    | reporter_1  | photo_100      |
| 6001    | reporter_2  |                |

**Requirements:**
- `reporter_1` and `reporter_2` must exist in Reporter model
- `photo_100` must exist in Photographer model
- Empty `photographerId` is OK if field is optional

**Validation:**
- **FK value doesn't exist:** Record is skipped and recorded as a failure
- **No pre-fetched data for FK:** All records with that FK are skipped

### Array/List Fields

Arrays support **multiple input formats** - choose whichever is easiest:

#### 1. JSON Array Format
```
["value1", "value2", "value3"]
```

#### 2. Semicolon-Separated
```
value1; value2; value3
```

#### 3. Comma-Separated
```
value1, value2, value3
```

#### 4. Space-Separated
```
value1 value2 value3
```

**Examples:**

```
Array field "tags":
  ["red", "blue", "green"] → ["red", "blue", "green"]
  red; blue; green → ["red", "blue", "green"]
  red, blue, green → ["red", "blue", "green"]
  red blue green → ["red", "blue", "green"]

Single value:
  red → ["red"]

Empty values are skipped:
  red, , blue → ["red", "blue"]
  red;; blue → ["red", "blue"]
```

**Key Points:**
- Whitespace is automatically trimmed from each element
- Empty elements are skipped
- Single values are treated as single-item arrays
- All formats produce the same result

### Enum Fields

Enum values are automatically converted to UPPERCASE with underscores (e.g., `active` → `ACTIVE`, `In Progress` → `IN_PROGRESS`). Invalid values in arrays are skipped; invalid single values cause errors.

### Custom Types

**Custom types** are composite objects defined in your GraphQL schema. They are not separate models, but embedded types within a model.

**How to specify custom type fields in Excel:**

For a custom type with multiple fields, each field becomes a separate column:

```graphql
# GraphQL Schema
type Address {
  street: String!
  city: String!
  zipCode: String
}

type User @model {
  name: String!
  address: Address
}
```

**Single custom type instance:**
```
Excel columns: address.street | address.city | address.zipCode
Example row:   123 Main St   | New York     | 10001
```

**Multiple instances (dash notation):**

When a field is a **list of custom types**, use dash-separated values to specify multiple instances:

```graphql
type User @model {
  name: String!
  addresses: [Address]
}
```

```
Excel columns: addresses.street           | addresses.city    | addresses.zipCode
Example row:   123 Main St - 456 Oak Ave  | New York - Boston | 10001 - 02101

Result:
addresses: [
  {street: "123 Main St", city: "New York", zipCode: "10001"},
  {street: "456 Oak Ave", city: "Boston", zipCode: "02101"}
]
```

**Key Points:**
- Each field of the custom type becomes its own Excel column
- Use dash notation (`value1 - value2`) to specify multiple instances
- All fields for the same instance index are grouped together
- Required fields within custom types must have values for each instance

---

## Data Formatting Rules

### Automatic Text Cleaning

All text values are automatically cleaned:

**Whitespace:**
- Leading/trailing whitespace is stripped
- Example: `  Hello  ` → `Hello`

**Unicode Control Characters (removed):**
- Zero-width spaces
- Soft hyphens
- Other format characters

**Unicode Characters (preserved):**
- Emoji: 😀, 👍
- Hebrew: שלום
- Chinese: 你好
- Arabic: مرحبا
- And all other valid Unicode

### Number Parsing

**Integer fields:**
```
Valid: 42, "42", 100
Invalid: "abc" (causes error)
```

**Float fields:**
```
Valid: 3.14, "3.14", 99.99
Invalid: "not a number" (causes error)
```

**In arrays:**
- Invalid numbers are skipped with warnings logged
- Valid numbers are preserved

### Boolean Conversion

Case-insensitive conversion:

| Input | Output |
|-------|--------|
| `true`, `TRUE`, `True` | `true` |
| `false`, `FALSE`, `False` | `false` |
| `1` | `true` |
| `0` | `false` |
| `yes`, `YES`, `y`, `Y` | `true` |
| `no`, `NO`, `n`, `N` | `false` |
| `v`, `V` | `true` (checkmark) |
| `x`, `X` | `false` |

### Date Parsing Priority
**Examples:**

```
These all parse to the same date:
  2023-06-15 (ISO format)
  15/06/2023 (DD/MM/YYYY)
  15-06-2023 (DD-MM-YYYY)
```

---

## Required vs Optional Fields

Fields marked with `!` in your GraphQL schema are **required** and must have values in every row. Optional fields can be left blank or omitted entirely.

```typescript
const schema = a.schema({
  Reporter: a.model({
    fullName: a.string().required(),  // Required - must have value
    email: a.string(),                 // Optional - can be empty
  })
});
```

---

## Validation and Error Handling

Records that fail validation are skipped and tracked. After migration, export failed records to fix and re-upload.

**Common validation errors:** Missing required fields, invalid foreign keys, wrong data types, invalid enum values. See [Common Issues](#common-issues-and-solutions) table for solutions.

---

## Complete Examples

### Example 1: Reporter Model (Simple)

**Amplify Gen 2 Schema:**
```typescript
const schema = a.schema({
  Reporter: a.model({
    fullName: a.string().required(),
    facebookAccountUrl: a.url(),
    anotherAccountUrl: a.url(),
  })
});
```

**Excel Sheet (Named "Reporter"):**

| full name     | Facebook account Url           | Another Account Url          |
|---------------|--------------------------------|------------------------------|
| John Smith    |                                |                              |
| Jane Doe      | https://facebook.com/janedoe   | https://linkedin.com/janedoe |
| Bob Johnson   | https://facebook.com/bob       |                              |
| Alice Brown   |                                | https://twitter.com/alice    |

**Notes:**
- `full name` auto-converts to `fullName`
- `Facebook account Url` auto-converts to `facebookAccountUrl`
- Empty cells are OK for optional fields
- `fullName` is required, so every row must have it

### Example 2: Observation Model (Complex)

**Amplify Gen 2 Schema (excerpt):**
```typescript
const schema = a.schema({
  Observation: a.model({
    localId: a.integer().required(),
    country: a.string().required(),
    date: a.date().required(),
    species: a.string().required(),
    count: a.integer(),
    reporter: a.belongsTo('Reporter'),  // Creates reporterId FK
    photographer: a.belongsTo('Photographer'),  // Creates photographerId FK
    stage: a.string(),
    sex: a.string(),
    condition: a.string(),
    pregnancy: a.boolean(),
    length: a.integer(),
    description: a.string(),
  })
});
```

**Excel Sheet (Named "Observation"):**

| Local Id | Country | Date       | Species          | Count | Reporter    | Photographer | Stage    | Sex    | Condition | Pregnancy | Length | Description        |
|----------|---------|------------|------------------|-------|-------------|--------------|----------|--------|-----------|-----------|--------|--------------------|
| 1001     | USA     | 15/06/2023 | Atlantic Salmon  | 1     | reporter_1  | photo_100    | Adult    | Female | Alive     | Y         | 150    | Swimming upstream  |
| 1002     | Canada  | 2023-06-15 | Rainbow Trout    | 5     | reporter_2  |              | Adult    | Male   | Alive     |           |        | Group in river     |
| 1003     | Mexico  | 15-06-2023 | Pacific Mackerel | 1     | reporter_1  | photo_101    | Juvenile | Male   | Dead      | N         | 45     | Caught in net      |

**Notes:**
- Multiple date formats work: `15/06/2023`, `2023-06-15`, `15-06-2023`
- `Reporter` column contains foreign key (reporter_1 must exist in Reporter model)
- Boolean `Pregnancy` accepts `Y` (true) and `N` (false)
- Empty values for optional fields are OK
- Mixed data types: numbers, text, dates, booleans, foreign keys

### Example 3: Array and Enum Fields

**Excel Sheet:**

| name | tags | status | scores |
|------|------|--------|---------|
| Item 1 | red; blue; green | active | 10, 20, 30 |
| Item 2 | ["yellow", "orange"] | pending | [5, 10, 15] |
| Item 3 | purple | completed | 100 |

**Results:**
```
Item 1:
  tags: ["red", "blue", "green"]
  status: "ACTIVE"
  scores: [10, 20, 30]

Item 2:
  tags: ["yellow", "orange"]
  status: "PENDING"
  scores: [5, 10, 15]

Item 3:
  tags: ["purple"]
  status: "COMPLETED"
  scores: [100]
```

---

## Common Issues and Solutions

| Error | Cause | Solution |
|-------|-------|----------|
| `No sheet named 'Reporter' found` | Sheet name doesn't match model (case-sensitive) | Rename sheet to exact model name |
| `Reporter.fullName is required but missing` | Empty required field | Add value to that field |
| `Reporter: rep_999 does not exist` | Foreign key ID not found | Create related record first, or use existing ID |
| `Cannot convert "abc" to Int` | Wrong data type | Use correct type (number for Int, etc.) |
| Date not parsing correctly | Ambiguous date format | Use ISO `2023-06-15`, DD/MM/YYYY `15/06/2023`, or DD-MM-YYYY `15-06-2023` |
| Boolean not recognized | Invalid boolean value | Use `true`/`false`, `1`/`0`, `yes`/`no`, `y`/`n`, `v`/`x` |
| Array only has one value | Wrong separator | Use semicolon, comma, JSON array, or space-separated |
| `Column 'full_name' not found` | Field doesn't exist in schema | Check schema, column auto-converts `snake_case` → `camelCase` |
| Including metadata fields | Auto-generated fields in Excel | Remove `id`, `createdAt`, `updatedAt`, `owner` columns |
| Enum not matching | Case mismatch | Tool auto-converts to UPPERCASE, check enum exists in schema |

---

## Technical Reference

### Edge Cases and Special Handling

**1. Dash Notation in Numbers:**
```
Input: "2-2" in an Int field
Behavior: Interpreted as 2+2 = 4
Reason: Historical parsing logic
```

**2. Array Empty Element Skipping:**
```
Input: "value1, , value3"
Output: ["value1", "value3"]
Reason: Empty strings are filtered out
```

**3. Single Value to Array:**
```
Schema field: tags: [String]  (array/list field)
Excel input: "red" (single value, no separators)
Output: ["red"] (wrapped in array)

How it works:
- No JSON brackets, semicolons, commas, or multiple words detected
- Single string is automatically wrapped: [input_str]
```

**4. Enum Array Tolerance:**
```
Input: ["VALID", "INVALID", "ANOTHER_VALID"]
Output: ["VALID", "ANOTHER_VALID"]
Behavior: Invalid items logged and skipped
```
