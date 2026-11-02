-- ==============================================================================
-- Smart Baby Monitoring System — Database Maintenance & Sanitation Script
-- ==============================================================================
-- Description:
--   1. Ensures the schema includes the new 'source' tracking column.
--   2. Deletes corrupted or false crying readings where the microphone was
--      unplugged/disconnected (rms_amplitude = 0 AND peak_amplitude = 0).
--   3. Cleans up simulated test data and orphan events from mock devices.
-- ==============================================================================

-- Step 1: Ensure 'source' column exists in sensor_readings
ALTER TABLE sensor_readings 
ADD COLUMN IF NOT EXISTS source VARCHAR(32) DEFAULT 'esp32_device';

-- Step 2: Delete invalid 'BABY_CRYING_DETECTED' readings recorded while microphone had zero energy
DELETE FROM sensor_readings 
WHERE rms_amplitude = 0 
  AND peak_amplitude = 0 
  AND classification IN ('BABY_CRYING_DETECTED', 'POSSIBLE_CRYING');

-- Step 3: Delete simulated test device readings (if any exist in database)
DELETE FROM sensor_readings 
WHERE device_id = 'esp32-devkit-v1-simulated' 
   OR source = 'demo';

-- Step 4: Delete simulated test device events
DELETE FROM crying_events 
WHERE device_id = 'esp32-devkit-v1-simulated';

-- Step 5: Clean up old unacknowledged events generated while mic was offline/disconnected
DELETE FROM crying_events
WHERE device_id = 'esp32-nursery-01'
  AND acknowledged = false
  AND duration_seconds < 1.0;

