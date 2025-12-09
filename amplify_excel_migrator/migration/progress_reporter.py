"""Handles progress and summary reporting during migration."""

from typing import Dict, List


class ProgressReporter:
    @staticmethod
    def print_sheet_result(
        sheet_name: str, success_count: int, total_rows: int, parsing_failures: int, upload_failures: int
    ) -> None:
        print(f"=== Upload of Excel sheet: {sheet_name} Complete ===")
        print(f"✅ Success: {success_count}")
        total_failures = parsing_failures + upload_failures
        print(f"❌ Failed: {total_failures} (Parsing: {parsing_failures}, Upload: {upload_failures})")
        print(f"📊 Total: {total_rows}")

    @staticmethod
    def print_migration_summary(
        sheets_processed: int, total_success: int, failures_by_sheet: Dict[str, List[Dict]]
    ) -> None:
        total_failed = sum(len(failures) for failures in failures_by_sheet.values())

        print("\n" + "=" * 60)
        print("MIGRATION SUMMARY")
        print("=" * 60)
        print(f"📊 Sheets processed: {sheets_processed}")
        print(f"✅ Total successful: {total_success}")
        print(f"❌ Total failed: {total_failed}")

        if (total_success + total_failed) > 0:
            success_rate = (total_success / (total_success + total_failed)) * 100
            print(f"📈 Success rate: {success_rate:.1f}%")
        else:
            print("📈 Success rate: N/A")

        if total_failed > 0:
            print("\n" + "=" * 60)
            print("FAILED RECORDS DETAILS")
            print("=" * 60)

            for sheet_name, failed_records in failures_by_sheet.items():
                if not failed_records:
                    continue

                print(f"\n📄 {sheet_name}:")
                print("-" * 60)
                for record in failed_records:
                    primary_field_value = record.get("primary_field_value", "Unknown")
                    error = record.get("error", "Unknown error")
                    print(f"  • Record: {primary_field_value}")
                    print(f"    Error: {error}")

            print("\n" + "=" * 60)
        else:
            print("\n✨ No failed records!")

        print("=" * 60)
