/**
 * 文档 & 切片 API
 */
import request from './index'
import type { DocumentInfo, DocumentListResponse, DocumentFilterParams, ChunkListResponse, ChunkDetail } from '@/types/document'

/** 上传文档 */
export function uploadDocumentApi(
  kbId: number,
  file: File,
  chunkStrategy: string,
  onProgress?: (percent: number) => void
): Promise<DocumentInfo> {
  const formData = new FormData()
  formData.append('upload_file', file)
  // query params handled via URL
  const url = `/documents/upload?kb_id=${kbId}&chunk_strategy=${chunkStrategy}`

  return request.post(url, formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
    onUploadProgress: (event) => {
      if (onProgress && event.total) {
        onProgress(Math.round((event.loaded * 100) / event.total))
      }
    },
  })
}

/** 文档列表 */
export function listDocumentsApi(params: DocumentFilterParams): Promise<DocumentListResponse> {
  return request.get('/documents', { params })
}

/** 文档详情 */
export function getDocumentApi(documentId: number): Promise<DocumentInfo> {
  return request.get(`/documents/${documentId}`)
}

/** 删除文档 */
export function deleteDocumentApi(documentId: number): Promise<{ detail: string; id: number }> {
  return request.delete(`/documents/${documentId}`)
}

/** 获取文档切片列表 (预览) */
export function listDocumentChunksApi(
  documentId: number,
  page: number = 1,
  pageSize: number = 20
): Promise<ChunkListResponse> {
  return request.get(`/chunks/document/${documentId}`, {
    params: { page, page_size: pageSize },
  })
}

/** 获取切片详情 */
export function getChunkDetailApi(chunkId: number): Promise<ChunkDetail> {
  return request.get(`/chunks/${chunkId}`)
}

/** 文档预览 */
export interface DocumentPreviewResponse {
  type: 'pdf' | 'html' | 'text'
  data: string
  filename: string
}

export function previewDocumentApi(documentId: number): Promise<DocumentPreviewResponse> {
  return request.get(`/documents/${documentId}/preview`)
}
