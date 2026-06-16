export default function StatCard({ label, value }) {
  return (
    <section className="surface-card p-5">
      <p className="text-[32px] font-medium leading-none text-slate-950">{value}</p>
      <p className="mt-2 text-[11px] font-medium uppercase tracking-wide text-slate-500">{label}</p>
    </section>
  );
}
