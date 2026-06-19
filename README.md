# SiteIQ — Construction Site Intelligence

Real-time construction site monitoring and optimization demo. Uses a simulation engine to generate asset position data, compute waste analytics, and prescribe operational fixes.

## Quick Start

### Backend
```bash
cd backend
uv sync
uv run uvicorn main:app --host 0.0.0.0 --port 8000
```

### Frontend
```bash
cd frontend
npm install
npm run dev
```

Open http://localhost:5173

## Architecture

- **Backend**: Python/FastAPI with in-memory simulation engine running at 10Hz, managed by `uv`
- **Frontend**: React/TypeScript/Vite with HTML5 Canvas rendering and Tailwind CSS
- **Communication**: WebSocket for real-time position + analytics streaming, REST for recommendations and controls

## Demo Flow

1. Site loads with 50 workers, 3 equipment pieces, and deliberately suboptimal facility placement
2. Watch workers walk absurd distances to toilets (placed in far corners)
3. Toggle "Trails" to see movement patterns — long diagonal lines are the waste
4. Switch to "Recommendations" tab and click "Apply All"
5. Watch facilities relocate, paths shorten, and waste numbers drop in real time
