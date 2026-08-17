# Geolocation Backend Implementation Specification

## Overview
This document defines the backend implementation requirements for geolocation services in Jarvis. The geolocation system provides location-based data retrieval, caching, and API integration while maintaining performance and reliability standards.

## Architecture

### Core Components

#### 1. Geolocation Service Layer
**File**: `src/services/geolocationService.ts`

- **Interface**: `GeolocationService`
  - `getCoordinates(address: string): Promise<Coordinates>`
  - `reverseGeocode(lat: number, lon: number): Promise<Address>`
  - `searchNearby(lat: number, lon: number, radius: number, type: string): Promise<Place[]>`
  - `validateCoordinates(lat: number, lon: number): boolean`
  - `calculateDistance(lat1: number, lon1: number, lat2: number, lon2: number): number`

- **Implementation**: `GeolocationServiceImpl`
  - Orchestrates geocoding, reverse geocoding, and nearby search operations
  - Manages cache invalidation policies
  - Handles fallback to secondary providers
  - Implements circuit breaker pattern for external API calls

#### 2. Provider Abstraction Layer
**File**: `src/providers/geolocationProvider.ts`

- **Abstract Base**: `GeolocationProvider`
  - `geocode(address: string): Promise<Coordinates>`
  - `reverseGeocode(lat: number, lon: number): Promise<Address>`
  - `searchNearby(lat: number, lon: number, radius: number, type: string): Promise<Place[]>`
  - `getProviderName(): string`
  - `isHealthy(): boolean`

- **Concrete Implementations**:
  - `GoogleMapsProvider`: Primary provider using Google Maps API
  - `OpenStreetMapProvider`: Secondary provider using Nominatim
  - `MapBoxProvider`: Tertiary provider for high-volume scenarios

#### 3. Cache Layer
**File**: `src/cache/geolocationCache.ts`

- **Interface**: `GeolocationCache`
  - `getCoordinates(key: string): Coordinates | null`
  - `setCoordinates(key: string, value: Coordinates, ttl: number): void`
  - `getAddress(key: string): Address | null`
  - `setAddress(key: string, value: Address, ttl: number): void`
  - `getNearby(key: string): Place[] | null`
  - `setNearby(key: string, value: Place[], ttl: number): void`
  - `invalidate(pattern: string): void`
  - `clear(): void`

- **Implementation**: `RedisGeolocationCache`
  - Redis-backed distributed cache
  - Key patterns: `geo:coords:{address}`, `geo:address:{lat}:{lon}`, `geo:nearby:{lat}:{lon}:{type}`
  - TTL values:
    - Coordinates: 30 days (addresses are relatively stable)
    - Address (reverse): 7 days (properties change less frequently)
    - Nearby search: 1 hour (business listings change frequently)
  - Automatic expiration and lazy invalidation

#### 4. Configuration Management
**File**: `src/config/geolocationConfig.ts`

```typescript
interface GeolocationConfig {
  // Provider settings
  providers: {
    google: {
      apiKey: string;
      enabled: boolean;
      priority: number;
    };
    openStreetMap: {
      enabled: boolean;
      priority: number;
      userAgent: string;
    };
    mapBox: {
      apiKey: string;
      enabled: boolean;
      priority: number;
    };
  };

  // Cache settings
  cache: {
    type: 'redis' | 'memory';
    ttl: {
      coordinates: number;
      address: number;
      nearby: number;
    };
    maxSize: number;
  };

  // Performance settings
  performance: {
    timeout: number;
    retries: number;
    circuitBreaker: {
      enabled: boolean;
      threshold: number;
      timeout: number;
    };
  };

  // Rate limiting
  rateLimiting: {
    enabled: boolean;
    requestsPerMinute: number;
    requestsPerDay: number;
  };
}
```

## Request/Response Flow

### Geocoding Request Flow

```
1. Client Request → GeolocationController
   ↓
2. Input Validation (address format, length)
   ↓
3. Cache Lookup (key: address)
   ↓ [Cache Miss]
4. Provider Selection (based on priority and health)
   ↓
5. External API Call (with timeout and retry logic)
   ↓
6. Response Normalization (to Coordinates type)
   ↓
7. Cache Storage (with TTL)
   ↓
8. Response to Client
```

### Error Handling & Fallback

- **Provider Failure**: Automatically try next provider in priority order
- **All Providers Fail**: Return cached stale data if available, else throw error
- **Rate Limited**: Queue request, retry with exponential backoff
- **Invalid Input**: Throw 400 Bad Request immediately
- **Timeout**: Return cached data or error after configured timeout

## API Endpoints

### POST /api/geolocation/geocode
Converts address to coordinates.

**Request**:
```json
{
  "address": "1600 Pennsylvania Avenue NW, Washington, DC",
  "options": {
    "bounds": null,
    "components": null
  }
}
```

**Response**:
```json
{
  "success": true,
  "data": {
    "latitude": 38.8976,
    "longitude": -77.0369,
    "formattedAddress": "1600 Pennsylvania Avenue NW, Washington, DC 20500, USA",
    "accuracy": "rooftop",
    "placeId": "ChIJXQcKMNkCt4kRm0v8OHHS_Ug"
  },
  "provider": "google",
  "cached": false,
  "timestamp": "2024-01-15T10:30:00Z"
}
```

### POST /api/geolocation/reverse-geocode
Converts coordinates to address.

**Request**:
```json
{
  "latitude": 38.8976,
  "longitude": -77.0369,
  "language": "en"
}
```

**Response**:
```json
{
  "success": true,
  "data": {
    "formattedAddress": "1600 Pennsylvania Avenue NW, Washington, DC 20500, USA",
    "addressComponents": [
      {
        "longName": "1600",
        "shortName": "1600",
        "types": ["street_number"]
      },
      {
        "longName": "Pennsylvania Avenue Northwest",
        "shortName": "Pennsylvania Ave NW",
        "types": ["route"]
      }
    ],
    "placeId": "ChIJXQcKMNkCt4kRm0v8OHHS_Ug"
  },
  "provider": "google",
  "cached": true,
  "timestamp": "2024-01-15T10:30:00Z"
}
```

### POST /api/geolocation/nearby
Searches for nearby places.

**Request**:
```json
{
  "latitude": 38.8976,
  "longitude": -77.0369,
  "radius": 1000,
  "type": "restaurant",
  "pageToken": null
}
```

**Response**:
```json
{
  "success": true,
  "data": {
    "places": [
      {
        "name": "The Hay-Adams",
        "latitude": 38.8972,
        "longitude": -77.0365,
        "distance": 65,
        "rating": 4.5,
        "types": ["restaurant", "point_of_interest"],
        "placeId": "ChIJ3-8ZUH9CzYkRhFuRk..."
      }
    ],
    "nextPageToken": "CiQmAAAAAA..."
  },
  "provider": "google",
  "cached": false,
  "timestamp": "2024-01-15T10:30:00Z"
}
```

### GET /api/geolocation/distance
Calculates distance between two points.

**Request**:
```
GET /api/geolocation/distance?lat1=38.8976&lon1=-77.0369&lat2=39.9526&lon2=-75.1652&unit=km
```

**Response**:
```json
{
  "success": true,
  "data": {
    "distance": 245.3,
    "unit": "km",
    "lat1": 38.8976,
    "lon1": -77.0369,
    "lat2": 39.9526,
    "lon2": -75.1652
  },
  "timestamp": "2024-01-15T10:30:00Z"
}
```

## Data Types

```typescript
interface Coordinates {
  latitude: number;
  longitude: number;
  accuracy?: 'rooftop' | 'range_interpolated' | 'geometric_center' | 'approximate';
  formattedAddress?: string;
  placeId?: string;
}

interface Address {
  formattedAddress: string;
  addressComponents: AddressComponent[];
  placeId?: string;
  country?: string;
  state?: string;
  city?: string;
  postalCode?: string;
}

interface AddressComponent {
  longName: string;
  shortName: string;
  types: string[];
}

interface Place {
  name: string;
  latitude: number;
  longitude: number;
  distance?: number;
  placeId: string;
  types: string[];
  rating?: number;
  openingHours?: OpeningHours;
  photos?: Photo[];
}

interface OpeningHours {
  weekdayText: string[];
  isOpen?: boolean;
  periods?: Period[];
}

interface Period {
  open: { day: number; time: string };
  close?: { day: number; time: string };
}

interface Photo {
  url: string;
  attributions: string[];
  height: number;
  width: number;
}
```

## Performance Requirements

- **Cached Response Time**: < 10ms (p99)
- **Uncached Response Time**: < 500ms (p99)
- **Cache Hit Rate**: > 70% for typical usage
- **Provider Availability**: > 99.5% (with fallback)
- **Throughput**: > 10,000 requests/second

## Database Schema (if persistence layer is added)

```sql
CREATE TABLE geolocation_cache (
  id BIGINT PRIMARY KEY AUTO_INCREMENT,
  cache_key VARCHAR(255) NOT NULL UNIQUE,
  cache_type ENUM('coordinates', 'address', 'nearby'),
  data JSON NOT NULL,
  provider VARCHAR(50),
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  expires_at TIMESTAMP,
  hit_count INT DEFAULT 0,
  INDEX idx_expires_at (expires_at)
);

CREATE TABLE geolocation_requests (
  id BIGINT PRIMARY KEY AUTO_INCREMENT,
  request_type VARCHAR(50),
  input_data JSON,
  result_data JSON,
  provider VARCHAR(50),
  response_time_ms INT,
  success BOOLEAN,
  error_message TEXT,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  INDEX idx_created_at (created_at),
  INDEX idx_provider (provider)
);

CREATE TABLE geolocation_analytics (
  id BIGINT PRIMARY KEY AUTO_INCREMENT,
  date DATE,
  request_type VARCHAR(50),
  total_requests INT,
  successful_requests INT,
  failed_requests INT,
  avg_response_time_ms FLOAT,
  cache_hit_count INT,
  provider_usage JSON,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  UNIQUE KEY unique_date_type (date, request_type)
);
```

## Testing Strategy

### Unit Tests
- Provider initialization and health checks
- Cache operations (get, set, invalidate)
- Distance calculations
- Input validation

### Integration Tests
- End-to-end geocoding flow
- Provider fallback mechanism
- Cache hit/miss scenarios
- Rate limiting behavior

### Performance Tests
- Cache response time benchmarks
- Provider API latency measurement
- Concurrent request handling
- Memory usage monitoring

### Security Tests
- API key protection
- Rate limiting effectiveness
- Input sanitization
- SQL injection prevention (if DB used)

## Monitoring & Logging

### Key Metrics
- Request count by operation type
- Response time percentiles (p50, p95, p99)
- Cache hit rate
- Provider success rate
- Error rate by type
- Circuit breaker state changes

### Logging Strategy
- **INFO**: Successful requests (sampled at 5%)
- **WARN**: Cache misses, provider failures, rate limiting
- **ERROR**: All exceptions, failed API calls
- **DEBUG**: Request/response details, provider selection logic

### Health Checks
- Provider endpoint reachability
- Cache connectivity (Redis)
- Rate limit quota status
- Circuit breaker state

## Security Considerations

1. **API Key Management**:
   - Store in environment variables or secure vault
   - Rotate keys regularly
   - Monitor API key usage

2. **Input Validation**:
   - Validate coordinate ranges (-90/90 lat, -180/180 lon)
   - Sanitize address strings
   - Limit string lengths

3. **Rate Limiting**:
   - Per-client rate limiting
   - Global rate limiting
   - Gradual degradation under load

4. **Data Privacy**:
   - Log minimal PII
   - Cache expiration for sensitive data
   - GDPR compliance for location data

## Deployment Considerations

1. **Environment Variables Required**:
   - `GOOGLE_MAPS_API_KEY`
   - `MAPBOX_API_KEY`
   - `REDIS_HOST`, `REDIS_PORT`, `REDIS_PASSWORD`
   - `GEOLOCATION_RATE_LIMIT_RPM`

2. **Infrastructure**:
   - Redis cluster for distributed caching
   - Load balancer for API endpoints
   - CDN for static assets
   - Monitoring stack (Prometheus, Grafana, ELK)

3. **Rollout Strategy**:
   - Canary deployment (5% → 25% → 50% → 100%)
   - Feature flags for provider switching
   - Blue-green deployment for zero downtime
   - Automated rollback on error threshold

## Future Enhancements

1. **Machine Learning Integration**:
   - Address standardization using ML models
   - Popular place prediction
   - Route optimization

2. **Advanced Caching**:
   - Geographical clustering for cache locality
   - Predictive prefetching of nearby areas
   - Bloom filters for negative cache

3. **Real-time Features**:
   - WebSocket support for live location tracking
   - Push notifications for geofence events
   - Real-time traffic integration

4. **Analytics**:
   - Heatmaps of location requests
   - Popular routes and destinations
   - User movement patterns (anonymized)
