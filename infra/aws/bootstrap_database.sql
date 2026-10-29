-- Run once as the RDS administrator, using psql with verified TLS.
\set ON_ERROR_STOP on
BEGIN;
DO $$
BEGIN
    IF current_database() <> 'reconnect' THEN
        RAISE EXCEPTION 'bootstrap requires the reconnect database';
    END IF;
END $$;

-- Deliberately fail and roll back on an existing role; never reuse unknown grants.
-- Login is enabled separately only after credentials have been provisioned.
CREATE ROLE reconnect_migrator NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE
    NOREPLICATION NOBYPASSRLS NOINHERIT;
CREATE ROLE reconnect_runtime NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE
    NOREPLICATION NOBYPASSRLS NOINHERIT;
REVOKE ALL ON DATABASE reconnect FROM PUBLIC;
GRANT CONNECT ON DATABASE reconnect TO reconnect_migrator, reconnect_runtime;
REVOKE ALL ON SCHEMA public FROM PUBLIC;
GRANT USAGE, CREATE ON SCHEMA public TO reconnect_migrator;
GRANT USAGE ON SCHEMA public TO reconnect_runtime;
ALTER ROLE reconnect_migrator IN DATABASE reconnect SET search_path = public;
ALTER ROLE reconnect_runtime IN DATABASE reconnect SET search_path = public;
-- The non-superuser RDS administrator cannot assume the new role on PG16.
-- The migrator sets its own function defaults in grant_runtime.sql.
-- No membership in the migration/owner role and no automatic grants to future tables.
COMMIT;
