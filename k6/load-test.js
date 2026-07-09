// k6 performance test for the EventBoard SQLi-demo app.
//
// Exercises the three real endpoints:
//   GET /            -> public event listing (single SELECT)
//   GET /?id=<n>     -> event detail (SELECT + per-row attendees SELECT, heavier)
//   GET /health      -> DB connectivity check
//
// Run:
//   k6 run k6/load-test.js
//   k6 run -e BASE_URL=http://209.38.217.57 k6/load-test.js
//   k6 run -e PROFILE=smoke   k6/load-test.js   # quick sanity, 1 VU
//   k6 run -e PROFILE=stress  k6/load-test.js   # push past comfort zone
//
import http from 'k6/http';
import { check, group, sleep } from 'k6';
import { Rate, Trend } from 'k6/metrics';

const BASE_URL = (__ENV.BASE_URL || 'http://209.38.217.57').replace(/\/$/, '');
const PROFILE = __ENV.PROFILE || 'load';

// There are 11 seeded events (ids 1..11). Detail views pick from this range.
const EVENT_IDS = Array.from({ length: 11 }, (_, i) => i + 1);

// Custom metrics for per-endpoint visibility.
const errorRate = new Rate('failed_requests');
const listingLatency = new Trend('latency_listing', true);
const detailLatency = new Trend('latency_detail', true);

const PROFILES = {
  // Minimal sanity check — is the app up and responding correctly?
  smoke: {
    executor: 'constant-vus',
    vus: 1,
    duration: '30s',
  },
  // Default: ramp up, hold, ramp down. Models steady everyday traffic.
  load: {
    executor: 'ramping-vus',
    startVUs: 0,
    stages: [
      { duration: '30s', target: 20 },  // ramp to 20 VUs
      { duration: '1m', target: 20 },   // hold
      { duration: '30s', target: 50 },  // ramp to 50 VUs
      { duration: '2m', target: 50 },   // hold
      { duration: '30s', target: 0 },   // ramp down
    ],
    gracefulRampDown: '10s',
  },
  // Push hard to find the breaking point.
  stress: {
    executor: 'ramping-vus',
    startVUs: 0,
    stages: [
      { duration: '1m', target: 100 },
      { duration: '2m', target: 200 },
      { duration: '2m', target: 300 },
      { duration: '1m', target: 0 },
    ],
    gracefulRampDown: '15s',
  },
};

export const options = {
  scenarios: {
    default: PROFILES[PROFILE] || PROFILES.load,
  },
  thresholds: {
    // 95% of requests under 500ms, 99% under 1.5s.
    http_req_duration: ['p(95)<500', 'p(99)<1500'],
    // Fewer than 1% of checks/requests may fail.
    failed_requests: ['rate<0.01'],
    http_req_failed: ['rate<0.01'],
    // The heavier detail endpoint gets its own budget.
    latency_detail: ['p(95)<800'],
  },
};

export default function () {
  // Traffic mix: ~60% listing, ~35% detail, ~5% health — roughly like a
  // browsing user landing on the list then opening a few events.
  const r = Math.random();

  if (r < 0.6) {
    group('listing', () => {
      const res = http.get(`${BASE_URL}/`);
      listingLatency.add(res.timings.duration);
      const ok = check(res, {
        'listing: status 200': (r) => r.status === 200,
        'listing: has events': (r) => r.body && r.body.includes('EventBoard'),
      });
      errorRate.add(!ok);
    });
  } else if (r < 0.95) {
    group('detail', () => {
      const id = EVENT_IDS[Math.floor(Math.random() * EVENT_IDS.length)];
      const res = http.get(`${BASE_URL}/?id=${id}`);
      detailLatency.add(res.timings.duration);
      const ok = check(res, {
        'detail: status 200': (r) => r.status === 200,
        'detail: rendered page': (r) => r.body && r.body.includes('Event ID'),
      });
      errorRate.add(!ok);
    });
  } else {
    group('health', () => {
      const res = http.get(`${BASE_URL}/health`);
      const ok = check(res, {
        'health: status 200': (r) => r.status === 200,
        'health: db up': (r) => {
          try {
            return r.json('db') === 'up';
          } catch (e) {
            return false;
          }
        },
      });
      errorRate.add(!ok);
    });
  }

  // Think time between actions (0.5–1.5s) so VUs model real users, not a flood.
  sleep(0.5 + Math.random());
}
