import argparse
import json
import logging
import re
import sys
from getpass import getpass
from pathlib import Path
from typing import Dict, Any

import pandas as pd

from amplify_client import AmplifyClient
from model_field_parser import ModelFieldParser

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

CONFIG_DIR = Path.home() / ".amplify-migrator"
CONFIG_FILE = CONFIG_DIR / "config.json"


class ExcelToAmplifyMigrator:
    def __init__(self, excel_file_path: str):
        self.model_field_parser = ModelFieldParser()
        self.excel_file_path = excel_file_path
        self.amplify_client = None

    def init_client(
        self,
        api_endpoint: str,
        region: str,
        user_pool_id: str,
        is_aws_admin: bool = False,
        client_id: str = None,
        username: str = None,
        aws_profile: str = None,
    ):

        self.amplify_client = AmplifyClient(
            api_endpoint=api_endpoint,
            user_pool_id=user_pool_id,
            region=region,
            client_id=client_id,
        )

        try:
            self.amplify_client.init_cognito_client(
                is_aws_admin=is_aws_admin, username=username, aws_profile=aws_profile
            )

        except RuntimeError or Exception:
            sys.exit(1)

    def authenticate(self, username: str, password: str) -> bool:
        return self.amplify_client.authenticate(username, password)

    def run(self):
        all_sheets = self.read_excel()

        for sheet_name, df in all_sheets.items():
            logger.info(f"Processing {sheet_name} sheet with {len(df)} rows")
            self.process_sheet(df, sheet_name)

    def read_excel(self) -> Dict[str, Any]:
        logger.info(f"Reading Excel file: {self.excel_file_path}")
        all_sheets = pd.read_excel(self.excel_file_path, sheet_name=None)

        logger.info(f"Loaded {len(all_sheets)} sheets from Excel")
        return all_sheets

    def process_sheet(self, df: pd.DataFrame, sheet_name: str):
        parsed_model_structure = self.get_parsed_model_structure(sheet_name)
        records = self.transform_rows_to_records(df, parsed_model_structure)

        # confirm = input(f"\nUpload {len(records)} records of {sheet_name} to Amplify? (yes/no): ")
        # if confirm.lower() != 'yes':
        #     logger.info("Upload cancelled for {sheet_name} sheet")
        #     return

        success_count, error_count = self.amplify_client.upload(records, sheet_name, parsed_model_structure)

        logger.info(f"=== Upload of Excel sheet: {sheet_name} Complete ===")
        logger.info(f"✅ Success: {success_count}")
        logger.info(f"❌ Failed: {error_count}")
        logger.info(f"📊 Total: {len(records)}")

    def transform_rows_to_records(self, df: pd.DataFrame, parsed_model_structure: Dict[str, Any]) -> list[Any]:
        records = []
        df.columns = [self.to_camel_case(c) for c in df.columns]
        for idx, row in df.iterrows():
            try:
                record = self.transform_row_to_record(row, parsed_model_structure)
                if record:
                    records.append(record)
            except Exception as e:
                logger.error(f"Error transforming row {idx}: {e}")

        logger.info(f"Prepared {len(records)} records for upload")

        return records

    def get_parsed_model_structure(self, sheet_name: str) -> Dict[str, Any]:
        model_structure = self.amplify_client.get_model_structure(sheet_name)
        return self.model_field_parser.parse_model_structure(model_structure)

    def transform_row_to_record(self, row: pd.Series, parsed_model_structure: Dict[str, Any]) -> dict[Any, Any] | None:
        """Transform a DataFrame row to Amplify model format"""

        model_record = {}

        for field in parsed_model_structure["fields"]:
            input = self.parse_input(row, field, parsed_model_structure)
            if input:
                model_record[field["name"]] = input

        return model_record

    def parse_input(self, row: pd.Series, field: Dict[str, Any], parsed_model_structure: Dict[str, Any]) -> Any:
        field_name = field["name"][:-2] if field["is_id"] else field["name"]

        if field_name not in row.index or pd.isna(row[field_name]):
            if field["is_required"]:
                raise ValueError(f"Required field '{field_name}' is missing in row {row.name}")
            else:
                return None

        if field.get("is_custom_type") and field.get("is_list"):
            return self._parse_custom_type_array(row, field)

        value = row.get(field_name)
        if field["is_id"]:
            if "related_model" in field:
                related_model = field["related_model"]
            else:
                related_model = (temp := field["name"][:-2])[0].upper() + temp[1:]

            record = self.amplify_client.get_record(
                related_model, parsed_model_structure=parsed_model_structure, value=value
            )
            if record:
                if record["id"] is None and field["is_required"]:
                    raise ValueError(f"{related_model}: {value} does not exist")
                else:
                    return record["id"]
            else:
                logger.error(f"Error fetching related record {related_model}: {value}")
                return None
        else:
            return self.model_field_parser.parse_field_input(field, field_name, value)

    def _parse_custom_type_array(self, row: pd.Series, field: Dict[str, Any]) -> Any:
        field_name = field["name"]

        if field_name in row.index and pd.notna(row[field_name]):
            value = row[field_name]
            if isinstance(value, str) and value.strip().startswith(("[", "{")):
                try:
                    return json.loads(value)
                except json.JSONDecodeError:
                    logger.warning(f"Failed to parse JSON for '{field_name}', trying column-based parsing")

        custom_type_name = field["type"]
        parsed_custom_type = self.get_parsed_model_structure(custom_type_name)
        custom_type_fields = parsed_custom_type["fields"]

        return self.model_field_parser.build_custom_type_from_columns(row, custom_type_fields, custom_type_name)

    @staticmethod
    def to_camel_case(s: str) -> str:
        # Handle PascalCase
        s_with_spaces = re.sub(r"(?<!^)(?=[A-Z])", " ", s)

        parts = re.split(r"[\s_\-]+", s_with_spaces.strip())
        return parts[0].lower() + "".join(word.capitalize() for word in parts[1:])


def get_config_value(prompt: str, default: str = "", secret: bool = False) -> str:
    if default:
        prompt = f"{prompt} [{default}]: "
    else:
        prompt = f"{prompt}: "

    if secret:
        value = getpass(prompt)
    else:
        value = input(prompt)

    return value.strip() if value.strip() else default


def save_config(config: Dict[str, str]) -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)

    cache_config = {k: v for k, v in config.items() if k not in ["password", "ADMIN_PASSWORD"]}

    with open(CONFIG_FILE, "w") as f:
        json.dump(cache_config, f, indent=2)

    logger.info(f"✅ Configuration saved to {CONFIG_FILE}")


def load_cached_config() -> Dict[str, str]:
    if not CONFIG_FILE.exists():
        return {}

    try:
        with open(CONFIG_FILE, "r") as f:
            return json.load(f)
    except Exception as e:
        logger.warning(f"Failed to load cached config: {e}")
        return {}


def get_cached_or_prompt(key: str, prompt: str, cached_config: Dict, default: str = "", secret: bool = False) -> str:
    if key in cached_config:
        return cached_config[key]

    return get_config_value(prompt, default, secret)


def cmd_show(args=None):
    print(
        """
    ╔════════════════════════════════════════════════════╗
    ║        Amplify Migrator - Current Configuration    ║
    ╚════════════════════════════════════════════════════╝
    """
    )

    cached_config = load_cached_config()

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
    print(f"\n📍 Config location: {CONFIG_FILE}")
    print(f"💡 Run 'amplify-migrator config' to update configuration.")


def cmd_config(args=None):
    print(
        """
    ╔════════════════════════════════════════════════════╗
    ║        Amplify Migrator - Configuration Setup      ║
    ╚════════════════════════════════════════════════════╝
    """
    )

    config = {
        "excel_path": get_config_value("Excel file path", "data.xlsx"),
        "api_endpoint": get_config_value("AWS Amplify API endpoint"),
        "region": get_config_value("AWS Region", "us-east-1"),
        "user_pool_id": get_config_value("Cognito User Pool ID"),
        "client_id": get_config_value("Cognito Client ID"),
        "username": get_config_value("Admin Username"),
    }

    save_config(config)
    print("\n✅ Configuration saved successfully!")
    print(f"💡 You can now run 'amplify-migrator migrate' to start the migration.")


def cmd_migrate(args=None):
    print(
        """
    ╔════════════════════════════════════════════════════╗
    ║             Migrator Tool for Amplify              ║
    ╠════════════════════════════════════════════════════╣
    ║   This tool requires admin privileges to execute   ║
    ╚════════════════════════════════════════════════════╝
    """
    )

    cached_config = load_cached_config()

    if not cached_config:
        print("\n❌ No configuration found!")
        print("💡 Run 'amplify-migrator config' first to set up your configuration.")
        sys.exit(1)

    excel_path = get_cached_or_prompt("excel_path", "Excel file path", cached_config, "data.xlsx")
    api_endpoint = get_cached_or_prompt("api_endpoint", "AWS Amplify API endpoint", cached_config)
    region = get_cached_or_prompt("region", "AWS Region", cached_config, "us-east-1")
    user_pool_id = get_cached_or_prompt("user_pool_id", "Cognito User Pool ID", cached_config)
    client_id = get_cached_or_prompt("client_id", "Cognito Client ID", cached_config)
    username = get_cached_or_prompt("username", "Admin Username", cached_config)

    print("\n🔐 Authentication:")
    print("-" * 54)
    password = get_config_value("Admin Password", secret=True)

    migrator = ExcelToAmplifyMigrator(excel_path)
    migrator.init_client(api_endpoint, region, user_pool_id, client_id=client_id, username=username)
    if not migrator.authenticate(username, password):
        return

    migrator.run()


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

    args = parser.parse_args()

    if args.command is None:
        parser.print_help()
        sys.exit(1)

    args.func(args)


if __name__ == "__main__":
    # For IDE debugging: set the command you want to test
    # Uncomment and modify one of these lines:

    # sys.argv = ['migrator.py', 'config']  # Test config command
    # sys.argv = ['migrator.py', 'show']    # Test show command
    sys.argv = ["migrator.py", "migrate"]  # Test migrate command

    main()
