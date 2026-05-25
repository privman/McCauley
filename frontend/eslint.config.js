import js from "@eslint/js";
import tseslint from "@typescript-eslint/eslint-plugin";
import tsParser from "@typescript-eslint/parser";
import react from "eslint-plugin-react";
import reactHooks from "eslint-plugin-react-hooks";
import jsxA11y from "eslint-plugin-jsx-a11y";
import globals from "globals";

export default [
  { ignores: ["dist/", "build/", ".vite/", "node_modules/"] },
  js.configs.recommended,
  {
    files: ["**/*.{ts,tsx}"],
    languageOptions: {
      parser: tsParser,
      parserOptions: {
        ecmaVersion: "latest",
        sourceType: "module",
        ecmaFeatures: { jsx: true },
      },
      globals: { ...globals.browser, ...globals.es2024 },
    },
    plugins: {
      "@typescript-eslint": tseslint,
      react,
      "react-hooks": reactHooks,
      "jsx-a11y": jsxA11y,
    },
    rules: {
      ...tseslint.configs.recommended.rules,
      ...react.configs.recommended.rules,
      ...reactHooks.configs.recommended.rules,
      // React 18+ with the automatic JSX runtime — no need to import React in scope.
      "react/react-in-jsx-scope": "off",
      // TypeScript already covers prop validation.
      "react/prop-types": "off",
      // TypeScript also covers undefined-identifier checks more accurately
      // (with DOM/Node lib types), so the base no-undef rule double-fires
      // on globals like `RequestInit`, `__dirname`, etc.
      "no-undef": "off",
      // The HTML-entity strictness adds noise without catching real bugs —
      // apostrophes in user-facing strings are fine.
      "react/no-unescaped-entities": "off",
      // Vars / args / caught errors prefixed with _ are intentionally unused.
      "@typescript-eslint/no-unused-vars": [
        "error",
        {
          argsIgnorePattern: "^_",
          varsIgnorePattern: "^_",
          caughtErrorsIgnorePattern: "^_",
        },
      ],
      // typescript-eslint's version replaces the base rule; turn the base
      // off so the two don't fire in tandem.
      "no-unused-vars": "off",
    },
    settings: { react: { version: "detect" } },
  },
];
