const styles = {
  active: 'bg-green-500',
  success: 'bg-green-500',
  provisioned: 'bg-green-500',
  synced: 'bg-green-500',
  inactive: 'bg-amber-500',
  pending: 'bg-amber-500',
  not_requested: 'bg-slate-400',
  expired: 'bg-red-500',
  failed: 'bg-red-500',
  error: 'bg-red-500',
};

export default function StatusBadge({ status }) {
  const normalized = String(status || 'inactive').toLowerCase();

  return (
    <span className="inline-flex items-center gap-1.5 rounded-full border border-slate-200 bg-white px-2.5 py-1 text-xs font-medium text-slate-700">
      <span className={`h-1.5 w-1.5 rounded-full ${styles[normalized] || styles.inactive}`} />
      {normalized.replaceAll('_', ' ')}
    </span>
  );
}
