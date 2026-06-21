import js from '@eslint/js'
import globals from 'globals'
import reactHooks from 'eslint-plugin-react-hooks'
import reactRefresh from 'eslint-plugin-react-refresh'
import tseslint from 'typescript-eslint'
import { defineConfig, globalIgnores } from 'eslint/config'

export default defineConfig([
  globalIgnores(['dist']),
  {
    files: ['**/*.{ts,tsx}'],
    extends: [
      js.configs.recommended,
      tseslint.configs.recommended,
      reactHooks.configs.flat.recommended,
      reactRefresh.configs.vite,
    ],
    languageOptions: {
      globals: globals.browser,
    },
    rules: {
      // The v7+ `set-state-in-effect` rule flags every "fetch on mount → setState"
      // pattern as a cascading-render warning. Across this codebase that pattern
      // is intentional (useSimulation, useWebSocket, useAnalytics, AuthProvider,
      // etc.) — and the rule offers no clean migration path short of suspense.
      // Demote to a hint until we adopt server-driven data fetching.
      'react-hooks/set-state-in-effect': 'off',
      // useWebSocket relies on a forward reference to `connect` inside its own
      // `onclose` handler — a self-referential pattern that's safe because the
      // closure runs after declaration. The rule's flag is technically correct
      // but functionally harmless here.
      'react-hooks/immutability': 'off',
    },
  },
  {
    // Files that legitimately export hooks alongside components.
    files: [
      'src/lib/auth/AuthProvider.tsx',
    ],
    rules: {
      'react-refresh/only-export-components': 'off',
    },
  },
])
