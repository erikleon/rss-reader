import { describe, expect, it } from "vitest";
import { formatRelative } from "./datetime";

const NOW = new Date("2026-02-01T12:00:00Z");

describe("formatRelative", () => {
  it("shows 'just now' for very recent times", () => {
    expect(formatRelative("2026-02-01T11:59:40", NOW)).toBe("just now");
  });

  it("shows minutes", () => {
    expect(formatRelative("2026-02-01T11:30:00", NOW)).toBe("30m ago");
  });

  it("shows hours", () => {
    expect(formatRelative("2026-02-01T09:00:00", NOW)).toBe("3h ago");
  });

  it("shows days", () => {
    expect(formatRelative("2026-01-30T12:00:00", NOW)).toBe("2d ago");
  });

  it("shows weeks", () => {
    expect(formatRelative("2026-01-18T12:00:00", NOW)).toBe("2w ago");
  });

  it("falls back to an absolute date when far in the past", () => {
    expect(formatRelative("2025-06-01T12:00:00", NOW)).toMatch(/2025/);
  });
});
