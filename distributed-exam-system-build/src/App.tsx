export default function App() {
  return (
    <div className="min-h-screen bg-slate-950 text-slate-100">
      <main className="relative isolate overflow-hidden">
        <div className="absolute inset-0 bg-[radial-gradient(circle_at_20%_10%,rgba(99,102,241,0.45),transparent_48%),radial-gradient(circle_at_80%_20%,rgba(56,189,248,0.28),transparent_42%),linear-gradient(to_bottom,#020617,#0f172a)]" />
        <section className="relative mx-auto flex min-h-screen max-w-6xl items-center px-6 py-20">
          <div className="max-w-3xl space-y-6">
            <p className="text-xs tracking-[0.24em] text-indigo-200/90 uppercase">Distributed Exam Platform</p>
            <h1 className="text-4xl font-semibold leading-tight tracking-tight sm:text-6xl">ExamSphere</h1>
            <p className="max-w-2xl text-base text-slate-300 sm:text-lg">
              Flask backend, JSON distributed storage, role-based dashboards, timed exams, evaluation workflow,
              and Google OAuth are implemented in this repository.
            </p>
            <div className="flex flex-wrap gap-3">
              <a
                href="http://127.0.0.1:5000"
                className="rounded-md bg-indigo-500 px-5 py-2.5 font-medium text-white transition hover:bg-indigo-400"
              >
                Open Flask App
              </a>
              <a
                href="/README.md"
                className="rounded-md border border-slate-700 bg-slate-900/50 px-5 py-2.5 font-medium text-slate-200 transition hover:bg-slate-800"
              >
                Setup Guide
              </a>
            </div>
            <p className="text-sm text-slate-400">Default seeded users are documented in README.md.</p>
          </div>
        </section>
      </main>
    </div>
  );
}
