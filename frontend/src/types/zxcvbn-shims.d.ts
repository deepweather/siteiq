/**
 * The `language-common` and `language-en` packages don't declare the
 * deep entry paths in their `package.json#exports`, so TypeScript
 * doesn't know what's there. We import the deep paths to skip the
 * heavyweight default `dictionary` export and only bring in the JSON
 * slices we need (see `PasswordField.tsx`). These shims keep tsc
 * happy without a full type definition for each JSON.
 */
declare module '@zxcvbn-ts/language-common/dist/adjacencyGraphs.json.mjs' {
  const value: Record<string, unknown>;
  export default value;
}
declare module '@zxcvbn-ts/language-en/dist/commonWords.json.mjs' {
  const value: string[];
  export default value;
}
declare module '@zxcvbn-ts/language-en/dist/firstnames.json.mjs' {
  const value: string[];
  export default value;
}
declare module '@zxcvbn-ts/language-en/dist/wordSequences.json.mjs' {
  const value: string[];
  export default value;
}
declare module '@zxcvbn-ts/language-en/dist/translations.mjs' {
  const value: unknown;
  export default value;
}
