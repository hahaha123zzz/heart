/** 在首次绘制时应用已确认的白灰主题，覆盖旧浏览器偏好。 */
export default function ThemeScript() {
  return (
    <script
      dangerouslySetInnerHTML={{ __html: `
        document.documentElement.classList.remove('dark', 'theme-glass');
        document.documentElement.classList.add('theme-snow');
        try { localStorage.setItem('deeptutor-theme', 'snow'); } catch {}
      ` }}
      suppressHydrationWarning
    />
  );
}
