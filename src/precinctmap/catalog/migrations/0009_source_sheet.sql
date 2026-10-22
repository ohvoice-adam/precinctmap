-- Multi-sheet results workbooks (2016: one sheet per party ballot plus questions & issues).
-- source_column is within this sheet; NULL for single-sheet files.
ALTER TABLE choices ADD COLUMN source_sheet VARCHAR;
