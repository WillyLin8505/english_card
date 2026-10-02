-- Runs once on a fresh Docker volume.
CREATE EXTENSION IF NOT EXISTS pg_trgm;
CREATE DATABASE lexicon_test;
\c lexicon_test
CREATE EXTENSION IF NOT EXISTS pg_trgm;
