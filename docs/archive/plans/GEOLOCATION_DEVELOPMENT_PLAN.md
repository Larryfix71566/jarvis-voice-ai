# Geolocation on Login: Development Plan

**Status:** SUPERSEDED — never built as written (status line added
2026-09-17; the document had none). This is a browser-side, TypeScript-shaped
plan (frontend localStorage, `src/services/geolocationService.ts`) dated
"2024", predating the Python bot. Its *intent* — a layered location fallback
feeding the weather and scheduler agents — is implemented in Python:
`jarvis/ambient_weather.py` prefers a device-reported location
(`set_device_location`), falls back to IP geolocation via ip-api.com, then to
the configured default; `jarvis/admin/server.py:2004` follows the same order.
None of the storage schema, endpoints or frontend code specified here exists,
and the web frontend itself is scheduled for removal (T1.4). Kept for the
design rationale only.


**Date:** 2024  
**Primary Location:** Spartanburg, SC  
**Primary Timezone:** America/New_York  

## Overview

This plan establishes a multi-layered approach to determine user geolocation at login, persist location data across sessions, and integrate it with weather and scheduler agents. The system prioritizes user privacy while providing accurate local context.

---

## 1. Geolocation Acquisition Strategy

### 1.1 Preferred Approach: Layered Fallback Chain

Implement a cascading strategy that tries multiple sources in order of preference:

#### Priority 1: Browser Geolocation API (Client-Side)
- **Method:** HTML5 Geolocation API (`navigator.geolocation.getCurrentPosition()`)
- **Pros:**
  - Highest precision (50m–1500m accuracy depending on device/network)
  - User explicitly grants permission
  - Works on mobile and desktop
  - Real-time location capture
- **Cons:**
  - Requires user permission prompt
  - May be slow (network triangulation)
  - May fail on private/incognito browsing
  - Not all users will grant permission
- **Implementation:**
  - Request immediately after successful login
  - Timeout: 10 seconds max (don't block login flow)
  - Store result in localStorage and backend

#### Priority 2: Stored Preference from Prior Session
- **Method:** Retrieve from localStorage or backend user settings
- **Pros:**
  - Instant (no new requests)
  - Users don't re-grant permissions
  - Consistent experience across sessions
- **Cons:**
  - Stale if user has moved
  - Only available after first login
- **Implementation:**
  - Check `localStorage.getItem('userLocation')`
  - If unavailable, check backend user profile `last_known_location`
  - Timestamp check: use stored location if < 30 days old

#### Priority 3: IP-Based Geolocation (Server-Side)
- **Method:** Query IP geolocation service on backend (e.g., MaxMind GeoIP2, IP2Location)
- **Pros:**
  - No user permission needed
  - Works when browser API fails
  - Server-side, reliable
  - Useful for detecting abuse/fraud
- **Cons:**
  - Lower precision (city/region level, ~15km accuracy)
  - Requires third-party service (cost)
  - VPN/proxy bypass issues
- **Implementation:**
  - Backend extracts client IP from request
  - Query GeoIP database on login
  - Use as fallback only if browser API fails
  - Cache result (per IP, 24h TTL)

#### Priority 4: Hardcoded Default (Fallback)
- **Method:** Use known primary location (Spartanburg, SC)
- **Behavior:** Fallback only if all prior methods fail
- **Coordinates:** ~34.965°N, 81.933°W (Spartanburg city center)
- **Rationale:** Ensures graceful degradation and consistent timezone/weather

### 1.2 Acquisition Flow (Pseudocode)

```
On Login:
1. Check localStorage for valid stored location (< 30 days old)
   ✓ If found → use it, trigger async refresh
2. Request browser Geolocation API (10s timeout)
   ✓ Success → store in localStorage + send to backend
   ✓ Failure → proceed to step 3
3. Query backend IP-based geolocation
   ✓ Success → store in localStorage + backend
   ✓ Failure → proceed to step 4
4. Use hardcoded Spartanburg default
   → still store in backend for user profile

After geolocation acquired:
→ Update timezone in UI
→ Fetch weather for location
→ Initialize scheduler with location context
```

---

## 2. Location Data Storage Architecture

### 2.1 Frontend Storage (Browser)

**localStorage Key:** `userLocation`

**Schema:**
```json
{
  "latitude": 34.965,
  "longitude": -81.933,
  "accuracy": 150,
  "source": "browser_geolocation",
  "timestamp": 1704067200000,
  "city": "Spartanburg",
  "state": "SC",
  "country": "US",
  "timezone": "America/New_York"
}
```

**Rationale:**
- Enables instant location on page reload
- Reduces login latency on subsequent sessions
- Survives browser restart
- Encrypted in secure contexts (HTTPS only)

**Expiration:** 30 days; invalidate and re-acquire if stale

### 2.2 Backend Storage (Database)

**User Profile Extension:**

```
users table additions:
├── last_known_location (JSON)
│   ├── latitude (decimal)
│   ├── longitude (decimal)
│   ├── accuracy (integer, meters)
│   ├── source ('browser_api' | 'ip_based' | 'default')
│   ├── city (string)
│   ├── state (string)
│   ├── country (string)
│   └── timezone (string)
├── location_updated_at (timestamp)
├── preferred_timezone (string, user override)
└── location_data_consent (boolean, GDPR/privacy flag)
```

**Rationale:**
- Persists across device/browser changes
- Enables location history for analytics
- Supports server-side weather prefetch
- Allows GDPR-compliant data retention policies

**Access Control:**
- Location data visible only to authenticated user
- Admin access logged and auditable
- No third-party sharing without explicit consent

---

## 3. Integration with Weather and Scheduler Agents

### 3.1 Weather Agent Integration

**Flow:**
```
1. User logs in
2. Geolocation acquired (lat/lon)
3. Frontend sends to `/api/weather` endpoint with:
   {
     "latitude": 34.965,
     "longitude": -81.933,
     "source": "browser_geolocation"
   }
4. Backend queries weather API (OpenWeatherMap, WeatherAPI, etc.)
5. Weather data cached per (lat/lon), 1h TTL
6. Return to frontend with:
   {
     "location": "Spartanburg, SC",
     "temp": 68,
     "condition": "Partly Cloudy",
     "timezone": "America/New_York"
   }
7. Render in UI dashboard
```

**Optimization:**
- Prefetch weather on login (don't wait for user interaction)
- Refresh every 30 minutes or on location change
- Cache location-specific weather for 1 hour
- Fall back to cached data if API is down

### 3.2 Scheduler Agent Integration

**Flow:**
```
1. Scheduler initialized after login
2. Receives location context via `/api/user/context`:
   {
     "location": {
       "city": "Spartanburg",
       "state": "SC",
       "timezone": "America/New_York",
       "latitude": 34.965,
       "longitude": -81.933
     }
   }
3. Scheduler uses timezone to:
   ✓ Format all times in user's local timezone
   ✓ Adjust event creation/display
   ✓ Set meeting times with proper TZ awareness
4. Location used for:
   ✓ Commute time estimates (integrate with Maps API)
   ✓ Weather-aware scheduling
   ✓ Local event recommendations
```

**Implementation:**
- Location context passed as JWT claim or session attribute
- Agents query `/api/user/context` on startup
- Timezone conflicts → user's stored preference wins
- Support timezone override in user settings

---

## 4. Fallback Behavior

### 4.1 Graceful Degradation Chain

| Scenario | Fallback | User Experience |
|----------|----------|-----------------|
| Browser API denied | Use stored location or IP-based | Seamless, no UI change |
| Stored location stale (>30d) | IP-based, then default | Minor refresh on login |
| IP-based fails | Use Spartanburg default | UI shows default location, offer manual override |
| All methods fail | Spartanburg default + error toast | "Using default location—please verify" |

### 4.2 Error Handling

**Frontend Error Handling:**
```javascript
try {
  loc = await getStoredLocation();
  if (loc && !isStale(loc)) return loc;
} catch (e) {
  console.warn('Stored location unavailable', e);
}

try {
  loc = await requestBrowserGeolocation(10000); // 10s timeout
  storeLocation(loc);
  return loc;
} catch (e) {
  console.warn('Browser geolocation denied/failed', e);
}

try {
  loc = await backend.getIPBasedLocation();
  storeLocation(loc);
  return loc;
} catch (e) {
  console.warn('IP-based geolocation failed', e);
}

// Fallback
return SPARTANBURG_DEFAULT;
```

**Backend Error Handling:**
```python
def get_location_for_user(user_id, client_ip):
    # Try user's stored location first
    stored = db.get_user_location(user_id)
    if stored and not is_stale(stored):
        return stored
    
    # Try IP-based geolocation
    try:
        ip_loc = geoip_service.lookup(client_ip)
        db.update_user_location(user_id, ip_loc)
        return ip_loc
    except Exception as e:
        logger.warning(f'IP geolocation failed for {client_ip}', e)
    
    # Fallback
    return {
        'city': 'Spartanburg',
        'state': 'SC',
        'latitude': 34.965,
        'longitude': -81.933,
        'timezone': 'America/New_York',
        'source': 'default'
    }
```

### 4.3 User Notification

- **Success (silent):** Location acquired, UI updates
- **Fallback to stored location:** Toast: "Using last known location (Spartanburg, 5 days ago)"
- **Using IP-based:** Toast: "Approximate location determined from network" (low accuracy message)
- **Using default:** Toast: "Using default location—update in settings" (CTA to manual override)

---

## 5. Privacy and Consent Considerations

### 5.1 Legal Framework

**Applicable Regulations:**
- **GDPR (EU):** Geolocation is personal data; explicit consent required
- **CCPA (California):** Location data is sensitive; right to delete/opt-out
- **Gramm-Leach-Bliley Act (if financial context):** Location tied to financial activity
- **HIPAA (if health context):** Location sensitive health info

### 5.2 Consent Model

**On First Login:**
```
Modal/Banner:
┌─────────────────────────────────────────┐
│ Location Access Permission              │
├─────────────────────────────────────────┤
│ We'd like to:                           │
│ ☐ Use your device location (most       │
│   accurate)                             │
│ ☐ Use your IP address (approx.)        │
│ ☑ Remember your location (localStorage)│
│                                         │
│ This helps us show local weather and   │
│ set the correct timezone.              │
│                                         │
│ [Learn More]  [Reject]  [Accept All]   │
└─────────────────────────────────────────┘
```

**Database Tracking:**
```
users.location_data_consent:
├── browser_api: true/false
├── ip_based: true/false
├── storage: true/false
├── created_at: timestamp
└── updated_at: timestamp
```

**Behavior:**
- If `browser_api=false`: skip Geolocation API request
- If `ip_based=false`: skip IP lookup (use stored/default only)
- If `storage=false`: use session-only storage (clear on logout)
- Consent revocation → immediately clear location data

### 5.3 Privacy-Preserving Implementation

1. **Data Minimization:**
   - Only store city/region + timezone (not raw lat/lon internally)
   - Delete location data after 90 days of inactivity
   - No third-party sharing without explicit consent

2. **Transparency:**
   - Clear privacy policy link in consent modal
   - Show data retention period (30 days default, 90 max)
   - Allow manual override/clearing anytime

3. **User Control:**
   - Settings page: "Manage Location Data"
   - Clear location history: one-click
   - Manual location entry option
   - Timezone override (independent of geolocation)

4. **Data Security:**
   - Location data encrypted at rest (database column encryption)
   - HTTPS-only transmission (no HTTP fallback)
   - No location data in logs/analytics without anonymization
   - IP-based geolocation: cache keyed by hash (not raw IP)

### 5.4 Third-Party Service Privacy

**If using external geolocation API (e.g., MaxMind):**
- Review their privacy policy
- Use Data Processing Agreement (DPA)
- Ensure they comply with GDPR/CCPA
- Only send IP address (no user ID linkage)
- Cache results to minimize API calls

---

## 6. Implementation Roadmap

### Phase 1: Foundation (Sprint 1–2)
- [ ] Design and implement localStorage schema
- [ ] Add `last_known_location` + consent fields to user schema
- [ ] Create `/api/user/location` backend endpoint
- [ ] Implement browser Geolocation API wrapper with timeout
- [ ] Build login flow integration (acquire location post-auth)
- [ ] Add fallback to Spartanburg default

### Phase 2: Backend Integration (Sprint 2–3)
- [ ] Integrate IP-based geolocation service (MaxMind or alternative)
- [ ] Implement location caching (Redis, 24h TTL)
- [ ] Add location to JWT/session context
- [ ] Build `/api/weather` endpoint with location parameter
- [ ] Implement location update audit logging

### Phase 3: UI & UX (Sprint 3)
- [ ] Build consent modal with granular options
- [ ] Add location display in UI header
- [ ] Create settings page for location management
- [ ] Implement manual location override feature
- [ ] Add toast notifications for fallback scenarios

### Phase 4: Agent Integration (Sprint 4)
- [ ] Integrate weather agent with location context
- [ ] Integrate scheduler agent with timezone context
- [ ] Add location-aware commute time estimates
- [ ] Test end-to-end weather + scheduling with location

### Phase 5: Privacy & Compliance (Sprint 5)
- [ ] GDPR audit and consent flow validation
- [ ] Implement data retention policies (90-day deletion)
- [ ] Add anonymization for analytics
- [ ] Create privacy policy documentation
- [ ] Perform security review (encryption, access control)

### Phase 6: Testing & Monitoring (Ongoing)
- [ ] Unit tests for geolocation fallback chain
- [ ] Integration tests with weather/scheduler
- [ ] Privacy tests (consent enforcement, data deletion)
- [ ] Monitoring: geolocation success rate, API latencies
- [ ] User testing with privacy-conscious users

---

## 7. Primary Location: Spartanburg, SC

### 7.1 Default Values

| Property | Value |
|----------|-------|
| **City** | Spartanburg |
| **State** | SC |
| **Country** | US |
| **Latitude** | 34.965 |
| **Longitude** | -81.933 |
| **Timezone** | America/New_York |
| **ISO Code** | US-SC-SPT |

### 7.2 Rationale for Default

- Primary user location; most sessions will be from/near Spartanburg
- Reduces reliance on geolocation when exact precision not needed
- Simplifies testing and development
- Acts as sensible fallback if all geolocation methods fail
- Timezone (America/New_York) is user's primary timezone

### 7.3 Timezone Handling

**Primary timezone:** `America/New_York` (Eastern Time)

**Rules:**
1. Always use user's `preferred_timezone` if set (allows override)
2. Fall back to geolocation-based timezone (derived from lat/lon)
3. Final fallback: America/New_York
4. Scheduler and weather agents MUST use user's timezone, not server time

**Implementation:**
```python
def get_user_timezone(user_id):
    user = db.get_user(user_id)
    if user.preferred_timezone:
        return user.preferred_timezone  # explicit override
    if user.last_known_location and user.last_known_location.timezone:
        return user.last_known_location.timezone  # from geolocation
    return 'America/New_York'  # default
```

---

## 8. Configuration & Environment Variables

```bash
# Geolocation & Privacy
GEOLOCATION_ENABLED=true
GEOLOCATION_BROWSER_API_TIMEOUT_MS=10000
GEOLOCATION_STORAGE_TTL_DAYS=30
GEOLOCATION_DEFAULT_CITY="Spartanburg"
GEOLOCATION_DEFAULT_STATE="SC"
GEOLOCATION_DEFAULT_LAT=34.965
GEOLOCATION_DEFAULT_LON=-81.933
GEOLOCATION_DEFAULT_TZ="America/New_York"

# IP-Based Geolocation
MAXMIND_GEOIP_ENABLED=true
MAXMIND_GEOIP_DB_PATH="/var/lib/geoip/GeoLite2-City.mmdb"
MAXMIND_CACHE_TTL_HOURS=24

# Weather API
WEATHER_API_KEY=<key>
WEATHER_API_PROVIDER="openweathermap"  # or "weatherapi"
WEATHER_CACHE_TTL_MINUTES=60

# Privacy & Retention
LOCATION_DATA_RETENTION_DAYS=90
LOCATION_DATA_ENCRYPTION_ENABLED=true
GDPR_CONSENT_REQUIRED=true
```

---

## 9. Data Schemas (SQL)

### 9.1 Users Table Extensions

```sql
ALTER TABLE users ADD COLUMN last_known_location JSONB DEFAULT NULL;
ALTER TABLE users ADD COLUMN location_updated_at TIMESTAMP DEFAULT NULL;
ALTER TABLE users ADD COLUMN preferred_timezone VARCHAR(50) DEFAULT 'America/New_York';
ALTER TABLE users ADD COLUMN location_data_consent JSONB DEFAULT '{
  "browser_api": false,
  "ip_based": false,
  "storage": false,
  "created_at": null,
  "updated_at": null
}';

-- Index for location lookups
CREATE INDEX idx_users_location_updated ON users(location_updated_at DESC);
```

### 9.2 Location Audit Log

```sql
CREATE TABLE location_audit_log (
  id UUID PRIMARY KEY,
  user_id UUID NOT NULL REFERENCES users(id),
  latitude DECIMAL(10, 6),
  longitude DECIMAL(10, 6),
  city VARCHAR(100),
  state VARCHAR(50),
  timezone VARCHAR(50),
  source VARCHAR(50),  -- 'browser_api', 'ip_based', 'manual', 'default'
  ip_address INET,
  user_agent TEXT,
  created_at TIMESTAMP NOT NULL DEFAULT NOW(),
  
  FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
  INDEX idx_user_id (user_id),
  INDEX idx_created_at (created_at DESC)
);
```

---

## 10. Testing Strategy

### 10.1 Unit Tests

- **Geolocation fallback chain:** All paths (browser success, browser fail, IP success, IP fail, default)
- **Timezone detection:** From lat/lon, from user preference, fallback
- **localStorage schema:** Valid, stale, invalid, missing fields
- **Consent enforcement:** API calls blocked by consent flags

### 10.2 Integration Tests

- **End-to-end login → geolocation → weather:** Full flow
- **Weather agent receives location context:** Correct timezone in output
- **Scheduler agent receives timezone:** Times displayed in correct TZ
- **IP-based geolocation + caching:** Cache hit/miss, TTL expiration

### 10.3 Privacy Tests

- **Consent modal appears on first login:** All scenarios
- **Revoked consent → data cleared:** Immediate effect
- **Data retention:** 90-day deletion job
- **Location not in logs:** Audit log review
- **Encryption:** Database column read/write

### 10.4 Manual Testing

- **Browser API permission denied:** Fallback chain triggered
- **Offline login:** Uses stored location or default
- **Location change (travel):** Manual override → override respected
- **Time zone override:** Scheduler uses override, not geolocation
- **Privacy settings:** Console verification (no PII in requests)

---

## 11. Monitoring & Observability

### 11.1 Key Metrics

```
- Geolocation success rate (by source: browser, IP, stored, default)
- Average accuracy (meters, when available)
- Browser API permission grant rate
- Location data freshness (% of users with recent location)
- Weather API latency (ms)
- Scheduler timezone correctness (audit)
- Location data deletion compliance (audit)
```

### 11.2 Logging

```
[INFO] User login complete: user_id=abc123, location_source=browser_api, lat=34.965, lon=-81.933, accuracy=150m
[INFO] Geolocation fallback: user_id=abc123, browser_api=denied, using_stored_location, age=5d
[WARN] IP geolocation failed: client_ip=203.0.113.42, error=MaxMind_API_down, using_default
[ERROR] Location consent violation: user_id=abc123, ip_lookup_attempted_but_consent=false
[INFO] Location data retention: deleted 1523 records older than 90 days
```

### 11.3 Alerting

- Geolocation success rate < 85% → investigate
- IP-based geolocation API down > 15min → fallback only
- Location encryption failures → security alert
- Consent violation attempts → audit log + investigate

---

## 12. Security Considerations

### 12.1 Threats & Mitigations

| Threat | Mitigation |
|--------|-----------|
| Location data breached | Column-level encryption + access control |
| Location inference attacks | Aggregate to city level, not raw coords in logs |
| IP spoofing | Validate IP format; use reverse DNS verification |
| Tracking without consent | Enforce consent flags; audit violations |
| VPN/proxy bypass | Cache by IP hash; accept location variance |
| Man-in-the-middle (geolocation) | HTTPS-only; validate cert |

### 12.2 Access Control

```
Location data accessible by:
├── Authenticated user (own data only)
├── Backend weather service (lat/lon only, no user ID)
├── Scheduler agent (city + timezone only, no lat/lon)
├── Admin (with audit logging)
└── Analytics (aggregated, anonymized, no user ID)
```

---

## 13. Future Enhancements

1. **Geofencing:** Alert user when location changes significantly (trip detection)
2. **Location History:** Timeline view; "where was I on date X?"
3. **Multiple Locations:** Support work + home; auto-switch based on time-of-day
4. **Weather Alerts:** Push notifications for severe weather at user's location
5. **Integration with Maps:** Commute time; nearby events/POI
6. **Machine Learning:** Predict timezone/location based on usage patterns

---

## Summary

This geolocation system provides accurate, privacy-respecting location context for weather and scheduling features. The layered acquisition strategy ensures reliability (browser API → stored → IP-based → default), while granular consent and data minimization respect user privacy. Integration with weather and scheduler agents is straightforward via location context passed in API calls and JWT claims. The system degrades gracefully, always providing Spartanburg (America/New_York) as a sensible fallback, ensuring consistent timezone handling across all features.

