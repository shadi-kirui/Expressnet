import { Link } from 'react-router-dom';

export default function NotFound() {
  return (
    <section className="rounded-xl border border-slate-200 bg-white p-10 text-center shadow-sm">
      <h1 className="text-xl font-semibold text-slate-900">Page not found</h1>
      <p className="mt-2 text-sm text-slate-500">The page you are looking for does not exist in this tenant portal.</p>
      <Link to="/dashboard" className="btn-primary mt-5 inline-flex">Back to dashboard</Link>
    </section>
  );
}
