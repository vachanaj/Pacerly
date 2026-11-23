-- Enforce SCRAM-SHA-256 password encryption for all database roles
SET password_encryption = 'scram-sha-256';

-- 1. Keycloak Identity Provider Database
CREATE USER keycloak_user WITH ENCRYPTED PASSWORD 'ChangeMeKeycloakDb!';
CREATE DATABASE keycloak OWNER keycloak_user;
GRANT ALL PRIVILEGES ON DATABASE keycloak TO keycloak_user;

-- 2. User Service Database
CREATE USER user_svc WITH ENCRYPTED PASSWORD 'ChangeMeUserDb!';
CREATE DATABASE user_db OWNER user_svc;
GRANT ALL PRIVILEGES ON DATABASE user_db TO user_svc;