-- Runs once, at first container boot only (docker-entrypoint-initdb.d scripts
-- only execute against an empty Postgres data directory). POSTGRES_DB only
-- provisions cartogen_phase1 itself -- Directus and LiteLLM each expect their
-- own database on the same Postgres instance in this merged compose stack.
-- Named 00- so it runs before 01-init.sql (docker-entrypoint-initdb.d runs
-- files in alphabetical order).
CREATE DATABASE directus;
CREATE DATABASE litellm;
