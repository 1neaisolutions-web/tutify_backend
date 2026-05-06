-- Manual SQL script to add profile_picture_url column to users table
-- Run this if migrations are having issues

-- Check if column exists, if not, add it
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 
        FROM information_schema.columns 
        WHERE table_name = 'users' 
        AND column_name = 'profile_picture_url'
    ) THEN
        ALTER TABLE users 
        ADD COLUMN profile_picture_url VARCHAR(500) NULL;
        
        RAISE NOTICE 'Column profile_picture_url added to users table';
    ELSE
        RAISE NOTICE 'Column profile_picture_url already exists';
    END IF;
END $$;
