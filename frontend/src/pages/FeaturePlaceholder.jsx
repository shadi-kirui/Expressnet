import { Clock3 } from 'lucide-react';

export default function FeaturePlaceholder({ title, description }) {
  return (
    <div className="space-y-4">
      <section className="surface-card p-5">
        <div className="flex items-center gap-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-md bg-app-navy text-white">
            <Clock3 size={20} />
          </div>
          <div>
            <h1 className="page-title">{title}</h1>
            <p className="page-subtitle">{description}</p>
          </div>
        </div>
      </section>

      <section className="surface-card p-5">
        <p className="text-sm font-medium text-slate-700">
          This workspace is ready for the next build step. Existing customer, package, payment, MikroTik, and Roamtech message settings remain available from the sidebar.
        </p>
      </section>
    </div>
  );
}
