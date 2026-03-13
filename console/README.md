# Nanobot Web 控制台前端

使用 React + TypeScript + Vite 构建。构建产物由 `nanobot dashboard` 自动托管。

## 开发

```bash
npm install
npm run dev
```

开发时 Vite 会将 `/api` 代理到 `http://127.0.0.1:18791`，需同时运行：

```bash
nanobot dashboard
```

## 生产构建

```bash
npm run build
```

在项目根目录执行 `nanobot dashboard` 时，会自动使用本目录下的 `dist/` 作为静态资源。
