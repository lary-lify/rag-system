/**
 * Excel 导出工具组合式函数
 */
import * as XLSX from 'xlsx'
import { saveAs } from 'file-saver'

export function useExport() {
  /**
   * 通用导出 Excel
   * @param data 数据数组
   * @param columns 列定义 [{ header: '表头', key: '字段名', width?: 20 }]
   * @param filename 文件名 (不含扩展名)
   * @param sheetName 工作表名
   */
  function exportToExcel(
    data: Record<string, unknown>[],
    columns: { header: string; key: string; width?: number }[],
    filename: string,
    sheetName: string = 'Sheet1'
  ) {
    // 提取列的表头和数据
    const headers = columns.map((c) => c.header)
    const keys = columns.map((c) => c.key)

    const rows = data.map((item) => keys.map((key) => item[key] ?? ''))

    const worksheet = XLSX.utils.aoa_to_sheet([headers, ...rows])

    // 设置列宽
    const colWidths = columns.map((c) => ({ wch: c.width || 20 }))
    worksheet['!cols'] = colWidths

    const workbook = XLSX.utils.book_new()
    XLSX.utils.book_append_sheet(workbook, worksheet, sheetName)

    const excelBuffer = XLSX.write(workbook, {
      bookType: 'xlsx',
      type: 'array',
    })

    const blob = new Blob([excelBuffer], {
      type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    })
    saveAs(blob, `${filename}.xlsx`)
  }

  /**
   * CSV 导出
   */
  function exportToCSV(
    data: Record<string, unknown>[],
    columns: { header: string; key: string }[],
    filename: string
  ) {
    const headers = columns.map((c) => c.header)
    const keys = columns.map((c) => c.key)

    const rows = data.map((item) =>
      keys
        .map((key) => {
          const val = item[key] ?? ''
          // CSV特殊字符转义
          const str = String(val)
          if (str.includes(',') || str.includes('"') || str.includes('\n')) {
            return `"${str.replace(/"/g, '""')}"`
          }
          return str
        })
        .join(',')
    )

    const csvContent = '\uFEFF' + [headers.join(','), ...rows].join('\n')
    const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8' })
    saveAs(blob, `${filename}.csv`)
  }

  return { exportToExcel, exportToCSV }
}
