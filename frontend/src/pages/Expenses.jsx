import { ChevronDown, Eye, Pencil, Plus, Search } from 'lucide-react';
import { useMemo, useState } from 'react';
import toast from 'react-hot-toast';

const initialExpenses = [
  { id: 'EXP-001', type: 'SMS', amount: 50, method: 'Mpesa', date: '2026-06-08T06:52:00' },
  { id: 'EXP-002', type: 'SYSTEM_PAYMENT', amount: 500, method: 'Paystack', date: '2026-06-04T20:00:00' },
  { id: 'EXP-003', type: 'SYSTEM_PAYMENT', amount: 500, method: 'Paystack', date: '2026-05-04T22:35:00' },
  { id: 'EXP-004', type: 'SYSTEM_PAYMENT', amount: 500, method: 'Paystack', date: '2026-04-04T11:22:00' },
  { id: 'EXP-005', type: 'SYSTEM_PAYMENT', amount: 500, method: 'Paystack', date: '2026-03-03T18:36:00' },
  { id: 'EXP-006', type: 'SYSTEM_PAYMENT', amount: 503, method: 'Paystack', date: '2026-02-03T13:40:00' },
  { id: 'EXP-007', type: 'SYSTEM_PAYMENT', amount: 500, method: 'Paystack', date: '2026-01-04T05:30:00' },
];

const blankExpense = { id: '', type: 'SYSTEM_PAYMENT', amount: 0, method: 'Paystack', date: '' };

function toDate(value) {
  const date = value ? new Date(value) : null;
  return date && !Number.isNaN(date.valueOf()) ? date : null;
}

function formatKES(value) {
  return `Ksh ${Number(value || 0).toLocaleString('en-KE', { minimumFractionDigits: 2 })}`;
}

function formatDate(value) {
  const date = toDate(value);
  if (!date) return '-';
  return `${String(date.getDate()).padStart(2, '0')}.${String(date.getMonth() + 1).padStart(2, '0')}.${date.getFullYear()} ${String(date.getHours()).padStart(2, '0')}:${String(date.getMinutes()).padStart(2, '0')}`;
}

function MetricCard({ title, value, helper }) {
  return (
    <div className="rounded-md bg-[#ffb783] p-5 shadow-[0_18px_30px_rgba(15,23,42,0.10)]">
      <p className="text-xs font-semibold text-black">{title}</p>
      <div className="mt-3 flex items-center gap-2">
        <p className="text-xl font-bold text-black">{formatKES(value)}</p>
        <Eye size={14} className="text-black" />
      </div>
      <p className="mt-2 text-xs text-black">{helper}</p>
    </div>
  );
}

export default function Expenses() {
  const [expenses, setExpenses] = useState(initialExpenses);
  const [draft, setDraft] = useState(blankExpense);
  const [editingId, setEditingId] = useState(null);
  const [modalOpen, setModalOpen] = useState(false);
  const [query, setQuery] = useState('');

  const filtered = useMemo(() => {
    const needle = query.toLowerCase();
    return expenses.filter((expense) => `${expense.type} ${expense.method} ${expense.amount}`.toLowerCase().includes(needle));
  }, [expenses, query]);

  const totals = useMemo(() => {
    const now = new Date();
    const weekStart = new Date(now);
    weekStart.setDate(now.getDate() - now.getDay());
    weekStart.setHours(0, 0, 0, 0);
    const monthStart = new Date(now.getFullYear(), now.getMonth(), 1);
    const yearStart = new Date(now.getFullYear(), 0, 1);
    const sumSince = (start) => expenses.reduce((sum, expense) => {
      const date = toDate(expense.date);
      return date && date >= start ? sum + Number(expense.amount || 0) : sum;
    }, 0);
    return {
      yearly: sumSince(yearStart),
      monthly: sumSince(monthStart),
      weekly: sumSince(weekStart),
    };
  }, [expenses]);

  const openCreate = () => {
    setDraft({ ...blankExpense, date: new Date().toISOString().slice(0, 16) });
    setEditingId(null);
    setModalOpen(true);
  };

  const openEdit = (expense) => {
    setDraft({ ...expense, date: toDate(expense.date)?.toISOString().slice(0, 16) || '' });
    setEditingId(expense.id);
    setModalOpen(true);
  };

  const save = (event) => {
    event.preventDefault();
    const payload = { ...draft, id: draft.id || `EXP-${Date.now().toString().slice(-4)}`, amount: Number(draft.amount || 0) };
    setExpenses((current) => (editingId ? current.map((item) => (item.id === editingId ? payload : item)) : [payload, ...current]));
    setModalOpen(false);
    setEditingId(null);
    setDraft(blankExpense);
    toast.success('Expense saved');
  };

  return (
    <div className="space-y-7">
      <div className="flex items-center justify-between gap-3">
        <h1 className="text-xl font-semibold text-black">Expenses</h1>
        <button type="button" className="inline-flex h-9 items-center gap-2 rounded-md bg-[#ff9347] px-4 text-xs font-semibold text-black shadow-md hover:bg-[#ff842f]" onClick={openCreate}>
          <Plus size={14} />
          Create Expense
        </button>
      </div>

      <section className="grid gap-6 md:grid-cols-3">
        <MetricCard title="Yearly Expenses" value={totals.yearly} helper="Total expenses this year" />
        <MetricCard title="Monthly Expenses" value={totals.monthly} helper="Total expenses this month" />
        <MetricCard title="Weekly Expenses" value={totals.weekly} helper="Total expenses this week" />
      </section>

      <section className="overflow-hidden rounded-lg border border-slate-200 bg-white">
        <div className="flex justify-end border-b border-slate-200 p-3">
          <label className="relative block w-full max-w-xs">
            <Search size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
            <input className="h-9 w-full rounded-md border border-slate-200 pl-9 pr-3 text-xs outline-none focus:border-[#fa8200] focus:ring-2 focus:ring-orange-100" placeholder="Search" value={query} onChange={(event) => setQuery(event.target.value)} />
          </label>
        </div>
        <div className="overflow-x-auto">
          <table className="min-w-[820px] w-full">
            <thead className="bg-slate-50 text-left text-xs font-semibold text-black">
              <tr>
                <th className="w-12 px-5 py-4"><input type="checkbox" className="h-4 w-4 rounded border-slate-300" /></th>
                {['Date', 'Type', 'Amount', 'Method'].map((heading) => (
                  <th key={heading} className="px-5 py-4">
                    <span className="inline-flex items-center gap-1">{heading}<ChevronDown size={15} className="text-slate-400" /></span>
                  </th>
                ))}
                <th className="px-5 py-4" />
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-200 text-xs text-black">
              {filtered.length === 0 ? (
                <tr><td className="px-5 py-10 text-center text-slate-500" colSpan="6">No expenses found.</td></tr>
              ) : filtered.map((expense) => (
                <tr key={expense.id}>
                  <td className="px-5 py-4"><input type="checkbox" className="h-4 w-4 rounded border-slate-300" /></td>
                  <td className="px-5 py-4">{formatDate(expense.date)}</td>
                  <td className="px-5 py-4">{expense.type}</td>
                  <td className="px-5 py-4">{formatKES(expense.amount)}</td>
                  <td className="px-5 py-4"><span className="rounded-md border border-orange-200 bg-orange-50 px-2 py-1 text-[10px] text-[#c95f00]">{expense.method}</span></td>
                  <td className="px-5 py-4 text-right">
                    <button type="button" className="inline-flex items-center gap-1 text-xs font-semibold text-[#c95f00]" onClick={() => openEdit(expense)}>
                      <Pencil size={14} className="text-slate-400" />
                      Edit
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      {modalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/50 p-4">
          <form className="w-full max-w-md rounded-lg bg-white p-5 shadow-xl" onSubmit={save}>
            <h2 className="text-base font-semibold text-black">{editingId ? 'Edit Expense' : 'Create Expense'}</h2>
            <div className="mt-4 grid gap-3">
              <label className="text-xs font-semibold text-slate-600">Date<input className="form-input" type="datetime-local" value={draft.date} onChange={(event) => setDraft((current) => ({ ...current, date: event.target.value }))} required /></label>
              <label className="text-xs font-semibold text-slate-600">Type<input className="form-input" value={draft.type} onChange={(event) => setDraft((current) => ({ ...current, type: event.target.value }))} required /></label>
              <label className="text-xs font-semibold text-slate-600">Amount<input className="form-input" type="number" value={draft.amount} onChange={(event) => setDraft((current) => ({ ...current, amount: event.target.value }))} required /></label>
              <label className="text-xs font-semibold text-slate-600">Method<select className="form-input" value={draft.method} onChange={(event) => setDraft((current) => ({ ...current, method: event.target.value }))}><option>Paystack</option><option>Mpesa</option><option>Cash</option><option>Bank</option></select></label>
            </div>
            <div className="mt-5 flex justify-end gap-2">
              <button type="button" className="btn-secondary" onClick={() => setModalOpen(false)}>Cancel</button>
              <button type="submit" className="inline-flex h-8 items-center rounded-md bg-[#ff9347] px-4 text-xs font-semibold text-black">Save</button>
            </div>
          </form>
        </div>
      )}
    </div>
  );
}
