"""
Performance profiling script for the Amplify Excel Migrator.

Usage:
    python profile_migrator.py [excel_file] [options]

Example:
    python profile_migrator.py --top 30
    python profile_migrator.py data.xlsx --top 30
"""

import cProfile
import pstats
import argparse
import sys
from io import StringIO
from getpass import getpass
from migrator import ExcelToAmplifyMigrator, load_cached_config, get_cached_or_prompt, get_config_value


def profile_migration(excel_path: str, api_endpoint: str, region: str, user_pool_id: str,
                     client_id: str, username: str, password: str, top_n: int = 20):
    """
    Profile the migration process and print statistics.

    Args:
        excel_path: Path to Excel file
        api_endpoint: AWS Amplify API endpoint
        region: AWS region
        user_pool_id: Cognito User Pool ID
        client_id: Cognito Client ID
        username: Admin username
        password: Admin password
        top_n: Number of top functions to display
    """

    print("\n" + "="*80)
    print("STARTING PERFORMANCE PROFILING")
    print("="*80 + "\n")

    # Create profiler
    profiler = cProfile.Profile()

    # Start profiling
    profiler.enable()

    try:
        # Run the migration
        migrator = ExcelToAmplifyMigrator(excel_path)
        migrator.init_client(api_endpoint, region, user_pool_id, client_id=client_id, username=username)

        if not migrator.authenticate(username, password):
            print("Authentication failed!")
            sys.exit(1)

        migrator.run()

    finally:
        # Stop profiling
        profiler.disable()

    print("\n" + "="*80)
    print("PROFILING RESULTS")
    print("="*80 + "\n")

    # Create stats object
    stats = pstats.Stats(profiler)

    # Sort by cumulative time
    stats.sort_stats('cumulative')

    # Print top N functions by cumulative time
    print(f"\n{'='*80}")
    print(f"TOP {top_n} FUNCTIONS BY CUMULATIVE TIME")
    print(f"{'='*80}\n")
    stats.print_stats(top_n)

    # Sort by total time (time spent in function itself, not including calls)
    stats.sort_stats('tottime')

    print(f"\n{'='*80}")
    print(f"TOP {top_n} FUNCTIONS BY TOTAL TIME (EXCLUDING SUBCALLS)")
    print(f"{'='*80}\n")
    stats.print_stats(top_n)

    # Save detailed stats to file
    output_file = "profile_output.txt"
    with open(output_file, 'w') as f:
        stats = pstats.Stats(profiler, stream=f)
        stats.sort_stats('cumulative')
        stats.print_stats()

    print(f"\n{'='*80}")
    print(f"Full profiling data saved to: {output_file}")
    print(f"{'='*80}\n")


def main():
    parser = argparse.ArgumentParser(
        description="Profile performance of Amplify Excel Migrator",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )

    parser.add_argument("excel_path", nargs='?', help="Path to Excel file (optional, will use cached config)")
    parser.add_argument("--api-endpoint", help="AWS Amplify API endpoint")
    parser.add_argument("--region", help="AWS region")
    parser.add_argument("--user-pool-id", help="Cognito User Pool ID")
    parser.add_argument("--client-id", help="Cognito Client ID")
    parser.add_argument("--username", help="Admin username")
    parser.add_argument("--password", help="Admin password")
    parser.add_argument("--top", type=int, default=20, help="Number of top functions to display (default: 20)")

    args = parser.parse_args()

    print(
        """
    ╔════════════════════════════════════════════════════╗
    ║        Performance Profiler for Amplify Migrator   ║
    ╚════════════════════════════════════════════════════╝
    """
    )

    # Load cached config
    cached_config = load_cached_config()

    if not cached_config and not all([args.api_endpoint, args.user_pool_id, args.client_id, args.username]):
        print("\n❌ No cached configuration found and required arguments not provided!")
        print("💡 Run 'amplify-migrator config' first or provide all required arguments.")
        sys.exit(1)

    # Get config values (from args or cached config)
    excel_path = args.excel_path or get_cached_or_prompt("excel_path", "Excel file path", cached_config, "data.xlsx")
    api_endpoint = args.api_endpoint or get_cached_or_prompt("api_endpoint", "AWS Amplify API endpoint", cached_config)
    region = args.region or get_cached_or_prompt("region", "AWS Region", cached_config, "us-east-1")
    user_pool_id = args.user_pool_id or get_cached_or_prompt("user_pool_id", "Cognito User Pool ID", cached_config)
    client_id = args.client_id or get_cached_or_prompt("client_id", "Cognito Client ID", cached_config)
    username = args.username or get_cached_or_prompt("username", "Admin Username", cached_config)

    # Always prompt for password (never cache)
    if args.password:
        password = args.password
    else:
        print("\n🔐 Authentication:")
        print("-" * 54)
        # password = get_config_value("Admin Password", secret=True)
        password = 'Eynavmil1!'

    profile_migration(
        excel_path,
        api_endpoint,
        region,
        user_pool_id,
        client_id,
        username,
        password,
        args.top
    )


if __name__ == "__main__":
    main()