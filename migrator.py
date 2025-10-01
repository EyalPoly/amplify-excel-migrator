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
            self.amplify_client.init_cognito_client(is_aws_admin=is_aws_admin, username=username, aws_profile=aws_profile)

        except RuntimeError or Exception:
            sys.exit(1)

    def authenticate(self, username: str, password: str) -> bool:
        return self.amplify_client.authenticate(username, password)

    def run(self):
        all_sheets = self.read_excel()

        for sheet_name, df in all_sheets.items():
            logger.info(f"Processing sheet: {sheet_name} with {len(df)} rows")
            self.process_sheet(df, sheet_name)

    def read_excel(self) -> Dict [str, Any]:
        logger.info(f"Reading Excel file: {self.excel_file_path}")
        all_sheets = pd.read_excel(self.excel_file_path, sheet_name=None)

        logger.info(f"Loaded {len(all_sheets)} sheets from Excel")
        return all_sheets

    def process_sheet(self, df: pd.DataFrame, sheet_name: str, batch_size: int = 10):
        records = []
        df.columns = [self._to_camel_case(c) for c in df.columns]
        parsed_model_structure = self.get_parsed_model_structure(sheet_name)
        try:
            for idx, row in df.iterrows():
                record = self.transform_row(row, parsed_model_structure)
                records.append(record)
        except Exception as e:
            logger.error(f"Error transforming row {idx}: {e}")

        logger.info(f"Prepared {len(records)} records for upload")

        confirm = input(f"\nUpload {len(records)} records to Amplify? (yes/no): ")
        if confirm.lower() != 'yes':
            logger.info("Upload cancelled")
            return

        success_count = 0
        error_count = 0

        for i in range(0, len(records), batch_size):
            batch = records[i:i + batch_size]
            logger.info(f"Uploading batch {i // batch_size + 1} ({len(batch)} items)...")

            for obs in batch:
                if self.upload_observation(obs):
                    success_count += 1
                    logger.debug(f"✓ Uploaded: {obs['sequentialId']}")
                else:
                    error_count += 1
                    logger.debug(f"✗ Failed: {obs['sequentialId']}")

        logger.info("\n=== Upload Complete ===")
        logger.info(f"✅ Success: {success_count}")
        logger.info(f"❌ Failed: {error_count}")
        logger.info(f"📊 Total: {len(records)}")

    def get_parsed_model_structure(self, sheet_name: str) -> Dict[str, Any]:
        model_structure = self.amplify_client.get_model_structure(sheet_name)
        return self.model_field_parser.parse_model_structure(model_structure)

    def transform_row(self, row: pd.Series, parsed_model_structure: Dict[str, Any]) -> Dict[str, Any]:
        """Transform a DataFrame row to Amplify model format"""

        model_record = {}

        for field in parsed_model_structure['fields']:
            input = self._parse_input(row, field)
            model_record[field['name']] = input

        return model_record

    def _parse_input(self, row: pd.Series, field: Dict[str, Any]) -> Any:
        field_name = field['name']
        if field_name not in row.index or pd.isna(row[field_name]):
            if field['is_required']:
                raise ValueError(f"Required field '{field_name}' is missing in row {row.name}")
            else:
                return None

        value = row.get(field_name)

        if field['type'] == 'String':
            return str(value)
        elif field['type'] == 'Int':
            return int(value)
        elif field['type'] == 'Float':
            return float(value)
        elif field['type'] == 'Boolean':
            return bool(value)
        elif field['type'] == 'AWSDateTime':
            if isinstance(value, pd.Timestamp):
                return value.isoformat()
            else:
                return str(value)
        else:
            return value

    @staticmethod
    def _to_camel_case(s: str) -> str:
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

    # username = os.getenv('ADMIN_USERNAME', input("Admin Username: "))
    # password = os.getenv('ADMIN_PASSWORD', getpass("Admin Password: "))

    username = "10eyal10@gmail.com"
    password = "Eynavmil1!"

    migrator.init_client(api_endpoint, region, user_pool_id, client_id=client_id, username=username)

    if not migrator.authenticate(username, password):
        return

    migrator.run()


if __name__ == "__main__":
    main()
