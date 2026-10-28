import { describe, expect, it } from "vitest";
import { routeFromPath } from "./route";

describe("routeFromPath", () => {
  it("finds the two app routes", () => {
    expect(routeFromPath("/author")).toBe("author");
    expect(routeFromPath("/explore/")).toBe("explore");
    expect(routeFromPath("/explore/abc")).toBe("explore");
  });
  it("sends everything else home", () => {
    expect(routeFromPath("/")).toBe("home");
    expect(routeFromPath("")).toBe("home");
    expect(routeFromPath("/authors")).toBe("home");
  });
});
