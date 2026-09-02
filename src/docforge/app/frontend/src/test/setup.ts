// Vitest global setup — extends `expect` with jest-dom's DOM matchers for every test file.
import "@testing-library/jest-dom/vitest";

import { cleanup } from "@testing-library/react";
import { afterEach } from "vitest";

// RTL's auto-cleanup-after-each relies on a global test framework being detected; this project
// runs vitest WITHOUT `test.globals` (explicit imports everywhere, matching the codebase's
// explicit-over-implicit convention), so that auto-registration never fires — wire it manually or
// every test file's DOM leaks into the next one within the same file.
afterEach(cleanup);
