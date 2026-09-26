# Deploy NEURASIGN to the future Google Cloud account

**Status: prepared and tested locally; not deployed to Google Cloud.** Do not use the unrelated account currently selected in the terminal. The deployment script takes an explicit `--account` and `--project` on every invocation and does not change gcloud’s active configuration. Its default mode writes local files without executing gcloud or making network requests.

## Runtime design

```text
Browser / phone — HTTPS → Cloud Run: Next.js web ingress (8080)
                                      ↓ localhost:8000
                                 private FastAPI sidecar
                                   ↙             ↘
                            Firebase Auth       Firestore
```

Cloud Run exposes the web container only; `/api/v1/*` proxies to the sidecar. The service URL is public for sign-in, but data endpoints enforce Firebase user or device credentials. Firestore uses the runtime service account, not service-account key files. State does not depend on Cloud Run’s ephemeral filesystem or a specific instance. The web and API run as non-root users. The API installs a hash-locked dependency set; the frontend uses `npm ci`.

Prepared resources: Artifact Registry, a Cloud Build source bucket and build service account, runtime service account, native Firestore `(default)` database with deletion protection/PITR, daily seven-day backups, TTL policies and deny-all client database rules, and one Cloud Run service. Default region: `europe-west1`; min instances 0, max 5, concurrency 20, 60-second request timeout. Each container has 1 CPU and 512 MiB. These are initial pilot settings, not measured capacity guarantees.

Runtime IAM: `roles/datastore.user` and `roles/firebaseauth.viewer`. Build IAM: Artifact Registry writer on its repository, source-bucket object viewer, logging writer and service-usage consumer. The deployment account receives Service Account User on these two service accounts. Provider API keys, `.env`, local databases, emulator exports and physiological recordings are excluded from Cloud Build uploads. Jev/Gemini are not needed by the company monitoring application; their existing local example remains at `/demo`, disabled in production.

## Once the new account is available

1. Obtain a **dedicated NEURASIGN Google Cloud project** with billing and permission to provision the resources above. The operator needs service enablement, IAM administration, service-account creation/act-as, Cloud Build, Artifact Registry, storage, Firestore, Firebase Rules/Auth configuration and Cloud Run administration. Bootstrap is intended for a project administrator. Organizational restrictions may require that administrator to create resources or allow public Cloud Run invocation.
2. Sign in explicitly with `gcloud auth login NEW_ACCOUNT_EMAIL`. The script never initiates sign-in or reads the active configuration as its target. No ADC key file is required on your computer or in the containers.
3. In the Firebase console, add Firebase to **that same project**, register a Web app, and enable **Email/Password** authentication. Enable a **Require** password policy with a minimum length of 12, and email enumeration protection. Configure and test the verification/reset email templates and sender. Copy the Web app’s public `apiKey`; this is separate from the existing Jev/Gemini credentials.
4. Leave Firestore creation to the script, or create a **native `(default)` database in the exact same selected region**, with production/locked rules. The script refuses an incompatible existing location or database type. It updates the default database’s rules, TTL, PITR and backup settings; use a dedicated project.

## Generate and inspect the offline plan

From `neurasign_server_dashboard/`:

```bash
python3 scripts/deploy_gcloud.py \
  --project NEW_PROJECT_ID \
  --account NEW_ACCOUNT_EMAIL \
  --firebase-api-key PUBLIC_FIREBASE_WEB_API_KEY \
  --region europe-west1 \
  --tag pilot-001
```

Review `var/deploy/service.json` and `var/deploy/cloudbuild.json`. The public Firebase web key appears in runtime configuration intentionally; no private provider or service-account key belongs there. Confirm the account, project, region and resource settings. To inspect the upload set locally, use `gcloud meta list-files-for-upload` from this directory; it does not require a cloud request. `.gcloudignore` must continue to exclude credentials, recordings and local state.

## Build and deploy

When the configuration is ready, run the same command with **`--apply`**. That flag creates or updates billable resources, builds/pushes both images, deploys the service, permits access to the login page and registers the resulting service domain with Firebase Auth. It applies the deny-all Firestore rules to the project’s default database. It never uploads the local `.env` or emulator data.

The script preflights email/password Auth and checks that the public web key belongs to the target project. Initial setup requires a key usable from the deploy machine; an HTTP-referrer-only restriction can block that preflight. Scope the key to the required Firebase Authentication APIs, and validate any tighter restrictions with both browser and future native clients.

The final read-only smoke check verifies `/`, `/api/v1/config`, rejected anonymous data access, and disabled demo routes. It can also be run independently:

```bash
python3 scripts/check_deployment.py https://YOUR_SERVICE_URL
```

The bootstrap checks existing resources before creation and can be rerun after a failed provisioning/build step. Each run creates a new ruleset and image tag; reuse a previous reviewed tag only intentionally. It is a small deployment script, not a Terraform state manager. It does not delete infrastructure on failure, schedule cleanup of old build artifacts or automatically roll back a revision.

## Acceptance before company use

Use two verified accounts and one separate-company account on the actual HTTPS deployment. Create a workspace and invitation, verify that only its intended email can redeem it, enable the employee’s sharing, authorize a **Demo recording** device, and send timestamped test windows through `/api/v1/readings`. Confirm the manager’s graph updates, the employee cannot read peers, and the other company receives 403. Check stale data, retry deduplication, pausing, deletion, device revocation and persistence across revisions. Local smoke scripts deliberately refuse a cloud target; repeat this acceptance with dedicated cloud test identities.

Test real verification/password-reset email delivery, revoked sessions and Firebase password policy. Verify direct client Firestore requests are denied. Confirm backup schedules/TTL policies have become active, test a restore into an isolated database, and reapply deletion requests after restoring. Set billing budgets/alerts and Cloud Monitoring alerts for API 5xx, latency and Firestore failures. Cloud Run/Cloud Build logs are available; the application does not log reading payloads, passwords or credentials. Audit events cover access-changing actions, not every data read.

Polling, Auth checks and Firestore reads create ongoing usage charges. Measure the intended team size and manager count before expanding beyond the 100-member pilot cap. Configure operational ownership, access/retention requirements and employee onboarding with the actual company. The current build has no SSO/MFA enrollment UI, configurable teams within a company, full historical explorer, owner-transfer workflow or complete account/company erasure workflow.

The mobile companion is still unimplemented. A device credential and successful HTTP upload establish the server contract; they do not establish Bluetooth range, background delivery, offline queue behavior or compatibility with WHOOP or any other wearable. Validate those separately on physical devices before describing a wearable as supported.

## Operations and rollback

Save the Cloud Run revision and image tag after acceptance. Use Cloud Run’s Revisions view to route traffic to the previous accepted revision if needed; keep the same Firestore schema compatible. A code rollback does not restore deleted data. Do not point rollback revisions at emulators or SQLite. Stop the local development stack with `docker compose down`; this is unrelated to the cloud service. Deleting the cloud database requires explicitly disabling its deletion protection.

The design follows [Cloud Run’s container and startup-order configuration](https://docs.cloud.google.com/run/docs/configuring/services/containers), [Firebase server token verification](https://firebase.google.com/docs/auth/admin/verify-id-tokens), [Auth emulator boundaries](https://firebase.google.com/docs/emulator-suite/connect_auth), and [Firebase Rules deployment](https://firebase.google.com/docs/rules/manage-deploy).
