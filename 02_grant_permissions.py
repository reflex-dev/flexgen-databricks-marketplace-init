# Databricks notebook source
# MAGIC %md
# MAGIC # Reflex — Grant permissions (step 2 of 2)
# MAGIC
# MAGIC Run it **last** — after both apps are
# MAGIC installed (installing an app creates its service principal). The **Reflex
# MAGIC app name is the only input**; everything else (its service principal, the
# MAGIC Lakebase instance, the Reflex: Sandbox app + its SCM volume, the secret
# MAGIC scopes) is discovered from the apps' resource bindings. It grants:
# MAGIC
# MAGIC - **Reflex's SP** → a Postgres role + schema privileges in Lakebase (the
# MAGIC   binding only grants database-level CONNECT/CREATE, not the schema-level
# MAGIC   CREATE that `reflex db migrate` needs) and `MANAGE` on the secret scopes,
# MAGIC - **Reflex: Sandbox's SP** → `USE CATALOG` / `USE SCHEMA` / `READ+WRITE
# MAGIC   VOLUME` on the SCM volume bound to Reflex: Sandbox (the app's
# MAGIC   `uc_securable` binding covers the volume itself but not the parent
# MAGIC   catalog/schema).
# MAGIC
# MAGIC Run it as a **workspace admin**. Edit the one **EDIT ME** cell below, then
# MAGIC **Run All**. (The `%pip` cell must run first — it restarts Python to load a
# MAGIC current SDK, which clears variables, so the editable cell follows it.)
# MAGIC Idempotent — safe to re-run.
# MAGIC
# MAGIC > Generated from the asset bundle. The `BUNDLE` cell is overwritten by
# MAGIC > `marketplace/build_marketplace.py`.

# COMMAND ----------

# MAGIC %pip install --quiet --upgrade "databricks-sdk" "psycopg[binary]"
# MAGIC %restart_python

# COMMAND ----------

# ========================= EDIT ME, THEN "RUN ALL" =========================
# The installed Reflex app's name — the only input. Everything else is read
# from Reflex's (and the linked Reflex: Sandbox app's) resource bindings.
BUILDER_APP_NAME = ""
# ===========================================================================

assert BUILDER_APP_NAME, "set BUILDER_APP_NAME to the installed Reflex app name"

# COMMAND ----------

# ===BEGIN GENERATED BUNDLE CONFIG===
BUNDLE = {
    "bundle_name": "reflex-build",
    "default_ident": "dev",
    "lakebase": {
        "name_suffix": "-db",
        "capacity": "CU_1",
        "database_name": "databricks_postgres",
        "branch_id": "production"
    },
    "secret_scopes": [
        {
            "suffix": "-app-secrets",
            "backend": "DATABRICKS",
            "env": "DATABRICKS_APP_SECRETS_SCOPE"
        },
        {
            "suffix": "-project-secrets",
            "backend": "DATABRICKS",
            "env": "DATABRICKS_PROJECT_SECRETS_SCOPE"
        },
        {
            "suffix": "-integration-secrets",
            "backend": "DATABRICKS",
            "env": "DATABRICKS_INTEGRATION_SECRETS_SCOPE"
        }
    ],
    "installer_env": {
        "sandbox": [],
        "builder": []
    }
}
# ===END GENERATED BUNDLE CONFIG===

# COMMAND ----------

import base64
import json
import urllib.parse

import psycopg
from databricks.sdk import WorkspaceClient
from databricks.sdk.service.catalog import PermissionsChange, Privilege
from databricks.sdk.service.postgres import (
    Endpoint,
    Role,
    RoleIdentityType,
    RoleRoleSpec,
)
from databricks.sdk.service.workspace import AclPermission
from psycopg import sql

w = WorkspaceClient()


def _get_app(name: str) -> dict:
    # Read resources straight from the REST response: the SDK model drops the
    # `app` resource binding's value, but the raw API returns it.
    return w.api_client.do("GET", f"/api/2.0/apps/{name}")


def _binding(app: dict, key: str) -> dict:
    for r in app.get("resources", []):
        if key in r:
            return r[key]
    raise RuntimeError(f"app {app.get('name')!r} has no {key!r} resource binding")


def _lakebase(builder: dict) -> tuple[str, str]:
    """(project_id, branch_id) from the builder's Lakebase binding.

    Handles both shapes the API returns: the legacy `database` binding
    (instance_name), and the `postgres` binding used by horizontal-scaling apps
    (branch = ``projects/<project_id>/branches/<branch_id>``).
    """
    for r in builder.get("resources", []):
        if "postgres" in r:
            parts = r["postgres"]["branch"].strip("/").split("/")
            branch = parts[3] if len(parts) > 3 else BUNDLE["lakebase"]["branch_id"]
            return parts[1], branch
        if "database" in r:
            return r["database"]["instance_name"], BUNDLE["lakebase"]["branch_id"]
    raise RuntimeError(f"builder app {BUILDER_APP_NAME!r} has no Lakebase binding")


# Discover everything from Reflex + the Reflex: Sandbox app it links to.
builder = _get_app(BUILDER_APP_NAME)
builder_sp = builder.get("service_principal_client_id")
assert builder_sp, f"builder app {BUILDER_APP_NAME!r} has no service principal yet"

project_id, branch_id = _lakebase(builder)
# The `postgres`/`database` binding paths encode the logical db name with a
# hyphen; the actual Postgres database is the bundle default (databricks_postgres).
database_name = BUNDLE["lakebase"]["database_name"]

sandbox_app_name = _binding(builder, "app")["name"]  # sandbox-app
sandbox = _get_app(sandbox_app_name)
sandbox_sp = sandbox.get("service_principal_client_id")
assert sandbox_sp, f"sandbox app {sandbox_app_name!r} has no service principal yet"

scm_catalog, scm_schema, scm_volume = _binding(sandbox, "uc_securable")[
    "securable_full_name"
].split(".")

# Scope names come straight from the builder's `secret` resource bindings — the
# admin selected each scope (+ the __SCOPE_NAME__ key) at install time.
scope_names = [
    r["secret"]["scope"]
    for r in builder.get("resources", [])
    if "secret" in r and r["secret"].get("scope")
]

# COMMAND ----------

# MAGIC %md ## Verify discovered resources
# MAGIC Check these before granting. Fix `BUILDER_APP_NAME` and re-run the cell
# MAGIC above if anything looks wrong — nothing is granted until the cells below.

# COMMAND ----------

print(f"Reflex          : {BUILDER_APP_NAME}  (SP {builder_sp})")
print(f"Reflex: Sandbox : {sandbox_app_name}  (SP {sandbox_sp})")
print(f"Lakebase      : {project_id} / {database_name}  (branch {branch_id})")
print(f"SCM volume    : {scm_catalog}.{scm_schema}.{scm_volume}")
print(f"secret scopes : {', '.join(scope_names) or '(none declared)'}")

# COMMAND ----------

# MAGIC %md ## Lakebase: Reflex's SP — Postgres role + schema privileges
# MAGIC Picking the Lakebase instance at install auto-creates the SP's Postgres
# MAGIC role and grants CONNECT + CREATE at the *database* level. This step adds
# MAGIC the schema-level USAGE + CREATE on `public` that the binding does NOT
# MAGIC grant — required for `reflex db migrate` to create tables. The role
# MAGIC creation here is an idempotent safety net. Mirrors
# MAGIC `scripts/grant_lakebase_permissions.py` from the bundle.

# COMMAND ----------

def _parent(project_id: str, branch_id: str) -> str:
    return f"projects/{project_id}/branches/{branch_id}"


def _jwt_sub(token: str) -> str:
    payload = token.split(".")[1]
    payload += "=" * (-len(payload) % 4)
    return json.loads(base64.urlsafe_b64decode(payload)).get("sub", "")


def _endpoint_host(endpoint: Endpoint) -> str:
    if endpoint.status and endpoint.status.hosts and endpoint.status.hosts.host:
        return endpoint.status.hosts.host
    raise RuntimeError(f"Lakebase endpoint {endpoint.name or '<unknown>'!r} has no host")


def _ensure_role(service_principal: str) -> None:
    for role in w.postgres.list_roles(_parent(project_id, branch_id)):
        if role.status and role.status.postgres_role == service_principal:
            return
    w.postgres.create_role(
        parent=_parent(project_id, branch_id),
        role=Role(
            spec=RoleRoleSpec(
                identity_type=RoleIdentityType.SERVICE_PRINCIPAL,
                postgres_role=service_principal,
            )
        ),
        role_id=f"sp-{service_principal}",
    ).wait()


endpoint = w.postgres.get_endpoint(f"{_parent(project_id, branch_id)}/endpoints/primary")
assert endpoint.name, "Lakebase primary endpoint has no name"
_ensure_role(builder_sp)

token = w.postgres.generate_database_credential(endpoint=endpoint.name).token
assert token, "Lakebase returned no credential token"
username = _jwt_sub(token)
assert username, "could not derive Lakebase username from credential token"
user_q, pw_q = urllib.parse.quote(username, safe=""), urllib.parse.quote(token, safe="")
dsn = (
    f"postgresql://{user_q}:{pw_q}@{_endpoint_host(endpoint)}:5432/"
    f"{database_name}?sslmode=require"
)

print(f"granting public-schema privileges to {builder_sp} on {project_id}/{database_name}...")
with psycopg.connect(dsn, autocommit=True) as conn:
    principal = sql.Identifier(builder_sp)
    conn.execute(sql.SQL("GRANT CONNECT ON DATABASE {} TO {}").format(sql.Identifier(database_name), principal))
    conn.execute(sql.SQL("GRANT USAGE, CREATE ON SCHEMA public TO {}").format(principal))
    conn.execute(sql.SQL("GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO {}").format(principal))
    conn.execute(sql.SQL("GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO {}").format(principal))
    conn.execute(sql.SQL("GRANT ALL PRIVILEGES ON ALL FUNCTIONS IN SCHEMA public TO {}").format(principal))
    conn.execute(sql.SQL("ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL PRIVILEGES ON TABLES TO {}").format(principal))
    conn.execute(sql.SQL("ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL PRIVILEGES ON SEQUENCES TO {}").format(principal))
    conn.execute(sql.SQL("ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL PRIVILEGES ON FUNCTIONS TO {}").format(principal))
print("Lakebase permissions configured")

# COMMAND ----------

# MAGIC %md ## SCM volume: Reflex: Sandbox's SP — catalog/schema/volume privileges
# MAGIC Mirrors `scripts/grant_scm_volume_permissions.sh` from the bundle.

# COMMAND ----------

volume_full_name = f"{scm_catalog}.{scm_schema}.{scm_volume}"

w.grants.update("CATALOG", scm_catalog, changes=[PermissionsChange(principal=sandbox_sp, add=[Privilege.USE_CATALOG])])
w.grants.update("SCHEMA", f"{scm_catalog}.{scm_schema}", changes=[PermissionsChange(principal=sandbox_sp, add=[Privilege.USE_SCHEMA])])
w.grants.update("VOLUME", volume_full_name, changes=[PermissionsChange(principal=sandbox_sp, add=[Privilege.READ_VOLUME, Privilege.WRITE_VOLUME])])
print(f"granted USE_CATALOG/USE_SCHEMA/READ+WRITE_VOLUME on {volume_full_name} to {sandbox_sp}")

# COMMAND ----------

# MAGIC %md ## Secret scopes: Reflex's SP — MANAGE
# MAGIC Mirrors the ACLs in `resources/secret_scopes.yml`.

# COMMAND ----------

for scope_name in scope_names:
    w.secrets.put_acl(scope=scope_name, principal=builder_sp, permission=AclPermission.MANAGE)
    print(f"granted MANAGE on {scope_name} to {builder_sp}")

# COMMAND ----------

print("All permissions configured. The apps can now be started.")
