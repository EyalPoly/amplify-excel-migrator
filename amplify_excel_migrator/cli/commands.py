"""CLI command handlers for Amplify Excel Migrator."""

import argparse
import sys

import pandas as pd

from amplify_excel_migrator.client import AmplifyClient
from amplify_excel_migrator.core import ConfigManager
from amplify_excel_migrator.schema import FieldParser, SchemaExporter
from amplify_excel_migrator.data import ExcelReader, DataTransformer
from amplify_excel_migrator.migration import (
    FailureTracker,
    ProgressReporter,
    BatchUploader,
    MigrationOrchestrator,
)
from amplify_auth import CognitoAuthProvider


def cmd_show(args=None):
    print("""
    ╔════════════════════════════════════════════════════╗
    ║        Amplify Migrator - Current Configuration    ║
    ╚════════════════════════════════════════════════════╝
    """)

    config_manager = ConfigManager()
    cached_config = config_manager.load()

    if not cached_config:
        print("\n❌ No configuration found!")
        print("💡 Run 'amplify-migrator config' first to set up your configuration.")
        return

    print("\n📋 Cached Configuration:")
    print("-" * 54)
    print(f"Excel file path:      {cached_config.get('excel_path', 'N/A')}")
    print(f"API endpoint:         {cached_config.get('api_endpoint', 'N/A')}")
    print(f"AWS Region:           {cached_config.get('region', 'N/A')}")
    print(f"User Pool ID:         {cached_config.get('user_pool_id', 'N/A')}")
    print(f"Client ID:            {cached_config.get('client_id', 'N/A')}")
    print(f"Admin Username:       {cached_config.get('username', 'N/A')}")
    print("-" * 54)
    print(f"\n📍 Config location: {config_manager.config_path}")
    print(f"💡 Run 'amplify-migrator config' to update configuration.")


def cmd_config(args=None):
    print("""
    ╔════════════════════════════════════════════════════╗
    ║        Amplify Migrator - Configuration Setup      ║
    ╚════════════════════════════════════════════════════╝
    """)

    config_manager = ConfigManager()
    cached_config = config_manager.load()

    config = {
        "excel_path": config_manager.prompt_for_value("Excel file path", cached_config.get("excel_path", "")),
        "api_endpoint": config_manager.prompt_for_value(
            "AWS Amplify API endpoint", cached_config.get("api_endpoint", "")
        ),
        "region": config_manager.prompt_for_value("AWS Region", cached_config.get("region", "")),
        "user_pool_id": config_manager.prompt_for_value("Cognito User Pool ID", cached_config.get("user_pool_id", "")),
        "client_id": config_manager.prompt_for_value("Cognito Client ID", cached_config.get("client_id", "")),
        "username": config_manager.prompt_for_value("Admin Username", cached_config.get("username", "")),
    }

    config_manager.save(config)
    print("\n✅ Configuration saved successfully!")
    print(f"💡 You can now run 'amplify-migrator migrate' to start the migration.")


def cmd_migrate(args=None):
    print("""
    ╔════════════════════════════════════════════════════╗
    ║             Migrator Tool for Amplify              ║
    ╠════════════════════════════════════════════════════╣
    ║   This tool requires admin privileges to execute   ║
    ╚════════════════════════════════════════════════════╝
    """)

    config_manager = ConfigManager()
    cached_config = config_manager.load()

    if not cached_config:
        print("\n❌ No configuration found!")
        print("💡 Run 'amplify-migrator config' first to set up your configuration.")
        sys.exit(1)

    excel_path = config_manager.get_or_prompt("excel_path", "Excel file path", "data.xlsx")
    api_endpoint = config_manager.get_or_prompt("api_endpoint", "AWS Amplify API endpoint")
    region = config_manager.get_or_prompt("region", "AWS Region", "us-east-1")
    user_pool_id = config_manager.get_or_prompt("user_pool_id", "Cognito User Pool ID")
    client_id = config_manager.get_or_prompt("client_id", "Cognito Client ID")
    username = config_manager.get_or_prompt("username", "Admin Username")

    print("\n🔐 Authentication:")
    print("-" * 54)
    password = config_manager.prompt_for_value("Admin Password", secret=True)

    from amplify_auth import CognitoAuthProvider

    auth_provider = CognitoAuthProvider(
        user_pool_id=user_pool_id,
        client_id=client_id,
        region=region,
    )

    amplify_client = AmplifyClient(
        api_endpoint=api_endpoint,
        auth_provider=auth_provider,
    )

    if not auth_provider.authenticate(username, password):
        return

    field_parser = FieldParser()

    orchestrator = MigrationOrchestrator(
        excel_reader=ExcelReader(excel_path),
        data_transformer=DataTransformer(field_parser),
        amplify_client=amplify_client,
        failure_tracker=FailureTracker(),
        progress_reporter=ProgressReporter(),
        batch_uploader=BatchUploader(amplify_client),
        field_parser=field_parser,
    )

    orchestrator.run()


def cmd_export_schema(args=None):
    print("""
    ╔════════════════════════════════════════════════════╗
    ║         Amplify Migrator - Schema Export           ║
    ╚════════════════════════════════════════════════════╝
    """)

    config_manager = ConfigManager()
    cached_config = config_manager.load()

    if not cached_config:
        print("\n❌ No configuration found!")
        print("💡 Run 'amplify-migrator config' first to set up your configuration.")
        sys.exit(1)

    api_endpoint = config_manager.get_or_prompt("api_endpoint", "AWS Amplify API endpoint")
    region = config_manager.get_or_prompt("region", "AWS Region", "us-east-1")
    user_pool_id = config_manager.get_or_prompt("user_pool_id", "Cognito User Pool ID")
    client_id = config_manager.get_or_prompt("client_id", "Cognito Client ID")
    username = config_manager.get_or_prompt("username", "Admin Username")

    output_path = args.output if args else "schema-reference.md"

    print("\n🔐 Authentication:")
    print("-" * 54)
    password = config_manager.prompt_for_value("Admin Password", secret=True)

    auth_provider = CognitoAuthProvider(
        user_pool_id=user_pool_id,
        client_id=client_id,
        region=region,
    )

    amplify_client = AmplifyClient(
        api_endpoint=api_endpoint,
        auth_provider=auth_provider,
    )

    if not auth_provider.authenticate(username, password):
        return

    print("\n📋 Exporting schema...")
    print("-" * 54)

    field_parser = FieldParser()
    schema_exporter = SchemaExporter(amplify_client, field_parser)

    try:
        schema_exporter.export_to_markdown(output_path, models=args.models if args and args.models else None)
        print(f"\n✅ Schema exported successfully to: {output_path}")
        print("💡 Share this file with your team to help them prepare Excel files.")
    except Exception as e:
        print(f"\n❌ Failed to export schema: {e}")
        sys.exit(1)


def cmd_export_data(args=None):
    print("""
    ╔════════════════════════════════════════════════════╗
    ║         Amplify Migrator - Export Data             ║
    ╚════════════════════════════════════════════════════╝
    """)

    config_manager = ConfigManager()
    cached_config = config_manager.load()

    if not cached_config:
        print("\n❌ No configuration found!")
        print("💡 Run 'amplify-migrator config' first to set up your configuration.")
        sys.exit(1)

    api_endpoint = config_manager.get_or_prompt("api_endpoint", "AWS Amplify API endpoint")
    region = config_manager.get_or_prompt("region", "AWS Region", "us-east-1")
    user_pool_id = config_manager.get_or_prompt("user_pool_id", "Cognito User Pool ID")
    client_id = config_manager.get_or_prompt("client_id", "Cognito Client ID")
    username = config_manager.get_or_prompt("username", "Admin Username")

    print("\n🔐 Authentication:")
    print("-" * 54)
    password = config_manager.prompt_for_value("Admin Password", secret=True)

    auth_provider = CognitoAuthProvider(
        user_pool_id=user_pool_id,
        client_id=client_id,
        region=region,
    )

    amplify_client = AmplifyClient(
        api_endpoint=api_endpoint,
        auth_provider=auth_provider,
    )

    if not auth_provider.authenticate(username, password):
        return

    field_parser = FieldParser()

    if getattr(args, "all", False):
        schema_exporter = SchemaExporter(amplify_client, field_parser)
        model_names = schema_exporter.discover_models()
        if not model_names:
            print("\n⚠️  No models discovered.")
            return
    else:
        model_names = args.model

    is_multi = len(model_names) > 1
    if args.output:
        output_path = args.output
    elif is_multi:
        output_path = "all_models_records.xlsx"
    else:
        output_path = f"{model_names[0]}_records.xlsx"

    print(f"\n📋 Exporting {len(model_names)} model(s)...")
    print("-" * 54)

    dataframes: dict[str, pd.DataFrame] = {}

    for model_name in model_names:
        try:
            records, primary_field = amplify_client.get_model_records(model_name, field_parser)
        except Exception as e:
            print(f"\n❌ Failed to fetch records for '{model_name}': {e}")
            continue

        if not records:
            print(f"  ⚠️  No records found for model '{model_name}', skipping.")
            continue

        df = pd.DataFrame(records)

        cols = list(df.columns)
        if primary_field in cols:
            cols.remove(primary_field)
            cols = [primary_field] + cols
        df = df[cols]

        if primary_field in df.columns:
            sort_key = df[primary_field].apply(lambda x: str(x).lower())
            df = df.iloc[sort_key.argsort()]

        dataframes[model_name] = df
        print(f"  ✅ {model_name}: {len(records)} records")

    if not dataframes:
        print("\n⚠️  No records found for any model.")
        return

    with pd.ExcelWriter(output_path, engine="openpyxl") as writer:
        for model_name, df in dataframes.items():
            df.to_excel(writer, index=False, sheet_name=model_name)

    print(f"\n✅ Exported to: {output_path}")
    if is_multi:
        total = sum(len(df) for df in dataframes.values())
        print(f"💡 {len(dataframes)} model(s), {total} total records")


def main():
    parser = argparse.ArgumentParser(
        description="Amplify Excel Migrator - Migrate Excel data to AWS Amplify GraphQL API",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    config_parser = subparsers.add_parser("config", help="Configure the migration tool")
    config_parser.set_defaults(func=cmd_config)

    show_parser = subparsers.add_parser("show", help="Show current configuration")
    show_parser.set_defaults(func=cmd_show)

    migrate_parser = subparsers.add_parser("migrate", help="Run the migration")
    migrate_parser.set_defaults(func=cmd_migrate)

    export_parser = subparsers.add_parser("export-schema", help="Export GraphQL schema to markdown reference")
    export_parser.add_argument(
        "--output",
        "-o",
        default="schema-reference.md",
        help="Output file path (default: schema-reference.md)",
    )
    export_parser.add_argument(
        "--models",
        "-m",
        nargs="*",
        help="Specific models to export (default: all models)",
    )
    export_parser.set_defaults(func=cmd_export_schema)

    export_data_parser = subparsers.add_parser("export-data", help="Export model records to Excel")
    export_data_model_group = export_data_parser.add_mutually_exclusive_group(required=True)
    export_data_model_group.add_argument(
        "--model",
        "-m",
        nargs="+",
        help="Model name(s) to export (e.g., Reporter User)",
    )
    export_data_model_group.add_argument(
        "--all",
        "-a",
        action="store_true",
        help="Export all models",
    )
    export_data_parser.add_argument(
        "--output",
        "-o",
        default=None,
        help="Output file path (default: {model}_records.xlsx or all_models_records.xlsx)",
    )
    export_data_parser.set_defaults(func=cmd_export_data)

    args = parser.parse_args()

    if args.command is None:
        parser.print_help()
        sys.exit(1)

    args.func(args)


if __name__ == "__main__":
    main()
