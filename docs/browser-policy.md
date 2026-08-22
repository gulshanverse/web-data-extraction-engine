# Browser Policy

## Purpose

The browser policy is a security and resource-control boundary between orchestration and asynchronous Playwright workers. It describes what a browser worker may access and how much work it may perform. It is not an AI prompt and cannot be weakened by page content or planner output.

Phase 0 defines the interface and responsibilities only. Enforcement is implemented and hardened in the browser and security phases.

## Policy shape

```json
{
  "allowed_domains": ["example.com"],
  "max_pages": 20,
  "max_crawl_depth": 2,
  "max_records": 1000,
  "navigation_timeout_ms": 30000,
  "request_rate_per_domain": 1.0,
  "max_redirects": 5,
  "max_response_bytes": 10485760,
  "max_total_bytes": 104857600,
  "max_browser_minutes": 10,
  "follow_robots": true,
  "allow_downloads": false,
  "allow_popups": false,
  "cancellation_key": "job-cancel-marker"
}
```

Defaults and upper bounds are configured by the service, not freely selected by a model. A project policy may narrow the service defaults but may not expand system safety limits.

## Policy interface

The future browser module should consume a typed policy similar to:

```python
class BrowserPolicy(Protocol):
    def allow_navigation(self, url: str, from_url: str | None) -> PolicyDecision: ...
    def allow_redirect(self, source_url: str, target_url: str) -> PolicyDecision: ...
    def allow_request(self, url: str, resource_type: str) -> PolicyDecision: ...
    def allow_page_count(self, current: int) -> PolicyDecision: ...
    def allow_depth(self, depth: int) -> PolicyDecision: ...
    def allow_record_count(self, current: int) -> PolicyDecision: ...
    def allow_response_size(self, size_bytes: int) -> PolicyDecision: ...
    def should_cancel(self, job_id: str) -> bool: ...
```

`PolicyDecision` contains an allow/deny outcome, stable reason code, and safe message. The browser worker must fail closed when a decision cannot be evaluated.

## Domain and URL controls

Only `http` and `https` URLs are eligible. Hostnames are normalized using a canonicalization policy and compared against explicitly allowed domains. Whether subdomains are permitted must be explicit; a policy for `example.com` must not implicitly grant `example.net` or unrelated lookalikes. Redirect targets are checked again before navigation.

DNS resolution and connection checks must protect against private, loopback, link-local, multicast, metadata-service, and other reserved address ranges. DNS answers should be pinned or revalidated to reduce rebinding risk. The browser must not navigate to `file:`, `data:`, `javascript:`, local IPC endpoints, or arbitrary internal services.

## Resource controls

The policy eventually limits page count, crawl depth, records, navigation time, request rate, redirects, response bytes, total bytes, browser duration, concurrent pages, downloads, and memory/CPU exposure. Large or unsupported resources are blocked or skipped with a recorded policy decision. Pagination and relevant-link traversal consume the same page and depth budgets.

Browser contexts are created per job or isolated job group. Cookies, local storage, cache, downloads, and permissions are not shared across unrelated jobs. Downloads are disabled by default. Popups, unsolicited new pages, and unsupported protocols are blocked unless a later explicitly reviewed policy enables them.

## Robots and access policy

The implementation should have a documented robots/access-policy decision. Following `robots.txt` is the default for ordinary discovery, but it does not replace authorization or create permission to access restricted content. A policy denial is terminal for the affected navigation unless the user changes the permitted scope.

The system must never add CAPTCHA solving, credential harvesting, stealth intended to defeat detection, paywall circumvention, authorization bypass, or anti-security evasion. When a site requires access the user has not supplied or is not permitted to use, the job stops safely.

## Browser actions

The browser agent may eventually perform `navigate`, `wait`, `click`, `scroll`, `fill`, `select`, open permitted links, inspect page structure, capture DOM, and capture relevant page state. Actions are selected by a validated plan and are checked against policy before execution. Page text, HTML, attributes, and scripts are untrusted data; they cannot redefine policy or grant additional capabilities.

The Browser Agent does not decide extraction requirements. The Planner produces the machine-readable intent and the Discovery/Extraction modules determine relevance within that plan.

## Cancellation and failure

Every browser action has a timeout and cancellation check. A policy violation produces a safe terminal code such as `DOMAIN_NOT_ALLOWED` or `RESOURCE_LIMIT_EXCEEDED`. A timeout produces `BROWSER_TIMEOUT`; a navigation failure produces `PAGE_LOAD_FAILED`. Diagnostics contain sanitized URL and category, not cookies, authorization headers, or unrestricted raw content.

## Testing responsibilities

Later phases should test URL canonicalization, private-IP blocking, redirects, DNS changes, domain matching, limits, cancellation, download blocking, resource-type filtering, and browser isolation. Tests must cover malformed and adversarial URLs and must use controlled fixtures rather than bypassing access controls on real services.
