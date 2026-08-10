-- Minimal fixture schema standing in for TeslaMate's database — trimmed to
-- exactly the columns Teslog's own code reads (see src/teslog/services/*.py
-- and src/teslog/metrics.py), not a full mirror of TeslaMate's real schema.

CREATE TABLE cars (
    id INTEGER PRIMARY KEY,
    vin TEXT,
    name TEXT,
    model TEXT,
    efficiency DOUBLE PRECISION
);

CREATE TABLE addresses (
    id INTEGER PRIMARY KEY,
    display_name TEXT
);

CREATE TABLE drives (
    id INTEGER PRIMARY KEY,
    car_id INTEGER NOT NULL REFERENCES cars(id),
    start_date TIMESTAMPTZ NOT NULL,
    end_date TIMESTAMPTZ,
    start_km DOUBLE PRECISION,
    end_km DOUBLE PRECISION,
    distance DOUBLE PRECISION,
    start_rated_range_km NUMERIC(6, 2),
    end_rated_range_km NUMERIC(6, 2),
    start_address_id INTEGER REFERENCES addresses(id),
    end_address_id INTEGER REFERENCES addresses(id)
);

CREATE TABLE positions (
    id SERIAL PRIMARY KEY,
    date TIMESTAMPTZ NOT NULL,
    latitude DOUBLE PRECISION,
    longitude DOUBLE PRECISION,
    odometer DOUBLE PRECISION,
    car_id INTEGER REFERENCES cars(id),
    drive_id INTEGER REFERENCES drives(id)
);

CREATE TABLE charging_processes (
    id INTEGER PRIMARY KEY,
    car_id INTEGER NOT NULL REFERENCES cars(id),
    start_date TIMESTAMPTZ NOT NULL,
    end_date TIMESTAMPTZ,
    charge_energy_added NUMERIC(8, 2),
    cost NUMERIC(6, 2)
);
