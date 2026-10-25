# Deploy

Everything in `terraform/`, `dashboards/`, and `scripts/build_dashboards.py` /
`scripts/export_dashboards.py` is how the Grafana Cloud side of this project
(folder, data source, plugins, the Race Centre dashboard) and the GitHub
side (`pitwall-data`'s Pages config, deploy key, Actions secrets) are
managed as code.

## Bootstrap from zero

These steps assume neither the HCP Terraform workspaces nor the GitHub
secrets exist yet. Most of this only needs doing once.

1. **Install Terraform** (>= 1.17.0) and **Node** (>= 20, for ESLint).

2. **Create an HCP Terraform organization** at app.terraform.io, if you
   don't have one. `terraform/*/versions.tf` reference a `cloud` block with
   `organization = "formula"` and workspace names `pitwall-grafana` /
   `pitwall-github` — update the org name if yours differs. The workspaces
   themselves are created automatically on first `terraform init`.

3. **Authenticate Terraform with HCP Terraform**: create an API token at
   app.terraform.io → your user icon → User Settings → Tokens (a *team*
   token, not a personal one, avoids a separate workspace team-access step).
   Store it:
   ```
   mkdir -p ~/.terraform.d
   cat > ~/.terraform.d/credentials.tfrc.json <<'EOF'
   { "credentials": { "app.terraform.io": { "token": "<token>" } } }
   EOF
   chmod 600 ~/.terraform.d/credentials.tfrc.json
   ```

4. **Create a Grafana service account token**: Grafana Cloud →
   Administration → Users and access → Service accounts → Add service
   account (role: Admin) → Add token. This is `grafana_auth` /
   `GRAFANA_AUTH`.

5. **Create a Grafana Cloud access policy token**: grafana.com → your org →
   Security → Access Policies → Create access policy, scope
   `stack-plugins:read`, `stack-plugins:write`, `stack-plugins:delete` →
   Create token. This is `grafana_cloud_api_key` / `GRAFANA_CLOUD_API_KEY`.

6. **Create a GitHub PAT** with `repo` scope (classic PAT; fine-grained
   equivalents are Contents, Pages, Deploy keys, Secrets, all read+write) on
   `pitwall-data` and `pitwall-observability`. This is `github_token` for
   `terraform/github`, and separately needs storing as the
   **`GH_TERRAFORM_TOKEN`** secret on `pitwall-observability` by hand
   (Settings → Secrets and variables → Actions → New repository secret) —
   this is the one credential that can't be created by Terraform itself,
   since it's the credential Terraform authenticates with to manage
   `pitwall-observability`'s other secrets.

7. **Fill in `terraform.tfvars`** in both `terraform/grafana/` and
   `terraform/github/` (copy from `terraform.tfvars.example`; these files
   are gitignored, never commit them). Use the same Grafana/token values in
   both where they overlap.

8. **Build the dashboard JSON**, then init/import/apply each module:
   ```
   python3 scripts/build_dashboards.py

   cd terraform/grafana
   terraform init
   # Only needed the FIRST time, to adopt the dashboard/plugin that already
   # exist rather than recreate them:
   terraform import grafana_apps_dashboard_dashboard_v2.race_centre roscr2t
   terraform import grafana_cloud_plugin_installation.business_charts "<stack-slug>:volkovlabs-echarts-panel"
   terraform plan   # review
   terraform apply

   cd ../github
   terraform init
   terraform import github_repository.pitwall_data pitwall-data
   terraform import github_repository_pages.pitwall_data pitwall-data
   terraform plan   # review
   terraform apply
   ```
   After this, `pitwall-observability`'s Actions secrets
   (`PITWALL_DATA_DEPLOY_KEY`, `GRAFANA_AUTH`, `GRAFANA_CLOUD_API_KEY`,
   `TF_API_TOKEN`, `GRAFANA_OTLP_ENDPOINT`, `GRAFANA_INSTANCE_ID`,
   `GRAFANA_OTLP_TOKEN`) exist and the GitHub Actions workflows can run.

### A real gap this surfaced

The `grafana_apps_dashboard_dashboard_v2` resource needs the provider's
`stack_id` set (Grafana Cloud stack ID — find it from your stack's own
settings, or it's the numeric ID embedded in OTLP instance IDs) for `import`
to work at all. Without it, import fails with a 403 even though the
underlying Grafana API call succeeds directly via curl with the same
token — the provider silently resolves to the wrong k8s namespace. This
isn't documented anywhere obvious; it was found by trial and error. Don't
skip `stack_id` in the provider block.

## The UI-edit → export → PR → apply workflow

The dashboard is built for live editing in Grafana (Business Charts panels,
tabs, layout) — not for hand-editing JSON. The loop:

1. **Edit live** in Grafana Cloud as normal. `allow_ui_updates = true` on
   the dashboard resource means Terraform won't fight you or overwrite your
   changes on the next apply.
2. **Export it back**:
   ```
   GRAFANA_URL=https://<your-stack>.grafana.net GRAFANA_AUTH=<token> \
     python3 scripts/export_dashboards.py --uid roscr2t --name race-centre
   ```
   This pulls the dashboard via the v2 App Platform API (NOT
   `/api/dashboards/uid/<uid>`, which silently downgrades v2-storage
   dashboards to legacy classic JSON — see the comment in
   `export_dashboards.py` if this ever needs debugging again), splits every
   Business Charts `getOption` script into `dashboards/race-centre/panels/*.js`,
   and writes a normalized `dashboard.json` (only the stable `name`/
   `namespace` metadata kept, no `resourceVersion`/`generation`/
   timestamps/labels/annotations — those are server state, not source).
3. **Review the diff.** Since panel JS lives in its own `.js` files, a
   one-line script change in the Grafana UI shows up as a one-line diff in
   git, not a multi-thousand-line JSON blob.
4. **Open a PR.** `terraform-pr.yml` runs ESLint on the panel JS,
   `terraform fmt -check`/`validate`/`plan` for both modules, and posts the
   plan output as a PR comment.
5. **Merge.** `terraform-apply.yml` rebuilds the dashboard JSON and applies
   both modules.

## Rotating secrets

All five rotatable credentials are Terraform variables; rotating one is
"get a new value, update `terraform.tfvars` (or the HCP Terraform workspace
variable in CI), `terraform apply`":

- **Grafana service account token** (`GRAFANA_AUTH`): revoke the old token
  in Grafana Cloud → Service accounts, create a new one, update the
  variable, re-apply `terraform/grafana` (this also re-applies
  `terraform/github`'s mirrored `GRAFANA_AUTH` secret).
- **Grafana Cloud access policy token** (`GRAFANA_CLOUD_API_KEY`): same
  pattern, via Security → Access Policies.
- **pitwall-data deploy key**: this one's easiest — just
  `terraform taint tls_private_key.pitwall_data_deploy` in
  `terraform/github` then `terraform apply`; it generates a fresh keypair,
  re-registers the public half as the deploy key, and re-mirrors the
  private half into the `PITWALL_DATA_DEPLOY_KEY` secret, all in one apply.
- **HCP Terraform API token** (`TF_API_TOKEN`): create a new team token in
  HCP Terraform, update `~/.terraform.d/credentials.tfrc.json` locally and
  the `TF_API_TOKEN` variable for CI, re-apply.
- **`GH_TERRAFORM_TOKEN`**: the one secret Terraform can't rotate for
  itself (same bootstrapping constraint as creating it). Create a new PAT,
  update the `GH_TERRAFORM_TOKEN` Actions secret by hand.

## Nightly drift

`terraform-drift.yml` runs `terraform plan -detailed-exitcode` against both
modules every night and opens a GitHub issue (label `terraform-drift`) if
either shows pending changes — most commonly a UI edit to the dashboard
that hasn't been exported back into git yet, or a plugin version Grafana
Cloud bumped automatically. The fix is either exporting the drifted change
(step 2 above) or running `terraform apply` directly if the drift should
just be accepted as-is.
