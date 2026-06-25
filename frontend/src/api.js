// Thin fetch wrappers around the Studio API. All paths are same-origin
// (Vite proxies /api to the backend during development).

async function req(method, path, body, isForm = false) {
  const opts = { method, headers: {} };
  if (body !== undefined) {
    if (isForm) {
      opts.body = body;
    } else {
      opts.headers["Content-Type"] = "application/json";
      opts.body = JSON.stringify(body);
    }
  }
  const res = await fetch(`/api${path}`, opts);
  const text = await res.text();
  const data = text ? JSON.parse(text) : null;
  if (!res.ok) {
    const detail = data && data.detail ? data.detail : res.statusText;
    throw new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
  }
  return data;
}

export const api = {
  health: () => req("GET", "/health"),
  templates: () => req("GET", "/templates"),
  template: (key) => req("GET", `/templates/${key}`),
  validate: (design) => req("POST", "/designs/validate", { design }),
  previewOutcome: (b) => req("POST", "/designs/preview-outcome", b),
  previewPrior: (b) => req("POST", "/designs/preview-prior", b),

  createProject: (b) => req("POST", "/projects", b),
  listProjects: () => req("GET", "/projects"),
  getProject: (id) => req("GET", `/projects/${id}`),
  updateDesign: (id, design) => req("PUT", `/projects/${id}/design`, { design }),
  deleteProject: (id) => req("DELETE", `/projects/${id}`),

  uploadData: (id, file) => {
    const fd = new FormData();
    fd.append("file", file);
    return req("POST", `/projects/${id}/data/upload`, fd, true);
  },
  commitData: (id, b) => req("POST", `/projects/${id}/data/commit`, b),
  profileData: (id) => req("POST", `/projects/${id}/data/profile`),
  commitDataAuto: (id, b) => req("POST", `/projects/${id}/data/commit-auto`, b),

  startFit: (id, b) => req("POST", `/projects/${id}/fit`, b),
  fitStatus: (id) => req("GET", `/projects/${id}/status`),

  generate: (id, b) => req("POST", `/projects/${id}/generate`, b),
  downloadUrl: (id, name) => `/api/projects/${id}/download/${name}`,
};
