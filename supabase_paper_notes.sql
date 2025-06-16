-- SQL script to create the PaperNotes table in Supabase

-- Create the PaperNotes table
CREATE TABLE IF NOT EXISTS "PaperNotes" (
  "id" UUID PRIMARY KEY,
  "paper_summary_id" UUID NOT NULL,
  "xml_id" TEXT,
  "place" TEXT,
  "note_number" TEXT,
  "content" TEXT,
  "references" JSONB,
  "html_content" TEXT,
  "created_at" TIMESTAMPTZ DEFAULT NOW(),
  "updated_at" TIMESTAMPTZ DEFAULT NOW(),
  
  -- Add foreign key constraint
  CONSTRAINT fk_paper_summary
    FOREIGN KEY ("paper_summary_id")
    REFERENCES "PaperMainStructure" ("id")
    ON DELETE CASCADE
);

-- Create index on paper_summary_id for faster lookups
CREATE INDEX IF NOT EXISTS "idx_paper_notes_paper_summary_id" ON "PaperNotes"("paper_summary_id");

-- Create index on xml_id for faster lookups
CREATE INDEX IF NOT EXISTS "idx_paper_notes_xml_id" ON "PaperNotes"("xml_id");

-- Enable Row Level Security (RLS)
ALTER TABLE "PaperNotes" ENABLE ROW LEVEL SECURITY;

-- Create a policy that allows all operations for authenticated users
CREATE POLICY "Allow full access to authenticated users" 
  ON "PaperNotes" 
  FOR ALL 
  TO anon 
  USING (true);
