{
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
}

import { enUS } from 'date-fns/locale';

let cachedLocale = enUS;
let initialized = false;

const LOCALE_MAP = {
    'en-US': () => import('date-fns/locale/en-US'),
    'en-GB': () => import('date-fns/locale/en-GB'),
    'en-AU': () => import('date-fns/locale/en-AU'),
    'en-CA': () => import('date-fns/locale/en-CA'),
    'en-IN': () => import('date-fns/locale/en-IN'),
    'en-NZ': () => import('date-fns/locale/en-NZ'),
    'en-IE': () => import('date-fns/locale/en-IE'),
    'en-ZA': () => import('date-fns/locale/en-ZA'),
    'pt-BR': () => import('date-fns/locale/pt-BR'),
    pt: () => import('date-fns/locale/pt'),
    es: () => import('date-fns/locale/es'),
    fr: () => import('date-fns/locale/fr'),
    de: () => import('date-fns/locale/de'),
    it: () => import('date-fns/locale/it'),
    ja: () => import('date-fns/locale/ja'),
    ko: () => import('date-fns/locale/ko'),
    'zh-CN': () => import('date-fns/locale/zh-CN'),
    'zh-TW': () => import('date-fns/locale/zh-TW'),
    ru: () => import('date-fns/locale/ru'),
    ar: () => import('date-fns/locale/ar'),
    he: () => import('date-fns/locale/he'),
    hi: () => import('date-fns/locale/hi'),
    nl: () => import('date-fns/locale/nl'),
    pl: () => import('date-fns/locale/pl'),
    sv: () => import('date-fns/locale/sv'),
    da: () => import('date-fns/locale/da'),
    fi: () => import('date-fns/locale/fi'),
    nb: () => import('date-fns/locale/nb'),
    tr: () => import('date-fns/locale/tr'),
    th: () => import('date-fns/locale/th'),
    vi: () => import('date-fns/locale/vi'),
    uk: () => import('date-fns/locale/uk'),
    cs: () => import('date-fns/locale/cs'),
    ro: () => import('date-fns/locale/ro'),
    hu: () => import('date-fns/locale/hu'),
    el: () => import('date-fns/locale/el'),
    id: () => import('date-fns/locale/id'),
    ms: () => import('date-fns/locale/ms'),
};

function findLocaleImporter(browserLocale) {
    if (LOCALE_MAP[browserLocale]) {
        return LOCALE_MAP[browserLocale];
    }

    const langOnly = browserLocale.split('-')[0];
    if (LOCALE_MAP[langOnly]) {
        return LOCALE_MAP[langOnly];
    }

    return null;
}

export async function initDateLocale() {
    if (initialized) return;

    const browserLocale = navigator.language;
    const importer = findLocaleImporter(browserLocale);

    if (importer) {
        try {
            const mod = await importer();
            cachedLocale = mod.default || mod;
        } catch {
            // Keep enUS fallback
        }
    }

    initialized = true;
}

export function getDateLocale() {
    return cachedLocale;
}
