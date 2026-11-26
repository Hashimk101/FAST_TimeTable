import os, sys, psycopg2

SQL = """
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = 'semesters'
          AND column_name = 'deleted_at'
    ) THEN
        ALTER TABLE public.semesters ADD COLUMN deleted_at TIMESTAMP NULL;
        RAISE NOTICE 'Added column deleted_at to public.semesters';
    ELSE
        RAISE NOTICE 'Column deleted_at already exists';
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
    print('deleted_at migration executed')

if __name__ == '__main__':
    main()
