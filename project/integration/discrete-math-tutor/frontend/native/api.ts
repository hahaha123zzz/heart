export function apiUrl(value:string) {
 if(value.startsWith('/api/deeptutor/tasks/') || value.startsWith('/static/')) return value;
 throw new Error('原生文件尚未获得宿主授权');
}
