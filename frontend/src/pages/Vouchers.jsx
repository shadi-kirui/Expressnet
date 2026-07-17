import { Copy, Pencil, Plus, Search, Trash2, WalletCards } from 'lucide-react';
import { useMemo, useState } from 'react';
import toast from 'react-hot-toast';
import StatusBadge from '../components/StatusBadge';

const initialVouchers = [
  { id: 'BATCH-062', packageName: '1 Hour Hotspot', quantity: 100, used: 63, prefix: 'EXP1H', price: 20, status: 'active' },
  { id: 'BATCH-061', packageName: 'Daily Hotspot', quantity: 80, used: 27, prefix: 'EXPDAY', price: 80, status: 'active' },
  { id: 'BATCH-060', packageName: 'Weekend Pass', quantity: 50, used: 50, prefix: 'EXPWKD', price: 150, status: 'sold_out' },
];

const blankVoucher = { id: '', packageName: '', quantity: 10, used: 0, prefix: '', price: 0, status: 'active' };

export default function Vouchers() {
  const [vouchers, setVouchers] = useState(initialVouchers);
  const [draft, setDraft] = useState(blankVoucher);
  const [editingId, setEditingId] = useState(null);
  const [query, setQuery] = useState('');

  const filtered = useMemo(() => vouchers.filter((item) => `${item.id} ${item.packageName} ${item.prefix}`.toLowerCase().includes(query.toLowerCase())), [query, vouchers]);

  const save = (event) => {
    event.preventDefault();
    const id = draft.id || `BATCH-${Math.floor(Math.random() * 900 + 100)}`;
    const payload = { ...draft, id, quantity: Number(draft.quantity || 0), used: Number(draft.used || 0), price: Number(draft.price || 0) };
    setVouchers((current) => (editingId ? current.map((item) => (item.id === editingId ? payload : item)) : [payload, ...current]));
    setDraft(blankVoucher);
    setEditingId(null);
    toast.success('Voucher batch saved');
  };

  const edit = (voucher) => {
    setDraft(voucher);
    setEditingId(voucher.id);
  };

  const remove = (voucher) => {
    setVouchers((current) => current.filter((item) => item.id !== voucher.id));
    toast.success('Voucher batch deleted');
  };

  return (
    <div className="grid gap-4 xl:grid-cols-[0.8fr_1.2fr]">
      <form className="surface-card p-4" onSubmit={save}>
        <div className="flex items-center gap-2 border-b border-slate-200 pb-3">
          <WalletCards size={18} className="text-app-navy" />
          <div>
            <h1 className="page-title">Vouchers</h1>
            <p className="page-subtitle">Generate and edit prepaid Hotspot voucher batches.</p>
          </div>
        </div>
        <div className="mt-4 grid gap-3">
          <input className="form-input" placeholder="Batch ID" value={draft.id} onChange={(event) => setDraft((v) => ({ ...v, id: event.target.value }))} />
          <input className="form-input" placeholder="Package name" value={draft.packageName} onChange={(event) => setDraft((v) => ({ ...v, packageName: event.target.value }))} />
          <div className="grid gap-3 sm:grid-cols-3">
            <input className="form-input" type="number" placeholder="Quantity" value={draft.quantity} onChange={(event) => setDraft((v) => ({ ...v, quantity: event.target.value }))} />
            <input className="form-input" type="number" placeholder="Price" value={draft.price} onChange={(event) => setDraft((v) => ({ ...v, price: event.target.value }))} />
            <input className="form-input" placeholder="Prefix" value={draft.prefix} onChange={(event) => setDraft((v) => ({ ...v, prefix: event.target.value }))} />
          </div>
          <select className="form-input" value={draft.status} onChange={(event) => setDraft((v) => ({ ...v, status: event.target.value }))}>
            <option value="active">Active</option>
            <option value="sold_out">Sold out</option>
            <option value="expired">Expired</option>
          </select>
        </div>
        <button type="submit" className="btn-primary mt-4 w-full">
          <Plus size={15} />
          {editingId ? 'Update batch' : 'Generate batch'}
        </button>
      </form>

      <section className="surface-card">
        <div className="flex items-center justify-between gap-3 border-b border-slate-200 p-4">
          <label className="relative block w-full max-w-sm">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" size={16} />
            <input className="form-input mt-0 pl-9" placeholder="Search voucher batches" value={query} onChange={(event) => setQuery(event.target.value)} />
          </label>
          <span className="text-xs text-slate-500">{filtered.length} batches</span>
        </div>
        <div className="overflow-x-auto">
          <table className="min-w-[760px] divide-y divide-slate-200">
            <thead className="table-head"><tr><th className="px-4 py-3">Batch</th><th className="px-4 py-3">Package</th><th className="px-4 py-3">Usage</th><th className="px-4 py-3">Price</th><th className="px-4 py-3">Status</th><th className="px-4 py-3 text-right">Actions</th></tr></thead>
            <tbody className="divide-y divide-slate-100">
              {filtered.map((voucher) => (
                <tr key={voucher.id}>
                  <td className="table-cell font-medium text-slate-950">{voucher.id}<span className="ml-2 text-slate-400">{voucher.prefix}</span></td>
                  <td className="table-cell">{voucher.packageName}</td>
                  <td className="table-cell">{voucher.used}/{voucher.quantity}</td>
                  <td className="table-cell">Ksh {voucher.price}</td>
                  <td className="table-cell"><StatusBadge status={voucher.status} /></td>
                  <td className="table-cell"><div className="flex justify-end gap-2"><button className="btn-secondary" type="button" onClick={() => toast('Codes copied')}><Copy size={14} />Copy</button><button className="btn-secondary" type="button" onClick={() => edit(voucher)}><Pencil size={14} />Edit</button><button className="btn-danger" type="button" onClick={() => remove(voucher)}><Trash2 size={14} />Delete</button></div></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
}
