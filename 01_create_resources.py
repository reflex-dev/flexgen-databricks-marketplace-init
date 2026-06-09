# Databricks notebook source
# MAGIC %md
# MAGIC # Reflex — Create resources (step 1 of 2)
# MAGIC
# MAGIC Run it once **Reflex: Sandbox** is installed, **before** installing
# MAGIC Reflex — it creates the resources the Reflex install flow needs to
# MAGIC select:
# MAGIC
# MAGIC - a **Lakebase** Postgres instance (backs Reflex application state),
# MAGIC - the **secret scopes** Reflex manages secrets inside.
# MAGIC
# MAGIC Run it as a **workspace admin**. Edit the one **EDIT ME** cell below, then
# MAGIC **Run All**. (The `%pip` cell must run first — it restarts Python to load a
# MAGIC current SDK, which clears variables, so the editable cell follows it.) The
# MAGIC final cell prints what to select / fill when installing Reflex.
# MAGIC
# MAGIC > Generated from the asset bundle. The `BUNDLE` cell is overwritten by
# MAGIC > `marketplace/build_marketplace.py` — edit the bundle, not the values there.

# COMMAND ----------

# MAGIC %pip install --quiet --upgrade databricks-sdk
# MAGIC %restart_python

# COMMAND ----------

# ========================= EDIT ME, THEN "RUN ALL" =========================
# The deployment name every resource created here is named after. Use the same
# value later in 02_grant_permissions.
DEPLOYMENT_NAME = "reflex-build-prod"
# ===========================================================================

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

# MAGIC %md ## Verify the resource names
# MAGIC Eyeball these before creating anything. If they're not what you want, edit
# MAGIC `DEPLOYMENT_NAME` above and re-run — nothing is created until the cells below.

# COMMAND ----------

lakebase_name = f"{DEPLOYMENT_NAME}{BUNDLE['lakebase']['name_suffix']}"
scope_plan = [
    {"env": sc["env"], "name": f"{DEPLOYMENT_NAME}{sc['suffix']}", "backend": sc["backend"]}
    for sc in BUNDLE["secret_scopes"]
]

print(f"deployment name  : {DEPLOYMENT_NAME}")
print(f"Lakebase instance: {lakebase_name}  (capacity={BUNDLE['lakebase']['capacity']})")
if scope_plan:
    print("secret scopes    :")
    for s in scope_plan:
        print(f"  - {s['name']}")
else:
    print("secret scopes    : (none declared by this bundle)")

# COMMAND ----------

from databricks.sdk import WorkspaceClient
from databricks.sdk.service.database import DatabaseInstance
from databricks.sdk.service.workspace import ScopeBackendType

w = WorkspaceClient()

# COMMAND ----------

# MAGIC %md ## Create the Lakebase Postgres instance

# COMMAND ----------

existing = {i.name for i in w.database.list_database_instances()}
if lakebase_name in existing:
    print(f"Lakebase instance already exists: {lakebase_name}")
else:
    print(f"creating Lakebase instance {lakebase_name} (capacity={BUNDLE['lakebase']['capacity']})...")
    w.database.create_database_instance_and_wait(
        DatabaseInstance(name=lakebase_name, capacity=BUNDLE["lakebase"]["capacity"])
    )
    print("created")

# COMMAND ----------

# MAGIC %md ## Create the secret scopes
# MAGIC Reflex manages whole scopes (keys are namespaced per app/project/
# MAGIC integration). Each scope also gets a `__SCOPE_NAME__` secret whose value is
# MAGIC the scope's own name — the Reflex install binds the scope-name env vars
# MAGIC via a `secret` resource (the install flow has no free-text env input), so
# MAGIC the admin selects the scope + the `__SCOPE_NAME__` key and the env var
# MAGIC resolves to the scope name.

# COMMAND ----------

existing_scopes = {s.name for s in w.secrets.list_scopes()}
for s in scope_plan:
    if s["name"] in existing_scopes:
        print(f"secret scope already exists: {s['name']}")
    else:
        print(f"creating secret scope {s['name']}...")
        w.secrets.create_scope(
            scope=s["name"], scope_backend_type=ScopeBackendType(s["backend"])
        )
    # The scope's own name, stored as a secret so the Reflex install can bind it
    # to a scope-name env var (select the scope + this __SCOPE_NAME__ key).
    w.secrets.put_secret(scope=s["name"], key="__SCOPE_NAME__", string_value=s["name"])
    print(f"  set {s['name']}/__SCOPE_NAME__")

# COMMAND ----------

# MAGIC %md ## Reflex install cheat sheet
# MAGIC Use the values below when installing **Reflex** (Reflex: Sandbox is already
# MAGIC installed at this point). After installing Reflex, run `02_grant_permissions`
# MAGIC (bundled with Reflex).

# COMMAND ----------

print("=" * 72)
print("WHEN INSTALLING REFLEX, BIND THESE RESOURCES")
print("=" * 72)
print(f"  lakebase-db   ->  select Lakebase instance:  {lakebase_name}")
print( "  sandbox-app   ->  select the installed Reflex: Sandbox app")
print()
print("  Scope-name env vars are bound via `secret` resources — for each resource")
print("  below, select the scope and its '__SCOPE_NAME__' key:")
for s in scope_plan:
    # Must match the secret-resource name derived in marketplace/build_marketplace.py.
    res = s["env"].lower().replace("_", "-").removeprefix("databricks-")
    print(f"    {res}  ->  scope {s['name']}  /  key __SCOPE_NAME__")
print("=" * 72)
print("Next: install Reflex (selecting the above), then run the bundled")
print("02_grant_permissions notebook.")
