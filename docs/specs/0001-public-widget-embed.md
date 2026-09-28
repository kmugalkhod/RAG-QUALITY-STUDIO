# 0001. Public website widget embed

**Date**: 2026-09-29
**Status**: Implemented locally

## Summary

A site owner copies one script into a shared layout. Any visitor on an allowed site can ask the selected answer deployment. Studio issues short lived browser credentials and pays for answers under the deployment's saved limits. The existing private visitor flow remains available and no existing deployment becomes public by default.

## Context

The current widget expects every customer site to provide a token route and keep a deployment key. That setup does not fit a static site or a WordPress owner who can paste a script but cannot add server code. A browser script cannot hold a deployment key safely. Public visitor access therefore needs an explicit owner choice and limits enforced by Studio.

The current stack is local only. This change proves the flow on loopback. Public internet use still requires separate HTTPS hosting, trusted ingress, operational checks, and release approval.

## Requirements

**User stories**:

- As a site owner, I want one script to show a working assistant so I do not need to write a token service.
- As a deployment owner, I want an explicit public access switch and saved limits so visitor traffic cannot silently consume my budget.

**Acceptance criteria**:

- **AC-1**: The owner can explicitly enable or disable public visitor access for an active deployment with allowed origins. Existing deployments remain private until enabled.
- **AC-2**: A static page on an allowed origin can load the versioned script and ask a question without a customer token route or deployment key. The answer and evidence use the existing deployed run path.
- **AC-3**: Studio issues short lived tokens only for a configured public deployment and an allowed site origin. Tokens stay in iframe memory, are revoked when public access is disabled, and cannot read another visitor's runs.
- **AC-4**: Token issuance and question admission obey bounded rates, queue limits, and the saved daily and monthly cost limits. Origin checks are an embed boundary, not proof of visitor identity.
- **AC-5**: Private embeds continue to use the customer token route and server key. Public and private scripts identify their mode clearly in Studio.
- **AC-6**: Local browser checks cover an allowed static site and an answer with evidence. Isolated backend checks cover blocked origins, disabled public mode, visitor ownership, and issuance rate refusal. No public hosting is claimed.

## Options considered

### Customer token service

Keep the current private flow. It gives each site full control over visitor identity but requires customer backend work.

### Studio issued public tokens

Studio issues bounded anonymous visitor tokens after a checked iframe handshake. This supports one script, while Studio must own abuse and spending controls.

### Put the server key in the script

This would let anyone copy the key and call the paid API. It is not acceptable.

## Decision

**Chosen option**: Studio issued public tokens alongside the existing private flow.

Public access is off by default. Owners opt in after selecting allowed origins and keeping deployment limits. The iframe requests a token from Studio after it verifies the parent origin. The loader never receives a server key.

## Rationale

This matches the requested one script customer setup without making the existing private flow public. Studio already has durable run admission, queue limits, and budget reservations. The public token endpoint needs a separate bounded issuance rule because a site origin can be spoofed by a nonbrowser client. The saved budget remains the final spending ceiling.

## Feature design

**Data model sketch**:

| Record | New or used fields | Relationship |
|---|---|---|
| Answer deployment | New `widget_public_enabled`, false by default | Owns widget settings, limits, and run history |
| Internal widget key | A server owned key row with no disclosed secret | One per public deployment, used for run accounting |
| Widget token | Existing hash, deployment, key, visitor binding, site origin, expiry, revocation | Belongs to the deployment and internal key |

**State transitions**: Private remains the default. An owner may enable public access only for an enabled widget with allowed origins and a ready active release. Disabling public access invalidates its outstanding tokens. Pausing the deployment stops new questions in either mode.

**API surface**:

| Endpoint | Method | Key inputs | Key outputs | Auth | Key errors |
|---|---|---|---|---|---|
| Project deployment widget settings | PUT | Revision, public flag, origins, branding | Saved revision and flags | Project owner or admin | 403, 412, 422 |
| Deployment widget config | GET | Deployment ID | Flags, origins, branding | Public read | 404 |
| Deployment public token | POST | Deployment ID, checked site origin | Token and expiry | Widget frame origin, public mode | 403, 409, 429, 503 |
| Widget questions and results | Existing | Token, question, run ID | Accepted run, answer, evidence | Browser token | Existing admission errors |

**Value sourcing**:

| Action | Value | Source |
|---|---|---|
| Copy script | Deployment ID and widget URL | Saved deployment and configured widget host |
| Check parent site | Site origin | Browser message origin checked against deployment origins |
| Issue public token | Visitor binding | Random per-frame visitor ID and a global deployment issuance cap |
| Limit spending | Rate and budgets | Saved deployment limits and existing organization ceilings |
| Show answer | Release, answer, evidence | Existing deployed run snapshot |

**Key invariants**: The public script contains no key. Only an owner or admin enables public access. A private deployment never issues a public token. Each token is short lived and scoped to one deployment and site origin. A copied or spoofed site origin cannot bypass the deployment spending ceiling.

**Security model**: Public visitors are anonymous. Allowed origins restrict ordinary browser embedding but do not authenticate an attacker outside a browser. The issuer limits tokens per deployment. Existing run admission limits, budget reservations, and worker controls stay authoritative. No public service is exposed until separate ingress work is approved.

## Migration plan

Migration 0036 adds a false-by-default public flag and a typed internal accounting key. Existing widget settings and customer keys remain private. Disabling public mode immediately makes previously issued public tokens unusable. The migration refuses rollback while internal public keys are retained.

**Critical test scenarios**:

- Allowed static site asks and inspects evidence, verifies **AC-2**, **AC-3**, and **AC-6**.
- Unknown origin, disabled mode, and stale token are refused, verifies **AC-1**, **AC-3**, and **AC-6**.
- Concurrent token and run requests hit the intended rate and budget ceilings, verifies **AC-4**.
- An existing private customer flow still works, verifies **AC-5**.

## Build plan

1. Add the explicit public flag and migration, then return it from management and public config. Verify existing records remain private. Covers **AC-1** and **AC-3**.
2. Add a server owned accounting key and bounded public token issuance while reusing widget token verification and run admission. Covers **AC-2**, **AC-3**, and **AC-4**.
3. Let the iframe obtain a public token after its checked site handshake. Make the loader token URL optional for public mode. Covers **AC-2** and **AC-5**.
4. Update Studio settings and the copied script to explain public and private modes, limits, and the local hosting boundary. Covers **AC-1** and **AC-5**.
5. Verify migration, backend authorization and budget behavior, widget tests, and an isolated static site browser journey. Covers **AC-6**.

## Consequences

Studio accepts paid anonymous traffic when an owner enables this mode. Site origin checks cannot prevent direct nonbrowser abuse, so rates and cost budgets are essential. Customers needing their own user access rules can keep the private token flow.

## Follow-up

Public HTTPS hosting, trusted client address handling at ingress, abuse monitoring, and production release checks remain separate work.

## Verification

The isolated PostgreSQL widget suite passed 7 tests and the loader suite passed 7 tests. An anonymous browser on the local static page obtained a Studio token, submitted a question through the durable worker, and displayed a real answer with three evidence items. The existing deployment was enabled only for the allowed loopback site with its saved cost and traffic limits.
