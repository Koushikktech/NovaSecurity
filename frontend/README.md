# NovaSecurity — Frontend Console

A sleek, cyberpunk-inspired security operations dashboard built with Next.js 16 (App Router), React 19, Tailwind CSS v4, and Framer Motion.

---

## 🎨 UI & Features

- **Hero & Target Input**:
  - Direct repository input supporting GitHub HTTP(S) and SSH URLs.
  - One-click benchmark demo presets (`lets-be-bad-guys`, `vulpy`) for instant showcase without API credentials.
- **Real-Time Scanning Visualizer (`ScanningSequence.tsx`)**:
  - Live Server-Sent Events (SSE) connection streaming current pipeline phase and progress.
  - Multi-agent pixel-art sprites and animated data stream particles.
  - Virtualized terminal STDOUT log stream displaying agent messages and task statuses.
- **Interactive Security Report (`ReportView.tsx`)**:
  - **Risk Assessment Metrics**: Overall security risk score gauge, severity distribution badges (Critical, High, Medium, Low), and finding tallies.
  - **Taint Flow & Graph Visualizer**: Interactive force-directed graph displaying source-to-sink data flow paths with attack routes highlighted in red.
  - **Findings Dossier (`FindingCard.tsx`)**: Filter findings by severity, view CWE IDs, line numbers, affected code snippets, and confidence scores.
  - **Adversarial Analysis Panel**: Inspect Red Team exploit PoC scripts and Blue Team defense refutations side-by-side.
- **Automated Remediation & Diff Viewer (`DiffViewer.tsx`, `Modal.tsx`)**:
  - Side-by-side and unified git diff preview of proposed fixes.
  - Detailed architectural rationale and suggested verification tests.
  - One-click GitHub Pull Request creation and branch comparison links.

---

## 🛠️ Tech Stack

- **Framework**: Next.js 16.1 (App Router)
- **Library**: React 19.2
- **Styling**: Tailwind CSS v4
- **Animations**: Framer Motion 12
- **Icons**: Lucide React
- **Package Manager**: Bun / npm

---

## 🚀 Getting Started

### Prerequisites
- Node.js 20+ or Bun

### Installation
```bash
cd frontend

# Using bun
bun install

# Or using npm
npm install
```

### Environment Configuration
Copy `.env.example` to `.env.local`:
```bash
cp .env.example .env.local
```
Set `NEXT_PUBLIC_API_URL` to your backend address (defaults to `http://localhost:8000`):
```env
NEXT_PUBLIC_API_URL=http://localhost:8000
```

### Run the Development Server
```bash
bun dev
# or npm run dev
```
Open [http://localhost:3000](http://localhost:3000) in your browser.

---

## 📁 Component Structure

```
frontend/app/
├── components/
│   ├── ui/
│   │   ├── Hero.tsx               # Main hero section with URL input & demo triggers
│   │   └── Modal.tsx              # Remediation drawer/modal dialog
│   ├── scan/
│   │   ├── ScanningSequence.tsx   # Real-time multi-agent scan visualizer
│   │   └── ScanningBackdrop.tsx   # Atmospheric background canvas effects
│   └── report/
│       ├── ReportView.tsx         # Executive dashboard, metrics & graph views
│       ├── FindingCard.tsx        # Finding details, PoC & defense badges
│       └── DiffViewer.tsx         # Code patch diff viewer with line highlights
├── hooks/
│   ├── useScan.ts                 # Scan state machine & SSE connection hook
│   └── useFixes.ts                # Remediation polling & PR workflow hook
├── lib/
│   ├── api.ts                     # Type-safe API client & SSE parser
│   └── types.ts                   # Domain types & interfaces
├── globals.css                    # Tailwind CSS v4 theme & custom utilities
├── layout.tsx                     # Root HTML layout & font definitions
└── page.tsx                       # Main page view state controller
```
