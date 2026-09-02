// ====== Code Summary ======
// Minimal flat ESLint config (ESLint 9). Its ENTIRE job is the gate persona demand: catch a
// Rules-of-Hooks violation (a custom/built-in hook called after a conditional early-return, or
// inside a condition/loop) at lint time instead of letting it crash the app at runtime — see the
// CollectionOverview incident this config exists to prevent. `exhaustive-deps` stays a warning
// (useful signal, not a release blocker) so it never blocks the gate on a legitimately-scoped
// dependency array.

import js from "@eslint/js";
import reactHooks from "eslint-plugin-react-hooks";
import tseslint from "typescript-eslint";

export default tseslint.config(
  { ignores: ["dist/**", "node_modules/**", "scripts/**", ".vite/**"] },
  js.configs.recommended,
  ...tseslint.configs.recommended,
  {
    files: ["src/**/*.{ts,tsx}"],
    plugins: { "react-hooks": reactHooks },
    rules: {
      "react-hooks/rules-of-hooks": "error",
      "react-hooks/exhaustive-deps": "warn",
      // Type-only params/locals are common in this codebase's typed API layer; tsc already
      // enforces unused-var hygiene (noUnusedLocals/noUnusedParameters) so this rule would only
      // duplicate that check with a less precise (JS-only) analysis.
      "@typescript-eslint/no-unused-vars": "off",
    },
  },
);
