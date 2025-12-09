"""Handles batch uploading of records to Amplify."""

import logging
from typing import Dict, List, Tuple, Any

logger = logging.getLogger(__name__)


class BatchUploader:
    def __init__(self, amplify_client):
        self.amplify_client = amplify_client

    def upload_records(
        self, records: List[Dict], sheet_name: str, parsed_model_structure: Dict[str, Any]
    ) -> Tuple[int, int, List[Dict]]:
        if not records:
            return 0, 0, []

        success_count, upload_error_count, failed_uploads = self.amplify_client.upload(
            records, sheet_name, parsed_model_structure
        )

        return success_count, upload_error_count, failed_uploads
