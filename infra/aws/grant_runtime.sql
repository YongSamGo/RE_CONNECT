-- Run as reconnect_migrator after every successful migration; transaction is atomic.
\set ON_ERROR_STOP on
BEGIN;
DO $$
DECLARE
    relation record;
BEGIN
    IF current_database() <> 'reconnect' OR current_user <> 'reconnect_migrator' THEN
        RAISE EXCEPTION 'requires the reconnect migration account';
    END IF;
    FOR relation IN
        SELECT c.relname, c.relkind, pg_get_userbyid(c.relowner) AS owner
        FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE n.nspname = 'public' AND c.relkind IN ('r', 'p', 'S')
    LOOP
        IF relation.owner <> current_user THEN
            RAISE EXCEPTION 'unexpected object owner; grants aborted';
        END IF;
        IF relation.relkind = 'S' THEN
            EXECUTE format('REVOKE ALL ON SEQUENCE public.%I FROM reconnect_runtime', relation.relname);
            EXECUTE format('GRANT USAGE, SELECT ON SEQUENCE public.%I TO reconnect_runtime', relation.relname);
        ELSE
            EXECUTE format('REVOKE ALL ON TABLE public.%I FROM reconnect_runtime', relation.relname);
            IF relation.relname <> 'alembic_version' THEN
                EXECUTE format('GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE public.%I TO reconnect_runtime', relation.relname);
            END IF;
        END IF;
    END LOOP;
END $$;
COMMIT;
