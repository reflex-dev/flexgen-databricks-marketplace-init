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

## Install flow

Each notebook runs once, at its step:

1. Install the **Reflex: Sandbox** app from Marketplace, selecting a Unity
   Catalog volume for its `scm-volume` resource.
2. Import and run [`01_create_resources.py`](01_create_resources.py):

   ```
   https://raw.githubusercontent.com/reflex-dev/flexgen-databricks-marketplace-init/main/01_create_resources.py
   ```

   It creates the Lakebase Postgres instance and secret scopes, and prints
   exactly what to select when installing the Reflex app.
3. Install the **Reflex** app from Marketplace, binding the resources printed
   in step 2.
4. Import and run [`02_grant_permissions.py`](02_grant_permissions.py):

   ```
   https://raw.githubusercontent.com/reflex-dev/flexgen-databricks-marketplace-init/main/02_grant_permissions.py
   ```

   It discovers the installed apps' resource bindings and grants both service
   principals access to the Lakebase instance, SCM volume, and secret scopes.
5. Start both apps and open Reflex.

---

These notebooks are generated from the Reflex Build asset bundle and published
here by its marketplace tooling — changes made in this repo will be overwritten
on the next publish.
