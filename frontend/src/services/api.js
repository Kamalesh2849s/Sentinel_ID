import axios from 'axios'

const API_BASE = import.meta.env.VITE_API_URL || 'http://localhost:8000'

const api = axios.create({
  baseURL: API_BASE,
  timeout: 120000, // 2 minutes for long processing
})

// Attach JWT token to every request
api.interceptors.request.use((config) => {
  const token = localStorage.getItem('sentinel_token')
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

// Handle 401 — clear token and redirect to login
api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      localStorage.removeItem('sentinel_token')
      localStorage.removeItem('sentinel_user')
      window.location.href = '/login'
    }
    return Promise.reject(error)
  }
)

// ─── Auth ─────────────────────────────────────────────────────────────────────
export const authApi = {
  login: (username, password) =>
    api.post('/api/auth/login', { username, password }),
}

// ─── Screenings ───────────────────────────────────────────────────────────────
export const screeningsApi = {
  create: (formData) =>
    api.post('/api/screenings', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    }),

  list: (params = {}) =>
    api.get('/api/screenings', { params }),

  get: (id) =>
    api.get(`/api/screenings/${id}`),

  reprocess: (id) =>
    api.post(`/api/screenings/${id}/reprocess`),
}

// ─── Dashboard ────────────────────────────────────────────────────────────────
export const dashboardApi = {
  getStats: () => api.get('/api/dashboard/statistics'),
}

// ─── Identity & Liveness ──────────────────────────────────────────────────────
export const identityApi = {
  start: (id) =>
    api.post(`/api/screenings/${id}/identity/start`),

  checkLiveness: (id, payload, isMultipart = false) => {
    if (isMultipart) {
      return api.post(`/api/screenings/${id}/identity/liveness`, payload, {
        headers: { 'Content-Type': 'multipart/form-data' },
      })
    }
    return api.post(`/api/screenings/${id}/identity/liveness`, payload)
  },

  checkFace: (id, payload, isMultipart = false) => {
    if (isMultipart) {
      return api.post(`/api/screenings/${id}/identity/face`, payload, {
        headers: { 'Content-Type': 'multipart/form-data' },
      })
    }
    return api.post(`/api/screenings/${id}/identity/face`, payload)
  },

  verify: (id, payload, isMultipart = false) => {
    if (isMultipart) {
      return api.post(`/api/screenings/${id}/identity/verify`, payload, {
        headers: { 'Content-Type': 'multipart/form-data' },
      })
    }
    return api.post(`/api/screenings/${id}/identity/verify`, payload)
  },

  get: (id) =>
    api.get(`/api/screenings/${id}/identity`),
}

// ─── Health ───────────────────────────────────────────────────────────────────
export const healthApi = {
  check: () => api.get('/api/health'),
}

export default api
