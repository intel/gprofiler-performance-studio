/*
 * Copyright (C) 2023 Intel Corporation
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *    http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */

const js = require('@eslint/js');
const react = require('eslint-plugin-react');
const reactHooks = require('eslint-plugin-react-hooks');
const simpleImportSort = require('eslint-plugin-simple-import-sort');
const prettier = require('eslint-plugin-prettier');
const eslintConfigPrettier = require('eslint-config-prettier');

module.exports = [
    js.configs.recommended,
    {
        files: ['**/*.{js,jsx}'],
        languageOptions: {
            ecmaVersion: 12,
            sourceType: 'module',
            parserOptions: {
                ecmaFeatures: {
                    jsx: true,
                },
            },
            globals: {
                // Browser globals
                window: 'readonly',
                document: 'readonly',
                navigator: 'readonly',
                console: 'readonly',
                localStorage: 'readonly',
                sessionStorage: 'readonly',
                fetch: 'readonly',
                setTimeout: 'readonly',
                clearTimeout: 'readonly',
                setInterval: 'readonly',
                clearInterval: 'readonly',
                URL: 'readonly',
                URLSearchParams: 'readonly',
                FormData: 'readonly',
                XMLHttpRequest: 'readonly',
                // ES2021 globals
                Promise: 'readonly',
                Symbol: 'readonly',
                WeakMap: 'readonly',
                WeakSet: 'readonly',
                Map: 'readonly',
                Set: 'readonly',
                Proxy: 'readonly',
                Reflect: 'readonly',
                // Common Node.js globals that might be used
                process: 'readonly',
                module: 'readonly',
                require: 'readonly',
                exports: 'readonly',
                __dirname: 'readonly',
                __filename: 'readonly',
            },
        },
        plugins: {
            react,
            'react-hooks': reactHooks,
            'simple-import-sort': simpleImportSort,
            prettier,
        },
        settings: {
            react: {
                createClass: 'createReactClass',
                pragma: 'React',
                fragment: 'Fragment',
                version: 'detect',
            },
        },
        rules: {
            ...react.configs.recommended.rules,
            ...reactHooks.configs.recommended.rules,
            'prettier/prettier': 'error',
            'react-hooks/rules-of-hooks': 'error',
            'react/react-in-jsx-scope': 'off',
            'react/no-unescaped-entities': 'off',
            'react-hooks/exhaustive-deps': 'warn',
            'no-use-before-define': 'off',
            'no-extra-boolean-cast': 'warn',
            'no-dupe-else-if': 'warn',
            'no-case-declarations': 'off',
            'react/jsx-key': 'warn',
            'no-prototype-builtins': 'warn',
            'react/display-name': 'warn',
            'react/prop-types': 0,
            '@typescript-eslint/no-use-before-define': 'off',
            'no-unused-vars': 'off',
            'react/jsx-pascal-case': [
                1,
                {
                    allowNamespace: true,
                },
            ],
            'simple-import-sort/exports': 'warn',
            'simple-import-sort/imports': 'warn',
            ...eslintConfigPrettier.rules,
        },
    },
    {
        files: ['**/*.stories.*'],
        rules: {
            'import/no-anonymous-default-export': 'off',
        },
    },
];
