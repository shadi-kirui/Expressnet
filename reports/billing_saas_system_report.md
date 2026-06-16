# Billing SaaS — Admin & Tenant Gap Analysis + Engineering Prompt

---

## Part 1: Gap Analysis

### 1.1 Admin Dashboard (`AdminDashboard.jsx`)

**What exists:**
- 4 static stat cards: total tenants, customers, payments today, system health.
- Single API call to `/admin/tenants/stats/summary`.

**Gaps identified:**
- No revenue trend chart (daily/weekly/monthly MRR).
- No subscription renewal calendar — no view of which tenants expire soon.
- "System Health" is hardcoded to `"healthy"` on the backend — no real checks (DB, Firebase, MikroTik reachability).
- No platform-level payment breakdown (pending vs paid vs failed across all tenants).
- No quick-action shortcuts (e.g. activate a pending tenant from the dashboard).
- No alerts/notifications panel for overdue tenant subscriptions.

---

### 1.2 Admin Tenants Page (`AdminTenants.jsx`)

**What exists:**
- Table with CRUD for tenants (create, edit, suspend/activate).
- Modal-based form covering business info, MikroTik, and Paystack fields.
- Four summary stat cards (total, active, pending, suspended).

**Gaps identified:**
- **No subscription/billing plan field.** Tenants have no `plan` (e.g. Basic / Pro / Enterprise) and no `subscription_expires_at` date. There is no concept of a monthly recurring charge for the tenant using the platform — every tenant is effectively free forever once created.
- **No payment history per tenant.** The admin has no way to see whether Tenant X has paid their monthly platform fee, how much they owe, or when they last paid.
- **No subscription expiry enforcement.** There is no job or check to auto-suspend tenants whose platform subscription has lapsed.
- **No renewal / invoice actions.** No "Send invoice", "Mark as paid", "Extend subscription" buttons.
- **No search/filter on the tenants table.** With 100+ tenants the table becomes unusable.
- **No pagination.** The entire tenant list is fetched and rendered in one call.
- **No bulk actions.** No way to suspend or message multiple tenants at once.
- **No onboarding status indicator.** No field showing whether MikroTik connection was tested, or whether the tenant has at least one customer/package set up.
- **No tenant health badges** — e.g. "MikroTik unreachable", "No customers yet", "Payment overdue".
- **Suspend uses DELETE endpoint** (`adminApi.delete`), which is semantically incorrect — suspension should be a PATCH to `status: suspended`, not deletion.

---

### 1.3 Tenant Detail Page (`AdminTenantDetail.jsx`)

**What exists:**
- Editable form for business/MikroTik/Paystack fields.
- Three tab-based sub-tables: customers, payments, packages.

**Gaps identified:**
- **No subscription/billing tab.** No place for the admin to record that this tenant paid KES X on date Y for plan Z.
- **No expiry date field** visible or editable on the detail page.
- **No revenue summary for this tenant** (total lifetime payments collected through the platform).
- **No MikroTik connection test button** — admin cannot verify credentials inline.
- **Customers tab has no expiry, no status action buttons** — admin can see customers but cannot act on them.
- **Payments tab missing date, provider, channel columns.**
- **No ticket/support history tab.**
- **No ability to impersonate/preview the tenant's portal.**

---

### 1.4 Admin Backend Views (`views.py`)

**What exists:**
- `admin_stats` — basic aggregation (total tenants, total customers, payments today).
- `admin_tenants` — list, create, patch, delete (suspend) tenants.
- `admin_audit_logs` — last 100 log entries.
- `admin_site` — site settings CRUD.
- `admin_users` — cross-tenant customer list + enable/disable actions.

**Gaps identified:**
- **No `TenantSubscription` model or endpoint.** There is no data model representing "Tenant X is on plan Y, pays KES Z/month, expires on date D."
- **No `/admin/billing` or `/admin/subscriptions` endpoint.** The admin cannot manage platform-level billing at all via the API.
- **`admin_stats` is N+1 query heavy** — it loops through every tenant and every payment in Firebase with no aggregation, will degrade badly at scale.
- **`admin_stats` `systemHealth` always returns `"healthy"`** — no real probe.
- **No `/admin/tenants/{id}/subscription` endpoint** to read or write subscription data.
- **No auto-expiry job** (Celery task or cron) to sweep tenants past their `subscription_expires_at` and set `status = suspended`.
- **No `/admin/tenants/{id}/mikrotik/test` endpoint** to test MikroTik connectivity on demand.
- **Rate limiting is in-process memory (`defaultdict`)** — this works for a single dyno but fails across multiple workers/containers. Must be moved to Redis or database-backed storage.
- **No load balancing configuration.** The `Procfile` runs a single `gunicorn` worker. No `WEB_CONCURRENCY`, no connection pooling, no Redis, no task queue.
- **SQLite in production** — `db.sqlite3` is the only database. SQLite cannot handle concurrent writes at scale and is not suitable for multi-tenant production traffic.
- **Firebase Realtime Database used as primary data store for tenant data**, while Django ORM models exist but are underused. This dual-store pattern creates sync complexity and makes queries slow (no indexed queries possible on Firebase Realtime DB for analytics).

---

### 1.5 Admin Layout & Navigation (`AdminLayout.jsx`)

**What exists:**
- 5-link sidebar: Dashboard, Tenants, Users, Site, Audit Log.

**Gaps identified:**
- **No "Billing / Subscriptions" nav link.**
- **No "Payments" nav link** for platform-level payment management.
- **No "System Health" or "Infrastructure" link.**
- **No notification badge** on any link (e.g. "3 tenants expiring this week").
- **No admin role differentiation** — all admins see everything; no read-only admin role.

---

### 1.6 Scalability & Infrastructure

| Area | Current state | Gap |
|---|---|---|
| **Database** | SQLite (file) | Must migrate to PostgreSQL; add `dj-database-url` |
| **Rate limiting** | In-process dict | Must use Redis (`django-redis`) for shared state across workers |
| **Task queue** | None | Add Celery + Redis for subscription expiry jobs, SMS, webhook retries |
| **Load balancing** | Single gunicorn process | Set `WEB_CONCURRENCY`, add `--worker-class gevent`, add nginx proxy or use Heroku/Railway horizontal scaling |
| **Caching** | None | Cache tenant lookups, stats aggregates with Redis |
| **Concurrent writes** | SQLite can't handle them | Move to PostgreSQL + connection pooling (pgBouncer or `CONN_MAX_AGE`) |
| **Firebase as primary store** | Creates N+1 HTTP reads | Move tenant/customer/payment data to PostgreSQL; use Firebase only for real-time push if needed |
| **Static files** | Served by Django | Move to whitenoise or CDN |
| **Health endpoint** | None | Add `/api/health/` that checks DB, Redis, Firebase connectivity |

---

## Part 2: Engineering Prompt

Use this prompt directly in a new conversation (or with Claude Code) to implement all the above gaps.

---

```
You are a senior full-stack engineer working on a multi-tenant ISP billing SaaS built with:
- Backend: Django 6, Django REST Framework, Firebase Realtime DB (currently used as primary data store), SQLite (dev), PyJWT auth
- Frontend: React + Vite + Tailwind CSS, React Router, lucide-react icons, react-hot-toast
- Target hosting: Heroku / Railway (12-factor app)

The project already has a working admin area at /admin/* with these pages:
  AdminDashboard, AdminTenants, AdminTenantDetail, AdminUsers, AdminSiteSettings, AdminAuditLog

Your task is to close ALL gaps listed below. Implement each section completely — do not stub or leave TODOs.

─────────────────────────────────────────────
SECTION A — DATABASE & INFRASTRUCTURE UPGRADES
─────────────────────────────────────────────

A1. Replace SQLite with PostgreSQL.
    - Add `psycopg2-binary` and `dj-database-url` to requirements.txt.
    - Update settings.py: read DATABASE_URL from env; fall back to SQLite for local dev only.
    - Add CONN_MAX_AGE=60 for connection pooling.

A2. Move rate limiting to Redis.
    - Add `django-redis` and `redis` to requirements.txt.
    - Replace the in-process `defaultdict` in SimpleRateLimitMiddleware with Redis INCR + EXPIRE commands.
    - Read REDIS_URL from env; fall back to local redis://localhost:6379/0.

A3. Add Celery for async tasks.
    - Add `celery` and `celery[redis]` to requirements.txt.
    - Create billing_saas_django/celery.py with standard Celery app init.
    - Update __init__.py to import the celery app.
    - Create billing_api/tasks.py with two tasks:
        * expire_tenant_subscriptions(): query TenantSubscription where expires_at < now and tenant.status != 'suspended'; for each, set tenant.status = 'suspended' and log to AdminAuditLog.
        * send_subscription_reminder_sms(): 3 days before expiry, send SMS via existing notification provider.
    - Add CELERY_BEAT_SCHEDULE in settings.py to run expire_tenant_subscriptions every hour.
    - Update Procfile to add: worker: celery -A billing_saas_django worker -l info and beat: celery -A billing_saas_django beat -l info.

A4. Upgrade gunicorn for concurrency.
    - Update Procfile web line to: web: gunicorn billing_saas_django.wsgi --workers 4 --worker-class gevent --bind 0.0.0.0:$PORT --timeout 30
    - Add gevent to requirements.txt.

A5. Add a real health check endpoint.
    - Add GET /api/health/ that checks: DB (simple SELECT 1), Redis (PING), Firebase (ref('/').get() with 2s timeout).
    - Returns JSON { db: "ok"|"error", redis: "ok"|"error", firebase: "ok"|"error", status: "healthy"|"degraded" }.
    - Add to urls.py. No auth required.

A6. Add django-whitenoise for static files.
    - Add whitenoise to requirements.txt and MIDDLEWARE.

─────────────────────────────────────────────
SECTION B — NEW DATA MODEL: TenantSubscription
─────────────────────────────────────────────

B1. Add TenantSubscription model to billing_api/models.py:

    class SubscriptionPlan(models.TextChoices):
        BASIC = "basic", "Basic"       # e.g. KES 1,500/month
        PRO = "pro", "Pro"             # e.g. KES 3,500/month
        ENTERPRISE = "enterprise", "Enterprise"  # e.g. KES 8,000/month

    class TenantSubscription(models.Model):
        tenant = models.OneToOneField(Tenant, related_name="subscription", on_delete=models.CASCADE)
        plan = models.CharField(max_length=50, choices=SubscriptionPlan.choices, default=SubscriptionPlan.BASIC)
        amount = models.DecimalField(max_digits=10, decimal_places=2, default=1500)
        currency = models.CharField(max_length=10, default="KES")
        billing_cycle_days = models.IntegerField(default=30)
        started_at = models.DateTimeField(null=True, blank=True)
        expires_at = models.DateTimeField(null=True, blank=True)
        last_paid_at = models.DateTimeField(null=True, blank=True)
        grace_period_days = models.IntegerField(default=3)
        auto_renew = models.BooleanField(default=True)
        notes = models.TextField(blank=True, default="")
        created_at = models.DateTimeField(auto_now_add=True)
        updated_at = models.DateTimeField(auto_now=True)

        def is_expired(self):
            return self.expires_at and timezone.now() > self.expires_at

        def days_until_expiry(self):
            if not self.expires_at:
                return None
            delta = self.expires_at - timezone.now()
            return delta.days

    class SubscriptionPayment(models.Model):
        """Records each monthly platform fee payment made by a tenant."""
        subscription = models.ForeignKey(TenantSubscription, related_name="payments", on_delete=models.CASCADE)
        amount = models.DecimalField(max_digits=10, decimal_places=2)
        currency = models.CharField(max_length=10, default="KES")
        paid_at = models.DateTimeField(default=timezone.now)
        method = models.CharField(max_length=80, blank=True, default="manual")  # manual, mpesa, paystack
        reference = models.CharField(max_length=255, blank=True, default="")
        period_start = models.DateTimeField(null=True, blank=True)
        period_end = models.DateTimeField(null=True, blank=True)
        recorded_by = models.CharField(max_length=255, blank=True, default="")  # admin email
        notes = models.TextField(blank=True, default="")
        created_at = models.DateTimeField(auto_now_add=True)

B2. Create and run a migration for TenantSubscription and SubscriptionPayment.
B3. When a new Tenant is created via admin_tenants POST, auto-create a TenantSubscription with:
    - plan = BASIC, expires_at = now + 30 days, started_at = now.

─────────────────────────────────────────────
SECTION C — NEW BACKEND ENDPOINTS
─────────────────────────────────────────────

C1. Add to billing_api/urls.py:
    path("admin/subscriptions", views.admin_subscriptions),
    path("admin/subscriptions/<int:subscription_id>", views.admin_subscriptions),
    path("admin/subscriptions/<int:subscription_id>/payments", views.admin_subscription_payments),
    path("admin/tenants/<str:tenant_id>/subscription", views.admin_tenant_subscription),
    path("admin/tenants/<str:tenant_id>/mikrotik/test", views.admin_mikrotik_test),
    path("admin/system/stats", views.admin_system_stats),  # replaces admin_stats

C2. Implement admin_tenant_subscription(request, tenant_id):
    GET  → return TenantSubscription for the tenant, include all SubscriptionPayments, days_until_expiry.
    PATCH → update plan, amount, expires_at, notes, auto_renew.
    POST → record a new SubscriptionPayment: { amount, method, reference, notes }.
           After recording payment, update subscription.last_paid_at = now, expires_at = max(current expires_at, now) + billing_cycle_days.

C3. Implement admin_subscriptions(request, subscription_id=None):
    GET (no id) → paginated list of all TenantSubscriptions with tenant name, plan, expires_at, days_until_expiry, last_paid_at.
                  Accept query params: ?status=expired|expiring_soon|active, ?plan=basic|pro|enterprise, ?search=.
    GET (with id) → detail.
    PATCH (with id) → update plan, amount, expires_at, auto_renew, notes.

C4. Implement admin_subscription_payments(request, subscription_id):
    GET → list all SubscriptionPayments for this subscription, newest first.
    POST → record a payment (same logic as C2 POST).

C5. Implement admin_mikrotik_test(request, tenant_id):
    POST → read tenant MikroTik credentials, attempt librouteros connection with 5s timeout.
    Return { success: true/false, error: "..." or null, routers_count: N }.

C6. Rewrite admin_system_stats (rename from admin_stats) to use ORM aggregations:
    from django.db.models import Count, Sum, Q
    Return:
    - totalTenants, activeTenants, suspendedTenants, pendingTenants
    - totalCustomers (Customer.objects.count())
    - paymentsToday (Payment.objects.filter(paid_at__date=today).aggregate(Sum('amount')))
    - monthlyRevenue (SubscriptionPayment.objects.filter(paid_at__month=current_month).aggregate(Sum('amount')))
    - expiringThisWeek (TenantSubscription.objects.filter(expires_at__lte=now+7days).count())
    - expiredCount (TenantSubscription.objects.filter(expires_at__lt=now).count())
    - systemHealth: call the same checks as /api/health/

─────────────────────────────────────────────
SECTION D — ADMIN DASHBOARD UPGRADE
─────────────────────────────────────────────

Replace AdminDashboard.jsx completely. The new dashboard must include:

D1. Top stat bar (6 cards, 3 per row on mobile, 6 on desktop):
    - Total Tenants (active count / total)
    - Tenants Expiring This Week (warning color if > 0)
    - Expired Tenants (danger color if > 0)
    - Total Customers (across all tenants)
    - Platform Revenue This Month (KES amount from SubscriptionPayments)
    - System Health (green "Healthy" / red "Degraded" — from /api/health/)

D2. Revenue trend chart (last 30 days):
    - Bar chart using recharts BarChart.
    - X axis: dates, Y axis: KES amount.
    - Data: group SubscriptionPayments by paid_at date.
    - Fetch from a new endpoint GET /admin/subscriptions/revenue-chart?days=30.

D3. Expiring tenants alert panel:
    - List tenants where days_until_expiry <= 7, sorted ascending.
    - Each row: tenant name, plan badge, expires_at, days left (red if <= 3).
    - "Send reminder" button per row (calls POST /admin/tenants/{id}/subscription/remind — stub OK).
    - "Extend 30 days" button per row (calls PATCH /admin/tenants/{id}/subscription with new expires_at).

D4. Quick stats table for top 5 tenants by customer count.

D5. Auto-refresh every 60 seconds using setInterval + useEffect cleanup.

─────────────────────────────────────────────
SECTION E — ADMIN TENANTS PAGE UPGRADE
─────────────────────────────────────────────

Upgrade AdminTenants.jsx:

E1. Add search input (filters by business_name, owner_name, email client-side).

E2. Add status filter tabs: All | Active | Pending | Suspended | Expiring Soon.

E3. Add a "Subscription" column to the table:
    - Show plan badge (Basic/Pro/Enterprise) + expiry date.
    - If expires within 7 days: amber badge.
    - If expired: red badge.
    - Fetch subscription data alongside tenant list (include in the /admin/tenants response).

E4. Fix the "Suspend" action to use PATCH { status: "suspended" } not DELETE.

E5. Add an "Extend" quick action button per row: opens a small modal to set a new expires_at and optionally record a payment.

E6. Pagination: show 20 tenants per page with Prev/Next controls.

E7. Add "Plan" selector to the Create/Edit tenant modal (Basic / Pro / Enterprise) which sets TenantSubscription.plan on create.

E8. Add onboarding checklist column showing icons for: ✓ MikroTik set, ✓ Has customers, ✓ Has packages (derive from data already in the response).

─────────────────────────────────────────────
SECTION F — TENANT DETAIL PAGE UPGRADE
─────────────────────────────────────────────

Upgrade AdminTenantDetail.jsx:

F1. Add a "Subscription" tab alongside customers/payments/packages.
    The Subscription tab shows:
    - Current plan, amount/month, expires_at, days_until_expiry, auto_renew toggle.
    - "Change Plan" dropdown (Basic/Pro/Enterprise) + Save.
    - "Record Payment" button → inline form: amount (pre-filled), method (manual/mpesa/paystack), reference, notes → POST to subscription payments endpoint.
    - Payment history table: date, amount, method, reference, period_start–period_end, recorded_by.

F2. Add a "Test MikroTik" button in the MikroTik section of the edit form.
    On click: POST /admin/tenants/{id}/mikrotik/test, show result inline (green "Connected — 3 routers" or red error message).

F3. In the Customers tab, add expiry_date column and a per-row "Disable" button.

F4. In the Payments tab, add: date, provider, channel, paid_at columns.

F5. Add a top info strip with 3 quick stats: total customers, total payments (KES), subscription status badge.

─────────────────────────────────────────────
SECTION G — NEW ADMIN SUBSCRIPTIONS PAGE
─────────────────────────────────────────────

Create frontend/src/pages/admin/AdminSubscriptions.jsx:

G1. Table of all tenant subscriptions:
    Columns: Business, Plan (badge), Amount/mo, Expires, Days Left, Last Paid, Status, Actions.

G2. Filters: ?status=all|active|expiring_soon|expired and ?plan=basic|pro|enterprise.

G3. Bulk action: select multiple → "Extend 30 days" for all selected.

G4. "Record Payment" modal per row: amount (pre-filled from plan), method, reference, notes.

G5. "Export CSV" button: downloads all subscription data as CSV.

G6. Summary strip at top: Total Active, Expiring This Week, Expired, Monthly MRR.

G7. Add this page to AdminLayout.jsx nav: { to: '/admin/subscriptions', label: 'Subscriptions', icon: CreditCard }.
    Also add a route in App.jsx (or wherever admin routes are defined).

─────────────────────────────────────────────
SECTION H — ADMIN LAYOUT & NAVIGATION UPGRADE
─────────────────────────────────────────────

Update AdminLayout.jsx:

H1. Add nav links:
    { to: '/admin/subscriptions', label: 'Subscriptions', icon: CreditCard },
    { to: '/admin/system', label: 'System', icon: Server },

H2. Add a notification badge on the "Subscriptions" link showing the count of tenants expiring in <= 7 days. Fetch count from stats on mount.

H3. Show admin name and role in the header; add a "Change password" link.

H4. Add a simple system status indicator (green dot / red dot) in the header based on /api/health/.

─────────────────────────────────────────────
SECTION I — NEW ADMIN SYSTEM PAGE
─────────────────────────────────────────────

Create frontend/src/pages/admin/AdminSystem.jsx:

I1. Health panel: DB, Redis, Firebase status (colored badges, auto-refresh every 30s).

I2. Load info: number of active tenants, total API requests today (if tracked), gunicorn worker count from env.

I3. Rate limit configuration display (current limits from RULES dict).

I4. Database info: provider (postgres/sqlite), migration status (list of unapplied migrations via /api/admin/system/migrations — add this GET endpoint that runs django.core.management.call_command('showmigrations')).

I5. Add route and nav link as per H1.

─────────────────────────────────────────────
GENERAL REQUIREMENTS
─────────────────────────────────────────────

- All new API endpoints must use @admin_required decorator.
- All admin mutations must call write_audit_log().
- All new frontend pages must match the existing design system: bg-[#1a1a2e] sidebar, bg-[#e94560] primary buttons, Tailwind utility classes, lucide-react icons, react-hot-toast for notifications.
- All tables must handle empty state and loading state.
- Error responses must follow the existing { error: "message" } shape.
- Do not break any existing tenant-facing endpoints.
- Write migrations for all new models.
- Add the new Celery tasks file and update the Procfile.
- After completing all sections, provide a summary of every file changed or created.
```

---

## Part 3: Priority Order

If implementing in sprints, do it in this order:

1. **Sprint 1 (Foundation):** A1 (PostgreSQL), A2 (Redis rate limiting), B1–B3 (TenantSubscription model + migration), C6 (fix admin_stats), E4 (fix DELETE→PATCH for suspend).
2. **Sprint 2 (Core Billing):** C2–C4 (subscription endpoints), G (Subscriptions page), D (Dashboard upgrade), F1 (Subscription tab in tenant detail).
3. **Sprint 3 (Operations):** A3 (Celery expiry jobs), C5 (MikroTik test), F2 (test button), E1–E8 (tenants page upgrades), H (nav upgrades).
4. **Sprint 4 (Scalability):** A4 (gunicorn concurrency), A5 (health endpoint), A6 (whitenoise), I (System page), E5 (bulk actions), G3 (bulk extend).