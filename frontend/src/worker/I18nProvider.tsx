/** i18n provider component. Logic + hook live in `i18n.ts`; this file
 *  exports only the component (keeps React Fast Refresh happy). */
import type { ReactNode } from 'react';
import { I18nContext, useI18nValue } from './i18n';

export function I18nProvider({ children }: { children: ReactNode }) {
  const value = useI18nValue();
  return <I18nContext.Provider value={value}>{children}</I18nContext.Provider>;
}
