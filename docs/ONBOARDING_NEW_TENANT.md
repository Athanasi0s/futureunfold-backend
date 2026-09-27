# Onboarding a New Tenant

**End-to-end runbook** for standing up a new FestApp tenant. Target: ~1 hour of
active work, plus 1–3 days of store review waits outside this document.

Companion doc: [`TENANT_DEPENDENCIES.md`](./TENANT_DEPENDENCIES.md) — canonical
inventory of every secret, env var, asset, and third-party registration
referenced here.

---

## Step 0 — Prerequisites (collect from customer)

Before starting, gather:

- [ ] **Slug** — lowercase, alphanumeric, letter-first. Used in
      `festapp-api-<slug>` and `com.festapp.<slug>`.
- [ ] **Display name** — shown in store + app header + wallet passes
      (populates `EVENT_NAME`).
- [ ] **Admin email** — seeds the initial admin account
      (populates `ADMIN_EMAILS`).
- [ ] **Branding assets** — 1024×1024 icon, adaptive-icon, splash-icon,
      favicon. If missing, ship with Panathenea placeholders and swap before
      store submission — icons/splash bake at build time and can't be OTA'd.
- [ ] **Stripe keys** (if ticketing enabled) — `STRIPE_SECRET_KEY` +
      customer's webhook signing secret.
- [ ] **Seed scope decision** — generic defaults only at launch, or starter
      seeds for venues / groups / sessions?

Local prerequisites:

- [ ] `flyctl auth whoami` returns your Fly.io user
- [ ] `openssl` on PATH
- [ ] Working copy of both repos checked out side-by-side
- [ ] `gcloud` CLI (only if you plan to script OAuth client creation —
      otherwise do it by hand in the console)

---

## Step 1 — Backend provisioning

From `festapp-backend/` repo root:

```bash
./scripts/provision_tenant.sh <slug> "<Event Name>" <admin_email>
```

The script creates the Fly app + Postgres + volume, sets `TENANT_KEY` /
`JWT_SECRET` / `EVENT_NAME` / `ADMIN_EMAILS` secrets, generates
`fly.<slug>.toml`, scaffolds `app/seed/tenants/<slug>/`, appends `<slug>` to
`tenants.yml`, runs the first deploy, and invokes `app.seed.bootstrap` once to
populate generic defaults.

> ⚠️ **Run in a real interactive terminal — not in CI, not via a tool that
> can't answer prompts.** The script has two interactive gates:
>
> 1. **Its own confirm prompt** (`Continue? [y/N]`) — answer `y`.
> 2. **`flyctl postgres create`** prompts twice with no non-interactive flag
>    available: (a) a "Use Managed Postgres instead?" deprecation warning —
>    answer **No** to stay on unmanaged like the other tenants, and (b) a
>    VM-size picker — choose **`shared-cpu-1x:256MB`** to match
>    `techsaloniki` / `reworks` (cheapest tier; bump later if needed).
>
> If the script bails mid-run at step `[3/9]`, the Fly app and
> `fly.<slug>.toml` will already exist. Either destroy and re-run, or pick
> up manually from `flyctl postgres create` onward (see comment block at the
> top of the script).

**Admin emails:** the script only accepts one admin email and validates it
as a single address, but `ADMIN_EMAILS` is comma-separated. If you have
multiple admins, pass one to the script and patch the secret afterwards:

```bash
flyctl secrets set -a festapp-api-<slug> ADMIN_EMAILS="a@x.com,b@x.com"
```

**After it finishes:**

```bash
./scripts/verify_tenant.sh <slug>                       # /health + /config both 200
git add fly.<slug>.toml app/seed/tenants/<slug>/ tenants.yml
git commit -m "chore: provision tenant <slug>"
git push origin main
```

The CI matrix now includes the new tenant in every future deploy.

---

## Step 2 — Google Cloud OAuth clients (4 per tenant)

In the shared GCP project → APIs & Services → Credentials:

1. **Web (backend — Google Calendar integration)**
   - Type: Web application
   - Authorized redirect URI: `https://festapp-api-<slug>.fly.dev/auth/google/redirect`
   - Copy **Client ID** → will become `GOOGLE_CLIENT_ID`
   - Copy **Client Secret** → will become `GOOGLE_CLIENT_SECRET`

2. **Web (mobile — `EXPO_PUBLIC_GOOGLE_CLIENT_ID`)**
   - Type: Web application
   - No redirect URI required; used for `expo-auth-session` Web flow
   - Copy **Client ID** only

3. **Android**
   - Type: Android
   - Package name: `com.festapp.<slug>`
   - SHA-1: **known only after first Android EAS build** — create this
     client *after* Step 7 (run `eas credentials` → select Android →
     view SHA-1)
   - Copy **Client ID**

4. **iOS**
   - Type: iOS
   - Bundle ID: `com.festapp.<slug>`
   - Copy **Client ID**

Set the backend OAuth secrets:

```bash
flyctl secrets set -a festapp-api-<slug> \
  GOOGLE_CLIENT_ID=<from step 2.1> \
  GOOGLE_CLIENT_SECRET=<from step 2.1> \
  GOOGLE_TOKEN_ENCRYPTION_KEY=$(openssl rand -hex 32)
```

The mobile (`EXPO_PUBLIC_*`) clients are consumed by EAS builds; set them in
Step 8.

**Skip this step** if the customer does not need Google Calendar integration.

---

## Step 3 — Firebase project (push notifications)

Required only if the customer needs push notifications.

1. Firebase console → Add project → name it after the tenant
2. Inside the project, **Add app** twice:
   - iOS — bundle ID `com.festapp.<slug>`. Download `GoogleService-Info.plist`.
   - Android — package `com.festapp.<slug>`. Download `google-services.json`.
3. Drop both files into `festapp-mobile/assets/tenants/<slug>/`

These files are read at build time by the mobile Expo config.

---

## Step 4 — Google Wallet classes

From `festapp-backend/` with the tenant's env loaded (local `.env` with
`TENANT_KEY=<slug>` + the wallet-related secrets, OR run via
`flyctl ssh console`):

```bash
# Option A — local with .env pointing at tenant-specific values
py -m scripts.register_wallet_classes --kind both

# Option B — on the deployed app
flyctl ssh console -a festapp-api-<slug> -C "py -m scripts.register_wallet_classes --kind both"
```

The script reads `EVENT_NAME` + `GOOGLE_WALLET_*` and creates (or confirms)
`<issuer>.<slug>_badge` + `<issuer>.<slug>_ticket`. Idempotent; safe to re-run.

Set the per-tenant wallet suffixes first (before running the script):

```bash
flyctl secrets set -a festapp-api-<slug> \
  GOOGLE_WALLET_CLASS_SUFFIX=<slug>_badge \
  GOOGLE_WALLET_TICKET_CLASS_SUFFIX=<slug>_ticket \
  GOOGLE_WALLET_ORIGIN=https://festapp-api-<slug>.fly.dev
```

The shared `GOOGLE_WALLET_ISSUER_ID` + `GOOGLE_WALLET_SA_JSON_B64` also need to
be copied onto the new app:

```bash
# Copy shared values from Panathenea
ISSUER=$(flyctl secrets list -a festapp-api-panathenea | grep GOOGLE_WALLET_ISSUER_ID | awk '{print $2}')
# GOOGLE_WALLET_SA_JSON_B64 cannot be read back — fetch from your password manager
flyctl secrets set -a festapp-api-<slug> \
  GOOGLE_WALLET_ISSUER_ID=$ISSUER \
  GOOGLE_WALLET_SA_JSON_B64=<value from secrets vault>
```

**Skip this step** if the customer does not need Google Wallet passes.

---

## Step 5 — Stripe webhook

Required only if the customer is selling tickets.

1. Customer creates a webhook endpoint in their Stripe dashboard:
   - URL: `https://festapp-api-<slug>.fly.dev/webhooks/stripe`
   - Events: `checkout.session.completed`, `charge.refunded`,
     `payment_intent.succeeded` (confirm with current backend route
     expectations before finalising)
   - Customer copies the **signing secret** and sends it to you
2. Set the backend secrets:
   ```bash
   flyctl secrets set -a festapp-api-<slug> \
     STRIPE_SECRET_KEY=<from customer> \
     STRIPE_WEBHOOK_SECRET=<from customer>
   ```
3. Optionally set `SENDGRID_FROM_EMAIL=<tenant-specific>` if the tenant wants
   their own from-address (domain must be verified in Sendgrid).

---

## Step 6 — Mobile config

In `festapp-mobile/app.config.ts`, add a new tenant entry inside the `tenants`
map. Use the existing `panathenea` / `techsaloniki` entries as reference. At
minimum:

```ts
<slug>: {
  name: "<Display Name>",
  slug: "<slug>",
  scheme: "<slug>mobile",                        // deep link scheme
  ios: {
    bundleIdentifier: "com.festapp.<slug>",
    buildNumber: "1",
  },
  android: {
    package: "com.festapp.<slug>",
    versionCode: 1,
  },
  apiBaseUrl: "https://festapp-api-<slug>.fly.dev",
  tenantKey: "<slug>",
  easProjectId: "<UUID — see below>",
  easChannel: "<slug>-production",
  assetsPath: "./assets/tenants/<slug>",
}
```

**EAS project ID:** Expo enforces a 1:1 slug/projectId mapping — you **must**
create a new project manually:

1. Visit [expo.dev/accounts/feststats/projects](https://expo.dev/accounts/feststats/projects)
2. **Create a new project** with slug `<slug>`
3. Copy the UUID and paste it into the `easProjectId` field above

In `festapp-mobile/eas.json`, add three profiles per tenant:
`<slug>-development`, `<slug>-preview`, `<slug>-production`. Mirror the
Panathenea block; change `TENANT` + `EXPO_PUBLIC_API_BASE_URL` + `channel`.

Drop branding + Firebase assets into
`festapp-mobile/assets/tenants/<slug>/` (6 files — see
[`TENANT_DEPENDENCIES.md`](./TENANT_DEPENDENCIES.md#mobile-assets)).

Commit:

```bash
git add app.config.ts eas.json assets/tenants/<slug>/
git commit -m "feat(multitenancy): add <slug> tenant"
git push
```

Mobile-side runbook with copy-paste templates lives at
`festapp-mobile/docs/ADD_NEW_TENANT.md`.

---

## Step 7 — Apple App Store Connect + Google Play Console

Create app records in both stores using the tenant's bundleId / package and
display name. Fill in the minimum metadata needed to reach internal testing
tracks; marketing copy / screenshots can wait.

- **App Store Connect** → My Apps → + → New App → Bundle ID `com.festapp.<slug>`
- **Google Play Console** → Create app → Package `com.festapp.<slug>`

---

## Step 8 — First build + internal test

```bash
cd festapp-mobile

# First Android build — accept "Generate a new Android keystore?" prompt.
# Immediately after it succeeds, back up the keystore:
eas build --profile <slug>-development --platform android
eas credentials  # select Android → download keystore to your password manager

# First iOS dev-client build
eas build --profile <slug>-development --platform ios
```

**After the first Android build:**
- Go back to Step 2.3 and create the Android OAuth client now that the keystore
  SHA-1 exists (`eas credentials` → Android → View SHA-1).

Set EAS **dashboard** env vars for the new project (at expo.dev; these are
separate from the `env` block in `eas.json`). At minimum for internal testing:
- `APPLE_API_ISSUER_ID` / `APPLE_API_KEY_ID` / `APPLE_API_KEY_PATH` (copy from
  Panathenea — shared)
- `EXPO_PUBLIC_API_BASE_URL` = `https://festapp-api-<slug>.fly.dev`

If Google Calendar is enabled, also set the `EXPO_PUBLIC_GOOGLE_*` trio from
Step 2.

**Smoke-test on device** (see [`festapp-mobile/docs/ADD_NEW_TENANT.md`](../../festapp-mobile/docs/ADD_NEW_TENANT.md) for the
full checklist). Minimum: login, push token registration, map loads, QR scan,
admin-push end-to-end.

---

## Step 9 — Store submission

Only proceed after Step 8 smoke test is green on a real device.

```bash
eas build --profile <slug>-production --platform all
eas submit --profile <slug>-production --platform all
```

Expect ~15–30 min per platform for the build, plus 10–30 min for Apple
processing before TestFlight becomes available. Play Console internal testing
track is near-instant.

Store review cycles (submitting to public tracks) take 1–3 days and are
outside this runbook.

---

## Step 9.5 — In-app logo (`app_logo_url`)

The in-app login screen and home/schedule tab headers fall back to a generic
`account-balance` MaterialIcon (in the tenant's primary theme color) until
`/config.app_logo_url` is set. Without this step, **every tenant looks
visually identical** in the in-app chrome, regardless of branding assets
dropped in `assets/tenants/<slug>/` — those only drive the OS launcher icon
+ splash, not in-app chrome.

Set it once the backend is live and the first admin is promoted:

1. Promote the admin user (needed for Step 10 too):
   ```bash
   flyctl ssh console -a festapp-api-<slug> -C \
     "python -c 'from app.db.session import SessionLocal; from app.models.user import User; from app.core.enums import UserRole; db=SessionLocal(); u=db.query(User).filter(User.email==\"<admin@email>\").first(); u.role=UserRole.admin; db.commit()'"
   ```
2. In the mobile dev-client build, log in as that admin → drawer → AppConfig →
   upload a logo image (typically `assets/tenants/<slug>/icon.png`).
3. Restart the app — login screen + home/schedule headers should render the
   tenant logo.

> Note: `POST /upload` returns an absolute URL (the tenant's
> `PUBLIC_BASE_URL` prefixed onto the file path), so admin-UI uploads land
> in `app_logo_url` ready to render. If you see the generic fallback after
> upload, check that `/config` returns an `https://…` URL (not a relative
> `/uploads/…` path — that would mean a regression in the upload endpoint).

---

## Step 10 — Hand-off

- [ ] Send the customer's admin the `ADMIN_EMAILS`-listed email address +
      instructions to register via the dev-client build (or via TestFlight
      once available)
- [ ] Confirm the admin can log in and access the admin drawer
- [ ] Confirm `app_logo_url` is set (Step 9.5) so the login + headers
      render the tenant's brand instead of the generic fallback
- [ ] Share customer-facing admin docs (if any)

---

## Rollback — failed tenant teardown

If a tenant needs to be torn down (test tenant, aborted onboarding, customer
churn):

```bash
cd festapp-backend
./scripts/deprovision_tenant.sh <slug>       # destroys Fly app + Postgres
git add tenants.yml
git commit -am "chore: deprovision tenant <slug>"
git push
```

Then the manual clean-up the script can't do:

- [ ] `festapp-mobile/app.config.ts` — remove the `<slug>` entry
- [ ] `festapp-mobile/eas.json` — remove `<slug>-*` profiles
- [ ] `festapp-mobile/assets/tenants/<slug>/` — delete
- [ ] GCP OAuth clients — revoke the 4 tenant-specific clients
- [ ] Firebase project — delete (if dedicated; shared projects never)
- [ ] App Store Connect / Play Console app records — delete or leave as drafts
- [ ] Wallet classes — no delete API; leave them, they're harmless
- [ ] Customer's Stripe webhook — customer deletes from their side

---

## Timing

- **Active work:** ~45–60 min for an experienced operator (the first
  onboarding took several hours due to learning curve — see
  `.planning/MULTITENANCY_PLAN.md` Phase E retro)
- **Store review:** 1–3 business days (outside this runbook)
- **Wallet class approval:** minutes-to-hours for automatic approval under an
  already-approved issuer

---

## When to update this runbook

Update this doc **and** `TENANT_DEPENDENCIES.md` **and**
`scripts/provision_tenant.sh` whenever:

- A new env var is added to `app/core/config.py`
- A new third-party integration is added (e.g. analytics, new OAuth provider)
- The mobile config contract in `app.config.ts` changes
- A new manual platform registration becomes necessary

Drift between these three is the #1 failure mode for new-tenant onboarding.
