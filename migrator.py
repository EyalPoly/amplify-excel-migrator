import logging
import os
import re
import sys
from getpass import getpass
from typing import Dict, Any

import pandas as pd
from dotenv import load_dotenv

from amplify_client import AmplifyClient
from mapper import observation_column_mapping
from model_field_parser import ModelFieldParser

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


class ExcelToAmplifyMigrator:
    def __init__(self, excel_file_path: str):
        self.model_field_parser = ModelFieldParser()
        self.excel_file_path = excel_file_path
        self.amplify_client = None
        self.column_mapping = observation_column_mapping

    def init_client(self, api_endpoint: str, region: str, user_pool_id: str, is_aws_admin: bool = False,
                    client_id: str = None, username: str = None, aws_profile: str = None):

        self.amplify_client = AmplifyClient(
            api_endpoint=api_endpoint,
            user_pool_id=user_pool_id,
            region=region,
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

        value = row.get(field_name)

        if field['is_id']:
            related_model = (temp := field['name'][:-2])[0].upper() + temp[1:]
            records = self.amplify_client.get_records(related_model, parsed_model_structure=parsed_model_structure,
                                                      fields=['id'])
            if records:
                value = next((record['id'] for record in records if record.get('name') == value), None)
                if value is None and field['is_required']:
                    raise ValueError(f"{related_model}: {value} does not exist")
            else:
                raise ValueError(f"Error fetching related record {related_model}: {value}")

        return value

    @staticmethod
    def to_camel_case(s: str) -> str:
        parts = re.split(r'[\s_\-]+', s.strip())
        return parts[0].lower() + ''.join(word.capitalize() for word in parts[1:])


def main():
    print("""
    ╔════════════════════════════════════════════════════╗
    ║             Migrator Tool for Amplify              ║
    ╠════════════════════════════════════════════════════╣
    ║   This tool requires admin privileges to execute   ║
    ╚════════════════════════════════════════════════════╝
    """)

    load_dotenv()

    excel_path = os.getenv('EXCEL_FILE_PATH', 'data.xlsx')
    api_endpoint = os.getenv('API_ENDPOINT', '')
    region = os.getenv('AWS_REGION', 'eu-north-1')
    user_pool_id = os.getenv('USER_POOL_ID', '')
    client_id = os.getenv('CLIENT_ID', None)

    migrator = ExcelToAmplifyMigrator(excel_path)

    username = os.getenv('ADMIN_USERNAME', input("Admin Username: "))
    password = os.getenv('ADMIN_PASSWORD', getpass("Admin Password: "))
    migrator.init_client(api_endpoint, region, user_pool_id, client_id=client_id, username=username)

    if not migrator.authenticate(username, password):
        return

    migrator.run()


if __name__ == "__main__":
    main()
