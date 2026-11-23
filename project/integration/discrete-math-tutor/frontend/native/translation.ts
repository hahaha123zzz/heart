import translations from '@/locales/zh/app.json';
import common from '@/locales/zh/common.json';
export function useTranslation() {
 return {t:(key:string,values:Record<string,unknown>={})=>String(translations[key] || common[key] || key)
  .replace(/\{\{([^}]+)\}\}/g,(_,name)=>String(values[name] ?? ''))};
}
