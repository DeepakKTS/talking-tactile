import { mkdtempSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { pathToFileURL } from "node:url";
import { describe, expect, it } from "vitest";
import { phoneHttps } from "../vite.config";

describe("npm run dev:phone", () => {
  const dir = mkdtempSync(join(tmpdir(), "certs-"));
  const url = pathToFileURL(`${dir}/`);

  it("serves plain HTTP unless HTTPS=1", () => {
    expect(phoneHttps({}, url)).toBeUndefined();
  });

  it("says how to make the certificate when it is missing", () => {
    expect(() => phoneHttps({ HTTPS: "1" }, url)).toThrow("run npm run cert:phone");
  });

  it("reads the certificate and key from the folder", () => {
    writeFileSync(join(dir, "phone.pem"), "CERT");
    writeFileSync(join(dir, "phone-key.pem"), "KEY");
    const got = phoneHttps({ HTTPS: "1" }, url);
    expect(got?.cert.toString()).toBe("CERT");
    expect(got?.key.toString()).toBe("KEY");
  });
});
