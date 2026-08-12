/** 全局类型声明 */

/** file-saver 模块声明 */
declare module 'file-saver' {
  export function saveAs(data: Blob | string, filename?: string): void
}
