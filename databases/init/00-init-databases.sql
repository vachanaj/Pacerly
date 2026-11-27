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

-- 3. Activity Service
CREATE USER activity_svc WITH ENCRYPTED PASSWORD 'ChangeMeActivityDb!';
CREATE DATABASE activities_db OWNER activity_svc;
GRANT ALL PRIVILEGES ON DATABASE activities_db TO activity_svc;

-- 4. Equipment Service
CREATE USER equipment_svc WITH ENCRYPTED PASSWORD 'ChangeMeEquipmentDb!';
CREATE DATABASE equipment_db OWNER equipment_svc;
GRANT ALL PRIVILEGES ON DATABASE equipment_db TO equipment_svc;

-- 5. Adaptive Pacing Service
CREATE USER pacing_svc WITH ENCRYPTED PASSWORD 'ChangeMePacingDb!';
CREATE DATABASE paces_db OWNER pacing_svc;
GRANT ALL PRIVILEGES ON DATABASE paces_db TO pacing_svc;