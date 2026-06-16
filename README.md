# Reflex on Databricks — setup notebooks

One-time admin setup notebooks for the **Reflex** and **Reflex: Sandbox**
Databricks Apps Marketplace listings. Apps installed from Marketplace don't
surface their bundled files in the workspace UI, so import the notebooks from
here instead.

## Import a notebook into your workspace

1. In your Databricks workspace, open **Workspace**, then right-click a folder
   (or use the **⋮** kebab menu) and choose **Import**.
2. Select **URL** and paste the notebook's raw link from below.
3. Open the imported notebook, edit the single **EDIT ME** cell, and **Run All**
   as a workspace admin.

## Prerequisite: create the shared control secret

Reflex drives the sandbox over an internal control channel. The Reflex app
authenticates to it with a secret that **both apps read**, so create it
**before installing either app** — both bind it during install.

Run these once with the [Databricks CLI](https://docs.databricks.com/dev-tools/cli/)
(any scope name works; the key must be `sandbox-control-auth`):

```bash
databricks secrets create-scope reflex-control-auth
databricks secrets put-secret reflex-control-auth sandbox-control-auth \
    --string-value "$(openssl rand -hex 32)"
```

When installing each app below, bind its **`control-auth`** resource to this
scope and its `sandbox-control-auth` key.

## Install flow

Each notebook runs once, at its step:

1. Install the **Reflex: Sandbox** app from Marketplace, selecting a Unity
   Catalog volume for its `scm-volume` resource and the `reflex-control-auth`
   scope (key `sandbox-control-auth`) for its `control-auth` resource.
2. Import and run [`01_create_resources.py`](01_create_resources.py):

   ```
   https://raw.githubusercontent.com/reflex-dev/flexgen-databricks-marketplace-init/main/01_create_resources.py
   ```

   It creates the Lakebase Postgres instance and secret scopes, and prints
   exactly what to select when installing the Reflex app.
3. Install the **Reflex** app from Marketplace, binding the resources printed
   in step 2, plus its `control-auth` resource to the same `reflex-control-auth`
   scope and `sandbox-control-auth` key from the prerequisite.
4. Import and run [`02_grant_permissions.py`](02_grant_permissions.py):

   ```
   https://raw.githubusercontent.com/reflex-dev/flexgen-databricks-marketplace-init/main/02_grant_permissions.py
   ```

   It discovers the installed apps' resource bindings and grants both service
   principals access to the Lakebase instance and SCM volume. (Secret-scope
   access needs no grant — the Reflex app binds each scope with `WRITE`.)
5. Start both apps and open Reflex.

---

These notebooks are generated from the Reflex Build asset bundle and published
here by its marketplace tooling — changes made in this repo will be overwritten
on the next publish.
