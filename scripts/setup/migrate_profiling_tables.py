#!/usr/bin/env python3
#
# Copyright (C) 2023 Intel Corporation
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#

"""
Script to apply the profiling tables migration to an existing PostgreSQL database.
"""

import os
import sys
import argparse
from pathlib import Path

# Add the src directory to the Python path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from gprofiler_dev.postgres import get_postgres_db


def apply_migration(migration_file: str, dry_run: bool = False):
    """Apply the migration SQL file to the database"""

    # Read the migration file
    migration_path = Path(__file__).parent / "postgres" / migration_file
    if not migration_path.exists():
        print(f"Error: Migration file {migration_path} not found!")
        sys.exit(1)

    with open(migration_path, 'r') as f:
        migration_sql = f.read()

    if dry_run:
        print("DRY RUN MODE - SQL that would be executed:")
        print("=" * 50)
        print(migration_sql)
        print("=" * 50)
        return

    try:
        # Get database connection
        db = get_postgres_db()

        print(f"Applying migration: {migration_file}")

        # Execute the migration SQL
        # Split by semicolon and execute each statement separately to handle complex SQL
        statements = [stmt.strip() for stmt in migration_sql.split(';') if stmt.strip()]

        for i, statement in enumerate(statements):
            if statement:
                print(f"Executing statement {i+1}/{len(statements)}")
                try:
                    db.execute(statement, {}, has_value=False)
                except Exception as e:
                    print(f"Error executing statement {i+1}: {e}")
                    print(f"Statement: {statement[:100]}...")
                    raise

        print("Migration applied successfully!")

    except Exception as e:
        print(f"Error applying migration: {e}")
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(description="Apply profiling tables migration")
    parser.add_argument(
        "--migration-file",
        default="add_profiling_tables.sql",
        help="Migration file to apply (default: add_profiling_tables.sql)"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be executed without actually running the migration"
    )

    args = parser.parse_args()

    apply_migration(args.migration_file, args.dry_run)


if __name__ == "__main__":
    main()
