# Security: How Your App Could Be Compromised & What to Do

This document lists the main ways an attacker could target your CivicCare app and how to reduce the risk.

---

## 1. **Weak or default secret key (JWT forgery)**

**Risk:** In `app/core/config.py`, `SECRET_KEY` defaults to a development value. If you don’t set a strong secret in production, anyone who learns it can forge JWTs and log in as any user (including admin).

**Fix:**
- In production, set a long random secret via environment:
  ```bash
  export SECRET_KEY="your-64-plus-character-random-secret-from-openssl-rand-hex-64"
  ```
- Use a `.env` file (and add `.env` to `.gitignore`) so the key is never committed.

---

## 2. **CORS allows any origin with credentials**

**Risk:** In `main.py`, CORS is configured with `allow_origins=["*"]` and `allow_credentials=True`. Any website can send cookies/credentials to your API. An attacker could host a page that calls your API with a victim’s session.

**Fix:**
- Restrict origins to your real frontend(s), e.g.:
  ```python
  allow_origins=[
      "https://yourdomain.com",
      "http://localhost:3000",  # only for local dev
  ],
  ```
- Avoid `allow_origins=["*"]` when using `allow_credentials=True`.

---

## 3. **Admin dashboard and sensitive APIs are “open”**

**Risk:**
- `/admin` serves the admin UI with no server-side auth. Anyone can load the page.
- Many APIs are public: list grievances, list workers, list wards/zones, get grievance by ID. Data can be scraped or enumerated.

**Fix:**
- Put the admin app behind auth (e.g. reverse proxy with login, or serve it only on an internal URL).
- Consider requiring auth for admin routes and for list/detail endpoints that expose sensitive data (e.g. workers, full grievance lists). Keep truly public only what citizens need (e.g. submit grievance, view own data).

---

## 4. **No rate limiting (brute force & abuse)**

**Risk:** Login and token refresh have no rate limiting. Attackers can try many passwords (e.g. for phone 9999999999 or known user IDs) or abuse registration/API.

**Fix:**
- Add rate limiting (e.g. `slowapi` or a reverse proxy like Nginx) on:
  - `POST /api/v1/auth/login`
  - `POST /api/v1/auth/register`
  - `POST /api/v1/auth/refresh`
- Optionally limit by IP and/or by identifier (phone/user_id) per time window.

---

## 5. **Default admin account**

**Risk:** If `init_db` runs and no staff user exists, it creates an admin with a known phone (e.g. 9999999999) and a default password (e.g. admin123). If that account stays in place in production, it’s an easy target.

**Fix:**
- Use this only in development.
- In production: either don’t seed this user, or change the password immediately and use a strong, unique password.
- Prefer creating the first admin via a one-time script or manual DB update, then disable or remove the default seed.

---

## 6. **File upload content not validated**

**Risk:** Uploads check extension and size but not file content. A file named `image.jpg` could contain HTML/JS or other executable content. Depending on how it’s stored and served, that could lead to XSS or other issues when the “image” is opened or linked.

**Fix:**
- Validate content (e.g. magic bytes / image headers) and reject non-image files.
- Serve uploads with safe, explicit `Content-Type` (e.g. `image/jpeg`) and `Content-Disposition: attachment` if they’re not meant to be rendered inline.
- Prefer storing files outside the web root or serving them through a handler that sets safe headers.

---

## 7. **OpenAPI spec and debug info**

**Risk:** `openapi_url` is enabled, so anyone can request `/api/v1/openapi.json` and see all routes, parameters, and descriptions. In production this can help attackers find attack surface.

**Fix:**
- In production, disable or restrict OpenAPI (e.g. set `openapi_url=None` or serve it only from an internal/admin URL).
- Ensure debug mode and stack traces are off in production.

---

## 8. **Database and environment**

**Risk:** Default `DATABASE_URL` or a weak DB password in `.env` can lead to full DB access (read/change/delete data).

**Fix:**
- Use a strong, unique DB password and a dedicated DB user with minimal required privileges.
- Prefer env-based config (e.g. `.env`) and never commit secrets. Rotate credentials if they may have been exposed.

---

## 9. **Running on 0.0.0.0**

**Risk:** Binding to `0.0.0.0` exposes the app to the whole network. Combined with weak auth or no firewall, the API is reachable from other machines.

**Fix:**
- Use a reverse proxy (e.g. Nginx) in front of the app and bind the app to `127.0.0.1` in production when possible.
- Restrict firewall rules so only the proxy (and necessary management hosts) can reach the app port.

---

## Summary checklist

| Item                         | Priority | Action |
|-----------------------------|----------|--------|
| Strong `SECRET_KEY` in prod | High     | Set via env; never use default. |
| CORS origins                | High     | Restrict to your frontend(s). |
| Admin / sensitive APIs      | High     | Protect admin UI and list/detail APIs. |
| Rate limiting               | Medium   | Add on login, register, refresh. |
| Default admin               | Medium   | Remove or change in prod. |
| File upload validation      | Medium   | Validate content type; safe headers. |
| OpenAPI in prod             | Low      | Disable or restrict. |
| DB and env secrets          | High     | Strong credentials; no commits. |

These steps significantly reduce the risk of your app being hacked; the highest impact is a strong secret key, restricted CORS, and proper protection of admin and sensitive data.
