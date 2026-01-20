import { describe, expect, it } from "vitest";
import { parseUtc } from "./datetime";

describe("parseUtc", () => {
  it("treats a naive timestamp as UTC", () => {
    expect(parseUtc("2026-01-05T14:30:00").toISOString()).toBe(
      "2026-01-05T14:30:00.000Z",
    );
  });

  it("respects an explicit Z", () => {
    expect(parseUtc("2026-01-05T14:30:00Z").toISOString()).toBe(
      "2026-01-05T14:30:00.000Z",
    );
  });

  it("respects an explicit offset", () => {
    expect(parseUtc("2026-01-05T09:30:00-05:00").toISOString()).toBe(
      "2026-01-05T14:30:00.000Z",
    );
  });
});
