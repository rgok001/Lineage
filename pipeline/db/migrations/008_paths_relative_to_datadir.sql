-- 008: store file paths relative to DATA_DIR, not the repo root.
--
-- Old code stored raw_path / extracted_text_path relative to REPO_ROOT, which
-- only works when DATA_DIR lives inside the repo (local default ./data). On a
-- deployed worker DATA_DIR is a separate mounted disk (e.g. /data), so
-- relative_to(REPO_ROOT) raised ValueError. The pipeline now stores and
-- resolves these paths relative to DATA_DIR.
--
-- Existing rows were written under the old scheme with a leading "data/"
-- component (the default DATA_DIR). Strip it so the new resolvers (data_dir() /
-- path) find them. Rows written by any non-default DATA_DIR would need manual
-- fixing, but the only pre-008 corpus used the default.

UPDATE papers SET raw_path = regexp_replace(raw_path, '^data/', '')
    WHERE raw_path LIKE 'data/%';
UPDATE papers SET extracted_text_path = regexp_replace(extracted_text_path, '^data/', '')
    WHERE extracted_text_path LIKE 'data/%';
