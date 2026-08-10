-- Fake TeslaMate data for the dashboard integration test.
-- Five completed drives for one car, plus three charging sessions (the third
-- deliberately has no cost, to exercise the "cost not tracked" path).

-- efficiency is kWh/km (TeslaMate's own unit for this column — not Wh/km), e.g. a real Model 3
-- around 150 Wh/km is stored here as 0.150.
INSERT INTO cars (id, vin, name, model, efficiency) VALUES
    (1, 'TEST00000000000001', 'Test Car', 'Model 3', 0.152);

INSERT INTO addresses (id, display_name) VALUES
    (1, '123 Home St, San Francisco'),
    (2, '456 Work Ave, San Francisco');

INSERT INTO drives
    (id, car_id, start_date, end_date, start_km, end_km, distance,
     start_rated_range_km, end_rated_range_km, start_address_id, end_address_id)
VALUES
    (101, 1, '2026-07-20 08:00:00+00', '2026-07-20 08:20:00+00', 1000.0, 1012.0, 12.0, 300.00, 284.00, 1, 2),
    (102, 1, '2026-07-21 08:00:00+00', '2026-07-21 08:22:00+00', 1012.0, 1025.5, 13.5, 284.00, 266.00, 1, 2),
    (103, 1, '2026-07-22 08:00:00+00', '2026-07-22 08:24:00+00', 1025.5, 1040.0, 14.5, 266.00, 247.00, 1, 2),
    (104, 1, '2026-07-23 08:00:00+00', '2026-07-23 08:18:00+00', 1040.0, 1051.0, 11.0, 247.00, 232.00, 1, 2),
    (105, 1, '2026-07-24 08:00:00+00', '2026-07-24 08:23:00+00', 1051.0, 1065.0, 14.0, 232.00, 213.00, 1, 2);

INSERT INTO positions (date, latitude, longitude, odometer, car_id, drive_id) VALUES
    ('2026-07-20 08:00:00+00', 37.7749, -122.4194, 1000.0, 1, 101),
    ('2026-07-20 08:20:00+00', 37.7849, -122.4094, 1012.0, 1, 101),
    ('2026-07-21 08:00:00+00', 37.7749, -122.4194, 1012.0, 1, 102),
    ('2026-07-21 08:22:00+00', 37.7849, -122.4094, 1025.5, 1, 102),
    ('2026-07-22 08:00:00+00', 37.7749, -122.4194, 1025.5, 1, 103),
    ('2026-07-22 08:24:00+00', 37.7849, -122.4094, 1040.0, 1, 103),
    ('2026-07-23 08:00:00+00', 37.7749, -122.4194, 1040.0, 1, 104),
    ('2026-07-23 08:18:00+00', 37.7849, -122.4094, 1051.0, 1, 104),
    ('2026-07-24 08:00:00+00', 37.7749, -122.4194, 1051.0, 1, 105),
    ('2026-07-24 08:23:00+00', 37.7849, -122.4094, 1065.0, 1, 105);

INSERT INTO charging_processes (id, car_id, start_date, end_date, charge_energy_added, cost) VALUES
    (201, 1, '2026-07-19 22:00:00+00', '2026-07-19 23:00:00+00', 25.40, 8.50),
    (202, 1, '2026-07-22 22:00:00+00', '2026-07-22 23:10:00+00', 30.10, 10.20),
    (203, 1, '2026-07-24 06:00:00+00', '2026-07-24 06:45:00+00', 18.75, NULL);
