-- Fake Teslog-computed data (what the sync loop would normally produce),
-- matching the drives in teslamate_seed.sql by drive_id. Pre-seeding this
-- directly (rather than letting the app compute it) avoids the test needing
-- a reachable OSRM server: the sync loop only calls OSRM for drives missing
-- from this table, and every drive here already has a row.

INSERT INTO drive_route_comparisons
    (car_id, drive_id, drive_start_at, drive_end_at, start_address, end_address,
     odometer_start, odometer_end, odometer_delta, teslamate_distance,
     osrm_route_distance, gps_trace_distance, drift_pct, unit, status, error_message)
VALUES
    (1, 101, '2026-07-20 08:00:00+00', '2026-07-20 08:20:00+00',
     '123 Home St, San Francisco', '456 Work Ave, San Francisco',
     1000.0, 1012.0, 12.0, 12.0, 11.5, 12.3, 4.35, 'km', 'complete', NULL),
    (1, 102, '2026-07-21 08:00:00+00', '2026-07-21 08:22:00+00',
     '123 Home St, San Francisco', '456 Work Ave, San Francisco',
     1012.0, 1025.5, 13.5, 13.5, 13.0, 13.8, 3.85, 'km', 'complete', NULL),
    (1, 103, '2026-07-22 08:00:00+00', '2026-07-22 08:24:00+00',
     '123 Home St, San Francisco', '456 Work Ave, San Francisco',
     1025.5, 1040.0, 14.5, 14.5, 13.9, 14.7, 4.32, 'km', 'complete', NULL),
    (1, 104, '2026-07-23 08:00:00+00', '2026-07-23 08:18:00+00',
     '123 Home St, San Francisco', '456 Work Ave, San Francisco',
     1040.0, 1051.0, 11.0, 11.0, 10.6, 11.2, 3.77, 'km', 'complete', NULL),
    (1, 105, '2026-07-24 08:00:00+00', '2026-07-24 08:23:00+00',
     '123 Home St, San Francisco', '456 Work Ave, San Francisco',
     1051.0, 1065.0, 14.0, 14.0, 13.4, 14.3, 4.48, 'km', 'complete', NULL);
