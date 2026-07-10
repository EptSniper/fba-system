import { NextRequest, NextResponse } from "next/server";

// Operator authentication (Code Review 2026-07-03, Finding #1). The /api/ops/* routes read
// and WRITE business tables with the Supabase service-role key, and /api/ops/decide stamps
// decisions human_approved — so nothing here may be reachable by anyone but the operator.
// Next.js route handlers accept requests from ANY origin by default; there is no such thing
// as a "same-origin only" API route without an explicit check like this one.
//
// Policy:
// - BASIC_AUTH_USER + BASIC_AUTH_PASS set  -> HTTP Basic auth required on every page and API
//   route (the browser prompts once; same-origin fetch() reuses the credentials).
// - Not set, running locally               -> open (dev convenience; localhost only).
// - Not set, deployed (VERCEL env present) WITH Supabase configured -> everything 503s.
//   Deploying live business data without auth is a misconfiguration, not a mode.
// This is the CC1-era stopgap; CC3 (CONTROL_CENTER_UPGRADE_PLAN.md) owns full hardening.

const USER = process.env.BASIC_AUTH_USER;
const PASS = process.env.BASIC_AUTH_PASS;

// Constant-time-ish comparison — avoids the classic early-exit timing leak on the password.
function safeEqual(a: string, b: string): boolean {
  if (a.length !== b.length) return false;
  let diff = 0;
  for (let i = 0; i < a.length; i++) diff |= a.charCodeAt(i) ^ b.charCodeAt(i);
  return diff === 0;
}

export function middleware(req: NextRequest) {
  const authConfigured = Boolean(USER && PASS);

  if (!authConfigured) {
    const deployed = Boolean(process.env.VERCEL);
    // ML audit fix (2026-07-09): the failsafe used to key ONLY on Supabase credentials — but
    // /api/ops/dispatch needs only GITHUB_PAT to trigger REAL workflow_dispatch runs (an
    // unauthenticated caller could hammer keepa-collect and drain the 60-token Keepa bank on
    // demand), and other server credentials are just as privileged. A deployed instance with
    // ANY privileged credential and no operator auth is a misconfiguration, not a mode.
    const privileged = Boolean(
      (process.env.SUPABASE_URL && process.env.SUPABASE_SERVICE_ROLE_KEY) ||
        process.env.GITHUB_PAT ||
        process.env.ANTHROPIC_API_KEY,
    );
    if (deployed && privileged) {
      return new NextResponse(
        "This deployment has privileged server credentials (Supabase/GitHub/Anthropic) but no " +
          "operator auth. Set BASIC_AUTH_USER and BASIC_AUTH_PASS in the deployment env to enable access.",
        { status: 503 },
      );
    }
    return NextResponse.next(); // local dev, or a credential-less demo deploy — nothing sensitive reachable
  }

  const header = req.headers.get("authorization") ?? "";
  if (header.startsWith("Basic ")) {
    try {
      const [user, ...passParts] = atob(header.slice(6)).split(":");
      const pass = passParts.join(":"); // passwords may themselves contain ":"
      if (safeEqual(user, USER!) && safeEqual(pass, PASS!)) return NextResponse.next();
    } catch {
      // fall through to the 401
    }
  }
  return new NextResponse("Authentication required.", {
    status: 401,
    headers: { "WWW-Authenticate": 'Basic realm="FBA Control Center"' },
  });
}

export const config = {
  // Everything except Next's own static assets — pages AND API routes are both operator-only.
  matcher: ["/((?!_next/static|_next/image|favicon.ico).*)"],
};
