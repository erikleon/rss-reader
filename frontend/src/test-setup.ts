// Pin the timezone so local-day grouping is deterministic regardless of where
// the tests run. Node honors a runtime change to process.env.TZ.
process.env.TZ = "UTC";
