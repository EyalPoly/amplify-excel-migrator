import logging
import os
import re
import sys
from getpass import getpass
from typing import Dict, Any

import pandas as pd
from dotenv import load_dotenv

from amplify_client import AmplifyClient
from model_field_parser import ModelFieldParser

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


class ExcelToAmplifyMigrator:
    def __init__(self, excel_file_path: str):
        self.model_field_parser = ModelFieldParser()
        self.excel_file_path = excel_file_path
        self.amplify_client = None

    def init_client(self, api_endpoint: str, region: str, user_pool_id: str, is_aws_admin: bool = False,
                    client_id: str = None, username: str = None, aws_profile: str = None, batch_size: int = 10):

        self.amplify_client = AmplifyClient(
            api_endpoint=api_endpoint,
            user_pool_id=user_pool_id,
            region=region,
            batch_size=batch_size,
            client_id=client_id,
        )

        try:
            self.amplify_client.init_cognito_client(is_aws_admin=is_aws_admin, username=username,
                                                    aws_profile=aws_profile)

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

        for field in parsed_model_structure['fields']:
            input = self.parse_input(row, field, parsed_model_structure)
            if input:
                model_record[field['name']] = input

        return model_record

    def parse_input(self, row: pd.Series, field: Dict[str, Any], parsed_model_structure: Dict[str, Any]) -> Any:
        field_name = field['name'][:-2] if field['is_id'] else field['name']
        if field_name not in row.index or pd.isna(row[field_name]):
            if field['is_required']:
                raise ValueError(f"Required field '{field_name}' is missing in row {row.name}")
            else:
                return None

        value = row.get(field['name'])
        if field['is_id']:
            related_model = (temp := field['name'][:-2])[0].upper() + temp[1:]
            record = self.amplify_client.get_record(related_model, parsed_model_structure=parsed_model_structure,
                                                     value=value, fields=['id'])
            if record:
                if record['id'] is None and field['is_required']:
                    raise ValueError(f"{related_model}: {value} does not exist")
                else:
                    value = record['id']
            else:
                raise ValueError(f"Error fetching related record {related_model}: {value}")

        return value

    @staticmethod
    def to_camel_case(s: str) -> str:
        parts = re.split(r'[\s_\-]+', s.strip())
        return parts[0].lower() + ''.join(word.capitalize() for word in parts[1:])


def get_config_value(key: str, prompt: str, default: str = '', secret: bool = False) -> str:
    env_value = os.getenv(key)
    if env_value:
        return env_value

    if default:
        prompt = f"{prompt} [{default}]: "
    else:
        prompt = f"{prompt}: "

    if secret:
        value = getpass(prompt)
    else:
        value = input(prompt)

    return value.strip() if value.strip() else default


def main():
    print("""
    ╔════════════════════════════════════════════════════╗
    ║             Migrator Tool for Amplify              ║
    ╠════════════════════════════════════════════════════╣
    ║   This tool requires admin privileges to execute   ║
    ╚════════════════════════════════════════════════════╝
    """)

    # Load .env if exists (for development only)
    load_dotenv()

    # Get configuration (interactively or from .env)
    print("\n📋 Configuration Setup:")
    print("-" * 54)

    excel_path = get_config_value('EXCEL_FILE_PATH', 'Excel file path', 'data.xlsx')
    api_endpoint = get_config_value('API_ENDPOINT', 'AWS Amplify API endpoint')
    region = get_config_value('AWS_REGION', 'AWS Region', 'us-east-1')
    user_pool_id = get_config_value('USER_POOL_ID', 'Cognito User Pool ID')
    client_id = get_config_value('CLIENT_ID', 'Cognito Client ID (optional)', '')

    print("\n🔐 Authentication:")
    print("-" * 54)

    username = get_config_value('ADMIN_USERNAME', 'Admin Username')
    password = get_config_value('ADMIN_PASSWORD', 'Admin Password', secret=True)

    migrator = ExcelToAmplifyMigrator(excel_path)

    migrator.init_client(api_endpoint, region, user_pool_id, client_id=client_id or None,
                        username=username)
    if not migrator.authenticate(username, password):
        return

    migrator.run()


if __name__ == "__main__":
    main()
