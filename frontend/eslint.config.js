import js from '@eslint/js';
import tseslint from 'typescript-eslint';
import hooks from 'eslint-plugin-react-hooks';
import globals from 'globals';

const testImports = {
  group: [
    '**/tests/**',
    'vitest',
    'vitest/*',
    '@testing-library/*',
    '@playwright/test',
    '**/*.test',
    '**/*.test.*',
    '**/*.spec',
    '**/*.spec.*',
    '**/test-setup',
    '**/test-setup.*',
  ],
  message: 'Keep test helpers and test libraries outside the application import graph.',
};
const featureImports = {
  group: ['**/features/**', '**/app/**'],
  message: 'Shared utilities and UI must not depend on feature or application modules.',
};

export default tseslint.config(
  { ignores: ['dist', 'playwright-report', 'test-results'] },
  js.configs.recommended,
  ...tseslint.configs.recommended,
  { files: ['scripts/*.mjs'], languageOptions: { globals: globals.node } },
  {
    files: ['**/*.{ts,tsx}'],
    languageOptions: { globals: { ...globals.browser, ...globals.node } },
    plugins: { 'react-hooks': hooks },
    rules: hooks.configs.recommended.rules,
  },
  {
    files: ['src/**/*.{ts,tsx}'],
    rules: {
      curly: ['error', 'all'],
      'no-restricted-imports': ['error', { patterns: [testImports] }],
    },
  },
  {
    files: ['src/lib/**/*.{ts,tsx}', 'src/components/**/*.{ts,tsx}'],
    rules: {
      'no-restricted-imports': ['error', { patterns: [testImports, featureImports] }],
    },
  },
);
