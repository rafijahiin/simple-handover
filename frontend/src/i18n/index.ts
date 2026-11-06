/**
 * i18n initialisation — i18next + react-i18next.
 *
 * Two languages: 'en' (default) and 'bn' (Bengali). Selection persists
 * to localStorage under key 'lang'. Bengali values are intentionally
 * empty strings until the supervisor confirms wording post-workshop —
 * i18next's `returnEmptyString: false` falls back to English whenever
 * a 'bn' key resolves to ''.
 *
 * Components consume strings via `useTranslation()` from react-i18next,
 * and the global toggle in <Spine> flips between languages without a
 * page reload via i18n.changeLanguage().
 */
import i18n from 'i18next'
import { initReactI18next } from 'react-i18next'

import en from './en.json'
import bn from './bn.json'

export type Lang = 'en' | 'bn'

const STORAGE_KEY = 'lang'

function detectLang(): Lang {
  if (typeof window === 'undefined') return 'en'
  const stored = window.localStorage.getItem(STORAGE_KEY)
  return stored === 'bn' ? 'bn' : 'en'
}

i18n
  .use(initReactI18next)
  .init({
    resources: {
      en: { translation: en },
      bn: { translation: bn },
    },
    lng: detectLang(),
    fallbackLng: 'en',
    // Bengali values are empty strings until workshop sign-off. We want
    // i18next to treat '' as missing and fall back to English so the UI
    // never renders a blank label.
    returnEmptyString: false,
    interpolation: {
      escapeValue: false, // React already escapes
    },
  })

/** Mirror i18n state onto <html lang="…"> so font fallback rules and
 *  screen readers pick up the right language. Called once on init and
 *  on every successful changeLanguage(). */
function syncHtmlLang(lang: string) {
  if (typeof document !== 'undefined') {
    document.documentElement.lang = lang
  }
}
syncHtmlLang(detectLang())
i18n.on('languageChanged', syncHtmlLang)

/** Persist language to localStorage and switch i18next without reload. */
export function setLanguage(lang: Lang) {
  if (typeof window !== 'undefined') {
    window.localStorage.setItem(STORAGE_KEY, lang)
  }
  void i18n.changeLanguage(lang)
}

export default i18n
