import os, sys, psycopg2

SQL = """
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = 'semesters'
          AND column_name = 'sync_policy'
    ) THEN
        ALTER TABLE public.semesters ADD COLUMN sync_policy TEXT DEFAULT 'AUTO_ENABLED';
        RAISE NOTICE 'Added column sync_policy to public.semesters';
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = 'semesters'
          AND column_name = 'state_version'
    ) THEN
        ALTER TABLE public.semesters ADD COLUMN state_version INTEGER DEFAULT 1;
        RAISE NOTICE 'Added column state_version to public.semesters';
    END IF;
END $$;
"""

def main():
    db_url = os.getenv('DATABASE_URL')
    if not db_url:
        print('DATABASE_URL not set')
        sys.exit(1)
    conn = psycopg2.connect(db_url)
    conn.autocommit = True
    cur = conn.cursor()
    cur.execute(SQL)
    cur.close()
    conn.close()
    print('sync_policy and state_version migrations executed')

if __name__ == '__main__':
    main()
