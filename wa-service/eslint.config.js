const nodeGlobals = Object.fromEntries(
  [
    "process", "console", "Buffer", "setTimeout", "clearTimeout", "setInterval", "clearInterval",
    "setImmediate", "fetch", "AbortController", "URL", "URLSearchParams", "WebAssembly",
    "TextEncoder", "TextDecoder", "structuredClone", "queueMicrotask",
  ].map((g) => [g, "readonly"])
);

export default [
  { ignores: ["node_modules/**", "auth/**", "uploads/**"] },
  {
    files: ["**/*.js"],
    languageOptions: { ecmaVersion: 2023, sourceType: "module", globals: nodeGlobals },
    rules: {
      "no-undef": "error",
      "no-unused-vars": ["warn", { argsIgnorePattern: "^_", varsIgnorePattern: "^_" }],
    },
  },
];
